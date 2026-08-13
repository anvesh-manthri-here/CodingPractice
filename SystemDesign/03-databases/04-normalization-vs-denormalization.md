# Normalization vs Denormalization

> **TL;DR:** Normalization eliminates redundancy to guarantee write consistency and save storage, at the cost of joins; denormalization trades redundancy back in to speed up reads, at the cost of update anomalies and storage bloat. Pick based on read/write ratio and consistency needs, not dogma.

## Quick Reference

| Aspect | Normalization | Denormalization |
|---|---|---|
| Goal | Eliminate redundancy | Eliminate joins |
| Optimizes for | Write consistency, storage | Read latency, throughput |
| Costs | Join complexity, read fan-out | Update anomalies, storage, staleness |
| Typical fit | OLTP (banking, orders, inventory) | OLAP, read-heavy APIs, NoSQL docs |
| Key forms | 1NF, 2NF, 3NF (BCNF, 4NF beyond) | Embedding, duplication, materialized views |
| Common tools | Postgres, MySQL (InnoDB), Oracle | MongoDB, DynamoDB, Redis, Elasticsearch, Snowflake |
| Sync mechanism (denorm) | N/A | App-level writes, triggers, CDC (Debezium), `REFRESH MATERIALIZED VIEW` |

## What It Is
- **Normalization**: structuring relational schema so each fact is stored exactly once, via decomposition into tables linked by foreign keys, governed by "normal forms" (1NF-3NF, BCNF, 4NF/5NF).
- **Denormalization**: deliberately reintroducing redundancy (duplicate columns, embedded documents, precomputed aggregates) to avoid runtime joins/aggregations.
- Not opposites of "good vs bad design" — both are correctness/performance trade-offs applied selectively, often mixed in the same system (normalized OLTP core + denormalized read replicas/caches).

## Responsibilities
- Normalization protects **data integrity**: no update/insert/delete anomalies, single source of truth per fact.
- Denormalization protects **query performance**: bounded read latency, fewer joins/aggregations per request, predictable scaling of reads.
- Both must coexist with an explicit strategy for **how redundant copies stay in sync** (sync writes, async replication, eventual consistency window).

## How It Works

### Normal Forms — Anomalies Fixed

| Form | Rule | Anomaly it fixes | Example fix |
|---|---|---|---|
| **1NF** | Atomic columns, no repeating groups/arrays in a cell | Cannot query/index individual values; ambiguous multi-valued cells | Split `phone1,phone2` column into a `phones` table (one row per phone) |
| **2NF** | 1NF + no partial dependency on part of a composite PK | Update anomaly: non-key attr depends on only part of PK, duplicated per row | `(OrderID, ProductID) -> ProductName` — ProductName depends only on ProductID, so move to `Products` table |
| **3NF** | 2NF + no transitive dependency (non-key -> non-key) | Update anomaly: change `ZipCode` requires updating every row with that zip; also insert/delete anomalies | `EmployeeID -> ZipCode -> City` — move City/State to a `ZipCodes` table |
| **BCNF** | Every determinant is a candidate key (stricter 3NF) | Edge cases where 3NF still allows anomalies with overlapping candidate keys | Rare in practice; interview-table stakes only |

- Anomaly types normalization targets: **insertion** (can't add a fact without an unrelated fact — e.g., can't add a product without an order), **update** (same fact edited in N places, risk of drift), **deletion** (deleting a row loses unrelated info — e.g., deleting the last order for a customer loses customer address).

### Why Normalization Optimizes Writes/Storage
- Single-row updates: change `ProductName` once in `Products`, all `OrderItems` referencing it stay consistent automatically (no fan-out writes, no drift).
- Storage: no duplicated blobs of the same attribute values across millions of rows; FK is 4-8 bytes vs re-storing a full name/address string.
- Enforced via constraints (FK, UNIQUE, CHECK) — DB engine guarantees integrity, app code doesn't have to.
- Cost: reads now require JOINs across normalized tables — more query planning, index lookups, potential N+1 patterns in ORMs (Hibernate, ActiveRecord).

## Types / Classifications

### Denormalization Strategies

| Strategy | What it does | Cost |
|---|---|---|
| **Embedding** (document DBs) | Nest child data inside parent doc, e.g. MongoDB order doc embeds line items | Doc grows unbounded (16MB cap in MongoDB); update embedded field in every doc that has it |
| **Duplication / redundant columns** | Copy a field into another table to avoid join, e.g. store `customerName` on `Orders` row | Must update N rows on every name change, or accept staleness |
| **Materialized views** | Precompute a query result as a physical table, refreshed periodically | Storage + refresh cost (`REFRESH MATERIALIZED VIEW CONCURRENTLY` in Postgres); staleness between refreshes |
| **Read replicas w/ denormalized schema** | ETL/CDC pipeline reshapes normalized OLTP data into wide denormalized tables for analytics | Pipeline lag (seconds-minutes), infra to build/maintain (Debezium + Kafka + Spark) |
| **Precomputed aggregates/counters** | Store `likeCount` on a post row instead of `COUNT(*)` on likes table | Race conditions on concurrent increments; needs atomic ops (Redis `INCR`, Postgres row lock) |
| **Caching layer** | Redis/Memcached cache of joined/aggregated results | Cache invalidation complexity — "one of the two hard problems" |

## Where It Fits
- **OLTP systems** (order processing, banking ledgers, inventory): normalize to 3NF — writes are frequent, correctness is non-negotiable, transactions (ACID) enforce invariants across normalized tables.
- **OLAP / analytics warehouses** (Snowflake, BigQuery, Redshift): denormalize into star/snowflake schemas — fact table + denormalized dimension tables — reads dominate, batch ETL handles consistency.
- **Read-heavy APIs / microservices**: denormalize via CQRS — write model normalized, read model (materialized view or separate store) denormalized and eventually consistent.
- **NoSQL document/key-value stores** (MongoDB, DynamoDB, Cassandra): schema-on-write denormalization is the *default* design pattern — no joins available (or expensive), so you model around access patterns, not entities.
- **Hybrid**: Postgres/MySQL primary normalized for writes -> CDC (Debezium) streams to Elasticsearch/materialized read store for search and dashboards.

## Common Patterns & Real-World Tools
- **Postgres materialized views**: `CREATE MATERIALIZED VIEW`, refresh via cron or trigger; `CONCURRENTLY` avoids read locks during refresh.
- **DynamoDB single-table design**: deliberately denormalize multiple entity types into one table keyed by access pattern (PK/SK overloading) to avoid cross-table joins DynamoDB doesn't support.
- **MongoDB embedding vs referencing**: embed for 1:few, bounded, read-together data (address in user doc); reference (like a FK) for 1:many unbounded (user -> orders).
- **CQRS + event sourcing**: normalized write-side aggregate, denormalized read-side projections rebuilt from event log (Kafka topics + consumers materializing views).
- **Star schema in Kimball-style warehousing**: fact table (sales) with denormalized dimension tables (date, product, customer) — trades storage for scan simplicity.
- **Outbox pattern + CDC**: keeps denormalized caches/search indexes in sync with normalized source of truth without dual-write race conditions.

## Pros & Cons / Trade-offs

| | Normalization | Denormalization |
|---|---|---|
| Pros | No update anomalies; less storage; strong consistency; smaller write footprint | Fast reads; fewer/no joins; scales read throughput horizontally; fits document/columnar models |
| Cons | Query complexity (multi-way joins); read latency under load; harder to shard cleanly | Redundant data must be kept in sync; write amplification; storage growth; staleness windows; complex invalidation |
| Best when | Writes frequent, correctness critical, ad-hoc queries needed | Reads >> writes, access patterns known upfront, latency SLA tight |

## Real-World Scenarios
- **E-commerce checkout**: `Orders`, `OrderItems`, `Products`, `Customers` normalized in Postgres — inventory decrement and payment must be transactionally consistent; a stale duplicated price would cause billing errors.
- **Product listing page**: denormalize `Products` with embedded `avgRating`, `reviewCount` (precomputed) instead of joining/aggregating `Reviews` on every page load — updated async via a background job or trigger.
- **Twitter/X-style feed**: fan-out-on-write denormalization — precompute each follower's timeline (materialized) rather than joining Follows x Tweets at read time for celebrities with millions of followers.
- **DynamoDB e-commerce**: single table stores `USER#123` and `ORDER#456` items together, duplicating customer name onto the order item, because DynamoDB has no server-side joins.
- **Data warehouse for BI**: nightly ETL denormalizes normalized OLTP tables into a wide `fact_sales` table joined to dimension tables — analysts run `GROUP BY` without 6-way joins.

## Nuances & Gotchas
- **Dual-write race conditions**: writing to normalized source + denormalized copy separately (not atomically) leads to permanent drift under failure/retry — use CDC/outbox pattern instead of app-level dual writes.
- **"Denormalize for reads, pay at write time" is not free — it's a shift, not an elimination**: someone must run the sync job; forgetting this creates silent staleness bugs that surface as support tickets, not errors.
- **Over-normalization kills performance too**: 8-way joins on hot paths in Postgres can blow past latency SLAs even with good indexes — normalize to 3NF as default, then selectively denormalize hot paths, don't design for 5NF/6NF in OLTP.
- **Precomputed counters drift**: `likeCount` cached on a row will desync from actual `COUNT(*)` under concurrent writes/crashes — periodic reconciliation jobs are mandatory, not optional.
- **Materialized view refresh blocks or lags**: non-concurrent refresh locks the view for reads during rebuild; concurrent refresh needs a unique index and still leaves a staleness window — know your freshness SLA.
- **MongoDB 16MB document limit**: unbounded embedding (e.g., embedding all comments in a post doc) silently breaks at scale — must switch to referencing before hitting the ceiling, plan the migration early.
- **Sharding interacts with normalization**: normalized FK-joins across shards are expensive/impossible in most sharded systems (Vitess, Citus) — denormalizing to keep related data co-located on one shard is often mandatory, not optional, at scale.
- **NoSQL schema is access-pattern-first, not entity-first**: designing DynamoDB/Cassandra tables the way you'd design Postgres tables (normalized) leads to expensive scatter-gather queries — model the table per query, not per entity.
- **Denormalization hides schema evolution pain**: changing a duplicated field's type/format later means migrating every copy, whereas normalized single-source fields migrate once — factor this into which fields you duplicate.
