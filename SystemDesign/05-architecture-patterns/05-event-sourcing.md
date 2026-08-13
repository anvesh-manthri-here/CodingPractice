# Event Sourcing

> **TL;DR:** Store every state-changing event as an immutable append-only log (the source of truth); derive current state by replaying events, and use snapshots to bound replay cost. Pair with CQRS for querying, because the event log itself is a terrible read model.

## Quick Reference

| Concept | Summary |
|---|---|
| Source of truth | Append-only event log, not a mutable row |
| Current state | `state = fold(replay(events))`, derived, not stored (or cached as a snapshot) |
| Snapshotting | Periodic materialized state + event offset, to avoid replaying millions of events |
| Read side | CQRS projections / read models (SQL tables, Elasticsearch, Redis) built from events |
| Consistency model | Eventually consistent between write (event store) and read (projections) |
| Common stores | EventStoreDB, Kafka (with compaction), Axon Server, Postgres append-only table |
| Schema evolution | Upcasting/versioned event handlers, never mutate old events |
| Best fit | Financial ledgers, audit/compliance domains, banking, order/booking workflows |
| Bad fit | CRUD apps, simple lookup services, teams without CQRS discipline |

## What It Is

- Instead of persisting "current balance = $500", persist `AccountOpened`, `Deposited($300)`, `Deposited($200)`.
- Current state is a **projection**: fold/reduce over the ordered event stream for an aggregate ID.
- The event log is immutable and append-only — you never `UPDATE` or `DELETE`, only append compensating events (e.g., `Deposited` reversed by `WithdrawalCorrected`).
- Contrast with typical CRUD: state-oriented persistence overwrites the "why", event sourcing preserves it forever.

## Responsibilities

- **Capture intent**, not just state diff: `OrderCancelled` carries more meaning than `status = 'cancelled'`.
- **Guarantee full history**: every state transition is reconstructable, auditable, replayable.
- **Enable temporal queries**: "what was the account balance on March 3rd" = replay events up to that timestamp.
- **Decouple write model from read model**: writes append events; reads are served from purpose-built projections (CQRS).
- **Support event-driven integration**: other services subscribe to the same event stream (outbox-free integration).

## How It Works

```
Command -> Aggregate (business logic) -> Event(s) appended to log
                                              |
                                              v
                                    Event Store (append-only)
                                              |
                     +------------------------+------------------------+
                     v                                                 v
             Snapshot (periodic)                         Projector -> Read Model(s)
             (state @ event #N)                           (SQL / ES / cache)
```

1. Command arrives (`WithdrawMoney`).
2. Aggregate loads its history: latest snapshot + events since snapshot, replays to rebuild in-memory state.
3. Aggregate validates command against current state (e.g., sufficient balance), emits new event(s) on success.
4. Event appended atomically to the store, keyed by `(aggregateId, version)` — optimistic concurrency check on version prevents lost updates.
5. Event published (via store subscription / outbox) to projectors that update read models asynchronously.
6. Snapshot taken every N events (e.g., every 100) to cap replay time; old events beyond retention can be archived, not deleted (audit requirement).

**Optimistic concurrency**: writer includes expected version; store rejects append if version has moved (another writer beat you) — same pattern as CAS.

## Types / Classifications

| Style | Description | Example |
|---|---|---|
| Aggregate-per-stream | One event stream per entity (e.g., `account-123`) | EventStoreDB streams |
| Log-based (Kafka-style) | Single/partitioned topic, compaction keeps latest per key | Kafka + ksqlDB |
| State + event hybrid | Store current state table AND event log (denormalized for fast reads) | Outbox pattern hybrids |
| Full ES + CQRS | Strict separation: write model = events only, read model = projections | Axon Framework, banking cores |
| Event-carried state transfer | Events carry full state snapshot, not just delta, for downstream consumers | Debezium CDC events |

## Where It Fits

- **Write path**: command handlers / aggregates own business rules, append events transactionally to the event store.
- **Read path**: one or more projectors consume the event stream, build denormalized views tuned per query (this *is* CQRS).
- **Integration**: event stream doubles as the integration bus — downstream services subscribe instead of polling APIs.
- **Audit/compliance layer**: regulators or internal audit query the raw event log directly, bypassing projections entirely.
- Typically sits behind a microservice boundary; each service owns its own event store (no shared ES across bounded contexts).

## Common Patterns & Real-World Tools

- **EventStoreDB**: purpose-built event store, native stream subscriptions, projections engine.
- **Kafka + compacted topics**: event log with retention/compaction; pair with ksqlDB or Kafka Streams for projections.
- **Axon Framework (Java)**: aggregates, event sourcing, CQRS, sagas out of the box.
- **Postgres append-only table**: `events(aggregate_id, version, type, payload jsonb, ts)`, unique constraint on `(aggregate_id, version)` for concurrency control — the "poor man's" event store, common in practice.
- **Snapshotting**: store `snapshots(aggregate_id, version, state jsonb)`; load latest snapshot + replay events after it.
- **Saga / Process Manager**: coordinates multi-aggregate workflows by reacting to events and issuing new commands (e.g., order → payment → shipping).
- **Outbox pattern**: often combined so events reliably escape the write DB transaction into Kafka without dual-write issues.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Full audit trail / compliance by construction | Query complexity — must build CQRS read models for anything beyond "get by ID" |
| Time-travel debugging: replay to any point in history | Eventual consistency between write and read sides confuses UX ("why isn't my update showing?") |
| Natural fit for event-driven architectures | Schema evolution of old events is hard — must support old formats forever |
| Rebuild bugs: fix projector logic, replay, done — no data migration | Replay cost grows unbounded without disciplined snapshotting |
| Decouples write model from read model scaling | Steep learning curve; debugging requires understanding folds over history, not just row state |
| No lost history — undo/redo, what-if analysis becomes trivial | Storage grows forever (mitigated by snapshots, not by deleting events) |

## Real-World Scenarios

- **Banking ledger**: every `Debit`/`Credit` retained forever; balance is a projection; regulators can replay full transaction history for any account — this is essentially double-entry bookkeeping, event sourcing's spiritual ancestor.
- **E-commerce order lifecycle**: `OrderPlaced`, `PaymentAuthorized`, `ItemShipped`, `OrderCancelled` — support/ops can see the exact sequence of what happened, not just "status: cancelled".
- **Insurance claims processing**: audit requires proving exactly what data was known at each decision point in time — event sourcing gives this for free via replay-to-timestamp.
- **Git itself**: commits are events, working tree is the projection — a familiar mental model for engineers.
- **Anti-pattern example**: a simple user-profile CRUD service (name, email, avatar) adopting event sourcing "for future-proofing" — adds CQRS/projection/replay complexity for a domain with no audit or temporal requirement; team velocity drops for no business payoff.

## Nuances & Gotchas

- **Schema evolution is the #1 production pain**: an old `OrderPlaced` event from 2019 lacks a field added in 2024. Solutions: **upcasting** (transform old event JSON to new shape on read), versioned event types (`OrderPlacedV2`), or tolerant readers with defaults — never mutate stored events in place.
- **Never delete events**, even for GDPR "right to be forgotten" — common workaround is **crypto-shredding**: encrypt PII per-user, delete the key to make old events unreadable without touching the log.
- **Snapshot staleness bugs**: if snapshot logic has a bug, all rebuilt state is wrong until you fix the snapshotter and force a re-snapshot — test snapshot/replay equivalence explicitly.
- **Aggregate boundary sizing matters**: too coarse (e.g., whole "Order" as one stream forever) means huge replay cost and lock contention; too fine causes cross-aggregate consistency headaches — model around transactional consistency boundaries, not object hierarchies.
- **Eventual consistency surprises users**: client writes an event, immediately queries the read model, and gets stale data because the projector hasn't caught up — mitigate with "read your own writes" via version tokens returned from the write, checked against projection version.
- **Replay determinism is mandatory**: event handlers must be pure functions of (state, event) — no calling external APIs, no `Random()`, no `DateTime.Now()` inside the fold logic, or replays produce different results each time.
- **Concurrent writers on the same aggregate**: must use optimistic concurrency (expected version check) — without it, two commands both reading version 5 both succeed, silently losing one set of business logic effects.
- **Projection rebuild at scale is a real operational event**: rebuilding a read model from millions of events after a projector bug fix can take hours; plan for blue-green projector deployments, not in-place rebuilds.
- **Don't event-source everything**: reach for it only when you need audit trail, temporal queries, or complex domain workflows with sagas — for reference/lookup data (catalog, config), plain CRUD with an audit-log *column* is far cheaper than full ES + CQRS.
- **Testing gets easier, not harder, once mastered**: given(events) -> when(command) -> then(events) is a clean, deterministic unit-test pattern — but the team must actually adopt it, or tests devolve into replaying entire histories per test (slow).
