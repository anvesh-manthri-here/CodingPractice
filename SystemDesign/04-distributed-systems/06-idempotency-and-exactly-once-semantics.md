# Idempotency and Exactly-Once Semantics

> **TL;DR:** Exactly-once *delivery* over an unreliable network is provably impossible (Two Generals Problem); what's achievable is exactly-once *effect* — at-least-once delivery + idempotent processing = the observable outcome of exactly-once.

## Quick Reference

| Concept | Mechanism | Example Tool |
|---|---|---|
| Delivery guarantee (real) | at-least-once + dedup | Kafka consumer, SQS |
| Delivery guarantee (illusion) | idempotency key + dedup table | Stripe API, payment gateways |
| Naturally idempotent op | PUT, DELETE, SET x=5 | REST, Redis `SET` |
| Non-idempotent op | POST, INCREMENT, APPEND | REST create, `INCR`, Kafka append |
| Producer-side de-dup | sequence number per (producer, partition) | Kafka idempotent producer |
| Cross-partition atomicity | 2PC-like commit protocol | Kafka transactions (EOS) |
| Client-side idempotency | UUID key + server dedup table + TTL | Stripe `Idempotency-Key` header |
| Conditional write | compare-and-swap / version check | DynamoDB `ConditionExpression`, Postgres `WHERE version=` |

## What It Is

- **Idempotency**: an operation `f` where `f(f(x)) = f(x)` — applying it multiple times has the same effect as applying it once.
- **Exactly-once delivery**: a guarantee that a message is transmitted and processed precisely one time, no more, no fewer — theoretically unattainable over a network where messages/acks can be lost.
- **Exactly-once semantics (EOS)**: the practical substitute — deliver at-least-once (retry until ack), but make processing idempotent so retries are harmless. Result *looks like* exactly-once to the end system.

## Responsibilities

- Prevent duplicate side effects (double charges, duplicate rows, double inventory decrements) under retries, network partitions, and crash-restarts.
- Preserve correctness without sacrificing availability — you don't need synchronous coordination if the effect is idempotent.
- Give clients a safe way to retry blindly (timeouts, connection resets) without querying "did that actually happen?" first.

## How It Works

**Two Generals Problem**: two armies must agree on an attack time by messenger across enemy territory; any message can be lost, and no number of acknowledgments makes success provable to both sides simultaneously. Maps directly to distributed systems: sender can never be 100% sure receiver processed a message even after "success," because the ack itself can be lost. Consequence — a sender that wants reliability must retry on ambiguous outcomes, which *guarantees* duplicates are possible.

**Solution shape**: accept duplicates will happen (at-least-once), neutralize them at the processing layer.

1. **Idempotency key pattern** (client-driven dedup):
   - Client generates a UUID once per logical operation (not per HTTP attempt) and sends it as a header/field, e.g. `Idempotency-Key: 7c9e...`.
   - Server looks up key in a dedup store (Redis/Postgres table `idempotency_keys(key, status, response, created_at)`).
   - If seen and completed → return cached response, skip re-execution.
   - If seen and in-flight → reject/409 or block (avoid concurrent double-processing).
   - If unseen → execute, atomically record result + key (same DB transaction as the business write), return.
   - TTL/expire keys (e.g., 24h) to bound storage growth.

2. **Conditional writes** (server-driven dedup via state, no key table):
   - Use compare-and-swap: `UPDATE orders SET status='shipped' WHERE id=? AND status='pending'`.
   - DynamoDB `ConditionExpression: attribute_not_exists(id)` for insert-once semantics.
   - Optimistic concurrency with a version column rejects stale/duplicate writes automatically.

3. **Kafka idempotent producer**:
   - Producer gets a unique `PID` (producer ID) from the broker on init.
   - Each message tagged with `PID` + monotonically increasing **sequence number** per partition.
   - Broker tracks last-committed sequence per `(PID, partition)`; if it sees a sequence it already has, it silently dedups (ack'd, not re-appended).
   - Fixes the classic "producer sends, ack lost, producer retries, broker now has 2 copies" bug — set via `enable.idempotence=true` (default since Kafka 3.0 with `acks=all`).

4. **Kafka transactions (EOS across read-process-write)**:
   - Wraps a consume-transform-produce loop so output writes + consumer offset commits happen atomically.
   - Producer starts transaction (`initTransactions`, `beginTransaction`), writes to output topic(s) *and* writes consumer offsets to `__consumer_offsets` via `sendOffsetsToTransaction`, then `commitTransaction`.
   - Uses a **transaction coordinator** (broker) + markers written to logs; consumers with `isolation.level=read_committed` skip aborted/uncommitted messages.
   - This is essentially a mini 2PC: coordinator writes a commit marker only after all partition leaders ack.

## Types / Classifications

| Type | Definition | Examples |
|---|---|---|
| Naturally idempotent | Same call N times = same end state, no coordination needed | `PUT /user/5 {name:"Bob"}`, `DELETE /order/9`, `SET key val`, absolute file write |
| Idempotent by design (needs key) | Operation is inherently creates/appends but made safe via dedup key | `POST /payments` + `Idempotency-Key`, Kafka idempotent producer |
| Non-idempotent, unsafe to retry blindly | Each call changes state further | `INCR counter`, `POST /order` (no key), `APPEND log`, email send |
| Read-only / safe | No side effects at all | `GET`, `SELECT` — trivially idempotent (retry-safe by definition) |

## Where It Fits

```
Client ──(retry w/ same idem-key)──> API Gateway ──> Service ──> Dedup Store (Redis/DB)
                                                          │
                                                          └──> Business DB (same txn as dedup record)

Producer ──(seq #, PID)──> Kafka Broker ──dedup on seq──> Partition Log
                                              │
                                        Txn Coordinator ──commit marker──> Consumer (read_committed)
```
- Sits at API boundaries (payment APIs, order creation), message queue producers/consumers, and DB write paths.
- Complements retries/circuit breakers at the network layer — idempotency is what makes retries *safe* in the first place.

## Common Patterns & Real-World Tools

- **Stripe/PayPal APIs**: mandatory `Idempotency-Key` on POST for charges; key cached ~24h, replayed request returns original response verbatim (even original HTTP status).
- **Kafka**: `enable.idempotence=true` (producer), `transactional.id` for cross-partition/cross-topic EOS, `isolation.level=read_committed` (consumer).
- **DynamoDB**: `ConditionExpression` for insert-once; TransactWriteItems for multi-item idempotent commits.
- **SQS**: FIFO queues provide dedup via `MessageDeduplicationId` (5-min dedup window) — standard queues are at-least-once only, no dedup.
- **Redis**: `SETNX` / `SET key val NX` for idempotent "claim" operations (distributed locks, once-only processing).
- **Postgres/MySQL**: `INSERT ... ON CONFLICT DO NOTHING` (upsert) as idempotent insert.
- **Outbox pattern**: pairs with idempotency to guarantee "write DB + publish event" atomically, consumer then dedups on event ID.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Idempotency key + dedup table | Works for any op, client controls retry semantics | Extra storage, TTL management, must be same txn as write (or a saga) |
| Conditional write / CAS | No extra table, atomic with the write itself | Only works when state itself encodes "already done"; retries need same target state |
| Kafka idempotent producer | Transparent, no app code changes, low overhead | Only dedups within a producer session (PID resets on restart) and per partition |
| Kafka transactions | True cross-partition atomicity | Throughput cost (~3-5% overhead), added latency (`transaction.timeout.ms`), coordinator complexity |
| Naturally idempotent design | Simplest, no infra needed | Not always possible (e.g., "charge $10" is inherently additive) |

## Real-World Scenarios

- **Double-charge bug**: mobile client times out on `POST /charge`, user taps "Pay" again → without idem key, two charges; with key, second call returns cached success from first.
- **Kafka producer retry storm**: broker leader failover causes ack timeout, producer retries → without `enable.idempotence`, duplicate messages land in partition; with it, broker dedups via sequence number.
- **Consumer crash mid-processing**: consumer processes message, crashes before committing offset, restarts, re-reads same message → downstream write must be idempotent (e.g., upsert by message key) or wrapped in Kafka transaction with atomic offset commit.
- **Inventory decrement**: `UPDATE inventory SET qty = qty - 1` is NOT idempotent; retried on ambiguous network failure → oversold stock. Fix: `UPDATE inventory SET qty = qty - 1 WHERE order_id != ? ...` guarded by an idempotency key check first, or CAS on expected qty.

## Nuances & Gotchas

- **Idempotency key scope matters**: keying only on request body (not client-supplied UUID) breaks for legitimately identical requests (e.g., two $10 charges to same user same day) — always use a client-generated unique key, not a content hash, unless content truly is unique.
- **Race condition on first insert**: two retries can arrive concurrently before the first dedup record commits — use `INSERT ... ON CONFLICT` or a unique constraint on the idempotency key column, not read-then-write.
- **Idempotency window ≠ forever**: TTL-expired keys mean a very late retry (client backed off 48h) can duplicate — pick TTL based on realistic max retry window, not arbitrary convenience.
- **Kafka idempotent producer resets PID on restart**: if producer process restarts mid-retry-sequence, dedup guarantee only covers messages within a single producer session — use `transactional.id` (stable across restarts) for durability-across-restart guarantees.
- **"Exactly-once" in Kafka means exactly-once *within the Kafka pipeline***, not once the effect leaves it — a consumer that calls an external non-idempotent API (send email, charge card) after reading a transactional message can still double-fire on redelivery.
- **Dedup table must be transactional with the business write**, or you get the classic split-brain: business write commits, dedup record write fails → replay redoes the business write. Use same DB transaction, or outbox/two-phase pattern.
- **`read_committed` doesn't mean "definitely committed forever"** — it filters aborted transactions from consumer view, but consumers still need their own offset-commit idempotency for crash-restart duplicates.
- **CAS-based idempotency silently fails if state changed for unrelated reasons** — e.g., `WHERE status='pending'` won't distinguish "already processed by our retry" from "moved to pending by a different flow"; combine with idempotency key when ambiguity is possible.
- **Two Generals corollary**: no amount of retrying achieves *certainty*; you're trading unprovable certainty for a system where the *effect* is deterministic regardless of duplicate delivery — that's the actual engineering target, not "guarantee no duplicates."
