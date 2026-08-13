# Sharding and Partitioning

> **TL;DR:** Partitioning splits data across nodes to scale writes/storage past a single machine's limits; the shard key choice determines whether you get even load distribution or a hot-shard disaster, and cross-shard operations (joins, transactions, secondary indexes) are the recurring tax you pay for that scale.

## Quick Reference

| Strategy | Lookup cost | Rebalance cost | Range scans | Hot spot risk | Used by |
|---|---|---|---|---|---|
| Range | O(log n) via routing table | Medium (split ranges) | Fast, contiguous | High (sequential keys, time-series) | HBase, Bigtable, CockroachDB (ranges) |
| Hash | O(1) via hash(key) | High (rehash) unless consistent hashing | Terrible (scattered) | Low (uniform) | DynamoDB, Cassandra, MongoDB (hashed) |
| Consistent hash | O(1) + ring lookup | Low (only neighbors move) | Terrible | Low | Cassandra, DynamoDB (internally), Riak |
| Directory-based | O(1) lookup + 1 extra hop | Low (update mapping table) | Depends on impl | Low, but directory is SPOF/bottleneck | Vitess (VSchema), Citus (metadata), MongoDB config servers |

## What It Is

- **Partitioning**: dividing one logical dataset into smaller chunks (partitions/shards) that can live on separate disks/nodes, so no single node holds all the data or serves all the traffic.
- **Sharding**: partitioning specifically across separate database instances/servers (horizontal scaling), as opposed to partitioning within a single instance (e.g., Postgres native table partitioning on one box).
- Goal: linear scale-out of storage and throughput; each shard handles a slice of data and a slice of query load independently.

## Responsibilities

- Distribute data + traffic evenly across nodes to avoid hotspots.
- Provide a routing layer so clients/queries find the correct shard(s) without scanning all of them.
- Support growth: add shards without full downtime (resharding/rebalancing).
- Preserve query semantics as much as possible (joins, transactions, secondary indexes) despite data being physically split.
- Maintain shard-local availability/durability (usually paired with replication per shard).

## How It Works

1. **Choose a shard/partition key** (e.g., `user_id`, `tenant_id`, `order_id`).
2. **Map key → shard** via one of three mechanisms (range, hash, directory) — see below.
3. **Router/coordinator** (proxy, client-side driver, or query engine) directs each request to the owning shard(s).
4. Each shard is typically its own replica set (primary + replicas) for HA — sharding and replication are orthogonal and combined in practice.
5. **Rebalancing**: as shards grow unevenly, splits/merges/moves happen — background migration copies data, then atomically flips routing metadata.

```
Client -> Router/Coordinator -> shard_map(key) -> Shard N (primary+replicas)
                              -> Shard M (for cross-shard fan-out)
```

## Types / Classifications

### Range partitioning
- Contiguous key ranges assigned to shards (e.g., A-M on shard1, N-Z on shard2; or timestamp ranges).
- Great for range scans ("orders from last week") — data is physically contiguous.
- **Hot-shard risk**: monotonically increasing keys (auto-increment IDs, timestamps) funnel all writes to the newest/last shard.
- Auto-splitting systems (HBase regions, Bigtable tablets, CockroachDB ranges) split a range once it exceeds a size threshold (e.g., 64MB/512MB) and reassign — mitigates but doesn't eliminate the write-hotspot-at-the-tail problem.

### Hash partitioning
- `shard = hash(key) % N` (naive) or consistent hashing ring.
- Naive `% N` means adding/removing a shard remaps almost every key → massive data movement. This is why nobody does plain modulo hashing in production at scale.
- **Consistent hashing** (Cassandra, DynamoDB, Riak): ring of hash space, each node owns arcs; adding/removing a node only moves keys in adjacent arcs (~1/N of data), not everything.
- Virtual nodes (vnodes) smooth out uneven ring distribution — Cassandra default 256 vnodes/node historically, now often lower (e.g., 16) for faster streaming.
- Kills range scans: consecutive keys land on random shards, so "give me users 1000-2000" becomes a scatter-gather.

### Directory-based (lookup service)
- A separate metadata service maps key/range → shard explicitly (not computed).
- Flexible: can rebalance arbitrarily, put hot keys on dedicated shards, migrate individual tenants.
- Adds a hop and a new single point of failure/bottleneck unless the directory itself is replicated and cached aggressively (e.g., Vitess topology server backed by etcd/Consul/ZooKeeper; MongoDB config servers as a 3-node replica set).
- Most real large-scale systems (Vitess, Citus, MongoDB) end up as **hybrid**: hash or range partitioning *plus* a directory/metadata layer for routing and rebalancing control.

## Where It Fits

- Sits below the query/application layer, above raw storage engines — usually implemented as a proxy (Vitess `vtgate`), a coordinator node (Citus coordinator, MongoDB `mongos`), or a client-side SDK (DynamoDB SDK computing partition from key).
- Complements (not replaces) replication: each shard is independently replicated for durability/HA; sharding solves *scale*, replication solves *availability*.
- Often paired with caching (Redis) in front to absorb read hotspots that partitioning alone can't fix.

## Common Patterns & Real-World Tools

| System | Partitioning approach | Routing | Rebalancing |
|---|---|---|---|
| **Vitess** (MySQL sharding, used by YouTube, Slack) | Range or hash via VSchema, "vindexes" | `vtgate` proxy parses SQL, routes to shard(s) | `Reshard`/`MoveTables` workflows — online, via VReplication (binlog copy + cutover) |
| **Citus** (Postgres extension) | Hash on distribution column by default | Coordinator node rewrites queries, fans out to workers | `citus_move_shard_placement`, shard rebalancer background daemon |
| **MongoDB sharding** | Range, hash, or zoned (geo) on shard key | `mongos` router + config servers (replica set) hold chunk map | Balancer migrates "chunks" (default 64-128MB) between shards automatically |
| **DynamoDB** | Hash on partition key (+ optional sort key), internally consistent-hash-like | Fully managed, invisible to client | Automatic adaptive capacity + partition splits on size (10GB) or throughput |
| **Cassandra** | Consistent hashing (token ring) | Coordinator node = any node (peer-to-peer, gossip) | `nodetool` streaming; vnodes reduce blast radius |
| **Elasticsearch** | Hash of doc `_id` into fixed N primary shards | Coordinating node | **Cannot** change primary shard count without reindexing — a major gotcha |

## Pros & Cons / Trade-offs

**Pros**
- Near-linear write and storage scaling beyond one machine's disk/CPU/memory limits.
- Blast-radius containment: one shard's outage/slow query doesn't take down the whole dataset.
- Enables tenant isolation (dedicated shard per large customer) for noisy-neighbor control.

**Cons**
- Cross-shard joins/transactions become distributed problems (2PC, sagas) — slower, more failure modes.
- Secondary indexes not on the shard key require either a scatter-gather query or a separate global index service (extra write cost to keep in sync).
- Operational complexity multiplies: migrations, schema changes, backups now happen N times.
- Rebalancing is never free — it's a background copy job competing for I/O/network with live traffic.

## Real-World Scenarios

- **Bad shard key**: sharding a chat app by `created_at` (range) → all new messages hit the newest/last shard = classic hot shard. Fix: hash on `conversation_id`, or composite key `hash(user_id) + timestamp`.
- **Celebrity/tenant hot key**: hash sharding by `user_id` still fails if one user (celebrity account, huge tenant) generates disproportionate traffic — needs key salting (`user_id#0..9`) or a dedicated shard.
- **Cross-shard query avoidance**: e-commerce sharded by `customer_id` — "all orders for customer" is a single-shard query (fast); "total revenue today across all customers" requires scatter-gather across every shard or a separate OLAP/analytics pipeline (Citus columnar, or export to Snowflake/BigQuery).
- **Vitess at YouTube/Slack scale**: MySQL sharded to hundreds of shards behind `vtgate`, so app code mostly still writes plain SQL; VSchema decides shard(s) transparently, resharding done online via VReplication without downtime.
- **DynamoDB adaptive capacity**: a partition exceeding 3000 RCU/1000 WCU or 10GB triggers an automatic split — but poorly chosen partition keys (e.g., a boolean `status` field) still throttle because splits can't fix low-cardinality keys.

## Nuances & Gotchas

- **Hot-shard trap from monotonic keys**: auto-increment PK or ISO timestamp as shard key concentrates all writes on one shard/node — the single most common sharding design mistake. Always check key cardinality *and* write distribution over time, not just cardinality.
- **Low cardinality shard keys** (e.g., `country`, `status`, boolean flags) cap max shard count and guarantee imbalance — DynamoDB, MongoDB, Cassandra all suffer this identically regardless of vendor.
- **Resharding is a live migration, not a config change**: real systems (Vitess VReplication, MongoDB chunk migration) copy data in the background then do an atomic metadata cutover; get this wrong and you get duplicate writes or brief unavailability during cutover.
- **Elasticsearch's fixed primary shard count** is a classic footgun — under-provisioning shard count at index creation forces a full reindex later; there's no online resharding of primaries (only shrink/split with constraints).
- **Cross-shard transactions**: MongoDB and Citus support distributed transactions (2PC) but at real latency cost (extra round trips, prepare/commit phases) — teams often redesign schemas to make transactions single-shard instead (denormalize, co-locate related data by shard key).
- **Secondary index fan-out**: querying by a non-shard-key attribute means either (a) scatter-gather to all shards (linear cost growth with shard count) or (b) maintaining a global secondary index (DynamoDB GSI, Elasticsearch as a side index) that's eventually consistent and costs double writes.
- **Rebalancing storms**: triggering a rebalance during peak traffic competes for network/disk I/O with production queries — MongoDB's balancer and Cassandra's `nodetool repair`/streaming are both notorious for causing latency spikes if not scheduled/throttled carefully.
- **Directory service as hidden SPOF**: MongoDB config servers or Vitess's topology server (etcd/ZooKeeper) look like "just metadata" but if they're unavailable, routing breaks cluster-wide even though shards themselves are healthy — must be replicated (3+ nodes) and monitored independently.
- **Co-location for joins**: Citus's trick — distribute related tables (e.g., `orders` and `order_items`) by the *same* shard key (`customer_id`) so joins stay local to one worker node instead of fanning out; this is the standard pattern to avoid the cross-shard join tax.
- **Shard key is effectively immutable**: changing it later means a full data migration equivalent to re-sharding from scratch — choose it based on the dominant query pattern up front, not on what's convenient at schema-design time.
