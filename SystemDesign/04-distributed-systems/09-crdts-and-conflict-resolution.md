# CRDTs and Conflict Resolution

> **TL;DR:** CRDTs are data structures whose merge operation is mathematically guaranteed (commutative, associative, idempotent) to converge to the same state on every replica, regardless of message order or duplication — enabling multi-master writes with zero coordination.

## Quick Reference

| Concept | Key Fact |
|---|---|
| CvRDT (state-based) | Ship full state, merge via least-upper-bound (join) over a semilattice |
| CmRDT (operation-based) | Ship ops, requires reliable causal-order delivery, no dupes |
| Convergence property | merge(merge(a,b),c) = merge(a,merge(b,c)); merge(a,b)=merge(b,a); merge(a,a)=a |
| G-Counter | Grow-only counter; per-replica increment vector, merge = elementwise max |
| PN-Counter | Two G-Counters (P, N); value = sum(P) − sum(N) |
| OR-Set | Add/remove set with unique tags per add; remove only kills seen tags |
| LWW-Register | Single value + timestamp; merge picks higher timestamp, ties by replica ID |
| Used in | Riak KV (bucket types), Redis Enterprise CRDBs, Automerge, Yjs, Figma (custom OT/CRDT hybrid) |
| vs Vector Clocks | VCs *detect* conflicts (siblings), don't resolve them; CRDTs *resolve* automatically |
| vs LWW | LWW is simplest CRDT but silently drops concurrent writes |

## What It Is

- **CRDT** = Conflict-free Replicated Data Type: a family of data structures (counters, sets, maps, sequences) designed for AP systems (per CAP) where any replica can accept writes independently.
- Core guarantee: no consensus, no locking, no central coordinator — replicas exchange state or ops asynchronously and *always* reach the same value once all updates are seen (strong eventual consistency, SEC).
- Formalized by Shapiro et al. (2011, INRIA) — the "CRDT paper" defines CvRDT and CmRDT as dual, provably equivalent models.

## Responsibilities

- Encode application intent (increment, add-to-set, insert-char) so merges are semantically meaningful, not just "pick a winner."
- Guarantee convergence without requiring synchronous replication, quorum reads/writes, or distributed locks.
- Preserve as much concurrent intent as possible (e.g., OR-Set keeps both concurrent adds) instead of silently discarding one writer's update.
- Tolerate network partitions, message reordering, and duplicate delivery — the algebra absorbs all three.

## How It Works

**State-based (CvRDT):**
1. Each replica mutates local state monotonically (state only moves "up" a join-semilattice).
2. Replica periodically gossips its *entire* state to peers.
3. Receiver computes `merge(local, received)` = the least upper bound (join) — usually elementwise max, set union, etc.
4. Idempotent + commutative + associative means any gossip topology, any order, any redelivery converges. Anti-entropy protocols (like Riak's) drive this gossip.

**Operation-based (CmRDT):**
1. Local op executes immediately; op is broadcast to replicas.
2. Requires a *causally-ordered, exactly-once (or at-least-once + dedup)* delivery channel — this is the hard part, offloaded to middleware (e.g., reliable causal broadcast).
3. Ops themselves must commute for concurrent, causally-unrelated operations (concurrent ops need not commute with causally dependent ones, only with each other).
4. Payload is smaller (deltas vs full state) but delivery guarantees are stronger and harder to build correctly.

**Delta-state CRDTs** (delta-CRDTs): hybrid — ship small state deltas instead of full state or ops, still idempotent/re-mergeable, used to cut bandwidth (e.g., Redis CRDBs, Akka Distributed Data).

## Types / Classifications

| Type | Structure | Merge Rule |
|---|---|---|
| **G-Counter** | vector of per-replica counts | elementwise max, sum for value |
| **PN-Counter** | two G-Counters (inc/dec) | merge each side independently |
| **G-Set** | grow-only set | union |
| **2P-Set** | add-set + tombstone-set | union both; remove wins forever (can't re-add) |
| **OR-Set** (Observed-Remove) | element → set of unique add-tags | union adds; remove strips only observed tags |
| **LWW-Register** | (value, timestamp, replica-id) | max timestamp wins, replica-id tiebreak |
| **MV-Register** | set of concurrent (value, version) pairs | keep all concurrent values (like Riak siblings), app resolves |
| **RGA / Yjs / Logoot** (sequence CRDTs) | ordered list with unique fractional/positional IDs | insert by ID ordering, tombstone deletes |
| **CRDT Maps** | key → nested CRDT (e.g., Riak Map) | recursive merge per key |

## Where It Fits

- **Multi-datacenter KV stores**: Riak KV (native CRDT bucket types: counters, sets, maps, registers), Redis Enterprise Active-Active (CRDBs — Conflict-free Replicated Databases) for cross-region writes.
- **Collaborative editors**: Automerge and Yjs implement sequence CRDTs for real-time text/JSON docs (Google Docs-style multi-cursor editing) without a central server arbitrating order.
- **Figma**: uses a custom multiplayer sync (property-based CRDT-like model over a central server) — not textbook CRDT but same convergence goals, with server as ordering authority for performance.
- **Mobile/offline-first apps**: local writes merge on reconnect (e.g., Ditto, PouchDB-adjacent tooling) without server round-trips.
- **Distributed counters/rate limiters**: G-Counter/PN-Counter pattern used in Akka Cluster's Distributed Data, Cassandra counter columns (loosely related).

## Common Patterns & Real-World Tools

- **Riak KV CRDT Map**: nested composition — a Map of Sets/Counters/Registers, each field merges independently; widely cited production CRDT deployment.
- **Redis Enterprise CRDB**: multi-region active-active; strings use LWW, hashes/sets/sorted-sets get custom CRDT semantics per data type.
- **Automerge / Yjs**: JSON-like document CRDTs; Yjs optimizes with a compact CRDT encoding (YATA algorithm) for large collaborative docs.
- **Delta-CRDT gossip + anti-entropy**: pair CRDTs with a gossip protocol (e.g., SWIM-based membership + periodic Merkle-tree diffing) to bound convergence time.
- **Hybrid: server-authoritative + CRDT merge** (Figma-style): central server sequences ops for low-latency UX but underlying model tolerates out-of-order application.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| No coordination/consensus needed for writes — low latency, partition-tolerant | Metadata overhead (tombstones, per-element tags) can bloat storage unboundedly |
| Automatic, deterministic convergence — provably correct | Limited data-type vocabulary; complex invariants (e.g., bank balance ≥ 0) are hard/impossible to express |
| Great UX for offline-first / multiplayer apps | Tombstones in OR-Set/2P-Set need garbage collection (causal stability tracking) or they grow forever |
| CmRDTs have smaller payloads than CvRDTs | CmRDTs need reliable causal delivery — reintroduces some infra complexity |
| Composable (Maps of CRDTs) | Semantic merges can surprise users (e.g., OR-Set "remove" that raced with a concurrent add loses the remove) |

## Real-World Scenarios

- **Multi-region shopping cart**: PN-Counter or OR-Set per cart item lets users add items from phone + laptop concurrently; both adds survive merge instead of one overwriting the other (classic Amazon Dynamo cart problem CRDTs were built to solve).
- **Collaborative doc editing**: Yjs/Automerge sequence CRDT lets two users type in the same paragraph offline; on reconnect both edits interleave correctly by position ID, no manual conflict resolution UI needed.
- **Active-active geo-replicated cache**: Redis CRDB across us-east/eu-west accepts writes in both regions during a transatlantic link outage; on reconnect, per-key CRDT semantics reconcile automatically instead of requiring a "designated primary."
- **Presence/like counters at scale**: G-Counter sharded per app-server instance avoids hot-key contention on a single counter row, merged periodically for the displayed total.

## Nuances & Gotchas

- **Unbounded tombstone growth**: OR-Set and 2P-Set never truly delete metadata; without causal stability pruning (all replicas ack'd receipt), storage grows forever — Riak had real incidents with multi-GB CRDT objects from long-lived sets with heavy churn.
- **LWW-Register data loss**: relies on synchronized clocks; clock skew across regions can silently discard a "later" real-world write because its timestamp was smaller — classic footgun in Redis/Cassandra LWW columns.
- **CmRDT delivery is the hard part**: "just send ops" sounds simple but requires causal broadcast — get this wrong (e.g., plain pub/sub with no dedup) and replicas diverge permanently, defeating the whole point.
- **CRDTs don't give you invariants**: can't build "unique username" or "account balance never negative" as a CRDT — those need coordination (consensus/locking) or app-level compensation; CRDTs solve *convergence*, not *business correctness*.
- **Concurrent semantics can be counter-intuitive**: OR-Set "add-wins" means a remove racing a concurrent add loses — element stays. Users expect "delete" to be final; CRDT semantics say otherwise unless explicitly modeled (e.g., causal context tracking).
- **State-based CRDTs cost bandwidth**: shipping full state on every gossip round doesn't scale for large documents — production systems (Redis CRDB, Yjs) use delta-states or op-based hybrids instead of naive CvRDT.
- **Merging isn't free CPU-wise**: large CRDT Maps/Sets with deep nesting mean O(n) or worse merges on every sync; Riak recommends bounding CRDT collection sizes for this reason.
- **Not a replacement for vector clocks conceptually**: vector clocks/version vectors are often used *inside* CRDTs (e.g., to tag OR-Set elements or detect causal concurrency) — the two techniques compose rather than compete.
- **Testing convergence is non-trivial**: must verify commutativity/associativity/idempotence hold for *all* op/merge orderings, including duplicates and out-of-order delivery — property-based testing (QuickCheck-style) is the standard approach, not example-based unit tests.
