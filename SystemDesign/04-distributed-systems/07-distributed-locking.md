# Distributed Locking

> **TL;DR:** A local mutex protects memory in one process; a distributed lock tries to protect a resource across machines over an unreliable network, which is fundamentally weaker — clocks drift, processes pause, messages get delayed. Treat distributed locks as an efficiency optimization, not a correctness guarantee, unless paired with fencing tokens.

## Quick Reference

| Mechanism | Tool | Correctness guarantee | Failure mode |
|---|---|---|---|
| Local mutex | pthread/std::mutex | Strong (shared memory, atomic CPU instr.) | N/A |
| Single-node lock | Redis `SET NX PX` | Weak — none by itself | Failover loses lock; GC pause causes double-hold |
| Redlock (multi-Redis quorum) | 5 Redis nodes | Marketed as strong; Kleppmann disputes | Clock jumps, GC pauses still break it |
| Lease-based lock | ZooKeeper, etcd, Consul | Strong *with* fencing tokens | Session/lease expiry mishandled by client |
| Fencing token | Monotonic counter from lock service | Makes any lock safe against stale holders | Storage layer must check/reject tokens |
| Optimistic concurrency | CAS, Postgres `WHERE version=?` | Strong, no lock service needed | Requires retry logic, contention causes retries |

## What It Is

- A distributed lock lets multiple processes on different machines coordinate exclusive access to a shared resource (a DB row, a file, a job, a leader role).
- Implemented via a third party (Redis, ZooKeeper, etcd) that all contenders trust to arbitrate "who holds it now."
- Two competing goals people conflate: **efficiency** (avoid duplicate work, e.g., two cron workers running the same job) vs. **correctness** (prevent data corruption). Only the latter needs airtight guarantees.

## Responsibilities

- Mutual exclusion: only one client believes it holds the lock at a time (best-effort in async networks).
- Deadlock avoidance: locks must expire/lease out so a crashed holder doesn't block forever.
- Fault tolerance: survive holder crash, network partition, or lock-service node failure.
- Fencing: give downstream systems a way to reject writes from a holder that the lock service has already evicted.

## How It Works

**Redis `SET NX PX` (single instance):**
```
SET lock:resource123 <unique-token> NX PX 30000
```
- `NX` = only set if not exists (acquire). `PX 30000` = auto-expire in 30s (prevents deadlock on crash).
- Release = Lua script that checks the unique token matches before `DEL` (prevents releasing someone else's lock after your TTL expired).
- Single point of failure: if that Redis node dies before replicating, failover can hand the "same" lock to two clients.

**Redlock (Redis's proposed fix):**
- Run 5 independent Redis masters. Client acquires lock by getting `SET NX PX` majority (3/5) within a time budget, accounting for elapsed time against the TTL.
- Claimed to survive individual node failure without relying on replication.

**Lease-based (ZooKeeper/etcd):**
- Client creates an ephemeral (ZK) or lease-bound (etcd) key. Node/lease tied to an active session with heartbeats.
- If client dies or network-partitions, session times out (ZK default ~session timeout, tunable, commonly 10–40s) and the node is deleted — next waiter in line (via sequential znodes / watch) acquires.
- ZooKeeper gives **totally ordered, monotonically increasing zxid/version** on every write — this is what makes fencing tokens easy to generate.

**Fencing tokens (the actual fix for both):**
```
1. Client A acquires lock, gets token=33 (monotonic counter from lock service)
2. Client A stalls (GC pause, VM suspend, swap)
3. Lock expires; Client B acquires lock, gets token=34
4. Client B writes to storage with token=34 — storage records "last token=34"
5. Client A wakes up, writes with token=33 — storage REJECTS (33 < 34)
```
- The lock service issues a monotonically increasing number with every lock grant; **the protected resource itself must check and reject stale tokens**. The lock alone cannot enforce this — the storage layer must cooperate.

## Types / Classifications

| Type | Example | Use when |
|---|---|---|
| Advisory lock | Redis SET NX, Postgres `pg_advisory_lock` | Cooperating clients, low stakes (dedup a cron job) |
| Mandatory/enforced lock | Fencing token + storage check | Correctness-critical (payments, inventory decrement) |
| Lease (time-bound) | ZK ephemeral node, etcd lease | Need auto-recovery from crashed holder |
| Reentrant/hierarchical | Curator `InterProcessMutex` | App needs nested lock semantics like local mutex |
| Read/write distributed lock | ZK recipes, etcd concurrency pkg | Readers don't block readers |

## Where It Fits

- **Leader election**: etcd (used by Kubernetes control plane), ZooKeeper (Kafka pre-KRaft, HBase), Consul sessions — elect a singleton coordinator.
- **Job scheduling dedup**: distributed cron (e.g., using Redis lock) ensures only one worker runs a scheduled task across a fleet.
- **Resource allocation**: locking a shard/partition before rebalancing (Kafka consumer group rebalance uses group coordinator, not a raw lock, but same idea).
- **Rate limiting / quota**: less common — usually better solved with atomic counters (Redis `INCR`) than locks.

## Common Patterns & Real-World Tools

- **Redlock**: `Redisson` (Java) implements it; used when teams want "good enough" locking without standing up ZK/etcd.
- **ZooKeeper recipes**: Apache Curator's `InterProcessMutex`, used by Kafka, Solr, HBase for leader election and distributed locks.
- **etcd**: `concurrency.NewMutex` + lease API; Kubernetes uses etcd leases for leader election in controllers (e.g., kube-scheduler, kube-controller-manager).
- **Postgres advisory locks**: `pg_advisory_lock(key)` — cheap, no extra infra, but tied to a single DB connection's session.
- **Chubby (Google)**: the original inspiration for ZK; internal lock service backed by Paxos, used by GFS/Bigtable master election.
- **DynamoDB conditional writes / Postgres `SELECT ... FOR UPDATE`**: not "distributed locks" per se but achieve mutual exclusion via the storage engine directly — often the better choice.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Redis SET NX | Fast, simple, low latency (<1ms) | No real safety guarantee alone; TTL vs. GC pause race |
| Redlock | Multi-node, no single point of failure | Kleppmann: still assumes bounded clock drift and bounded pause — false in practice; adds complexity for marginal gain |
| ZK/etcd lease | Strong ordering, sessions, built-in fencing tokens, watches for notification | Heavier ops burden (quorum cluster), higher latency (~ms to tens of ms), learning curve |
| Fencing tokens | Makes lock safe regardless of underlying lock impl | Requires cooperation from every resource writer — can't retrofit onto systems you don't control |
| Optimistic concurrency (CAS) | No lock service, no expiry tuning, scales with load | Requires retry logic; livelock under high contention; not real "exclusion," just conflict detection |

## Real-World Scenarios

- **Two schedulers double-charge a customer**: cron-based billing job ran on two nodes because Redis lock's node failed over mid-TTL and the new master had no record of the lock — classic Redlock/single-node failure mode. Fix: fencing token checked by the payment-write path, or move to idempotent charge keys.
- **Kubernetes leader election**: controller-manager uses etcd lease with ~15s TTL and renew-before-expiry; if the leader process pauses (e.g., stop-the-world GC in a sidecar, or VM live-migration), another replica takes over — acceptable because etcd's `Compare-And-Swap` on the lease key plus API server validation acts like a fencing check.
- **S3-backed "lock" via conditional PUT**: teams sometimes fake a distributed lock with `PutObject` + `If-None-Match` (now supported) instead of standing up ZK — fine for low-contention, non-critical coordination.
- **Inventory decrement race**: instead of locking the inventory row across services, use `UPDATE inventory SET qty = qty - 1 WHERE qty >= 1 AND id = ?` — pure CAS, no lock service, avoids the entire distributed-locking problem.

## Nuances & Gotchas

- **Kleppmann's core critique of Redlock**: it conflates two failure models — Redlock analysis assumes a synchronous system (bounded delays, bounded clocks), but real systems are asynchronous (GC pauses of seconds, VM pauses, NTP jumps, swap). A "safe" TTL can be violated by an OS-level pause you can't bound in advance.
- **Lock without fencing = false safety**: even ZK's ephemeral nodes don't help if the resource being protected (e.g., a network filesystem write) doesn't itself check a fencing token — the lock only tells you who *should* be writing, not who *is actually* writing.
- **TTL tuning is a lose-lose**: too short → lock expires while holder is still legitimately working (e.g., slow disk I/O), causing double-execution; too long → slow recovery after real crash, blocking the whole system.
- **Clock skew between the lock service and the resource's storage** can break fencing token comparisons if tokens are timestamp-based instead of a monotonic counter — always use a counter, not wall-clock time, for tokens.
- **Split-brain during network partition**: a "minority" client that thinks it still holds the lock can keep writing right up until it notices its session expired — this window is exactly what fencing tokens close, and exactly what naive Redis locks don't.
- **ZK/etcd session expiry vs. client library heartbeat bugs**: a slow or buggy client can fail to renew a lease due to app-level thread starvation, not the network — the lock service correctly evicts it, but app logs will misleadingly suggest "the lock service is unreliable."
- **Prefer no lock at all when possible**: if the operation can be expressed as a single atomic DB operation (CAS, `INSERT ... ON CONFLICT`, conditional write), skip the lock service entirely — fewer moving parts, no expiry tuning, and correctness holds even under arbitrary pauses.
- **Reentrancy traps**: naive Redis lock implementations aren't reentrant — a client that acquires the lock twice (e.g., recursive call) can deadlock itself or double-decrement a counter on release.
- **Testing gap**: distributed lock bugs rarely show up in unit tests — they require chaos testing (Jepsen-style: inject GC pauses, clock skew, network partitions) to surface, which is why Kleppmann used Jepsen-adjacent reasoning to critique Redlock in the first place.
