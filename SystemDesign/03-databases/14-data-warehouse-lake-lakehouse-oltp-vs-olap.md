# Data Warehouse, Lake, Lakehouse — OLTP vs OLAP

> **TL;DR:** OLTP engines optimize for many small row reads/writes (row store, indexes); OLAP engines optimize for scanning billions of rows for aggregates (columnar store, vectorized execution). Warehouses curate structured data (schema-on-write); lakes hoard raw data cheaply (schema-on-read); lakehouses (Delta Lake, Iceberg, Hudi) add ACID/schema/time-travel on top of lake storage, closing the gap.

## Quick Reference

| Dimension | OLTP | OLAP |
|---|---|---|
| Workload | Point reads/writes, short txns | Aggregations over large scans |
| Storage layout | Row-oriented | Column-oriented |
| Query latency | ms | seconds–minutes |
| Concurrency | High (thousands of small txns) | Low-moderate (few heavy queries) |
| Index style | B-tree on PK/FK | Zone maps, min/max, bloom filters |
| Example engines | Postgres, MySQL, Oracle, DynamoDB | Snowflake, BigQuery, Redshift, ClickHouse |

| Storage paradigm | Schema | Format | ACID | Example |
|---|---|---|---|---|
| Data Warehouse | Schema-on-write | Proprietary columnar | Yes | Snowflake, Redshift, BigQuery, Teradata |
| Data Lake | Schema-on-read | Raw files (Parquet/CSV/JSON) | No | S3 + Hive, ADLS, HDFS |
| Lakehouse | Schema enforced, evolvable | Open table format on object store | Yes | Delta Lake, Apache Iceberg, Apache Hudi |

## What It Is
- **OLTP** (Online Transaction Processing): systems of record — orders, payments, inventory. Optimized for correctness and low-latency mutation of individual rows.
- **OLAP** (Online Analytical Processing): systems of insight — dashboards, BI, ML feature aggregation. Optimized for throughput over huge column scans, not per-row latency.
- **Data Warehouse**: centralized, curated, structured store for reporting; data is cleaned/modeled before load (star/snowflake schemas).
- **Data Lake**: cheap, scalable storage (object storage) holding raw data in native/semi-structured form; schema applied at query time.
- **Lakehouse**: architecture layering transactional metadata (table format) over lake files so the lake behaves like a warehouse — ACID, upserts, time travel — while keeping open formats and cheap storage.

## Responsibilities
- OLTP engine: enforce constraints, isolation levels, referential integrity, durability (WAL), serve app-facing APIs.
- OLAP engine: vectorized/SIMD execution, predicate pushdown, columnar compression, query planning/cost-based optimization across huge scans.
- Warehouse: governance, BI semantic layer, curated marts, strict SLAs for reporting.
- Lake: ingest anything cheaply (logs, images, clickstream, IoT), decouple storage from compute, support ML/data science exploration.
- Lakehouse: unify batch + streaming, support both BI and ML on one copy of data, provide table-level ACID and schema evolution.

## How It Works
**Row store (OLTP):** a row's fields stored contiguously on disk page → `SELECT * FROM orders WHERE id=5` reads one page. Writes are cheap (single page update + WAL append).

**Column store (OLAP):** each column stored contiguously and compressed (RLE, dictionary encoding) → `SELECT AVG(amount) FROM orders` reads only the `amount` column, skips others via zone maps/min-max stats. Point lookups are expensive (must reconstruct row across column files); this is why one engine rarely serves both well — the physical layout trade-off is fundamental, not just tuning.

**Lakehouse table format mechanics** (Delta/Iceberg/Hudi):
- Data files (Parquet) written to object storage (S3/ADLS/GCS), immutable.
- A transaction log / metadata layer tracks which files constitute the current table version:
  - Delta Lake: `_delta_log` JSON + Parquet checkpoint files, Spark-native.
  - Iceberg: manifest lists → manifests → data files, engine-agnostic (Spark, Trino, Flink, Snowflake all read it).
  - Hudi: timeline + copy-on-write or merge-on-read for streaming upserts.
- Writers commit new metadata atomically (optimistic concurrency, conditional PUT) → gives ACID without a database engine.
- Readers pin a snapshot → time travel (`VERSION AS OF`), consistent reads during concurrent writes.

```
OLTP DB ──CDC/batch──▶ raw zone (lake) ──transform──▶ curated zone (lakehouse tables) ──▶ BI/ML
   (row store)            (Parquet/JSON)            (Delta/Iceberg + ACID)
```

## Types / Classifications
- **OLTP isolation levels**: Read Committed, Repeatable Read, Serializable — trade consistency for concurrency.
- **OLAP query engines**: MPP warehouses (Redshift, BigQuery, Snowflake) vs. query-on-lake engines (Trino, Presto, Athena, Spark SQL) vs. real-time OLAP (ClickHouse, Druid, Pinot for sub-second dashboards on streaming data).
- **Lake zones**: bronze (raw)/silver (cleaned)/gold (aggregated) — medallion architecture (Databricks convention).
- **Table format flavors**: copy-on-write (rewrite files on update, faster reads) vs merge-on-read (log deltas, faster writes, compaction needed) — Hudi exposes both explicitly; Iceberg/Delta lean copy-on-write by default with merge-on-read options.

## Where It Fits
- App → OLTP DB (source of truth) → CDC (Debezium) or batch extract → lake/warehouse → BI tools (Looker, Tableau, Power BI) and ML pipelines.
- Lakehouse sits at the convergence: same Parquet files serve Spark ML jobs and SQL BI queries — no separate warehouse copy needed.
- Streaming: Kafka → Flink/Spark Structured Streaming → lakehouse table (Hudi/Delta support streaming upserts) → near-real-time analytics.

## Common Patterns & Real-World Tools
- **ETL** (Extract-Transform-Load): transform before load; classic warehouse pattern (Informatica, Talend) — enforces schema early, expensive compute needed upfront, slower to adapt to new sources.
- **ELT** (Extract-Load-Transform): load raw first, transform in-warehouse/lake using SQL (dbt) — leverages cheap elastic compute (Snowflake/BigQuery), faster iteration, dominant pattern since ~2018.
- **CDC**: Debezium + Kafka streams DB row changes into lake/warehouse continuously instead of nightly batch dumps.
- **dbt**: the ELT transformation layer — version-controlled SQL models, tests, lineage, runs inside the warehouse/lakehouse compute.
- **Iceberg/Delta as the "open table" bet**: Snowflake, Databricks, Redshift, BigQuery, Trino all now read Iceberg tables directly — avoids vendor lock-in on storage format.

## Pros & Cons / Trade-offs
| Approach | Pros | Cons |
|---|---|---|
| Warehouse | Fast BI queries, strong governance, mature SQL tooling | Expensive storage, rigid schema, proprietary lock-in, slow to ingest unstructured data |
| Lake | Cheap storage, stores anything, decoupled compute, great for ML | No ACID (classic Hive tables), "data swamp" risk, poor BI query latency, no upserts |
| Lakehouse | ACID + schema evolution + cheap storage + one copy of data | Younger tooling, compaction/small-file management overhead, still maturing concurrent-writer semantics |
| ETL | Predictable, governed, transform once | Rigid, slow to add sources, requires upfront schema design |
| ELT | Flexible, fast onboarding of new sources, reprocessable | Raw data sprawl, transform logic scattered if not disciplined (mitigated by dbt) |

## Real-World Scenarios
- **E-commerce checkout**: Postgres/DynamoDB OLTP handles order writes at p99 <10ms; nightly/streaming CDC pushes to Snowflake for revenue dashboards — never run analytics queries against the OLTP replica in production without a read replica, they'll starve transactional throughput.
- **Netflix/Uber-scale lakehouse**: S3 + Iceberg tables, Spark for ETL, Trino for ad-hoc SQL, same files feed ML feature stores — avoids maintaining a separate warehouse copy of petabytes of data.
- **Real-time fraud dashboard**: ClickHouse or Druid ingest Kafka events directly for sub-second aggregation queries — neither a row-store OLTP nor a batch warehouse meets the latency bar.
- **Startup on a budget**: BigQuery/Snowflake with ELT + dbt — skip building a lake entirely until data volume/variety justifies it (dbt handles the "T", warehouse compute is elastic).

## Nuances & Gotchas
- **Never point BI tools directly at your OLTP primary** — a single bad analytical query (full table scan for a report) can lock rows/exhaust connections and take down checkout. Use CDC replicas or a warehouse.
- **Column stores hate high-cardinality point updates** — Delta/Iceberg upserts rewrite whole Parquet files (copy-on-write) unless you use merge-on-read, causing write amplification; watch for "too many small files" degrading scan performance — needs periodic compaction (`OPTIMIZE` in Delta, `rewrite_data_files` in Iceberg).
- **Schema-on-read is a governance trap** — "we'll figure out the schema later" often means nobody does, and the lake becomes an unqueryable swamp; medallion architecture (bronze/silver/gold) and enforced silver-layer contracts mitigate this.
- **Lakehouse concurrent writers**: optimistic concurrency control means concurrent writes to overlapping partitions can fail/retry storms under high-frequency streaming ingestion — Hudi's async compaction and Iceberg's row-level delete files exist specifically to reduce contention.
- **CDC lag and schema drift**: Debezium pipelines break silently when source DB schema changes (column added/renamed) — need schema registry (Confluent Schema Registry) or Iceberg schema evolution to avoid pipeline failures downstream.
- **Columnar compression ratios lie about cost**: OLAP storage looks cheap per GB, but reprocessing/backfills at scale (rewriting years of Parquet for a schema fix) can dwarf the original ETL cost — plan partitioning (by date) up front, it's expensive to retrofit.
- **"Real-time" OLAP is a different beast**: ClickHouse/Druid/Pinot trade some SQL flexibility and consistency for sub-second latency on streaming ingest — don't assume Snowflake/BigQuery batch-oriented warehouses can hit those latencies without re-architecting (materialized views, streaming inserts have limits).
- **ELT pushes compute cost into the warehouse** — a runaway dbt model doing cross joins on billions of rows shows up as a surprise Snowflake/BigQuery bill, not a slow query; cost governance (query tagging, resource monitors) matters as much as correctness.
