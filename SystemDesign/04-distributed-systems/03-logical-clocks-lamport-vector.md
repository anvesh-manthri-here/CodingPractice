# Logical Clocks — Lamport and Vector Clocks

> **TL;DR:** Wall clocks can't reliably order events across machines because of skew and network delay; logical clocks (Lamport, vector, HLC) encode *causality* instead of time, letting distributed systems detect ordering and conflicts without a global clock.

## Quick Reference

| Mechanism | Encodes | Detects concurrency? | Size | Used by |
|---|---|---|---|---|
| Wall clock (NTP) | Physical time | No (skew, no total order) | 8 bytes | Logging, TTLs |
| Lamport timestamp | Partial causal order | No (only a total order via tie-break) | 8 bytes (single int) | Chubby, some log systems |
| Vector clock | Full causal order per node | Yes (concurrent vs happens-before) | O(N) nodes | Dynamo, Riak, Voldemort |
| Version vector (dotted) | Per-replica version, pruned | Yes, with GC of stale entries | O(active writers) | Riak 2.x, Cassandra (legacy) |
| Hybrid Logical Clock (HLC) | Physical time + logical counter | Approximate (bounded), gives causality + near wall-clock | 8–16 bytes | CockroachDB, MongoDB (cluster time), YugabyteDB |

## What It Is

- **Logical clock**: a counter/structure assigned to events that preserves *causal order* (if A caused B, A's timestamp < B's) without relying on synchronized physical clocks.
- Contrast with **physical clocks**: NTP typically bounds skew to 1–100ms in datacenters (GPS/atomic refs like Google TrueTime get to ~7ms uncertainty), but skew is never zero and can spike on VM stalls, leap seconds, or NTP daemon failures.
- Core problem: there is no global "now" in a distributed system — Lamport's 1978 paper "Time, Clocks, and the Ordering of Events" formalized this.

## Responsibilities

- Establish **happens-before** (→) relation: causally related events get ordered; unrelated ones don't need to be.
- Enable **conflict detection** in multi-master/leaderless systems (concurrent writes to same key).
- Provide **consistent snapshots** / ordering for distributed transactions (e.g., CockroachDB's HLC-stamped MVCC).
- Avoid the cost of full consensus/locking just to get "did A happen before B."

## How It Works

### Lamport Clocks
- Each process keeps integer counter `C`.
- Rule 1: before executing an event, `C = C + 1`.
- Rule 2 (send): attach `C` to outgoing message.
- Rule 3 (receive): `C = max(C_local, C_msg) + 1`.
- Guarantees: if `A → B` (happens-before), then `C(A) < C(B)`. **Converse is false** — `C(A) < C(B)` does not imply `A → B` (could be concurrent, coincidentally ordered).
- Total order: break ties with process ID → gives a total order used e.g. for distributed mutual exclusion (Lamport's bakery-style algorithm).

### Vector Clocks
- Each process `i` keeps a vector `V[1..N]`, one counter per known process/replica.
- On local event: `V[i] += 1`.
- On send: attach full vector.
- On receive from j: `V[k] = max(V[k], V_msg[k])` for all k, then `V[i] += 1`.
- Comparison:
  - `V(A) ≤ V(B)` element-wise and `V(A) ≠ V(B)` → `A → B` (causal).
  - Neither `V(A) ≤ V(B)` nor `V(B) ≤ V(A)` → **concurrent** (`A || B`) — this is the payoff Lamport clocks can't give you.

```
Node1: [1,0,0] --write--> [2,0,0] --replicate--> Node2 merges: [2,1,0]
Node3: [0,0,1] --write--> [0,0,2]   (concurrent with Node1's writes: neither vector dominates)
```

### Hybrid Logical Clocks (HLC)
- Combines physical time (`pt`, from NTP) with a logical counter (`l`) for tie-breaking within the same physical tick.
- On event: `l.pt = max(pt_now, l.pt)`; if `l.pt` unchanged from last, bump logical counter, else reset to 0.
- On receive: merge similarly with sender's HLC, taking max physical component.
- Result: timestamps stay close to wall-clock time (useful for humans/debugging/TTLs) *and* preserve happens-before like Lamport clocks.
- See `consistency-models` notes for how HLC underpins **bounded staleness** and **causal consistency** guarantees (e.g., CockroachDB's `hlc.Clock`, MongoDB's cluster time for causal consistency sessions).

## Types / Classifications

| Type | Causality captured | Conflict detection | Overhead |
|---|---|---|---|
| Scalar physical (NTP time) | None reliable | No | Low, but wrong |
| Lamport scalar | Partial order only | No | O(1) |
| Vector clock | Full partial order | Yes | O(N) per write, grows with replica churn |
| Dotted version vector | Full, GC'd | Yes, avoids sibling explosion | O(active writers), better GC than plain VC |
| Interval Tree Clocks | Full, dynamic membership | Yes | Variable, designed for node join/leave |
| HLC | Approx causal + physical | Bounded (needs epsilon bound like TrueTime for strict) | O(1), 8–16 bytes |

## Where It Fits

- **Leaderless replication (Dynamo-style)**: vector clocks (or dotted version vectors) attached to each object version to detect sibling/conflicting writes on read-repair.
- **Distributed tracing**: Lamport-style counters order spans within a trace when clock skew would misorder them.
- **MVCC transaction systems**: HLC timestamps used as commit/read timestamps (CockroachDB, YugabyteDB) — replaces pure wall clock while staying human-readable.
- **CRDTs**: often piggyback on vector clocks/version vectors to know which updates to merge vs which one "wins."
- **Distributed logs (Kafka, etc.)**: mostly sidestep this by using a single ordered partition (physical append order) rather than logical clocks — logical clocks matter more once you have multiple writers.

## Common Patterns & Real-World Tools

- **Amazon Dynamo (2007 paper)**: vector clocks per key; on divergent versions, both siblings returned to client (`get` may return multiple values), client/app resolves conflict — the canonical case study.
- **Riak**: originally plain vector clocks, migrated to **dotted version vectors** to fix vector clock growth/pruning issues (clocks grew unbounded with client-generated actor IDs).
- **Voldemort (LinkedIn)**: Dynamo-style vector clocks for versioning.
- **CockroachDB**: HLC for all MVCC timestamps; combined with uncertainty intervals to give serializable isolation without atomic clocks.
- **Google Spanner**: not a logical clock — uses **TrueTime** (physical, hardware-assisted, bounded uncertainty via GPS+atomic clocks) to get external consistency; different tool, same problem space, worth contrasting.
- **MongoDB**: hybrid logical "cluster time" for causal consistency sessions across replica sets.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Wall clock only | Simple, human-readable, cheap | Skew causes silent misordering; unsafe for correctness-critical ordering |
| Lamport | Tiny (1 int), simple total order | Can't detect concurrency — false causality inferred from `<` |
| Vector clock | Exact concurrency detection | Size grows with number of replicas/actors; needs pruning/GC or unbounded growth |
| HLC | Near wall-clock + causality, compact | Still needs NTP-bounded skew for tight uncertainty bounds; not a substitute for atomic clocks in strict external consistency |
| TrueTime-style (physical, bounded) | Strong external consistency | Requires specialized hardware (GPS/atomic clocks), high infra cost, Google/cloud-vendor-only in practice |

## Real-World Scenarios

- **Shopping cart conflict (Dynamo)**: two devices add items offline; vector clocks show writes are concurrent (neither dominates) → app merges cart items instead of silently dropping one write.
- **Debugging out-of-order logs**: server wall clocks drift by 200ms; naive time-sort misorders causally related log lines across services — Lamport/HLC timestamps fix ordering for trace reconstruction (Jaeger/Zipkin span ordering).
- **Multi-region write with vector clock bloat**: Riak cluster with many ephemeral client actor IDs saw vector clocks grow to KBs per object, blowing up storage/network — root-caused vector clock growth, fixed by switching to dotted version vectors with actor epochs.
- **CockroachDB clock skew alarm**: node's NTP drifts beyond configured `--max-offset` (default 500ms) → node self-terminates rather than risk serializability violation from HLC uncertainty exceeding bound.

## Nuances & Gotchas

- **Lamport clock false ordering**: `C(A) < C(B)` is necessary but not sufficient for `A → B`; treating it as causal is a classic bug (e.g., using Lamport timestamps alone to decide "last write wins" silently discards concurrent, non-conflicting writes).
- **Vector clock unbounded growth**: if every client/device gets its own vector entry (rather than a fixed set of server replicas), the vector never stops growing — Riak hit this in production; fix is server-side vector clocks (Dynamo does this) or dotted version vectors with GC of dead actors.
- **Sibling explosion**: leaderless stores returning multiple concurrent versions can pile up if client never resolves them (crashed client, never re-writes) — needs a reconciliation/GC policy (Riak's `allow_mult`, tombstone/vclock pruning after N versions or TTL).
- **Clock merge on every message**: vector/Lamport clocks must be updated on *every* send/receive including internal RPCs/heartbeats — missing an update path silently breaks causal guarantees; easy to introduce in a service mesh sidecar that doesn't propagate the clock.
- **HLC still bounded by NTP skew**: HLC's physical component inherits whatever skew NTP has; if skew exceeds your uncertainty window assumption, causality can still be violated for near-simultaneous cross-node events — CockroachDB mitigates by refusing to operate (`max-offset` panic) rather than risk it.
- **Comparing vector clocks is O(N)**: at high replica/actor counts this becomes a real CPU/network cost on every read repair — bound the vector size (fixed replica count, not per-client).
- **Time doesn't imply causality even with perfect NTP**: two independent writes with identical wall-clock timestamp are still concurrent; only a logical/vector/HLC scheme (or explicit dependency tracking) can tell you that, wall time alone never can.
- **Leap seconds / NTP smear**: physical-time components (wall clock, HLC's `pt`) can jump or repeat during leap-second smearing — systems assuming monotonicity (like `time.Now()` diffs) can misbehave; use monotonic clock sources (`CLOCK_MONOTONIC`) for duration math, not for the logical/HLC timestamp itself.
