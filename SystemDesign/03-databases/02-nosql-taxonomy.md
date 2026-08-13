# NoSQL Taxonomy

> **TL;DR:** NoSQL isn't one thing — pick the data model (KV, document, wide-column, graph, time-series) that matches your access pattern, then accept denormalization and weaker consistency in exchange for horizontal scale and schema flexibility.

## Quick Reference

| Category | Data Model | Real Engines | Scale Mechanism | Consistency Default |
|---|---|---|---|---|
| Key-Value | opaque blob by key | Redis, DynamoDB, Memcached, Riak | consistent hashing, sharding | tunable (Redis: single-thread strong; DynamoDB: eventual/strong per-read) |
| Document | JSON/BSON per doc | MongoDB, Couchbase, Firestore | range/hash sharding on shard key | eventual (secondaries), tunable write concern |
| Wide-Column | column families, sparse rows | Cassandra, HBase, Bigtable, ScyllaDB | consistent hashing (Cassandra ring) / range-partitioned regions (HBase/Bigtable) | tunable quorum (Cassandra), strong (Bigtable/HBase via single master region) |
| Graph | nodes + edges + properties | Neo4j, Amazon Neptune, JanusGraph | hard to shard; mostly vertical or federated | strong (single-instance), causal cluster in Neo4j |
| Time-Series | timestamp + tags + metrics | InfluxDB, TimescaleDB, Prometheus | time-based partitioning/chunking | strong within shard, eventual across replicas |

## What It Is

- NoSQL = non-relational storage engines optimized for a specific access pattern instead of general-purpose ad-hoc query (SQL joins/aggregation).
- Trade ACID/relational algebra for horizontal partition-ability, flexible schema, and throughput at scale.
- "NoSQL" is an umbrella of five distinct data models, each with different CAP-theorem trade-offs — don't treat MongoDB and Cassandra as interchangeable.

## Responsibilities

- Serve high-throughput reads/writes with predictable latency at scale (millions of ops/sec).
- Handle horizontal partitioning transparently (sharding, consistent hashing, region splitting).
- Provide flexible/schema-less or schema-per-document modeling for evolving data.
- Offer tunable consistency/availability trade-offs (CAP) instead of one-size-fits-all ACID.
- Support model-specific query patterns: point lookup (KV), nested doc query (document), wide scans (wide-column), traversal (graph), range/rollup queries (time-series).

## How It Works

**Key-Value**: hash(key) → node via consistent hashing ring; O(1) get/put; no query language beyond key lookup (Redis adds data structures: lists, sets, sorted sets, hashes).

**Document**: stores self-contained JSON/BSON docs; shard key (hashed or ranged) determines placement; secondary indexes on doc fields enable rich queries without joins; aggregation pipelines (MongoDB) replace SQL joins via embedding or `$lookup`.

**Wide-Column**: rows keyed by partition key + clustering columns, grouped into column families; Cassandra uses a leaderless ring (every node equal, gossip protocol, tunable `CL=QUORUM/ONE/ALL`); Bigtable/HBase use master-region-server architecture with rows sorted lexicographically by row key across tablets — hot row-key ranges are the classic failure mode.

**Graph**: stores adjacency lists natively (index-free adjacency) so traversals are O(1) per hop instead of O(log n) join lookups; query via Cypher (Neo4j) or Gremlin (TinkerPop/JanusGraph); doesn't shard well because traversals cross partitions — most graph DBs scale vertically or via read replicas.

**Time-Series**: writes are append-mostly, ordered by time; data partitioned into time-bucketed chunks (Timescale "hypertables", Influx "shards"); downsampling/rollups and TTL-based retention policies purge old high-resolution data automatically; compression exploits monotonic timestamps + delta-of-delta encoding.

```
Client → Router/Coordinator → hash(partition key) → Shard/Node
                                     |
                         Replica set (async or quorum writes)
```

## Types / Classifications

| Model | Example Query | Not Good At |
|---|---|---|
| Key-Value | `GET user:123` | range queries, relationships |
| Document | find users where `address.city="NYC"` | multi-doc transactions at scale, joins |
| Wide-Column | scan `sensor_id` between t1 and t2 | ad-hoc secondary-index queries |
| Graph | shortest path A→B, friend-of-friend | bulk analytical scans, aggregation |
| Time-Series | avg(cpu) group by 5min over 30 days | non-temporal relational queries |

## Where It Fits

- **Caching / session store**: Redis, Memcached — sits in front of RDBMS to absorb read load.
- **Catalog / user profile / content management**: MongoDB, Couchbase — flexible schema, nested objects match app models 1:1.
- **Massive write-heavy telemetry / IoT / logs**: Cassandra, Bigtable, InfluxDB — linear write scale across commodity nodes.
- **Social graph, recommendation, fraud detection**: Neo4j, Neptune — relationship-first queries.
- **Metrics/monitoring**: Prometheus (short-term) + InfluxDB/Timescale (long-term retention + rollups).
- Sits alongside, not instead of, relational — most real systems are polyglot persistence (e.g., Postgres for orders, Redis for cache, Elasticsearch for search, S3 for blobs).

## Common Patterns & Real-World Tools

- **CQRS + event sourcing**: Kafka writes events, wide-column/doc store materializes read views.
- **Denormalization by embedding**: MongoDB embeds child docs (e.g., order + line items) to avoid joins — read-optimized, write-amplifying on updates.
- **Wide-column time-bucketing**: Cassandra table keyed by `(sensor_id, day)` partition + `timestamp` clustering column to bound partition size.
- **Cache-aside**: Redis in front of DynamoDB/Postgres, app manages invalidation.
- **Secondary index workaround**: DynamoDB Global Secondary Indexes (GSI) since native only supports primary-key access.
- **Graph + doc hybrid**: use Neo4j for relationship queries, MongoDB for entity attributes, synced via CDC (Debezium).

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| Key-Value | fastest, simplest, predictable latency | no query flexibility, no relationships |
| Document | flexible schema, natural app mapping | denormalization drift, weak multi-doc transactions (though MongoDB 4.0+ supports them, at a perf cost) |
| Wide-Column | massive write throughput, linear scale | query patterns must be known upfront (schema-on-write to row key design), no ad-hoc joins |
| Graph | fast multi-hop traversal | hard to horizontally scale, smaller ecosystem/tooling |
| Time-Series | efficient compression, retention policies | poor fit for non-time-ordered data, limited relational query |

## Real-World Scenarios

- **E-commerce product catalog**: MongoDB — products have wildly varying attributes per category; schema-less avoids sparse-column hell in relational.
- **Session/auth token store**: Redis with TTL — sub-millisecond reads, natural expiry, no durability requirement beyond seconds.
- **IoT sensor ingestion (millions of writes/sec)**: Cassandra or InfluxDB — write-optimized LSM-tree storage, horizontal ring scale, no single write bottleneck.
- **Netflix-scale user profile store**: DynamoDB or Cassandra — needs 99.99% availability across regions, tolerates eventual consistency on profile reads.
- **LinkedIn "people you may know"**: Neo4j/Neptune graph traversal — 3-hop relationship query in ms vs recursive SQL CTE that thrashes joins.
- **Uber trip telemetry dashboards**: TimescaleDB — SQL-compatible rollups (`time_bucket()`) plus PostGIS for geo, avoids relearning a new query language.

## Nuances & Gotchas

- **No joins means the join moves to app code or write time.** Denormalization = data duplication = update-anomaly risk; you now own consistency the DB used to guarantee.
- **Eventual consistency bites in read-after-write scenarios.** DynamoDB default eventual reads can return stale data milliseconds after a write — use `ConsistentRead=true` or accept UX glitches (e.g., "where did my comment go").
- **Cassandra hot partitions**: a poorly chosen partition key (e.g., partitioning by `day` on a viral event) sends all traffic to one set of replicas — design partition key for even distribution, not query convenience alone.
- **MongoDB unbounded document growth**: embedding an array that grows indefinitely (e.g., comments on a post) hits the 16MB BSON document limit and causes repeated document moves on disk.
- **Wide-column schema is query-driven, not entity-driven** — you must know your access patterns before modeling tables (Cassandra: "one table per query"); pivoting to a new query later often means a full data reshape/backfill.
- **Graph DBs don't scale traversals across shards** — sharding a graph breaks index-free adjacency; most graph workloads that "need to scale" actually need read replicas, not partitioning.
- **Secondary indexes are expensive or missing.** Cassandra secondary indexes perform poorly at scale (fan out to all nodes); DynamoDB GSIs are eventually consistent by default and cost extra write capacity.
- **Multi-document/multi-row transactions are limited or costly.** MongoDB multi-doc ACID transactions (since 4.0) work but tank throughput if overused — a sign you should've modeled as one document.
- **Compaction and tombstones**: Cassandra deletes create tombstones; too many unresolved tombstones (`tombstone_failure_threshold`) can make ranges unreadable until compaction runs — recurring on delete-heavy workloads (e.g., queues modeled in Cassandra, an anti-pattern).
- **Time-series cardinality explosion**: InfluxDB/Prometheus performance collapses when tag values are high-cardinality (e.g., tagging by `user_id` instead of `service_name`) — each unique tag combo creates a new series, blowing up index memory.
- **"NoSQL means no schema" is a myth** — schema moves from DB-enforced to app-enforced; without discipline (or a schema validation layer like MongoDB's JSON Schema validator) you get silent data-shape drift across app versions.
