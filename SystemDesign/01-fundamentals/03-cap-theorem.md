# The CAP Theorem

> **TL;DR:** During a network partition, a distributed system must choose between staying linearizably Consistent or staying Available — you don't "pick 2 of 3" in normal operation, you only face a real trade-off once P actually happens.

## Quick Reference

| Term | Precise meaning | Formalized by |
|---|---|---|
| **C**onsistency | Linearizability — every read returns the most recent write, as if there were one copy | Gilbert & Lynch, 2002 |
| **A**vailability | Every request to a non-failed node gets a (non-error) response, in bounded time | Gilbert & Lynch, 2002 |
| **P**artition tolerance | System continues operating despite arbitrary message loss/delay between nodes | Gilbert & Lynch, 2002 |
| Theorem statement | Asynchronous network: cannot guarantee C and A simultaneously **when P occurs** | Formal proof, not folklore |
| Practical read | P is not optional on a real network — so it's really C vs A during partitions | — |
| Successor model | PACELC: else (no partition), trade Latency vs Consistency too | Daniel Abadi, 2010 |

## What It Is

- A **theorem**, not a design philosophy: Seth Gilbert & Nancy Lynch formally proved it in 2002, building on Eric Brewer's 2000 conjecture.
- States: in an asynchronous network model (no bound on message delay), no algorithm can simultaneously guarantee linearizable Consistency and total Availability once a network Partition occurs.
- It's a statement about the **impossibility of a specific guarantee combo under a specific fault**, not a recipe telling you which two to "choose" for your architecture.
- Scope is narrow: it says nothing about latency, throughput, durability, or behavior absent a partition — that's where PACELC picks up.

## Responsibilities

CAP itself doesn't "do" anything operationally — but understanding it correctly forces you to answer three design questions for any distributed datastore:

- What happens to a read/write request on the minority side of a partition — block, error, or serve stale data?
- What consistency model does the system actually offer end-to-end (linearizable, sequential, causal, eventual)?
- What is the partition detection/recovery mechanism (timeouts, heartbeats, quorum re-formation, anti-entropy/read-repair)?

## How It Works

1. **Model**: nodes communicate only via an unreliable async network; a partition = some messages between two node groups are dropped or arbitrarily delayed.
2. **Proof sketch (Gilbert-Lynch)**: assume a system that's both C and A. Partition the network into G1 and G2. Client writes value to a node in G1; another client reads from a node in G2. Because G1 cannot communicate with G2, G2 can either (a) return the stale value — violating linearizability — or (b) block/error waiting for sync — violating availability. Contradiction ⇒ can't have both under P.
3. **Key subtlety**: the theorem triggers "only during P." Absent a partition, a system can be perfectly C and A simultaneously — that's the normal operating mode of almost every DB.
4. **"Choosing" P**: you don't get to opt out of P — partitions are a physical-network fact (NIC failures, switch issues, GC pauses that look like partitions, cross-AZ/region link loss). So the only real choice being exercised at design time is: when P happens, do you sacrifice C or sacrifice A?

```
        no partition: C and A both fine
              |
      ── partition occurs ──
       /                    \
   choose C (CP)        choose A (AP)
   reject/block          serve possibly
   minority requests     stale reads/writes
```

## Types / Classifications

### CP systems (sacrifice availability under partition)
- Minority-side nodes refuse writes/reads (or return errors) rather than risk inconsistency.
- Examples: **ZooKeeper**, **etcd**, **Consul** (all use Raft/Paxos-style quorum — need majority to proceed), **HBase** (region servers unavailable without master/ZK quorum), **MongoDB** (single-primary, majority write concern — secondaries reject writes), **Google Spanner** (uses TrueTime + Paxos; CP but with extremely tight availability windows).

### AP systems (sacrifice strict consistency under partition)
- Every replica keeps answering; conflicts reconciled later (eventual consistency, vector clocks, CRDTs, last-write-wins).
- Examples: **Cassandra**, **DynamoDB** (classic, tunable), **Riak**, **CouchDB**, **Voldemort** — descendants of Amazon's original Dynamo paper.

### The "CA" myth
- CA (consistent + available, but not partition tolerant) only makes sense for a **single-node system** or a system running on a network that literally cannot partition (rare — e.g., some traditional RDBMS on one box). Once you have ≥2 nodes on a real network, P is not optional, so "CA distributed system" is a contradiction in practice.

### Tunable / hybrid
- Cassandra/DynamoDB let you choose consistency level **per request** (e.g., QUORUM, ONE, ALL) — same cluster can behave CP-ish or AP-ish depending on call.
- MongoDB: `majority` write/read concern pushes it toward CP; `local`/`available` reads push toward AP.

## Where It Fits

- Sits beneath every distributed **data layer** decision: primary DB choice, cache invalidation strategy, multi-region replication topology, service-mesh/service-discovery store (etcd/Consul are CP by design — that's *why* Kubernetes control plane can stall during network splits).
- Directly informs **replication strategy** (sync quorum vs async), **leader election** (Raft/Paxos require majority — inherently CP), and **client-side conflict resolution** (needed only in AP systems).
- Precedes **PACELC** in the decision chain: CAP governs partition behavior; PACELC governs the *far more common* non-partition case (latency vs consistency trade-off, e.g., sync replication cost even when the network is healthy).

## Common Patterns & Real-World Tools

| Pattern | Mechanism | Tools |
|---|---|---|
| Quorum consensus | Majority read/write (R+W>N) to guarantee overlap | Cassandra, DynamoDB, Riak |
| Leader-based consensus | Raft/Paxos elect single writer; minority can't commit | etcd, Consul, ZooKeeper, CockroachDB |
| Sloppy quorum + hinted handoff | Accept writes even if some replicas unreachable; replay later | Dynamo, Cassandra, Riak |
| CRDTs | Data structures that merge conflict-free regardless of order | Riak, Redis (some modules), Automerge |
| Vector clocks / LWW | Track causality or pick "latest" write to resolve conflicts | Dynamo-style stores |
| Read repair / anti-entropy | Background sync fixes stale replicas post-partition | Cassandra, Riak |

## Pros & Cons / Trade-offs

| Choice | Pros | Cons |
|---|---|---|
| CP | No stale reads; simpler app-level reasoning; safe for financial/inventory data | Minority partition = downtime for those nodes; higher write latency (needs quorum ack) |
| AP | Always accepts reads/writes; low latency; great UX under network stress | App must handle conflicts/staleness; harder correctness reasoning; possible lost updates |
| Tunable (Cassandra-style) | Flexibility per-query | Operational complexity; easy to misconfigure consistency level and silently get AP when you meant CP |

## Real-World Scenarios

- **Bank ledger / payments**: CP required — better to reject a transaction than double-spend or show wrong balance. Spanner, CockroachDB, traditional RDBMS with sync replication fit here.
- **Shopping cart / "add to cart"**: classic AP use case from the original Dynamo paper — better to accept the write and merge later than block the user.
- **Kubernetes control plane on etcd**: during a network partition, minority-side API servers/etcd nodes stop serving writes (CP) — this is why a split cluster can appear "stuck" rather than silently diverging.
- **DNS**: intentionally AP-ish (TTL-based eventual consistency) — total availability valued far above perfect freshness.
- **Multi-region session store**: teams often pick AP (DynamoDB global tables, Cassandra multi-DC) and accept eventual consistency to avoid cross-region write latency, then bolt on idempotency/conflict resolution at the app layer.

## Nuances & Gotchas

- **"Pick 2 of 3" is the most repeated wrong framing.** You can't "pick" CA in a real distributed system — P isn't optional, so in practice every system is really choosing CP or AP, and only *during* a partition. Interviewers who ask "so which 2 do you pick?" expecting a clean triangle answer are testing whether you catch this.
- **CAP says nothing about latency.** A system can be "available" per Gilbert-Lynch (returns *something* in bounded time) yet be so slow under sync quorum that it's operationally useless — this gap is exactly what **PACELC** (Abadi) fixes: **P**artition → **A**vailability vs **C**onsistency, **E**lse → **L**atency vs **C**onsistency. Always point forward to PACELC when discussing CAP in a design review — it's the more actionable model.
- **Partitions aren't binary "network cable cut" events.** In production they show up as GC pauses that make a node miss heartbeats, asymmetric partitions (A can reach B but not vice versa), packet loss thresholds, cross-AZ latency spikes, or overloaded NICs — "partition" is really "any communication failure that looks like one to the failure detector."
- **Most systems are CP or AP only for a specific operation, not globally.** MongoDB is CP for majority-acknowledged writes but can serve stale reads from secondaries. Calling a whole product "a CP database" without specifying the read/write concern is imprecise and will get called out at staff level.
- **Consistency in CAP ≠ consistency in ACID.** CAP's C is linearizability (a real-time recency guarantee); ACID's C is about invariant preservation (constraints, foreign keys). Conflating them is a common interview trap.
- **You can get availability without partition tolerance in theory, but not on any real multi-DC deployment** — so "CA" databases (single-node Postgres, etc.) stop being CA the moment you add a replica across a network boundary.
- **Split-brain is the CP failure mode to fear**: if quorum logic is misconfigured (e.g., even node count, misjudged majority), both sides of a partition can believe they're the majority and accept conflicting writes — defeating the entire point of choosing CP. Always verify quorum math (N, majority = ⌊N/2⌋+1) explicitly.
- **AP "eventual consistency" has no bound by default.** Without a convergence mechanism (anti-entropy, read repair, gossip) staleness can persist indefinitely under sustained partition — "eventual" is doing a lot of unstated work; production systems need an explicit convergence SLA.
- **Client libraries can silently downgrade your guarantee.** E.g., a driver defaulting to `ONE` consistency on Cassandra turns a "CP-configured" cluster into effectively AP behavior for that call path — always audit the actual per-call consistency level, not just the cluster's theoretical design.

## Self-Check

1. A candidate says "our system is CA, not CP or AP." Why is that claim wrong for any real multi-node deployment, and when (if ever) is "CA" a valid label?
2. Per Gilbert-Lynch, what exactly must an algorithm guarantee to count as "Available," and what does the theorem *not* say about that guarantee?
3. MongoDB is often called "a CP database." Why is that framing imprecise at staff level?
4. What causes split-brain in a CP system, and what's the concrete guardrail against it?
5. CAP's "C" and ACID's "C" are both called "Consistency." How do they differ, and why does conflating them matter in an interview?

<details><summary>Answers</summary>

1. CA requires P to be optional, but on any real network with ≥2 nodes, partitions are a physical-network fact — so "CA distributed system" is a contradiction. It's only valid for a single-node system (or a non-partitionable network), which stops being CA the instant a networked replica is added.
2. Availability means every request to a non-failed node gets a non-error response in bounded time — nothing about how fast. CAP says nothing about latency, so a technically "available" system can still be too slow to be useful; that gap is what PACELC addresses.
3. MongoDB is only CP for majority-acknowledged writes — it can still serve stale reads from secondaries. Calling the whole product "CP" without specifying the read/write concern glosses over per-operation behavior, which is the level staff interviews probe.
4. Split-brain happens when quorum logic is misconfigured (e.g., even node count or misjudged majority) so both sides of a partition believe they hold majority and accept conflicting writes. The guardrail is explicitly verifying quorum math: majority = ⌊N/2⌋+1.
5. CAP's C is linearizability — a real-time recency guarantee on reads/writes. ACID's C is invariant preservation — constraints and foreign keys staying valid. Conflating them is a classic interview trap because a system can satisfy one and violate the other.
</details>

---
**Related:** [PACELC Theorem](04-pacelc-theorem.md) · [Consistency Models](05-consistency-models.md) · [Availability and the Nines](06-availability-and-nines.md)

*Last reviewed: 2026-08*
