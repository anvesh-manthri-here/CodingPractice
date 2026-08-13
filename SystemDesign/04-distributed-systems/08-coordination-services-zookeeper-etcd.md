# Coordination Services — ZooKeeper and etcd

> **TL;DR:** A coordination service is a small, strongly consistent metadata store (backed by a consensus protocol) that other distributed systems use for locks, leader election, config, and service discovery — ZooKeeper (ZAB) is the classic; etcd (Raft) is its modern successor and Kubernetes' brain.

## Quick Reference

| Aspect | ZooKeeper | etcd |
|---|---|---|
| Consensus protocol | ZAB (ZooKeeper Atomic Broadcast) | Raft |
| Data model | Hierarchical znode tree (like a filesystem) | Flat key-value store (keys look hierarchical by convention) |
| Node types | Persistent, ephemeral, sequential (combinable) | Key + optional lease (TTL) binding |
| Change notification | Watches (one-shot, must re-register) | Watches (streaming, via gRPC, no re-register needed) |
| Client protocol | Custom TCP (Jute), Java-centric | gRPC / HTTP, easy multi-language clients |
| Consistency | Linearizable writes, sequential reads (can be stale) | Linearizable reads/writes by default (quorum read) |
| Typical cluster size | 3, 5, 7 (odd, tolerate ⌊(n-1)/2⌋ failures) | 3, 5, 7 (same math) |
| Max recommended data size | Small (~few GB, in-memory dataset) | Small (~2-8 GB, backed by BoltDB) |
| Famous users | Kafka (pre-KRaft), Hadoop HDFS HA, HBase, SolrCloud | Kubernetes, CoreDNS, Vault (backend), Doorman |
| CAP stance | CP — sacrifices availability on partition | CP — same |

## What It Is

- A **coordination service** is a specialized distributed system whose entire job is to provide correctness primitives (mutual exclusion, ordering, membership) that are hard to build correctly on top of an app's own database.
- It is not a general-purpose database: small dataset, low write throughput expected (hundreds to low-thousands writes/sec), strong consistency prioritized over scale.
- Both ZooKeeper and etcd expose a **replicated state machine**: every write goes through consensus so all nodes apply the same operations in the same order.

## Responsibilities

- **Leader election** — exactly one process in a group is elected "leader" at any time (e.g., HDFS NameNode HA, Kafka controller pre-KRaft).
- **Distributed locking / mutual exclusion** — ephemeral znodes / leases give locks that auto-release if the holder dies.
- **Configuration management** — centralized, watchable config (feature flags, topology) pushed to all subscribers.
- **Service discovery / membership** — who's alive right now (ephemeral registration + heartbeat via session or lease).
- **Metadata store** — Kafka topic/partition assignments (legacy), Kubernetes' entire cluster state (etcd is K8s's *only* source of truth).
- **Barriers / queues** — coordination primitives built from sequential znodes.

## How It Works

- **Write path**: client → leader node → leader proposes to followers → majority ack → commit → leader responds to client. Same shape in ZAB and Raft: leader-based, quorum-committed, log-replicated.
- **ZAB** (ZooKeeper): leader election phase + atomic broadcast phase; strictly orders all writes into a global sequence (zxid — 64-bit, epoch + counter).
- **Raft** (etcd): leader election via randomized timeouts + term numbers; log replication with strict log-matching property; well-documented, easier to reason about than ZAB (a major reason etcd/Consul chose it).
- **Reads**: ZooKeeper reads are served by any node from local (possibly stale) state unless you call `sync()` first; etcd's linearizable reads (default) require a round-trip to leader/quorum, but it also offers cheaper "serializable" reads for staleness-tolerant callers.
- **Sessions/Leases**: ZK session = TCP connection + heartbeats; ephemeral znodes vanish when session expires. etcd lease = independent TTL object you attach keys to; a lease refresh (keep-alive) is decoupled from any single connection — more resilient to client reconnect churn.
- **Watches**: client sets a watch on a key/znode, gets a one-time event on change (ZK) or a continuous event stream (etcd `Watch` API, gRPC streaming) — etcd's model avoids the "watch gap" race ZK clients must code around.

```
        writes                     writes
Client ────────► Leader ──quorum──► Followers
                    │  (ZAB / Raft log replication)
Client ◄── reads ───┘ (local, possibly stale — unless linearizable/sync)
```

## Types / Classifications

**ZooKeeper znode types** (composable flags):
- Persistent — survives until explicitly deleted.
- Ephemeral — deleted automatically when creating session ends; can't have children; used for liveness/locks.
- Sequential — server appends monotonic counter to name; used for ordered locks, queues, leader election ("lowest sequence number wins").
- Container / TTL nodes (newer ZK 3.5+) — auto-cleanup for scoped subtrees.

**etcd primitives:**
- Plain key-value pairs with optional lease attachment (TTL).
- `Lease` — independent grant with keep-alive; multiple keys can share one lease.
- `Watch` — streaming subscription with revision-based history (MVCC — every write bumps a global revision, enabling watch-from-revision replay, unlike ZK's fire-and-forget watches).
- Built-in higher-level recipes via `etcdctl`/client libraries: `Lock`, `Election`, `mutex` — implemented client-side on top of leases + watches (etcd core stays minimal, unlike ZK's built-in recipes library "Curator" pattern).

## Where It Fits

- Sits **beside**, not inside, the systems it coordinates — a separate cluster the app cluster talks to over the network.
- Kubernetes control plane: API server is the only etcd client; all other components (scheduler, controller-manager, kubelets) talk to API server, which persists/reads all cluster state in etcd.
- Kafka (pre-2.8/KRaft): brokers registered ephemeral znodes in ZK, controller election via ZK, topic/partition metadata in ZK — KRaft (Kafka's own Raft-based metadata quorum, GA since Kafka 3.5+/4.0 default) removed this dependency to cut operational surface and improve partition-count scalability.
- HDFS: ZK used for NameNode HA failover (ZKFC — ZooKeeper Failover Controller) to avoid split-brain NameNodes.
- Service meshes / discovery: Consul (Raft, its own but similar role) often compared to etcd+extra features (health checks, DNS, KV).

## Common Patterns & Real-World Tools

- **Leader election**: create ephemeral+sequential node under `/election`; node with lowest sequence number is leader; others watch the node just below them (not the leader — avoids herd effect on failover).
- **Distributed lock**: same pattern — lock acquired if you hold lowest sequence node; release on delete or session death.
- **Apache Curator** (Java): wraps raw ZK API into production-safe recipes (locks, leader election, caches) — hand-rolling ZK client logic is a known footgun.
- **etcd client recipes** (`clientv3/concurrency` package in Go): `NewSession` + `Mutex` + `Election` give the same primitives with less ceremony thanks to leases.
- **Service discovery**: Netflix Eureka / Consul are AP alternatives; ZK/etcd are the CP choice when correctness (no split-brain leader) trumps availability during partition.

## Pros & Cons / Trade-offs

| | ZooKeeper | etcd |
|---|---|---|
| Pros | Battle-tested (15+ yrs), rich recipe ecosystem (Curator), strong ordering guarantees | Simpler protocol (Raft) to reason about/debug, gRPC-native, great K8s integration, built-in MVCC history |
| Cons | JVM ops overhead (GC pauses can stall consensus), Jute wire protocol clunky for non-JVM clients, ZAB less documented than Raft | Smaller feature set for pure locking (must build recipes client-side), BoltDB file grows without periodic compaction/defrag, gRPC message size limits (1.5MB default) bite on large values |
| Shared con | CP means a lost quorum = **total write outage** (and stale/no reads without workarounds) — by design, not a bug | same |

## Real-World Scenarios

- **Kafka controller election (legacy)**: broker registers ephemeral znode in `/controller`; if controller broker dies, znode disappears, remaining brokers race to recreate it — winner becomes new controller. KRaft replaced this with an internal Raft-based metadata log to remove the ZK hop and support 100k+ partitions.
- **Kubernetes etcd disk-latency incident pattern**: etcd is disk-fsync-sensitive (Raft log must be durably persisted before ack); slow/shared disks (common on noisy-node bare metal or under-provisioned cloud volumes) cause leader election flapping and API server timeouts across the whole cluster — root cause of many "K8s API unresponsive" postmortems.
- **HDFS NameNode failover**: ZKFC monitors NameNode health, on failure it fences the old active (via ephemeral znode expiry + fencing script) before promoting standby — prevents two NameNodes writing simultaneously.
- **etcd cluster resize during K8s upgrade**: operators must add/remove members one at a time and keep an odd quorum size throughout — even briefly running 2-member etcd loses fault tolerance entirely (any 1 failure = quorum loss).

## Nuances & Gotchas

- **Quorum loss = full outage by design.** Losing majority of nodes (e.g., 2 of 3) doesn't degrade gracefully — writes stop entirely, and reads may stop too; this is the CP trade-off, not a failure mode to "fix."
- **Never run an even-sized cluster.** 4 nodes tolerate only 1 failure (same as 3) but need 3 for quorum — strictly worse cost/benefit than an odd cluster; a classic misconfiguration.
- **ZK ephemeral node "false expiry" during GC pauses**: a long JVM stop-the-world GC can exceed the session timeout, making ZK think the client died — a live leader loses its lock and duplicate work starts (split-brain risk) unless downstream logic fences using the zxid/lease generation number.
- **etcd disk fsync sensitivity**: Raft requires durable log writes before ack; on cloud VMs, noisy-neighbor or network-attached disks routinely cause `etcdserver: request timed out` and election storms — official guidance mandates local SSD, `fdatasync` benchmarked <10ms.
- **etcd DB size limit**: default backend quota is 2GB (configurable, commonly raised to 8GB) — exceeding it puts the cluster into alarm mode (read-only) until compacted + defragmented; a notorious "why is my cluster suddenly read-only" incident.
- **Watches are not a substitute for polling on critical paths**: both systems can drop/coalesce events under load or on reconnect (ZK: must resync full state after reconnect, since events during disconnect are lost; etcd: watch can fall behind and get "compacted" error, requiring full re-list from current revision).
- **Don't use these as a general database or message queue.** Both explicitly warn against storing large values or high-churn data — ZK znodes recommended <1MB, etcd default gRPC message cap 1.5MB; both keep full dataset in memory/mmap for speed, so large datasets blow memory budgets and slow snapshotting.
- **Client library choice matters more than protocol theory.** Most real incidents trace to home-rolled locking/leader-election code getting fencing wrong (e.g., not checking a lock's "epoch"/lease ID before acting) — always prefer Curator (ZK) or `concurrency` package (etcd) over hand-rolled recipes.
- **Network partition + minority side "thinks" it's still fine**: clients connected only to the minority partition see hung requests, not clean errors — timeouts must be tuned explicitly; naive retry-forever clients can cascade load once quorum is restored.
