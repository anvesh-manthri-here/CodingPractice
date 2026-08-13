# Distributed Transactions — 2PC and 3PC

> **TL;DR:** 2PC gives atomic commit across nodes via a coordinator but blocks forever if the coordinator dies after prepare; 3PC adds a timeout-safe extra phase to fix blocking but is barely used because it can't handle network partitions correctly. Modern systems mostly avoid both, preferring sagas, outbox, or single-leader consensus (Spanner/CockroachDB) instead.

## Quick Reference

| Aspect | 2PC | 3PC | Modern alternative |
|---|---|---|---|
| Phases | Prepare, Commit | CanCommit, PreCommit, DoCommit | N/A (async) |
| Blocking on coordinator crash | Yes, indefinitely | No (in theory, non-partitioned) | N/A |
| Network partition safe | No | No (assumes no partition) | Yes (saga compensations) |
| Latency | 2 round trips + fsync each | 3 round trips + fsync each | Async, eventual |
| Used in practice | XA (JTA/MSDTC), Spanner internals | Almost never | Sagas, outbox, Kafka transactions |
| CAP stance | Sacrifices A under partition | Sacrifices P (assumes synchrony) | Sacrifices C (eventual) |
| Failure recovery | Manual/heuristic or wait for coordinator | Automatic via timeout | Compensating transactions |

## What It Is

- **2PC (Two-Phase Commit):** a protocol to atomically commit a transaction spanning multiple resource managers (DBs, queues) coordinated by one node.
- **3PC (Three-Phase Commit):** a variant that inserts a non-blocking "pre-commit" acknowledgment phase so participants can safely time out and unilaterally decide, avoiding indefinite blocking — under the assumption of no network partitions.
- Both are **atomic commitment protocols**, not consensus protocols (they don't tolerate the coordinator being wrong/split, unlike Paxos/Raft).

## Responsibilities

- **Coordinator (transaction manager):** assigns global transaction ID, sends prepare/vote requests, collects votes, decides commit/abort, broadcasts decision, logs decision durably.
- **Participants (resource managers):** vote yes/no on prepare, must hold locks and be able to commit/abort on command once voted yes ("in-doubt" state), write to their own durable log before voting.
- Both sides must persist protocol state to disk (write-ahead log) to survive crash and resume correctly.

## How It Works

### 2PC mechanics
```
Coordinator                 Participant A        Participant B
   |--- PREPARE ------------>|                     |
   |--- PREPARE --------------------------------->  |
   |<-- VOTE YES (locked) ---|                     |
   |<-- VOTE YES (locked) -------------------------  |
   |  (all yes -> decide COMMIT, log it)
   |--- COMMIT -------------->|                     |
   |--- COMMIT ------------------------------------>|
   |<-- ACK -------------------|                     |
```
- **Phase 1 (Prepare/Vote):** coordinator asks all participants "can you commit?" Each participant does all work, writes redo/undo log, and votes yes (promising to commit) or no.
- **Phase 2 (Commit/Abort):** if all voted yes, coordinator logs "commit" decision (this log write is the true commit point) and tells everyone to commit; if any voted no, or timeout, it broadcasts abort.
- Participants that voted yes but haven't heard back are **"in doubt"**: they must hold locks and cannot unilaterally decide — this is the blocking window.

### The blocking failure mode
- If coordinator crashes after receiving all votes but before (or while) broadcasting the decision, participants that voted yes are stuck holding locks indefinitely.
- They cannot safely commit (another participant might have voted no) or abort (another might already have committed) without knowing the coordinator's decision.
- Only recovery: wait for coordinator to restart and read its log, or a human/DBA intervenes (heuristic commit/abort — risks inconsistency).

### 3PC mechanics
- Splits phase 2 into **CanCommit → PreCommit → DoCommit**.
- After all vote yes, coordinator sends **PreCommit** (not final commit) — participants ack it and now know a decision is coming, then move to a state where they can safely time out and commit even without hearing DoCommit, because "everyone acked PreCommit" implies no one will abort.
- If coordinator dies, a newly elected coordinator queries participant states: if any participant reached PreCommit, it's safe to commit; if none did, safe to abort.
- **Why it fails in practice:** this correctness proof assumes no network partition (synchronous network with bounded delay). Under a partition, a participant can time out and commit while the coordinator (partitioned away) independently tells others to abort — split-brain, actual inconsistency, worse than blocking. Also adds a full extra round trip of latency and fsyncs.

## Types / Classifications

| Variant | Notes |
|---|---|
| **Presumed abort 2PC** | Optimization: if coordinator log has no record, assume abort — avoids logging aborts, common in XA implementations |
| **Presumed commit 2PC** | Inverse optimization for commit-heavy workloads |
| **XA (X/Open Distributed Transaction)** | Industry-standard 2PC API; used by JTA (Java), MSDTC (Microsoft), Oracle/Postgres/MySQL support it |
| **3PC (classic, Skeen/Stonebraker)** | Non-blocking under crash-only faults, not partition-tolerant |
| **Paxos Commit / Spanner-style** | Replaces single coordinator with a Paxos group per participant shard — tolerates coordinator failure via consensus, not just timeout |

## Where It Fits

- Sits at the **transaction coordination layer**, above storage engines, below application code — e.g., a JTA transaction manager coordinating a JDBC connection and a JMS queue.
- **Google Spanner:** uses 2PC to commit transactions that span multiple Paxos groups (shards); each shard is itself Paxos-replicated so the "coordinator" and "participants" are fault-tolerant groups, not single machines — this is what makes it safe in practice.
- **CockroachDB / YugabyteDB:** similarly run 2PC across Raft-replicated ranges, avoiding the single-point-of-failure blocking problem.
- **Kafka transactions:** internal 2PC-like protocol between the Transaction Coordinator and partition leaders for exactly-once semantics across topics.

## Common Patterns & Real-World Tools

| Tool/Pattern | Role |
|---|---|
| **XA / JTA** | Standard 2PC across JDBC/JMS resources in Java EE |
| **MSDTC** | Windows distributed transaction coordinator, 2PC across SQL Server/MSMQ |
| **Saga pattern** | Sequence of local transactions + compensating actions, no locks held across services |
| **Outbox pattern** | Write to local DB table + async relay (Debezium CDC) to message broker, avoids dual-write problem without 2PC |
| **Kafka transactional producer** | 2PC-flavored protocol for atomic multi-partition writes |
| **Spanner TrueTime + 2PC** | 2PC over Paxos groups for cross-shard commits |

## Pros & Cons / Trade-offs

**2PC**
- Pro: true ACID atomicity across nodes, simple mental model, strong consistency.
- Con: blocking on coordinator failure, holds locks across network round trips (throughput killer), single point of failure, doesn't handle partitions.

**3PC**
- Pro: solves blocking under simple crash-stop failures.
- Con: extra round trip/latency, still fails under network partitions, rarely implemented, adds complexity for a fix that doesn't fully work — hence near-zero production adoption.

**Sagas/Outbox**
- Pro: no cross-service locks, services stay available independently, horizontally scalable.
- Con: no true isolation (dirty reads possible mid-saga), requires writing compensating logic, eventual consistency, harder to reason about failure states.

## Real-World Scenarios

- **Bank transfer across two microservices' own DBs:** 2PC would lock both accounts' rows for the full round trip; a saga instead does "debit A" then "credit B" with a compensating "refund A" if credit fails — used by most fintech systems (e.g., money-movement platforms) to keep services independently available.
- **Order + inventory + payment services:** classic saga (orchestrated via a state machine, e.g., AWS Step Functions or Temporal) with compensations like "cancel order," "release inventory," "refund payment."
- **Spanner cross-shard multi-row transaction:** 2PC used internally because each participant is itself a Paxos-replicated group — the coordinator dying doesn't block forever because a new Paxos leader takes over that shard's role.
- **Local DB + outbox table:** service writes business row and an "event" row in the same local ACID transaction, then Debezium CDC tails the outbox and publishes to Kafka — avoids the "write to DB and publish to broker" dual-write problem without any distributed transaction.

## Nuances & Gotchas

- **The "in-doubt" window is the real production hazard:** locks held by a stalled participant can cascade — other transactions queue behind them, causing a full outage, not just delay for the one transaction.
- **Heuristic decisions break atomicity:** many XA implementations let an admin force-commit or force-abort an in-doubt transaction after a timeout; if the coordinator later comes back with the opposite decision, data is now genuinely inconsistent — this is a manual escape hatch, not a real fix.
- **Coordinator log durability is the actual commit point** — if the coordinator's "commit" log write is lost/corrupted after telling participants to commit, you get orphaned commits with no record; coordinator DB is itself a single point of failure unless it's replicated.
- **2PC does not compose well with retries/idempotency naively** — network timeouts during phase 2 make it ambiguous whether a participant committed; participants must dedupe by transaction ID.
- **3PC's non-blocking guarantee silently assumes synchronous network** — real internet/cloud networks have unbounded delay, so the timeout-based "safe to proceed" logic can produce split-brain; this is why almost no production system implements classic 3PC (Zookeeper's earlier design flirted with 3PC-like ideas but moved to Zab/Paxos-style consensus instead).
- **Performance:** 2PC's synchronous fsync + round trip per participant per transaction caps throughput far below single-node commit — this, more than correctness, is why high-throughput systems (payment processors, e-commerce checkouts) avoid it.
- **Sagas trade isolation for availability:** intermediate states are visible to other transactions (no "I" in ACID), so systems must design for that — e.g., using semantic locks, versioning, or "pending" states visible to readers.
- **Outbox pattern still needs exactly-once delivery from relay to broker** — usually achieved via idempotent consumers + dedupe keys, not magic; Debezium/CDC guarantees at-least-once, not exactly-once, out of the box.
- **Spanner's trick isn't "2PC solved," it's "2PC over already-fault-tolerant participants"** — don't assume plain 2PC across two ordinary databases behaves the same way; the fault tolerance comes from Paxos underneath, not from 2PC itself.
