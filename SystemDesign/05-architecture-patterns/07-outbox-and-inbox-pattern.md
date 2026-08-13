# Outbox and Inbox Pattern

> **TL;DR:** Never do a DB write and a message-broker publish as two separate operations — one can fail while the other succeeds. Write the event to an "outbox" table in the same DB transaction as the business change, then relay it asynchronously; the "inbox" table does the mirror-image dedup on the consumer side.

## Quick Reference

| Concept | Outbox | Inbox |
|---|---|---|
| Side | Producer | Consumer |
| Solves | Dual-write (DB + broker not atomic) | Duplicate/out-of-order delivery |
| Storage | `outbox` table, same DB/txn as business write | `inbox` table (processed message IDs) keyed by DB/consumer |
| Relay mechanism | CDC (Debezium) or polling publisher | N/A — read on consume, not relayed |
| Guarantee | At-least-once delivery | Exactly-once **processing** (idempotent effect) |
| Cleanup | Delete/archive after publish ack | TTL or delete after processed + grace window |
| Real tools | Debezium, Kafka Connect, AWS DMS, custom poller | Postgres unique constraint, Redis SETNX, dedup table |

## What It Is

- **Dual-write problem**: a service updates its DB row AND publishes an event to Kafka/RabbitMQ in one logical operation, but DB commit and broker publish are two independent systems — no distributed transaction across them in practice (2PC/XA is slow, brittle, rarely supported by brokers).
- Failure modes without outbox: DB commits, publish fails (network blip) → downstream never learns of the change. Or publish succeeds, DB rolls back → downstream acts on an event that never really happened.
- **Outbox pattern**: instead of publishing directly, insert the event as a row into an `outbox` table in the *same local ACID transaction* as the business write. A separate relay process reads the outbox and publishes to the broker, retrying until success.
- **Inbox pattern**: consumer records the message ID (or dedup key) in an `inbox` table in the same transaction as applying the business effect. Before processing, check if the ID is already in the inbox — if so, skip (idempotent no-op).

## Responsibilities

- Outbox: guarantee the event is durably recorded iff the business transaction commits (atomicity), and guarantee it eventually reaches the broker (at-least-once).
- Relay/publisher: read outbox rows in order, publish, mark as sent (or delete), handle broker downtime with retry/backoff.
- Inbox: guarantee a consumer's side effect (charge a card, decrement inventory) happens exactly once even if the same message is redelivered.
- Both: keep the "did this happen" answer local to one DB, avoiding cross-system coordination.

## How It Works

```
Producer TX: BEGIN
  UPDATE orders SET status='PAID' WHERE id=1;
  INSERT INTO outbox(id, aggregate_id, type, payload, created_at)
    VALUES (uuid(), 1, 'OrderPaid', '{...}', now());
COMMIT
        |
        v  (async, separate process)
  CDC (Debezium reads WAL/binlog)  --or--  Polling publisher (SELECT ... WHERE sent=false)
        |
        v
   Kafka topic "order-events"
        |
        v
Consumer TX: BEGIN
  SELECT 1 FROM inbox WHERE msg_id = ?;      -- dedup check
  if exists: COMMIT (no-op)
  else:
    UPDATE inventory SET qty = qty - 1;
    INSERT INTO inbox(msg_id, processed_at) VALUES (?, now());
COMMIT
```

- Two relay strategies:
  - **CDC / log-tailing** (preferred): Debezium tails the DB's write-ahead log (Postgres logical replication, MySQL binlog) and streams outbox inserts to Kafka — no polling load on the DB, near-real-time, doesn't compete with app transactions.
  - **Polling publisher**: a cron/loop does `SELECT * FROM outbox WHERE sent=false ORDER BY created_at LIMIT 100`, publishes, then updates/deletes. Simpler, no extra infra, but adds DB load and polling latency (typically 100ms–5s intervals).
- Ordering: partition Kafka by `aggregate_id` so events for the same entity stay ordered; outbox table should have a monotonic sequence/timestamp for the poller to read in order.
- Cleanup: outbox rows deleted or archived after confirmed publish (or use a `sent` flag + periodic purge) to keep table small — unbounded growth kills polling performance and CDC replay time.

## Types / Classifications

- **Outbox delivery style**: transactional outbox (classic) vs. **transaction log tailing** (CDC-only, no explicit outbox table — read business table's log directly, e.g., Debezium + custom SMT, less common, more coupling to schema).
- **Inbox dedup key**: message ID (broker-assigned or producer-assigned UUID) vs. business idempotency key (e.g., `order_id + event_type`) — business key is more robust if producer can resend with a new message ID.
- **Relay topology**: single relay instance (simple, single point of lag) vs. sharded relay by aggregate/partition (scales throughput, needs leader election, e.g., via Kafka Connect tasks).

## Where It Fits

- Sits at the boundary between a service's local DB transaction and its messaging/event layer — the standard building block under:
  - **Sagas**: each saga step is a local transaction + outbox event that triggers the next step; inbox on each participant ensures compensating/forward actions aren't double-applied.
  - **CQRS read-model sync**: write-side commits + outbox event → projector consumes (with inbox dedup) → updates read model (Elasticsearch, materialized view) without 2PC between write DB and read store.
  - **Event-driven microservices** generally: any service that must reliably tell others "this happened" after committing.
- Not needed for pure request/response (REST call to another service) — that's a different reliability problem (retries, circuit breakers).

## Common Patterns & Real-World Tools

- **Debezium + Kafka Connect**: most common production setup — outbox table + Debezium's dedicated "outbox event router" SMT (single message transform) that unwraps the outbox envelope into a clean Kafka topic/key/payload.
- **AWS**: DynamoDB Streams as a de facto outbox (item written triggers stream record) + Lambda relay to SNS/SQS; or RDS + DMS (Database Migration Service) for CDC.
- **Polling libraries**: many frameworks bake this in — e.g., NServiceBus/MassTransit (.NET) outbox support, Spring's `ApplicationEventPublisher` + `@TransactionalEventListener(AFTER_COMMIT)` for simpler in-process cases.
- **Inbox dedup implementations**: Postgres `INSERT ... ON CONFLICT (msg_id) DO NOTHING`, Redis `SET key val NX EX ttl`, Kafka consumer offsets + separate idempotency table for exactly-once *effects* (offsets alone only give exactly-once *consumption tracking*, not idempotent side effects).

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| Outbox | Atomic with business write, no distributed TX, survives broker outages (events queue up in table) | Extra table + relay infra, added latency (CDC lag ~ms–s, polling lag = interval), schema coupling if using log tailing |
| Inbox | Makes redelivery safe, simple dedup logic | Extra write per message, unbounded table growth if not pruned, still needs idempotent *business logic* for effects with side channels (e.g., calling a 3rd-party API) |
| CDC relay | Low latency, no polling load | Extra infra (Debezium/Kafka Connect), DB must support logical replication/binlog access (may need permissions, WAL retention tuning) |
| Polling relay | Simple, no extra infra | DB load, coarser latency, needs careful locking (`SELECT ... FOR UPDATE SKIP LOCKED`) to avoid double-publish across multiple relay instances |

## Real-World Scenarios

- **E-commerce checkout**: `orders` table updated to PAID + `OrderPaid` outbox event in one txn → inventory service consumes via inbox-deduped handler to reserve stock, exactly once even if Kafka redelivers after a consumer crash mid-processing.
- **Saga for order fulfillment**: Order service commits + outbox event `OrderCreated` → Payment service (inbox dedup) charges card, commits + outbox event `PaymentCompleted` → Shipping service triggers. Each hop is local-transaction-safe; no 2PC across three DBs.
- **CQRS projection**: write-side Postgres commits order + outbox row → Debezium streams to Kafka → projector (inbox-deduped) upserts into Elasticsearch read model; replaying the same Kafka message after projector restart doesn't double-count aggregates.
- **Multi-tenant SaaS billing**: usage-event writes to `usage` table + outbox `UsageRecorded` → billing aggregator consumes with inbox to prevent double-billing on consumer retries/rebalances.

## Nuances & Gotchas

- **Outbox table growth is a silent DB killer**: forgetting to purge sent rows bloats the table, slows down polling queries and even unrelated queries via table bloat/vacuum pressure (Postgres) — always pair with a cleanup job or TTL partition.
- **Polling relay + multiple instances = double publish** unless you use `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres) or a distributed lock; naive polling from 2 replicas publishes every event twice.
- **CDC lag is not zero**: Debezium replays from WAL, so there's a window (typically sub-second, but can spike to minutes under replication lag or connector restart) where the event hasn't reached Kafka yet — don't assume synchronous-like delivery.
- **Inbox alone doesn't make non-idempotent side effects safe**: if the consumer's handler calls a third-party payment API, deduping the DB write doesn't stop a duplicate external call made *before* the crash that skipped the inbox insert — need idempotency keys on the external call too (e.g., Stripe idempotency-key header).
- **Ordering guarantees are easy to lose**: if the poller/CDC doesn't preserve outbox insertion order per aggregate (e.g., re-partitioning, multi-threaded publish), consumers can see `OrderShipped` before `OrderCreated` — always partition/key by aggregate ID.
- **Schema coupling with log-tailing CDC**: reading business tables directly (no outbox) means every column rename/migration breaks the CDC pipeline; the outbox table's stable envelope schema (id, type, payload, timestamp) decouples internal schema churn from the event contract.
- **Outbox event payload staleness**: if you capture the payload at write time but downstream needs the *latest* state (not point-in-time), a slow relay can deliver stale data — decide explicitly between "event carries full state" vs. "event is a notification, consumer re-fetches."
- **Forgetting the relay is a SPOF**: a single poller instance crashing halts all event delivery silently unless monitored (lag alerting on outbox row age, e.g., alert if oldest unsent row > 60s).
- **Debezium outbox router misconfiguration**: forgetting to set the correct `route.by.field` (aggregate type) sends all events to one Kafka topic, losing the ability to scale/consume per-aggregate-type independently.
