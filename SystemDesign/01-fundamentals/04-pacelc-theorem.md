# The PACELC Theorem

> **TL;DR:** CAP only describes behavior during a network partition; PACELC (Daniel Abadi, 2010; formalized in IEEE Computer, 2012) extends it — **if Partitioned, choose A or C; Else (normal operation), choose L or C.** The "else" branch is the one you live in 99.9% of the time, because partitions are rare but latency/consistency trade-offs happen on every single request.

## Quick Reference

| Class | Partition behavior | Normal-time behavior | Example systems |
|---|---|---|---|
| **PA/EL** | Availability over consistency | Latency over consistency | DynamoDB (default), Cassandra (default), Riak, Couchbase |
| **PA/EC** | Availability over consistency | Consistency over latency | Rare combo — MongoDB (with majority writes), some Couchbase configs |
| **PC/EL** | Consistency over availability | Latency over consistency | **Yahoo PNUTS** (the canonical example — Abadi's own); some tunable stores in relaxed-read mode |
| **PC/EC** | Consistency over availability | Consistency over latency | Spanner, CockroachDB, HBase, MongoDB (strong config), traditional RDBMS with sync replication |

| Concept | Meaning |
|---|---|
| P | Network Partition occurring |
| A | Availability (system responds, possibly stale) |
| C | Consistency (linearizable/strong reads) |
| E | Else — normal operation, no partition |
| L | Latency (fast response, weaker consistency) |

## What It Is

- CAP theorem says: under a partition, pick Consistency or Availability — but it says **nothing about the 99.99% of time there's no partition**.
- Abadi observed real systems make a *second*, independent trade-off during normal operation: replicate synchronously (consistent, slower) or asynchronously (fast, eventually consistent).
- PACELC = **P**artition → **A** or **C**; **E**lse → **L** or **C**. Two dials, not one.
- It's a classification lens, not a proof — use it to reason about a system's *default posture*, which is usually configurable per-operation.

## Responsibilities

PACELC as a framework should let you answer:
- What does this datastore do when a partition splits replicas — reject writes, or accept and reconcile later?
- What does this datastore do on an *ordinary* write with all replicas reachable — wait for a quorum/all replicas (consistent, higher latency), or ack after one node and replicate async (fast, eventually consistent)?
- Is the trade-off fixed by architecture, or a per-query knob (consistency level, read preference)?

## How It Works

```
        Partition?
        /        \
      yes          no
      /              \
   A or C          L or C
 (CAP world)    (the "else" — daily reality)
```

- **PA path**: on partition, minority-side replicas keep serving reads/writes → risk of stale reads / conflicting writes needing reconciliation (vector clocks, LWW, CRDTs).
- **PC path**: on partition, minority side stops serving (or steps down) until it can re-establish quorum → unavailability, but no divergence.
- **EL path**: no partition, but the system still replicates asynchronously or serves from a local/nearest replica to shave milliseconds off latency, accepting a replication-lag window.
- **EC path**: no partition, but writes block until a quorum (or all) replicas confirm — e.g. Raft/Paxos commit, or synchronous 2PC across regions — trading latency for a guaranteed-consistent read afterward.
- The "else" trade-off is dominated by physics: cross-region round-trip time (50-150ms) vs. local ack (<1ms). Synchronous consensus pays that RTT on every write.

## Types / Classifications

- **PA/EL** — "AP-leaning always." Prioritizes uptime and speed both when partitioned and when not. Tunable systems default here but let you dial up consistency per-query.
- **PC/EC** — "CP-leaning always." Never sacrifices correctness; pays the latency tax constantly (consensus round-trips) and can go unavailable on partition.
- **PA/EC** — Rare: available under partition (accepts writes on both sides) but demands strong consistency in normal times (e.g., wait for majority ack). MongoDB with `w:majority` read/write concern approximates this.
- **PC/EL** — Sounds contradictory but is a real design: refuses availability under partition, yet optimizes for latency normally. **Yahoo PNUTS** is the canonical case — every record has a single master region that orders writes (PC: lose the master, that record's writes stop), but reads are served from the *local* region's replica without waiting for the master (EL: fast, possibly stale). Abadi cites it as the quadrant that proves PACELC adds information CAP can't express.

## Where It Fits

- Sits one layer below CAP in the system-design stack: CAP tells you the *failure-mode* trade-off; PACELC tells you the *everyday* trade-off, which usually drives 95% of your latency SLOs and consistency bugs.
- Directly informs: replication topology (sync vs async), quorum config (`W+R>N`), read/write consistency levels, and multi-region architecture (single-leader vs multi-leader vs consensus-per-write like Spanner/CockroachDB).
- Feeds into SLA design: p99 latency budgets are set by whether you're on the E/L or E/C side.

## Common Patterns & Real-World Tools

| System | Partition (PA/PC) | Normal (EL/EC) | Mechanism |
|---|---|---|---|
| **DynamoDB** | PA | EL (default), EC opt-in | Eventually consistent reads by default; `ConsistentRead=true` flag switches to EC per-request |
| **Cassandra** | PA | EL (default), EC tunable | `ONE`/`QUORUM`/`ALL` consistency level per query; async hinted handoff |
| **MongoDB** | PC (primary steps down w/o quorum) | EC with `w:majority`, EL with `w:1` | Read/write concern tunable per operation |
| **Spanner** | PC | EC | TrueTime + Paxos synchronous commit across replicas; latency cost is the price of global consistency |
| **CockroachDB** | PC | EC | Raft consensus per range; every write needs majority ack |
| **HBase** | PC | EC | Single active RegionServer per region, strongly consistent, no tunability |
| **Riak / Couchbase** | PA | EL | Dynamo-style, vector clocks / CRDTs for conflict resolution |
| **PostgreSQL (sync replication)** | PC | EC | `synchronous_commit=on` blocks until standby acks |
| **PostgreSQL (async replication)** | PA-ish | EL | Default async streaming replication — fast, replica can lag/lose data on failover |

## Pros & Cons / Trade-offs

- **PA/EL**: best latency and uptime; cost = stale reads, conflict resolution complexity (CRDTs, application-level merge logic), read-your-writes violations.
- **PC/EC**: strongest correctness guarantees, simplest application logic; cost = higher tail latency (consensus RTT), reduced availability during network issues, harder to scale writes globally.
- Tunable systems (Cassandra, DynamoDB, MongoDB, ScyllaDB) let you pick the point on the PACELC line **per operation** — the real-world answer is rarely a single global choice.
- No free lunch: you can't get PA/EL's latency and PC/EC's guarantees simultaneously on the same write path — physics (speed of light, RTT) enforces it.

## Real-World Scenarios

- **Shopping cart / session store**: PA/EL (DynamoDB default) — availability and low latency matter more than a rare stale read; conflicts resolved with last-writer-wins or CRDTs.
- **Bank ledger / payments**: PC/EC (Spanner, CockroachDB, or RDBMS with sync replication) — correctness non-negotiable, willing to pay 10-50ms extra latency and occasional unavailability.
- **Social media feed / like counts**: PA/EL (Cassandra `ONE`) — eventual consistency invisible to users, huge throughput win.
- **Inventory count at checkout**: often escalate to EC for just that read/write (e.g., DynamoDB `ConsistentRead=true`, Mongo `w:majority`) while the rest of the app stays EL — mixed strategy inside one system.
- **Global multi-region SaaS config service**: Spanner/CockroachDB chosen specifically to avoid split-brain config drift, accepting the latency cost because config changes are low-frequency.

## Nuances & Gotchas

- **The "else" branch is the one that bites in production**, not the partition branch — partitions are rare (maybe minutes/year), but every single write pays the sync-vs-async cost. Teams over-index on CAP interviews and under-design for EL/EC reality.
- **Consistency level is a per-request knob, not a system-wide constant** in tunable stores — a bug where one code path uses `QUORUM` and another uses `ONE` on the same table is a classic silent-inconsistency source.
- **Read-your-writes violations** are the most common PA/EL surprise: user writes, immediately reads from a different (lagging) replica, sees old data — fix with session/sticky consistency or read-after-write routing to the leader.
- **Synchronous replication ≠ automatic consistency**: Postgres `synchronous_commit=on` waits for WAL flush ack on the standby, but failover logic still matters — a misconfigured quorum can still lose acknowledged writes.
- **Spanner's trick**: it looks like it violates PACELC (strong consistency AND decent latency) because TrueTime bounds clock uncertainty tightly enough that the "wait out uncertainty" cost is single-digit ms, not a full cross-region RTT — it doesn't escape the trade-off, it just pays a smaller, bounded tax.
- **DynamoDB Global Tables / Cassandra multi-DC** are PA/EL across regions — last-writer-wins by timestamp can silently drop a concurrent write; know your conflict resolution before relying on multi-region writes.
- **MongoDB's default changed over versions** — older defaults were weaker (`w:1`, primary-only reads); modern best practice uses `w:majority` explicitly for anything correctness-sensitive, i.e., you must actively choose EC.
- **HBase/Spanner-style PC/EC systems degrade to full unavailability on quorum loss** — losing 1 of 3 replicas is fine, losing 2 of 3 halts writes entirely; capacity-plan replica placement across failure domains accordingly.
- **When picking a datastore**: don't ask "CP or AP" (a partition-day question); ask "what's my write-ack latency budget, and can my application tolerate stale reads?" — that's the PACELC question you'll actually face daily.

## Self-Check

1. Why does Abadi say the "else" branch matters more in practice than the partition branch?
2. Classify Yahoo PNUTS into a PACELC quadrant and justify both letters of your answer.
3. A tunable store shows a silent-inconsistency bug where one code path reads at `QUORUM` and another at `ONE` on the same table. What does PACELC say is actually going on here?
4. Spanner offers strong consistency with latency that looks far better than a typical cross-region RTT. Does this mean Spanner escapes the PACELC trade-off? Explain via TrueTime.
5. Why is PA/EC described as a rare combination, and which system approximates it?

<details><summary>Answers</summary>

1. Partitions are rare (minutes/year) but the L-vs-C replication trade-off is paid on every single write/read, so it dominates day-to-day latency SLOs and consistency bugs far more than partition handling does.
2. PC/EL: PC because each record has a single master region ordering writes, so losing that master halts writes for that record (no availability during partition); EL because normal-time reads are served from the local replica without waiting on the master, prioritizing latency over freshness.
3. It's not a bug in the system, it's a per-request PACELC knob — tunable stores let consistency level be chosen per operation, so two code paths disagreeing on `QUORUM` vs `ONE` silently produces different consistency guarantees on the same data.
4. No — it doesn't escape the trade-off, it shrinks it. TrueTime bounds clock uncertainty tightly enough that the "wait out uncertainty" commit cost is single-digit ms instead of a full cross-region RTT, so Spanner still pays a latency tax for consistency, just a much smaller bounded one.
5. PA/EC is rare because being available under partition (accepting writes on both sides) normally implies loose replication, which conflicts with demanding strong majority-ack consistency in normal times; MongoDB configured with `w:majority` reads/writes approximates it.
</details>

---
**Related:** [CAP Theorem](03-cap-theorem.md) · [Consistency Models](05-consistency-models.md) · [Latency, Throughput, Bandwidth](02-latency-throughput-bandwidth.md)

*Last reviewed: 2026-08*
