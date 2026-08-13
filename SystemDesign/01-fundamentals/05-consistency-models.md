# Consistency Models

> **TL;DR:** Consistency models trade off how "instantaneous and global" data updates appear versus how fast/available the system stays; strong models (linearizability) are expensive and coordination-heavy, weak models (eventual) are cheap but push anomaly-handling to the app. Real systems mix models per-operation, not per-system.

## Quick Reference

| Model | Real-time order? | Global total order? | Typical latency cost | Impl mechanism |
|---|---|---|---|---|
| Strict serializability | Yes | Yes (txns) | Highest | Consensus + txn coordination (Spanner) |
| Linearizability | Yes | Yes (per-object) | High | Quorums, leases, consensus (Raft/Paxos) |
| Sequential consistency | No | Yes | Medium-high | Total-order broadcast |
| Causal consistency | Partial (causal only) | No | Medium | Vector clocks, dependency tracking |
| Session guarantees | Per-client only | No | Low-medium | Sticky sessions, version tokens |
| Eventual consistency | No | No | Lowest | Gossip, anti-entropy, CRDTs |

## What It Is

- A consistency model is a **contract** between a distributed data store and its clients: which orderings/values a read is allowed to return given a set of concurrent writes.
- It is orthogonal to **availability** (CAP) and to **isolation levels** (which govern multi-key/multi-statement transaction anomalies like dirty reads, phantom reads) — consistency models govern visibility of single-object/single-key operations across replicas, though the two vocabularies overlap at the top (linearizability, serializability).
- Core tension: stronger guarantees require **coordination** (consensus, locks, quorums) which costs latency and reduces availability under partition (CAP/PACELC).

## Responsibilities

- Define legal **interleavings** of concurrent operations from multiple clients/replicas.
- Bound **staleness**: how far behind (in time, in causal history, in version) a read can lag the latest write.
- Provide **predictability** for application authors so they can reason about what a read might return.
- Determine what coordination primitive is needed at write time, read time, or both.

## How It Works

**PACELC framing**: under Partition, trade Availability vs Consistency; Else (normal operation), trade Latency vs Consistency. Every model below sits somewhere on that line.

Implementation mechanisms:
- **Quorums (W+R>N)**: Dynamo-style stores (Cassandra, Riak) use read/write quorums; `R+W>N` gives read-your-writes-ish overlap but NOT linearizability without extra fencing (clock skew, concurrent writes can still race).
- **Leases/leader-based**: single leader serializes all writes and often reads (Raft/Multi-Paxos leader lease) → linearizable single-object ops as long as lease is safe (no clock-based lease violated by GC pause).
- **Consensus (Raft/Paxos/Zab)**: total-order broadcast of a log → sequential/linearizable consistency for state built on top of it (etcd, Zookeeper, Kafka's controller).
- **Hybrid Logical Clocks (HLC)**: combine physical time + logical counter (CockroachDB) to get causally-consistent, roughly-real-time-ordered timestamps without atomic clocks; used to detect/bound uncertainty windows.
- **TrueTime (Spanner)**: GPS+atomic clocks bound clock uncertainty epsilon (~ms); commit-wait (wait out epsilon before acknowledging) turns bounded clock error into external (strict serializable) consistency.
- **Vector clocks / version vectors**: causal consistency implementation (Riak, COPS, original Dynamo) — track per-node counters so causally dependent writes are ordered, concurrent writes are detected and flagged (siblings).
- **CRDTs**: conflict-free replicated data types (G-counters, OR-Sets) — mathematically guarantee convergence under eventual consistency without coordination (Redis CRDTs, Automerge, Riak DT).

## Types / Classifications

### The hierarchy (strongest → weakest)

```
Strict Serializability
        │ (linearizability + txn atomicity across keys)
Linearizability
        │ (add total real-time order guarantee)
Sequential Consistency
        │ (drop real-time, keep single global order)
Causal Consistency
        │ (drop total order, keep cause→effect order)
Session Guarantees (RYW, MR, MW, WFR)
        │ (per-client causal subset)
Eventual Consistency
   (only guarantee: convergence, no ordering)
```

Each level down permits strictly more anomalies but costs less coordination/latency.

### The four session guarantees (client-centric, sit between causal and eventual)

| Guarantee | Meaning | Anomaly it prevents |
|---|---|---|
| Read-Your-Writes (RYW) | A client always sees its own prior writes | Post to profile, refresh, see old profile |
| Monotonic Reads (MR) | Successive reads never go backward in time | See new comment, refresh, comment vanishes |
| Monotonic Writes (MW) | A client's writes are applied in the order issued | Write v2 then v1 arrives out of order at a replica |
| Writes-Follow-Reads (WFR) | A write based on a previously read value is ordered after it everywhere | Reply to comment X, reply appears before X on another replica |

Implemented via **sticky sessions** (route client to same replica) or **version/token passing** (client carries last-seen vector clock/LSN, server waits until replica catches up).

### Anomaly per model, concretely

| Model | Anomaly still permitted | Concrete example |
|---|---|---|
| Eventual | Stale reads indefinitely, no ordering | Read replica returns value from 5 min ago; two replicas disagree forever until next write |
| Causal | Concurrent (non-causally-related) writes can be seen in different orders by different clients | Alice and Bob both edit unrelated fields concurrently; client A sees Alice's edit first, client B sees Bob's first — fine, because unrelated |
| Sequential | Operation can return a value "from the future" relative to real time (no real-time bound) | Client A writes X=1 at t=1, finishes at t=2; Client B starts read at t=3 but can still legally see X=0 if system picked a global order where B's op is "before" A's, as long as each client's own program order is preserved |
| Linearizable | None on single objects, but no multi-key atomicity | Transfer $10 from A to B: linearizable per-key reads/writes are fine individually, but a reader can see A already debited and B not yet credited (money "missing" mid-transfer) |
| Strict Serializable | None (real-time + txn atomicity) | The transfer above never shows a partial state; equivalent to some real-time-consistent serial execution |

### Linearizability vs Serializability vs Strict Serializability

- **Linearizability**: single-object, real-time order. Every operation appears to take effect atomically at some point between invocation and response. No notion of multi-key transactions.
- **Serializability**: multi-object/transaction, but **no real-time constraint** — the system just needs *some* order equivalent to a serial execution of transactions; that order can violate wall-clock order (e.g., T2 committed after T1 in real time can still be "ordered before" T1 in the serialization).
- **Strict Serializability = Linearizability + Serializability**: multi-key transactions AND real-time ordering respected. This is what Spanner, CockroachDB, FoundationDB, YugabyteDB target.
- Common trap: "serializable" (e.g., Postgres `SERIALIZABLE` isolation) does **not** imply linearizable — two serializable transactions on different connections can be reordered relative to real time.

## Where It Fits

- **Storage layer**: replica read/write paths (leader-only reads vs any-replica reads), replication protocol (sync/async/quorum).
- **Transaction manager**: 2PC/consensus layer sits above raw replication to add atomicity across keys/shards.
- **Client library / SDK**: session guarantees are often implemented client-side (token passing, sticky routing) rather than server-side.
- **API contract**: exposed to callers as read preference (`ReadYourWrites`, `Bounded Staleness`, `Eventual`) — e.g., DynamoDB's `ConsistentRead=true/false`, Cosmos DB's 5 explicit levels, MongoDB read/write concerns.

## Common Patterns & Real-World Tools

| Tool | Default model | Tunable? |
|---|---|---|
| Google Spanner | External (strict serializable) via TrueTime commit-wait | Read modes: strong / bounded-staleness / exact-staleness |
| CockroachDB | Serializable (strict serializable via HLC + uncertainty intervals) | Not much — always serializable |
| DynamoDB | Eventual reads | `ConsistentRead=true` → linearizable-ish read (still single-region) |
| Cassandra | Tunable (default ONE/QUORUM) | `ANY, ONE, QUORUM, ALL, LOCAL_QUORUM` per query |
| Cosmos DB | Session | 5 explicit levels: Strong, Bounded Staleness, Session, Consistent Prefix, Eventual |
| Zookeeper / etcd | Linearizable writes, sequential reads (or linearizable with quorum read) | `--consistency=serializable` for stale local read |
| Riak / Dynamo-original | Eventual + causal (vector clocks, siblings) | N/R/W tunable |
| Kafka | Per-partition total order (sequential within partition) | `acks=all` + `min.insync.replicas` for durability/consistency trade |
| Redis (single primary) | Linearizable-ish (single-threaded leader) | Async replicas = eventual for replica reads |

## Pros & Cons / Trade-offs

- **Linearizable/Strict Serializable**: Pros — simplest mental model, no anomalies. Cons — highest latency (cross-region consensus round trips), reduced availability under partition (CP in CAP).
- **Sequential**: Pros — global order simplifies replay/debugging (e.g., Kafka partition log). Cons — still needs total-order broadcast; no real-time guarantee surprises engineers who assume "sequential ≈ real time."
- **Causal**: Pros — captures the ordering that actually matters for UX (cause before effect) at lower cost than total order; scales better geo-distributed. Cons — concurrent-write conflicts still need resolution (LWW, CRDT merge, app-level).
- **Session guarantees**: Pros — cheap, client-scoped, huge UX win (fixes "my own post disappeared" bugs) without global coordination. Cons — only protects the guaranteeing client; other clients can still see anomalies.
- **Eventual**: Pros — best availability/latency/partition tolerance (AP). Cons — app must handle conflicting/stale data; convergence time unbounded without anti-entropy.

## Real-World Scenarios

- **Bank transfer / ledger**: needs strict serializability (Spanner, CockroachDB) — partial states are unacceptable, real-time order matters for audits.
- **Social media "like" counter**: eventual consistency + CRDT counter is fine — approximate count, converges, no user-visible correctness issue.
- **User posts own comment, must see it immediately on refresh**: read-your-writes session guarantee is the minimum bar; full linearizability is overkill.
- **Shopping cart**: causal consistency + WFR — "add to cart" then "checkout" must be ordered; but cart state across unrelated users doesn't need global order.
- **Leader election / distributed lock (Zookeeper, etcd)**: linearizability is mandatory — two nodes must never both believe they hold the lock.
- **Chat app message ordering within a room**: sequential consistency (single-partition Kafka topic) — all clients see same order, doesn't need to match wall-clock exactly.
- **Multi-region config service (feature flags)**: bounded staleness (Cosmos DB) — accept a few seconds of lag in exchange for low-latency local reads.

## Nuances & Gotchas

- **"Eventually consistent" has no time bound by definition** — teams often assume "a few seconds" but under partition/GC pause it can be minutes; always ask "what's the anti-entropy interval / hinted-handoff timeout?"
- **Read-your-writes breaks silently with load balancers**: client hits replica A (write), then LB routes next request to replica B that hasn't caught up — classic sticky-session bug, especially after a deploy that resets session affinity.
- **Quorum overlap (W+R>N) is NOT linearizability**: it guarantees a read *can* see the latest write, not that it *will* — without additional read-repair/monotonic read-index (e.g., Raft ReadIndex) you can still get stale or non-monotonic reads.
- **Clock skew silently downgrades "strong" systems**: TrueTime's commit-wait assumes bounded clock uncertainty (epsilon, historically ~7ms at Google); NTP-only clusters attempting the same trick without atomic clocks can produce actual consistency violations under skew, not just staleness.
- **Serializable isolation ≠ linearizable**: a very common interview and production mistake — Postgres `SERIALIZABLE` transactions can be legally reordered relative to wall-clock commit order across sessions; don't assume cross-service ordering from DB isolation level alone.
- **Causal consistency's "concurrent write" ambiguity**: when two writes are truly concurrent (no causal link), the model explicitly allows different final values per replica until resolved — apps must define merge (LWW by timestamp loses data silently; CRDT/app-level merge is safer).
- **Choose per-operation, not per-system**: e.g., an e-commerce platform can run inventory decrement as linearizable (avoid overselling) while product reviews and view counts run eventual — forcing one global consistency level either kills performance or introduces correctness bugs. Design the model at the API/operation boundary.
- **Session guarantee tokens must be propagated correctly across service boundaries** (e.g., through an API gateway or mobile app reinstall) — losing the version token silently downgrades a client to eventual consistency with no error.
- **Leader leases under GC pause / VM stall**: a "linearizable" leader-based system can violate linearizability if the old leader's lease is believed expired by others while the old leader (paused by GC) still thinks it's active and serves a stale read — mitigated by lease durations >> max expected pause, or fenced tokens (fencing generation numbers on writes to storage).
- **Bounded staleness configs (Cosmos DB, CockroachDB follower reads) trade a knob you must monitor**: staleness bound is a promise under normal operation; under partition it can silently exceed the configured bound unless the system halts reads (fail-closed) vs serves stale (fail-open) — know which your store does.

## Self-Check

1. A Dynamo-style store uses `W+R>N` quorums. A team claims this makes their reads linearizable. Give a concrete scenario where this claim fails.
2. Take the bank-transfer example: describe an interleaving where the system is linearizable but NOT serializable/strict-serializable, and explain why a reader could observe A debited but B not yet credited.
3. A Raft leader holds a time-based lease and believes it's still active. Under what condition can this leader serve a stale read that violates linearizability, and what are two mitigations?
4. Postgres `SERIALIZABLE` isolation is often assumed to imply linearizable ordering across sessions. Why is this wrong — what could actually happen?
5. A client passes a version token to maintain read-your-writes across an API gateway. Name a real failure mode that silently downgrades this client to eventual consistency, with no error surfaced.

<details><summary>Answers</summary>

1. Quorum overlap only guarantees a read *can* intersect the latest write's replica set, not that it *will* return that value — without read-repair or a monotonic read-index, a client can still read stale or even non-monotonic values (e.g., see v2 then v1 on a later read) because nothing forces the read to pick the freshest version among the overlapping replicas.
2. Per-key operations (debit A, credit B) are each linearizable individually, but there's no cross-key atomicity: a reader can observe the debit-A operation's linearization point has passed while credit-B's has not, seeing money "missing" mid-transfer. Serializability/strict-serializability would wrap both writes in one transaction so no reader ever sees that intermediate state.
3. If the leader is paused by GC/VM stall past its lease duration, other nodes may believe the lease expired and elect a new leader, while the paused leader wakes up still believing it's active and serves a stale read. Mitigations: set lease duration much greater than max expected pause, and/or use fenced tokens (monotonic fencing/generation numbers checked on every write to storage).
4. Postgres `SERIALIZABLE` only guarantees *some* order equivalent to a serial execution of transactions — it has no real-time constraint. Two serializable transactions on different connections can be legally reordered relative to wall-clock commit order, so a transaction that commits later in real time can still be "ordered before" one that committed earlier.
5. Losing or failing to propagate the version/vector-clock token across a service boundary (e.g., an API gateway that doesn't forward it, or a mobile app reinstall that resets local state) — the client then reads from any replica with no staleness check, silently falling back to eventual consistency with no visible error.

</details>

---
**Related:** [CAP Theorem](03-cap-theorem.md) · [PACELC Theorem](04-pacelc-theorem.md) · [Cache Eviction and Invalidation](../02-core-components/05-cache-eviction-and-invalidation.md)

*Last reviewed: 2026-08*
