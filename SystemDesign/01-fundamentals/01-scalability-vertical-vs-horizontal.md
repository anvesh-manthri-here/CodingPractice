# Scalability — Vertical vs Horizontal Scaling

> **TL;DR:** Vertical scaling (scale-up) buys bigger hardware for one node — simple but hits a physical/cost ceiling; horizontal scaling (scale-out) adds more nodes — unbounded in theory but demands statelessness, and past a point coordination overhead makes throughput *fall*, not just plateau.

## Quick Reference

| Aspect | Vertical (Scale-Up) | Horizontal (Scale-Out) |
|---|---|---|
| Mechanism | Bigger CPU/RAM/disk on one machine | More machines behind a distributor |
| Ceiling | Hardware limits (~ largest cloud instance) | Near-unbounded, bounded by coordination cost |
| Downtime to scale | Usually yes (reboot/migrate) | No (add nodes live) |
| Prerequisite | None | Statelessness / partitionable state |
| Cost curve | Superlinear near top-end (exotic hardware) | Roughly linear + coordination overhead |
| Fault tolerance | Single point of failure | Node loss ≈ capacity dip, not outage |
| Complexity | Low (no distributed systems) | High (consensus, partitioning, LB, retries) |
| Governing law | Amdahl's Law | Universal Scalability Law (USL) |
| Example ceiling | AWS `u-24tb1.metal` (24TB RAM) | Google/AWS: 10,000s of nodes |

## What It Is
- **Vertical scaling**: increase capacity of a single node — more cores, RAM, faster NVMe/network. Same architecture, bigger box.
- **Horizontal scaling**: increase capacity by adding more nodes running the same workload, coordinated via a load balancer, partitioning scheme, or cluster manager.
- Both address the same question — "how do I serve more load?" — via orthogonal axes (compute per node vs. number of nodes).

## Responsibilities
- Vertical: choose instance/hardware tier, manage OS-level tuning (kernel limits, NUMA, I/O schedulers), plan migration/downtime windows.
- Horizontal: design statelessness or state partitioning, build service discovery + load balancing, handle partial failure, manage data consistency across nodes, automate provisioning (autoscaling groups, k8s HPA).

## How It Works
- **Scale-up mechanics**: swap VM/instance type (e.g., `m5.large` → `m5.24xlarge`), add RAM/disk, upgrade to faster storage tier. Vertical DB scaling = bigger primary instance (RDS instance class bump).
- **Scale-out mechanics**: put a load balancer (L4/L7) or sharding key in front; each new node is a stateless replica or owns a data partition. Read replicas, consistent hashing, gossip-based membership (e.g., Cassandra) are common substrates.
- **Statelessness is the enabling condition** for horizontal scaling: if any node holds session/user state in local memory/disk, requests must be sticky-routed (limits elasticity) or state must be externalized (Redis/DB) so any node can serve any request.
- Stateful systems horizontal-scale via **partitioning/sharding** (data split by key), not replication of identical state — each shard node is itself effectively "vertical" within its partition.

## Types / Classifications
- **Scale-up (vertical)**: CPU-bound, memory-bound, I/O-bound upgrades — pick the resource that's actually the bottleneck (profile first).
- **Scale-out (horizontal)**: stateless service replication vs. data partitioning (sharding) vs. functional decomposition (microservices — splitting by capability, not just replicating).
- **The Scale Cube** (Abbott & Fisher, *The Art of Scalability*) — three independent axes:
  - **X-axis**: clone the app, put N identical instances behind a load balancer. Easiest, but every instance needs full dataset/state access.
  - **Y-axis**: split by function/service (microservices) — checkout service, catalog service, etc. Reduces per-service complexity and blast radius.
  - **Z-axis**: split by data partition/shard (e.g., customer ID range, geography) — each node handles a subset of data, cutting per-node dataset size.
  - Real systems combine all three (e.g., microservices [Y], each horizontally replicated [X], each with sharded data stores [Z]).

## Where It Fits
- **Vertical first, horizontal later** is a common pragmatic path: cheaper to resize an instance than to re-architect for statelessness/sharding.
- Stateless web/app tier → horizontal (X-axis) is default in cloud-native design.
- Stateful data tier (primary DB) → vertical scaling or read-replica horizontal scaling for reads; writes scale via sharding (Z-axis) or moving to a horizontally-native store (Cassandra, DynamoDB, Vitess/CockroachDB).
- Caching layers (Redis Cluster, Memcached) → horizontal via consistent hashing to avoid vertical ceilings on hot keys.

## Common Patterns & Real-World Tools
- **Vertical**: RDS/Cloud SQL instance class upgrades, single-node Redis, mainframes (still vertical-scaled for OLTP), EC2 `X2iedn`/`u-*` memory-optimized families.
- **Horizontal — stateless**: Kubernetes HPA, AWS Auto Scaling Groups, NGINX/ELB/ALB load balancing, serverless (Lambda) — infinite horizontal by design.
- **Horizontal — stateful**: Cassandra/DynamoDB (consistent hashing + partitions), Vitess/CockroachDB/Spanner (sharded SQL with distributed consensus), Kafka (partitions across brokers), Elasticsearch (shards + replicas).
- **Hybrid**: vertically-scaled shards that are also horizontally replicated (e.g., MongoDB: shard = horizontal, replica set per shard = redundancy, each replica vertically sized).

## Pros & Cons / Trade-offs

| | Vertical | Horizontal |
|---|---|---|
| Pros | No code changes, no distributed-systems tax, strong consistency trivial | Elastic, fault-tolerant, scales past any single machine, incremental cost |
| Cons | Hard ceiling, downtime to resize, single point of failure, cost grows superlinearly at top end | Requires re-architecture (statelessness/partitioning), coordination overhead, eventual consistency trade-offs, ops complexity (service discovery, retries, distributed tracing) |

- **Cost curve**: vertical cost is roughly linear until you approach the top-of-line instance, then jumps steeply (specialized/rare hardware, diminishing price-performance). Horizontal cost is closer to linear per added commodity node, but coordination overhead (below) adds a hidden tax that grows with N.

## Real-World Scenarios
- **Startup MVP**: single Postgres + single app server, vertically scaled (bump instance size) until traffic or team size makes horizontal worth the complexity — classic "scale up until it hurts."
- **Black Friday traffic spike**: stateless checkout/API tier scales horizontally (autoscaling groups) in minutes; the payment DB primary is vertically maxed and protected by read replicas + caching to absorb read load.
- **Sharded multi-tenant SaaS**: Z-axis partitioning by tenant ID/customer — each shard vertically sized for its own load, horizontally added as tenant count grows (Slack-style, Vitess-style).
- **Legacy monolith migration**: Y-axis decomposition into services enables independently scaling the hot path (e.g., search) horizontally while leaving low-traffic admin services vertically scaled on one box.

## Nuances & Gotchas
- **Amdahl's Law**: speedup is capped by the serial (non-parallelizable) fraction of work — `Speedup(N) = 1 / (S + (1-S)/N)`. With just 5% serial code, max speedup caps around 20x no matter how many nodes you add; identify and eliminate serial bottlenecks (global locks, single-writer logs) before throwing nodes at it.
- **Universal Scalability Law (Gunther)** extends Amdahl with a second penalty term for **coherency** (cross-node cache/state synchronization): `C(N) = N / (1 + α(N-1) + βN(N-1))`. The `α` term is contention (serialization, e.g., lock waits); the `β` term is **coherency delay** — cost of keeping nodes consistent (cache invalidation, consensus rounds, gossip). Crucially, `β > 0` means throughput **peaks and then declines** as N grows — more nodes make things *worse* past a threshold, unlike Amdahl which only plateaus.
- **The coherency penalty is why "just add more nodes" fails in practice**: distributed locks, chatty consensus (e.g., naive Paxos/Raft on every write), or a shared bottleneck resource (single DB primary, global cache) all contribute `β`. Symptoms: adding replicas increases p99 latency and *decreases* aggregate throughput.
- **Statelessness is necessary but not sufficient**: even stateless services share a stateful backend (DB, cache) — that backend becomes the real ceiling; horizontal scaling of the front tier just moves load faster into the bottleneck (thundering herd on the DB).
- **Sticky sessions defeat horizontal elasticity**: session affinity ties a client to one node, reintroducing a soft state dependency — losing that node degrades UX and complicates rolling deploys/autoscaling.
- **Vertical scaling has hidden discontinuities**: crossing a NUMA boundary, hitting network interface (NIC) limits, or exceeding a single-threaded hot path (e.g., Redis pre-7.0 single-threaded command execution) means adding cores/RAM stops helping — profile before buying bigger.
- **Horizontal scaling amplifies operational surface area**: N nodes means N times the patching, monitoring, certificate rotation, and failure modes (partial failures, split-brain, network partitions) — Kubernetes/Consul help but add their own failure modes (etcd quorum loss).
- **Rebalancing cost on scale-out**: adding/removing shards in a sharded system (non-consistent-hash schemes) can trigger massive data movement — consistent hashing (Cassandra, DynamoDB) minimizes this to ~1/N of data moved per node change.
- **Diminishing returns interact with cost**: past the USL peak, paying for more nodes is strictly worse — capacity planning must find `N*` (the throughput-maximizing point), not assume monotonic gains; Gunther's model lets you solve for it from just a few load-test data points via regression.
- **Vertical-first isn't just simplicity — it's fewer consistency bugs**: single-node ACID transactions vs. distributed transactions (2PC, sagas) is a real complexity cliff; don't horizontal-scale the data tier until vertical + read replicas + caching genuinely can't keep up.

## Self-Check

1. With 5% serial code, what's the maximum speedup Amdahl's Law predicts, no matter how many nodes you add?
2. Why does the Universal Scalability Law predict throughput can *decline* past a certain N, whereas Amdahl's Law only predicts a plateau?
3. A cluster shows adding replicas increases p99 latency and decreases aggregate throughput. Which USL term is the likely culprit, and what real mechanisms produce it?
4. Why is "the app tier is stateless" not sufficient to claim a system scales horizontally without limit?
5. Under the Scale Cube, which axis is "clone the app behind a load balancer," and what's its main downside compared to Y/Z-axis splits?

<details><summary>Answers</summary>

1. About 20x (`1/0.05`) — the ceiling from `1/(S + (1-S)/N)` as N approaches infinity.
2. USL adds a `βN(N-1)` coherency term (cross-node sync cost) on top of Amdahl's contention term; because it grows faster than N, throughput eventually falls, not just flattens.
3. The `β` (coherency) term — caused by distributed locks, chatty consensus (Paxos/Raft per write), or cache invalidation/gossip across nodes.
4. Stateless nodes still depend on a shared stateful backend (DB, cache); that backend becomes the real bottleneck, so scaling the front tier just pushes more load into it faster (thundering herd).
5. X-axis; its downside is every instance needs full dataset/state access, unlike Y-axis (functional split) or Z-axis (data partitioning) which reduce per-node scope.
</details>

---
**Related:** [Latency, Throughput, Bandwidth](02-latency-throughput-bandwidth.md) · [Availability and the Nines](06-availability-and-nines.md) · [Load Balancers](../02-core-components/01-load-balancers.md)

*Last reviewed: 2026-08*
