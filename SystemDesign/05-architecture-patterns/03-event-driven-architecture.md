# Event-Driven Architecture

> **TL;DR:** Services communicate via asynchronous events instead of direct calls, decoupling producers from consumers in time, space, and flow-control — at the cost of implicit, hard-to-trace control flow that requires distributed tracing and correlation IDs to debug.

## Quick Reference

| Concept | Choice | Coupling | Traceability |
|---|---|---|---|
| Coordination style | **Choreography** | Low (services react independently) | Hard — no central log of "the process" |
| Coordination style | **Orchestration** | Higher (central coordinator knows the flow) | Easier — orchestrator = single source of truth |
| Event flavor | **Event Notification** | Lowest (thin event, "something happened") | Consumer must call back for details |
| Event flavor | **Event-Carried State Transfer (ECST)** | Medium (event carries full payload) | Self-contained but payload duplication/staleness |
| Event flavor | **Event Sourcing** | Tight to event schema, loose to services | Full audit log; replay = rebuild state |
| Broker examples | Kafka, RabbitMQ, AWS SNS/SQS, EventBridge, NATS | — | Kafka retains history; SQS deletes on ack |
| Debugging aid | OpenTelemetry, Jaeger, Zipkin + correlation/trace IDs propagated in event headers | — | — |

## What It Is

- Architecture style where state changes are published as **events** (immutable facts: `OrderPlaced`, `PaymentFailed`) and interested parties subscribe, instead of caller invoking callee synchronously.
- Producers don't know who consumes their events, or how many consumers exist — inversion of control vs request/response.
- Requires a broker/log (Kafka topic, RabbitMQ exchange, SNS topic) as the durable intermediary; the broker owns delivery guarantees, not the producer.

## Responsibilities

- **Producer**: emit events on state change, own schema/versioning, no knowledge of downstream consumers.
- **Broker**: durable storage/buffering, delivery (at-least-once typically), ordering guarantees (per-partition in Kafka), retention.
- **Consumer**: idempotent processing (duplicates *will* happen), own offset/ack management, dead-letter handling for poison messages.
- **Schema registry** (Confluent Schema Registry, AWS Glue): contract enforcement so producers/consumers evolve independently without breaking each other.

## How It Works

1. Domain event occurs → producer publishes to topic/queue (fire-and-forget or with ack from broker only, not consumer).
2. Broker persists and fans out to N subscribers per topic (pub/sub) or load-balances across a consumer group (queue semantics).
3. Each consumer processes independently, at its own pace — producer's call stack has already returned.
4. Consumer may itself publish new events → cascading reactions ("event chains") without any single service knowing the full chain.

```
Producer --event--> [ Broker/Log ] --fanout--> Consumer A (reacts, may emit new event)
                                    --fanout--> Consumer B
                                    --fanout--> Consumer C
```

- This breaks the synchronous call chain: instead of `A→B→C→D` blocking calls (latency sums, one failure cascades), each hop is async and independently retryable.

## Types / Classifications

### Choreography vs Orchestration (the core fork)
- **Choreography**: each service listens for events and decides its own next action; no central brain. E.g., `OrderPlaced` → Inventory reserves stock → emits `StockReserved` → Payment charges → emits `PaymentCaptured` → Shipping ships.
  - Pro: max decoupling, services deployed/scaled independently, no SPOF coordinator.
  - Con: business process is nowhere written down in code — it emerges from N services' listener configs; hard to answer "what happens when an order is placed?" without reading every service.
- **Orchestration**: a central orchestrator (Camunda, Temporal, AWS Step Functions, or a "saga orchestrator" service) explicitly calls each step and tracks state.
  - Pro: process visible in one place, easier compensation/rollback logic (sagas), easier to add timeouts/retries centrally.
  - Con: orchestrator becomes a coupling point and potential bottleneck/SPOF; services expose orchestrator-callable APIs, reintroducing some sync coupling.
- Real systems mix both: choreography for loosely related side effects (analytics, notifications), orchestration for the money-path (checkout, payment saga).

### Three Event Flavors (Martin Fowler's taxonomy)
- **Event Notification**: skinny event, just an ID + type (`{orderId: 123, type: "OrderPlaced"}`). Consumer must call back to producer's API for details → **reintroduces temporal coupling** (producer must be up when consumer looks up details).
- **Event-Carried State Transfer (ECST)**: event carries the full relevant state (`{orderId, items, total, customerId, address}`). Consumer caches/stores it locally, never calls back → true temporal decoupling, but data duplication and eventual staleness across services.
- **Event Sourcing**: the event log *is* the system of record; current state = fold/replay of all events for an entity. No separate "state" table — state is derived. Enables audit trail, temporal queries, replay-to-rebuild. Heaviest to adopt (event schema versioning is forever, snapshots needed for perf).

## Where It Fits

- Cross-service integration in microservices where sync REST/gRPC chains create latency stacking and cascading failures.
- Domain event propagation (order → inventory → shipping → billing) where steps don't need an immediate response.
- CQRS read-model updates: write side emits events, read side (materialized views in Elasticsearch/Redis) updates asynchronously.
- Stream processing pipelines (clickstream, IoT telemetry, fraud detection) via Kafka Streams, Flink, Kinesis Analytics.
- NOT a good fit for synchronous request/response needs (user waiting on screen for immediate answer) — use sync call or async-with-polling/websocket instead.

## Common Patterns & Real-World Tools

| Pattern | Tool examples | Notes |
|---|---|---|
| Log-based pub/sub | Kafka, Redpanda, Pulsar | Retains history, replay, consumer groups, high throughput |
| Message queue | RabbitMQ, ActiveMQ, SQS | Point-to-point, deleted after ack, simpler ops |
| Managed event bus | AWS EventBridge, Azure Event Grid | Schema registry + routing rules built in |
| Saga pattern | Temporal, Camunda, custom orchestrator | Compensating transactions for distributed rollback |
| CDC (Change Data Capture) | Debezium + Kafka Connect | Turns DB row changes into events without app code changes |
| Outbox pattern | Transactional outbox table + CDC | Solves dual-write problem (DB write + event publish atomicity) |

## Pros & Cons / Trade-offs

**Pros**
- Temporal decoupling: producer and consumer don't need to be up simultaneously (broker buffers).
- Reduced blocking call chains → lower tail latency for the producer, independent scaling of consumers.
- New consumers can be added without touching the producer (open for extension).
- Natural fit for audit/replay (event sourcing) and multi-consumer fan-out (analytics + billing + notifications from one event).

**Cons**
- Implicit control flow — no stack trace spans the whole business process; requires reading broker configs/topic subscriptions to reconstruct "what calls what."
- Eventual consistency everywhere — no immediate read-your-write guarantee across services.
- Debugging/testing harder: reproducing a bug means replaying an event sequence, not a single HTTP call.
- Operational overhead: broker cluster to run, monitor, capacity-plan (Kafka partition rebalancing, consumer lag).
- Duplicate delivery is normal (at-least-once) → every consumer must be idempotent or use dedup keys.

## Real-World Scenarios

- **E-commerce checkout saga**: `OrderPlaced` → Inventory (choreographed reservation) → Payment → on failure, compensating `OrderCancelled` event triggers inventory release. Orchestrated version: Temporal workflow explicitly sequences these with built-in retry/compensation.
- **Uber/Lyft trip lifecycle**: dozens of services (pricing, matching, ETA, payments) react to `TripRequested`, `DriverAssigned`, `TripCompleted` via Kafka — choreography, because no single service should own "the whole trip."
- **Netflix**: uses Kafka extensively for choreographed event pipelines (viewing activity → recommendations, billing, A/B test tracking) — each team owns its own consumer, decoupled from producer team's release cycle.
- **Banking ledger**: event sourcing for account transactions — balance is derived by replaying `Deposited`/`Withdrawn` events; enables point-in-time audit for regulators.

## Nuances & Gotchas

- **The "distributed monolith via events" trap**: choreography with dozens of implicit event chains can be *worse* than a monolith — you've traded readable code for an untraceable web of topic subscriptions. If nobody can draw the flow diagram from memory, it's already too coupled.
- **Ordering is not free**: Kafka guarantees order only within a partition; cross-entity or cross-topic ordering requires careful partition-key design (e.g., partition by `orderId`) or you'll process `PaymentCaptured` before `OrderPlaced`.
- **Dual-write problem**: writing to your DB and publishing an event are two separate operations — a crash between them loses the event or leaves inconsistent state. Fix with the **transactional outbox pattern** (write event to an outbox table in the same DB transaction, CDC/Debezium tails it into Kafka).
- **Schema evolution breaks consumers silently**: adding a required field or renaming one can break consumers deployed weeks ago with no compile-time signal — enforce backward-compatible schemas via a registry (Avro/Protobuf + Confluent Schema Registry) with compatibility checks in CI.
- **Poison messages and DLQs**: a malformed event can block a partition/queue forever if not routed to a dead-letter queue; always configure max-retry + DLQ, and alert on DLQ depth.
- **Consumer lag as the real health metric**: a "healthy" broker with growing consumer lag means downstream is silently falling behind — monitor lag (Kafka `kafka-consumer-groups.sh` or Burrow), not just broker uptime.
- **Tracing mitigation is mandatory, not optional**: propagate a `trace_id`/`correlation_id` in every event's headers (W3C Trace Context), instrument producers/consumers with OpenTelemetry, and ship spans to Jaeger/Zipkin/Honeycomb — without this, incident response degenerates into grepping logs across 20 services by timestamp.
- **Replay danger in event sourcing**: replaying events against external side-effecting consumers (e.g., "send email on `OrderPlaced`") will re-trigger those side effects unless replay is routed through a separate, non-side-effecting path or idempotency keys dedupe at the effect boundary.
- **Testing gets harder, not easier**: contract tests (Pact) between producer/consumer schemas, plus consumer-driven contract testing, become necessary since there's no compiler to catch a broken integration.
