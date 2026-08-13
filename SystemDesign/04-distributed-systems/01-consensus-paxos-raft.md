# Consensus — Paxos and Raft

> **TL;DR:** Consensus lets a cluster of unreliable nodes agree on a single value (or an ordered log of values) despite crashes and network partitions. Paxos proves it's possible and is provably correct but famously hard to implement; Raft achieves the same guarantees with an explicit leader and a design optimized for human understandability.

## Quick Reference

| Aspect | Paxos | Raft |
|---|---|---|
| Roles | Proposer, Acceptor, Learner | Leader, Follower, Candidate |
| Leader | Implicit / per-round (Multi-Paxos adds stable leader) | Explicit, elected, required |
| Quorum size | Majority (N/2 + 1) | Majority (N/2 + 1) |
| Fault tolerance | Tolerates ⌊(N-1)/2⌋ failures | Tolerates ⌊(N-1)/2⌋ failures |
| Log replication | Not in base Paxos (Multi-Paxos bolts it on) | Built-in, core to the design |
| Understandability | Notoriously hard (Lamport's own paper needed a "Paxos Made Simple" follow-up) | Designed thesis-first for teachability (Ongaro & Ousterhout, 2014) |
| Real-world users | Chubby (Google), early Spanner, ZAB (ZooKeeper, Paxos-inspired) | etcd, CockroachDB, Kafka KRaft, TiKV, Consul |
| Typical latency | 2 RTT per value (Basic Paxos) / 1 RTT steady-state (Multi-Paxos) | 1 RTT steady-state (leader batches + pipelines) |

## What It Is

- **Consensus problem**: get N nodes to agree on one value from a set of proposals, such that the decision is final, and all correct nodes eventually learn it — even if some nodes crash or messages are delayed/lost (not Byzantine/malicious, by default).
- Formal guarantees required: **Agreement** (no two nodes decide differently), **Validity** (decided value was actually proposed), **Termination** (eventually a value is decided, under sufficient synchrony).
- FLP impossibility (1985): pure asynchronous consensus with even one faulty node cannot guarantee termination deterministically — Paxos/Raft sidestep this via timeouts and randomized election backoff, trading strict async guarantees for practical liveness.

## Responsibilities

- Guarantee **safety** always (never disagree), even during partitions — safety must never be violated regardless of timing.
- Guarantee **liveness** under partial synchrony (a majority can communicate) — progress resumes once network stabilizes.
- Provide a **replicated log** abstraction: an ordered, durable sequence of commands applied identically on every replica (state machine replication).
- Survive minority failures without data loss or split-brain: at most one leader/value per term can be committed.

## How It Works

### Basic Paxos (single value)
1. **Prepare phase**: Proposer picks a proposal number *n*, sends `Prepare(n)` to a majority of Acceptors.
2. Acceptor promises not to accept any proposal < *n*, replies with the highest-numbered proposal it has already accepted (if any).
3. **Accept phase**: If a majority promises, Proposer sends `Accept(n, v)` — where *v* is either its own value or the highest-numbered value returned by acceptors (safety-critical rule: must adopt already-accepted values).
4. If a majority accepts, the value is **chosen**; Learners are notified.
- **Multi-Paxos** adds a stable leader that skips Prepare on every round (does it once), turning it into ~1 RTT per log entry — this is what real systems (Chubby) actually run.

### Raft
1. **Leader election**: nodes start as Followers with randomized election timeout (~150–300ms typical). On timeout, becomes Candidate, increments **term**, votes for self, requests votes (RequestVote RPC).
2. Wins with majority votes → becomes Leader for that term; sends periodic **heartbeats** (AppendEntries with no entries) to prevent re-election.
3. **Log replication**: client writes go to Leader → appended to Leader's log → replicated via AppendEntries RPC to Followers → once a majority ack, entry is **committed** → Leader applies to state machine and responds to client.
4. **Safety**: election restriction — a candidate can only win if its log is at least as up-to-date as a majority (compares last log term/index) — guarantees committed entries survive leader changes.
5. **Term** acts as a logical clock; stale leaders step down on seeing higher term.

```
Client -> Leader.append(entry)
Leader -> Followers: AppendEntries(entry)
Followers -> Leader: ack
Leader: on majority ack -> commit -> apply -> respond to client
```

## Types / Classifications

- **Crash Fault Tolerant (CFT)**: Paxos, Raft, ZAB, Viewstamped Replication — assume nodes fail-stop, not malicious. Majority quorum suffices.
- **Byzantine Fault Tolerant (BFT)**: PBFT, Tendermint, HotStuff — assume malicious/arbitrary behavior, need 3f+1 nodes to tolerate f faults. Used in blockchains, not typical OLTP databases.
- **Single-value vs. log-based**: Basic Paxos decides one value; Multi-Paxos/Raft/ZAB decide an ordered sequence (log) — what real systems need.
- **Leaderless vs. leader-based**: Basic Paxos is leaderless per-round (any proposer can compete); Raft mandates a single leader for all writes, simplifying reasoning at the cost of a failover pause.
- **EPaxos / Generalized Paxos**: leaderless, geo-distributed variants avoiding a single leader bottleneck — used in some low-latency multi-region designs (rare in production compared to Raft).

## Where It Fits

- **Coordination services**: etcd (Raft) and ZooKeeper (ZAB, a Paxos-like protocol tuned for primary-order broadcast) provide distributed locks, leader election, config/metadata storage for other systems (Kubernetes uses etcd as its source of truth).
- **Distributed SQL / NewSQL**: CockroachDB and TiKV run a **Raft group per data range/shard** — each range independently replicated and consensus-committed, enabling horizontal scale with per-shard fault tolerance.
- **Log/streaming systems**: Kafka historically used ZooKeeper for controller election/metadata; **KRaft** (KIP-500, GA since Kafka 3.x/4.0) replaces ZooKeeper with a built-in Raft-based metadata quorum — removes an external dependency.
- **Google Spanner/Chubby**: Chubby (lock service) built on Multi-Paxos; Spanner uses Paxos per shard for replication, layered with TrueTime for global ordering.
- Sits below the **replication layer** of a distributed DB — application/SQL layer talks to a leader; consensus layer ensures the leader's log is durable and agreed upon.

## Common Patterns & Real-World Tools

| Pattern | Tool Example |
|---|---|
| Leader-per-shard Raft group | CockroachDB, TiKV, YugabyteDB |
| Cluster metadata quorum | etcd (K8s), Kafka KRaft controller quorum |
| Primary-order atomic broadcast | ZooKeeper ZAB |
| Distributed lock / config store built on consensus | Consul (Raft), etcd |
| Multi-Paxos with pipelined leader | Chubby, Google Megastore |
| State machine replication library | Hashicorp Raft (`raft` Go lib), etcd's `raft` package (reused by TiKV, CockroachDB's own fork, M3DB) |

## Pros & Cons / Trade-offs

**Paxos**
- (+) Formally minimal and provably correct; the theoretical baseline everything else is measured against.
- (+) Basic Paxos is leaderless — no single point of coordination bottleneck for role of proposer.
- (−) Notoriously hard to implement correctly from the paper alone; real systems (Chubby team) reported needing significant engineering beyond the spec.
- (−) No native log/reconfiguration story — Multi-Paxos and membership changes are "engineering," not in the base algorithm.

**Raft**
- (+) Explicit leader simplifies reasoning, debugging, and log matching (strong leader property: log only flows leader → follower).
- (+) Well-specified membership changes (joint consensus / single-server change) and log compaction (snapshotting) as first-class parts of the protocol.
- (+) Wide battle-tested library ecosystem (etcd/raft, hashicorp/raft) — most teams don't hand-roll it.
- (−) All writes serialize through one leader — throughput ceiling, and leader becomes a hot spot for high-write workloads (mitigated by sharding into multiple Raft groups).
- (−) Leader failover causes a availability blip (missed heartbeat → election timeout → new election), typically hundreds of ms to a few seconds.

## Real-World Scenarios

- **Kubernetes control plane outage**: etcd loses quorum (e.g., 2 of 5 nodes down is fine, 3 of 5 down is not) → API server writes fail cluster-wide even though pods keep running — classic "consensus layer down ≠ data plane down" split.
- **Kafka KRaft migration**: replacing ZooKeeper removes an external Paxos-like dependency, collapsing controller failover from tens of seconds (ZK-based) to sub-second in many deployments, and simplifying operational surface (one system instead of two).
- **CockroachDB range split**: a hot range gets split into two Raft groups automatically; each half needs its own leader election and quorum before serving writes — brief latency spike during rebalancing.
- **Multi-region Raft group**: placing Raft replicas across regions (e.g., us-east, us-west, eu) adds ~70-150ms RTT to every commit since a majority ack requires the farthest follower — a common reason to keep quorums region-local and use async replication cross-region instead.

## Nuances & Gotchas

- **Quorum overlap is the whole trick**: any two majorities of N nodes must intersect in at least one node — this is why N is usually odd (2f+1) and why 4 nodes give no better fault tolerance than 3 (both tolerate f=1) while costing more.
- **Committed ≠ applied**: an entry can be committed (majority replicated) before the leader crashes and before it's applied to the state machine on followers — new leader must replay/catch up; clients relying on "commit ack" need to know applied state may lag momentarily.
- **Split-brain from stale leader**: without proper term/fencing checks, a partitioned old leader can keep accepting writes it thinks are valid — Raft's term check and "step down on higher term" prevents this, but naive homegrown implementations get this wrong (dual-leader bugs are the #1 real-world consensus bug class).
- **Log matching property is fragile in edge cases**: Raft's leader-only-appends rule + log continuity check (prevTerm/prevIndex) prevent divergence, but a buggy snapshot/log-compaction interaction has caused real outages (etcd had multiple CVEs/bugs here historically).
- **Election storms**: aggressive timeouts + simultaneous candidate elections without proper randomized backoff can cause repeated failed elections ("dueling candidates") — Raft mitigates with randomized election timeout ranges, but misconfigured timeouts in high-latency networks (cross-region) can cause livelock.
- **Membership changes are a classic correctness trap**: naive single-step reconfiguration can create two disjoint majorities momentarily (old config majority + new config majority don't overlap) — Raft's joint consensus phase or single-server-change rule exists specifically to prevent this.
- **Consensus ≠ linearizability by itself**: Raft/Paxos give you an agreed, ordered log, but stale reads from followers or read-without-leader-lease can violate linearizability — systems add read leases/ReadIndex (Raft) or lease-based leadership to serve consistent reads without a full round-trip.
- **Performance tuning matters more than protocol choice**: batching, pipelining multiple AppendEntries before waiting for acks, and separate flush-vs-network-fsync tuning often dominate real throughput more than "Paxos vs Raft" — most performance complaints are disk fsync latency, not the consensus algorithm.
- **CAP framing**: consensus systems choose **CP** — during a partition, minority side stops accepting writes rather than risk split-brain; this is a deliberate trade-off, not a bug, and surprises teams expecting AP behavior.
