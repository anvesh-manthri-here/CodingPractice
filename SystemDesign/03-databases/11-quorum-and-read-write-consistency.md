# Quorum and Read/Write Consistency

> **TL;DR:** In N-way replicated systems, requiring read set + write set to overlap (R+W>N) guarantees you always touch at least one node with the latest write — but overlap alone gives you "read your writes across replicas," not linearizability. Tuning N/W/R trades latency and availability for consistency.

## Quick Reference

| Term | Meaning |
|---|---|
| N | Replication factor — total copies of data |
| W | Nodes that must ack a write before it succeeds |
| R | Nodes queried on read; client picks freshest (highest timestamp/version) |
| Strict quorum | R+W>N — read set guaranteed to overlap write set |
| W=N, R=1 | Fastest reads, slowest/least available writes |
| W=1, R=N | Fastest writes, slowest/least available reads |
| QUORUM (Cassandra) | `⌊N/2⌋+1` — e.g., N=3 → W=R=2 |
| Sloppy quorum | W/R satisfied by any N reachable nodes, not fixed "home" set |
| Hinted handoff | Temp node stores write intended for a down node, replays later |
| DynamoDB defaults | Eventually-consistent read (R=1, cheap) vs strongly-consistent read (reads quorum, 2x cost) |

## What It Is

- A **quorum system** is a replication consistency mechanism: instead of requiring all N replicas to respond (unavailable if one is down) or just one (fast but stale), you require a *subset* sized so read and write subsets mathematically must intersect.
- Popularized by Dynamo (2007) paper; used by Cassandra, Riak, DynamoDB (internally), CockroachDB/etcd use quorums differently (Raft majority, see gotchas).
- Core guarantee: **R + W > N** ⇒ every read set shares ≥1 node with every write set ⇒ at least one replica returned by a read has seen the most recent acknowledged write.

## Responsibilities

- Balance **availability** (how many node failures tolerated) vs **consistency** (staleness risk) vs **latency** (how many nodes to wait for) — this is the practical, per-request expression of CAP/PACELC trade-offs.
- Let operators tune per-query, not just per-cluster: Cassandra lets each query specify consistency level independently.
- Provide partial fault tolerance: with N=3, W=2, cluster survives 1 node down without blocking writes.
- Enable conflict detection/resolution on read (compare versions/timestamps/vector clocks across the R replicas queried).

## How It Works

1. **Write path**: coordinator sends write to all N replicas (or their preference list), waits for W acks, returns success to client. Remaining N-W replicas update asynchronously.
2. **Read path**: coordinator queries R replicas, compares versions (timestamp, vector clock, or LWW), returns the latest, optionally triggers **read repair** to fix stale replicas in background.
3. **Overlap math**: if W=2, R=2, N=3 → any 2-of-3 write set and any 2-of-3 read set share ≥1 node (pigeonhole). If R+W≤N (e.g., W=1,R=1,N=3), no overlap guaranteed → stale reads possible.
4. Latency ≈ time for the **slowest of the W (or R) responding replicas**, not all N — tail latency amplification is real: more replicas queried = higher chance of hitting a slow one (p99 problem).

## Types / Classifications

| Level | Cassandra CL | Effect |
|---|---|---|
| ONE | W=1 or R=1 | Lowest latency, weakest consistency, tolerates N-1 failures |
| QUORUM | ⌊N/2⌋+1 | Balanced; tolerates ⌊N/2⌋ failures while still meeting quorum |
| ALL | W=N or R=N | Strongest overlap guarantee, zero fault tolerance (any node down blocks) |
| LOCAL_QUORUM | Majority within local DC | Avoids cross-DC latency, common multi-region default |
| EACH_QUORUM | Majority in every DC | Strong multi-DC consistency, high latency |

- **Strict quorum**: fixed replica set must respond; if too many are down, write/read fails (favors consistency, per CAP).
- **Sloppy quorum**: accept W acks from *any* W reachable nodes (not necessarily the "correct" owners) to keep availability during partitions; requires hinted handoff to reconcile later (favors availability).

## Where It Fits

```
Client
  │
  ▼
Coordinator node ── write to N replicas, wait for W acks ──► [R1] [R2] [R3]
  │                                                             (async to rest)
  ▼
Read: query R replicas, merge/reconcile, return newest, read-repair stale ones
```
- Sits inside the replication layer of a distributed KV/wide-column store (Cassandra, Riak, ScyllaDB, DynamoDB, Voldemort).
- Distinct from **consensus-based replication** (Raft/Paxos majority in etcd, CockroachDB, Spanner) — those use quorums too, but couple them with a leader/log to get linearizability; Dynamo-style quorums don't.

## Common Patterns & Real-World Tools

- **Cassandra**: per-query CL tuning; `QUORUM` write + `QUORUM` read is the standard "strong-ish" default; `LOCAL_QUORUM` for multi-DC to avoid WAN round trips.
- **DynamoDB**: `ConsistentRead=true` forces quorum read (majority of storage nodes) at 2x read capacity cost vs eventually consistent default.
- **Riak**: exposes N/R/W/DW (durable writes) as tunable bucket properties, classic Dynamo-paper implementation.
- **Hinted handoff**: coordinator stores a "hint" (write + target node ID) on a substitute node when the real owner is down; replays it once the owner rejoins — bounds staleness window but hints can pile up/get dropped if owner stays down too long.
- **Read repair**: on every quorum read, mismatched replicas get patched with the latest value (synchronous read-repair blocks reply, async doesn't).
- **Anti-entropy / Merkle trees**: background full-replica reconciliation (Cassandra's `nodetool repair`) — the backstop for what read repair and hinted handoff miss.

## Pros & Cons / Trade-offs

| Choice | Pro | Con |
|---|---|---|
| Higher W | Fewer lost writes on failure | Slower writes, less available during partitions |
| Higher R | Fresher reads | Slower reads |
| W=R=QUORUM | Balances read/write latency, tolerates minority failure | Still not linearizable (see below) |
| Sloppy quorum | Keeps accepting writes during partition | Can accept conflicting writes on both sides → needs reconciliation (vector clocks, LWW, CRDTs) |
| ONE/ONE | Max throughput, max availability | Read-your-writes not guaranteed, lost update risk |

## Real-World Scenarios

- **Cassandra N=3, W=1, R=1 ("ONE")**: e-commerce click-tracking — losing/staling a few events is fine, want max write throughput.
- **N=3, QUORUM/QUORUM**: user profile store — need decent consistency without full ALL-node latency tax; survives 1 node outage.
- **DynamoDB shopping cart (original Dynamo use case)**: sloppy quorum + hinted handoff so "add to cart" never fails during a partition; conflicting cart versions merged (union of items) client-side.
- **Multi-region Cassandra with LOCAL_QUORUM**: avoids cross-ocean latency per request; EACH_QUORUM reserved for rare must-be-globally-consistent writes (e.g., account creation dedup).
- **Bank balance with ALL/ALL**: forces strongest overlap when correctness matters more than availability — but one dead replica halts all writes.

## Nuances & Gotchas

- **R+W>N ≠ linearizability.** Quorum overlap guarantees a read *can* see the latest write, not that it *will* deterministically, nor that reads are globally ordered — concurrent reads can still return different "latest" values if writes race and version comparison (LWW/clock skew) picks wrong. See `consistency-models.md` — this is the classic "Dynamo-style quorums give tunable/eventual consistency, not strong consistency" nuance.
- **Clock skew breaks LWW**: if replicas use wall-clock timestamps for conflict resolution and clocks drift, a "later" write can lose to an "earlier" one with a bigger timestamp — Cassandra is famous for this footgun.
- **Sloppy quorum + hinted handoff can silently violate R+W>N**: writes accepted by non-owner nodes during a partition mean the "real" replica set never got W acks, so a strict-quorum read from the correct owners may miss the write entirely until anti-entropy repairs it.
- **Read-during-resharding / topology change**: replica set membership changes (node add/remove, vnode reassignment) can transiently break the overlap guarantee if read and write happened against different "views" of the ring.
- **QUORUM math changes with RF**: `⌊N/2⌋+1` — for N=2, QUORUM=2 (=ALL), no fault tolerance benefit; always use odd N (3, 5) for real quorum benefit.
- **Tail latency**: querying R or W nodes means you're exposed to the slowest of that subset — going from R=1 to R=3 can 3x your p99 due to straggler nodes, even though median barely moves.
- **Multi-DC LOCAL_QUORUM is not globally consistent**: a LOCAL_QUORUM write in DC1 can be invisible to a LOCAL_QUORUM read in DC2 until cross-DC replication catches up — teams often assume it's "quorum" therefore "safe" and get burned.
- **This is not consensus**: no single writer/leader, no total order log — for invariants requiring strict ordering (unique constraints, leader election, distributed locks), use Raft/Paxos-based systems (etcd, ZooKeeper, Spanner) instead of Dynamo-style quorums.
- **Downed nodes reduce effective fault tolerance silently**: if 1 of 3 nodes is down and you're running QUORUM (needs 2), you have zero more slack — next failure causes `UnavailableException`; monitor replica health, not just quorum math on paper.
