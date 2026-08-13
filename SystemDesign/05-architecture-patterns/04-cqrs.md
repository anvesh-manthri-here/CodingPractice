# CQRS (Command Query Responsibility Segregation)

> **TL;DR:** Split the write path (commands, normalized, invariant-enforcing) from the read path (queries, denormalized, view-optimized) into separate models — sometimes separate stores entirely — trading consistency and complexity for read scalability and domain clarity.

## Quick Reference

| Aspect | Write Model | Read Model |
|---|---|---|
| Purpose | Enforce invariants, validate | Serve fast, shaped queries |
| Shape | Normalized (3NF), domain-driven | Denormalized, per-view tables |
| Store | Postgres/MySQL (transactional) | Elasticsearch, Redis, Mongo, materialized views |
| Consistency | Strong (ACID within aggregate) | Eventual (lag: ms–seconds typically) |
| Update trigger | Command handler | Event/CDC feed from write side |
| Scaling axis | Write throughput, correctness | Read throughput, latency |
| Typical sync mechanism | Domain events, outbox, CDC (Debezium) | Projector/subscriber rebuilds view |

## What It Is

- Architectural pattern: commands (mutate state) and queries (read state) use **different models**, not just different methods on one class (that's the CQS principle at code level; CQRS is CQS applied at the architecture/data level).
- Write model = source of truth, optimized for correctness and business rule enforcement per aggregate (DDD term).
- Read model = one or more projections optimized per UI/query need — can have N read models for one write model (e.g., search index, dashboard cache, recommendation table).
- Not a single pattern instance — spectrum from "separate methods, same DB" to "separate services, separate databases, separate teams."

## Responsibilities

- **Command side**: validate input, enforce invariants (e.g., "inventory can't go negative"), execute business logic, persist state change, emit event describing what happened.
- **Read side**: subscribe to change events, transform/denormalize, update query-optimized store, serve reads with zero business logic (just projections).
- **Sync mechanism** (not part of CQRS itself but required): outbox pattern, CDC (Debezium/Kafka Connect), domain event bus, or direct dual-write (risky, avoid).

## How It Works

```
Client --Command--> Command Handler --> Aggregate --> Write DB
                                            |
                                      Domain Event
                                            |
                                    Event Bus / CDC
                                            |
                                      Projector(s)
                                            |
                                       Read DB(s) <-- Query <-- Client
```

- Command handler loads aggregate, applies business logic, persists, publishes event — typically within one transaction (write DB + outbox row) to avoid dual-write inconsistency.
- Projector consumes events asynchronously, updates one or more read stores; can rebuild a read model from scratch by replaying events (if event-sourced) or by re-querying write DB (if not).
- Query side never touches command side's schema or logic — a query is just "SELECT from projection table," no joins across 10 normalized tables.

## Types / Classifications

| Variant | Write DB | Read DB | Consistency | Complexity |
|---|---|---|---|---|
| Logical CQRS | Same DB | Same DB, different views/queries | Strong | Low — just separate DTOs/query objects |
| Physical CQRS, single DB | Same DB | Same DB, materialized views | Strong (sync) or near-strong | Medium |
| Physical CQRS, separate DBs | Postgres | Elasticsearch/Redis/Mongo | Eventual | High |
| CQRS + Event Sourcing | Event store (append-only) | Multiple projections | Eventual | Highest |

- **CQRS ≠ Event Sourcing.** CQRS just needs *some* signal to update read models — can be DB triggers, CDC on row changes, or a simple "publish event after commit" without ever storing the event log as source of truth.
- Event Sourcing is a natural pairing because events are already the artifact needed to build projections, and projections can be rebuilt/replayed at will — but plenty of CQRS systems just do write-then-async-refresh of a materialized view with no event store.

## Where It Fits

- Sits at the application/persistence layer, orthogonal to microservices vs monolith — a single bounded context can be CQRS internally.
- Common with **DDD aggregates**: aggregate boundary = transactional consistency boundary for writes; read model spans/denormalizes across aggregates freely.
- Pairs with **event-driven architecture**: Kafka/RabbitMQ/EventBridge as the event bus between command and read sides.
- Read replicas (Postgres streaming replication) are a *poor man's* CQRS — same schema, just offloading read traffic; true CQRS reshapes the schema too.

## Common Patterns & Real-World Tools

- **Outbox pattern**: write aggregate state + event to same DB transaction, separate relay (Debezium) publishes to Kafka — avoids dual-write problem.
- **Materialized views**: Postgres `MATERIALIZED VIEW` with `REFRESH CONCURRENLY`, or DB triggers — cheap logical CQRS without new infra.
- **Search projections**: MySQL/Postgres as write store, Elasticsearch/OpenSearch as read store for full-text/faceted queries (classic e-commerce pattern).
- **Cache-as-read-model**: Redis populated by write-side events, serving hot-path reads (product pages, leaderboards).
- **Axon Framework, EventStoreDB, Marten**: frameworks that bundle CQRS + event sourcing for JVM/.NET/Postgres stacks.
- **AWS pattern**: DynamoDB (write) + DynamoDB Streams + Lambda projector + OpenSearch (read) is a common managed-services CQRS stack.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Independent scaling of reads vs writes | Two (or more) models to build, test, deploy, version |
| Read models tailored per UI — no runtime joins/aggregation | Eventual consistency confuses users/devs if not designed for |
| Write model stays clean, focused on invariants | Operational overhead: event bus, projectors, monitoring lag |
| Enables polyglot persistence (best store per access pattern) | Debugging spans multiple stores/async pipelines |
| Natural fit for CQRS+ES audit/replay needs | Overkill for CRUD — most apps don't need this |

## Real-World Scenarios

- **E-commerce order system**: writes go to normalized `orders`/`order_items` in Postgres with strict inventory checks; reads for "order history" page come from a denormalized Mongo/Elasticsearch document per order, updated via CDC — search and filter without joins.
- **Financial ledger**: command side is event-sourced (every transaction immutable), read side maintains multiple projections — account balance (fast lookup), monthly statement (aggregated), fraud-detection feed (streaming) — each rebuildable independently.
- **Social feed**: write = "user posted" command touches one row; read = fan-out to follower timelines (Redis lists) — massive read/write asymmetry (1 write, 10K reads) is the textbook justification.
- **SaaS admin dashboard**: complex reporting queries (joins across 15 tables) killing OLTP performance — split into write-optimized OLTP + read-optimized reporting DB refreshed nightly or via CDC, without going full event sourcing.

## Nuances & Gotchas

- **Eventual consistency UX trap**: user submits a command, immediately queries the read model, sees stale data ("where's my order?"). Mitigate with read-your-writes tricks: return command result directly to client, optimistic UI updates, or route the immediate post-write read to the write DB.
- **Dual-write bug**: writing to write-DB and publishing event as two separate operations risks losing the event on crash — always use outbox/CDC, never a naive "commit then publish."
- **Projector lag under load**: event bus backpressure or slow projector can push read-model staleness from ms to minutes — must monitor consumer lag (Kafka consumer group lag) as a first-class SLO, not an afterthought.
- **Schema drift**: read projections silently diverge from write model's true state after bugs/replays — need reconciliation jobs or checksums, not just "trust the pipeline."
- **Overuse is the #1 real-world failure**: teams adopt CQRS for a simple CRUD admin panel, inherit eventual consistency and async debugging pain for zero read/write asymmetry benefit — only justified when read/write patterns, scale, or domain complexity genuinely diverge.
- **Rebuild storms**: replaying full event history to rebuild a read model after a bug fix can take hours on large streams — need snapshotting or partitioned replay strategies.
- **Testing complexity**: integration tests must account for async propagation delay (poll/wait for read model to catch up) instead of synchronous assert-after-write, slowing CI or causing flaky tests if timeouts are too tight.
- **Team boundary cost**: separate read/write models often mean separate deploy cycles and ownership — coordination overhead can exceed the technical benefit for small teams (<10 engineers).
- **Not free consistency once you add multiple read models**: each projection can lag independently, so two read models (e.g., search index and cache) can show *different* stale states simultaneously — decide per-feature which staleness is tolerable.
