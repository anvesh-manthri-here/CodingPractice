# Leader Election

> **TL;DR:** Electing a single coordinated writer avoids the need for expensive multi-writer conflict resolution, but the moment two nodes both believe they're leader (split-brain), you need fencing tokens — not just faster elections — to keep the system correct.

## Quick Reference

| Mechanism | System | Election trigger | Typical failover time | Split-brain defense |
|---|---|---|---|---|
| Randomized election timeout + term counter | Raft (etcd, Consul) | Follower misses heartbeat | 150–300ms timeout, ~1–3 elections to converge | Term numbers reject stale leader msgs |
| Ephemeral sequential znodes | ZooKeeper (Kafka, HBase) | Session expiry (heartbeat loss) | Session timeout (default 6–30s) + watch latency | zxid/epoch fencing |
| Lease with TTL | etcd, Chubby | Lease not renewed in time | Lease TTL (commonly 5–15s) | Lease ID as fencing token |
| Bully / ring algorithms | Legacy custom systems | Node detects coordinator down | O(n) messages, seconds | Weak — rarely used alone now |

## What It Is

- **Leader election**: a distributed consensus problem — get a majority of nodes to agree on exactly one process as "leader" for a given term/epoch, even amid crashes, network partitions, and message delays.
- Distinct from simple failover scripts: must guarantee **at most one leader per term** (safety), not just "someone becomes leader eventually" (liveness).
- Underpins single-writer systems: Kafka partition leaders, Raft/etcd cluster leader, HBase region server master, Postgres primary in Patroni.

## Responsibilities

- Guarantee **uniqueness**: no two nodes act as leader for the same term simultaneously (safety property).
- Guarantee **liveness**: a new leader is elected within bounded time after failure (availability property).
- Provide a **monotonic epoch/term/fencing token** so stale leaders can be detected and rejected by followers/storage.
- Propagate leadership changes to clients/followers (via heartbeats, watches, or gossip) so writes route correctly.

## How It Works

**Raft (etcd, Consul, CockroachDB, TiKV):**
- Each node is Follower, Candidate, or Leader. Leader sends heartbeats (AppendEntries) every ~50–100ms.
- Follower with no heartbeat for a **randomized election timeout** (150–300ms range, randomized to avoid split votes) becomes Candidate, increments `term`, requests votes.
- Wins with majority quorum vote; ties/split votes retry with fresh random timeout — randomization is what makes this converge quickly in practice.
- Term number monotonically increases each election; any message with a stale term is rejected — this *is* the fencing mechanism baked into the protocol.

**ZooKeeper (ephemeral sequential znodes):**
- Candidates create `/election/node_` with `EPHEMERAL_SEQUENTIAL` flag → ZK appends a monotonic sequence number.
- Node with the **lowest sequence number** is leader; others watch the znode immediately below their own (avoids herd effect on notification).
- If leader's session dies (missed heartbeats past session timeout), its ephemeral znode auto-deletes, triggering the next-in-line's watch to fire.
- Kafka (older controller election, pre-KRaft) and HBase Master election used this pattern.

**etcd leases (lease-based leadership):**
- Leader acquires a lease with TTL (e.g., 10s) and attaches it to a key; must send keepalives to renew.
- If leader crashes/partitions, lease expires, key is deleted, watchers are notified, another node campaigns via `etcd election` API (built on Raft underneath).
- Simpler mental model than raw Raft terms — used by Kubernetes controller-manager/scheduler leader election.

## Types / Classifications

| Type | Basis | Example |
|---|---|---|
| Consensus-based | Quorum voting with terms | Raft, Paxos (Multi-Paxos), ZAB |
| Coordination-service-based | External strongly-consistent store | ZooKeeper znodes, etcd leases, Chubby locks |
| Ranking/priority-based | Deterministic ID comparison | Bully algorithm, ring algorithm |
| Gossip/SWIM-based | Failure detection + convention (no formal quorum) | Some Cassandra-adjacent custom setups (weaker guarantees) |

## Where It Fits

```
Client writes ---> [Leader] ---replicate---> Followers (quorum ack)
                       ^
                 elected via Raft/ZK/etcd
                 term/epoch N
```
- Sits beneath replicated state machines, distributed locks, partition ownership assignment (Kafka), and primary/standby DB failover (Patroni for Postgres, MHA for MySQL).
- Client/proxy layer (e.g., PgBouncer, Kafka producer metadata) must be leader-aware to route writes correctly — stale routing is a common source of write failures during failover.

## Common Patterns & Real-World Tools

- **Kubernetes controller-manager/scheduler**: uses etcd-based lease locking (`coordination.k8s.io/Lease`) so only one replica actively reconciles.
- **Kafka**: KRaft mode (post-ZooKeeper removal, KIP-500) uses a Raft-based controller quorum instead of ZK ephemeral nodes.
- **Patroni (Postgres HA)**: uses etcd/Consul/ZooKeeper as the DCS (distributed config store) to elect primary and manage fencing via `pg_rewind` + STONITH-like mechanisms.
- **Redis Sentinel**: quorum-based leader (master) failover, notoriously prone to split-brain in partition scenarios (no fencing tokens by default — a known weakness).
- **Chubby (Google)**: lease-based advisory locks, inspiration for etcd/ZooKeeper design.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Raft-native election | Built-in fencing via terms, fast (sub-second), no external dependency | Requires implementing/embedding full consensus protocol |
| ZooKeeper znodes | Battle-tested, simple leader-per-path model, herd-effect-free watches | Extra operational dependency, session timeout tuning is finicky |
| etcd lease election | Simple API, reuses etcd's Raft safety | Lease renewal under GC pause can cause false expiry |
| Static/manual failover | Fully predictable, no flapping | Slow (minutes), human in the loop, doesn't scale |

## Real-World Scenarios

- **Kafka partition leader failure**: controller detects broker disconnect via ZK/KRaft session, reassigns leadership from in-sync replica (ISR) set; producers refresh metadata and redirect writes — takes ~seconds, tunable via `replica.lag.time.max.ms`.
- **etcd cluster network partition (minority side)**: minority nodes can't reach quorum, step down / can't elect, remain read-only or unavailable — correctly refuses to serve writes rather than risk split-brain.
- **Kubernetes control plane upgrade**: rolling restart of leader pod triggers lease expiry (~15s default), a standby controller-manager instance acquires the lease and resumes reconciliation with near-zero downtime.
- **Postgres with Patroni, stale primary**: old primary loses etcd lease during a GC pause, Patroni promotes a replica; fencing script (STONITH — power off / network isolate old primary) prevents old primary from accepting writes if it wakes up.

## Nuances & Gotchas

- **Fencing tokens are the real fix, not faster elections.** A monotonically increasing token (Raft term, ZK zxid, etcd lease ID) must be checked by the *storage layer itself* — e.g., a distributed lock manager rejects writes from a lower token even if the old leader thinks it's still in charge (classic Martin Kleppmann GC-pause example).
- **GC pauses / STW pauses are the #1 real-world split-brain trigger**, not network partitions — a leader can be paused past its lease TTL, resume, and issue a write believing it's still leader. Fencing at the storage layer is the only reliable defense.
- **Election timeout tuning is a stability/latency trade-off**: too short (e.g., <100ms) causes "flapping" — spurious re-elections under transient GC pauses or network jitter, thrashing the cluster. Too long (>1s) means longer unavailability windows after a genuine crash.
- **Randomization in Raft timeouts isn't cosmetic** — without it, all followers time out simultaneously, split the vote every round, and the cluster can livelock without ever electing a leader.
- **ZooKeeper session timeout vs. GC**: a JVM-based client (e.g., HBase RegionServer) with long GC pauses can exceed session timeout, lose its ephemeral znode, and get "expired" even though the process is alive — leads to false failovers under load.
- **Redis Sentinel lacks strong fencing by default** — during asymmetric partitions, old and new master can both accept writes; mitigated only by `min-replicas-to-write` and careful quorum config, still weaker than Raft/ZK guarantees.
- **Quorum size matters more than node count**: a 4-node Raft cluster has the same fault tolerance (1 failure) as a 3-node cluster but needs 3 votes instead of 2 — always deploy odd numbers (3, 5, 7).
- **Leader stickiness vs. balance**: some systems (Kafka) intentionally avoid unnecessary leader migration (`auto.leader.rebalance.enable`) because each leadership change causes a replication/catch-up cost, even when no failure occurred.
- **Read-after-write consistency depends on leader routing**: if followers serve stale reads during a leadership transition window, clients can observe non-monotonic reads unless read-index/lease-read protocols (Raft) are used.
