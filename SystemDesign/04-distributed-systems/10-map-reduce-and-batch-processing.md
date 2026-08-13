# MapReduce and Batch Processing

> **TL;DR:** MapReduce made distributed batch computation reliable and cheap on commodity hardware by pushing computation to data and re-executing failed tasks; Spark's in-memory DAG execution superseded it for anything iterative or interactive, leaving classic MapReduce as a historical/legacy engine.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Map stage | Parallel, stateless, runs on each input split (block) |
| Shuffle stage | Sort + partition + network transfer of intermediate KV pairs; the expensive stage |
| Reduce stage | Aggregates per-key values after shuffle |
| Fault tolerance | Re-run failed task on new node using immutable input (no checkpointing needed) |
| Data locality | Scheduler places map tasks on nodes holding the HDFS block (rack-aware) |
| HDFS block size | 128 MB (Hadoop 2/3 default), drives split count |
| Spark advantage | In-memory RDD/DataFrame caching, DAG scheduler, avoids re-reading disk each stage |
| Spark shuffle | Still disk+network bound; same fundamental cost as MapReduce shuffle |
| dbt | SQL-based transformation layer, runs "batch" transforms inside a warehouse (Snowflake/BigQuery) |
| Batch vs stream | Batch: bounded, high latency (minutes-hours), high throughput; Stream: unbounded, low latency (ms-sec) |
| Modern batch engines | Spark, Flink (batch mode), BigQuery, Trino/Presto |

## What It Is

- **MapReduce**: a programming model + execution framework (Google 2004 paper, Hadoop implementation) for processing huge datasets across clusters of unreliable, commodity machines.
- Core idea: express computation as two user functions — `map(k1,v1) -> list(k2,v2)` and `reduce(k2, list(v2)) -> list(v3)` — and let the framework handle parallelization, distribution, fault tolerance, and I/O.
- **Batch processing**: computing over a bounded, finite dataset (a day's logs, a table snapshot) as opposed to processing unbounded event streams continuously.

## Responsibilities

- **Framework (JobTracker/ResourceManager + TaskTrackers, or YARN)**: task scheduling, data locality placement, retry on failure, speculative execution of stragglers.
- **HDFS (or S3/GCS in modern setups)**: durable, replicated (3x) storage of input splits and intermediate/output data.
- **Map phase**: read a split, apply user `map()`, emit intermediate KV pairs to local disk, partitioned by key hash for reducers.
- **Shuffle phase**: framework sorts and transfers each reducer's partition across the network from every mapper.
- **Reduce phase**: merge-sort incoming partitions, apply user `reduce()`, write final output to durable storage.

## How It Works

```
Input (HDFS blocks) -> Map tasks (1 per split) -> local disk spill (sorted, partitioned)
        -> SHUFFLE (network fetch + merge-sort per reducer key range)
        -> Reduce tasks -> Output (HDFS, replicated)
```

- **Data locality**: scheduler tries map task placement so it reads the HDFS block from local disk/rack, avoiding network I/O for the largest data movement (input read is O(dataset size); shuffle can be smaller if map has selectivity/combiners).
- **Combiners**: optional local mini-reduce on the mapper side (e.g., partial sum) to cut shuffle volume before network transfer — critical optimization (word count: combine reduces shuffle bytes by orders of magnitude).
- **Fault tolerance mechanism**: inputs are immutable (HDFS files), so any failed map or reduce task can simply be re-run from scratch on another node; no distributed transaction or checkpoint protocol needed. Master detects failure via heartbeat timeout.
- **Speculative execution**: framework launches duplicate copies of slow ("straggler") tasks near job completion; first to finish wins, others killed — mitigates skewed hardware/data.
- **Why commodity hardware worked**: assume failures are the norm (Google's design point — cheap disks, cheap nodes, frequent crashes). Replication (3x in HDFS) + task re-execution gives reliability without expensive RAID/enterprise servers.

## Types / Classifications

| Model | Execution unit | State between stages | Fault recovery |
|---|---|---|---|
| Classic MapReduce (Hadoop 1/2) | Map + Reduce only, chained via disk | Written to disk/HDFS every stage | Re-run task from disk input |
| Spark RDD/DataFrame | Arbitrary DAG of transformations | Cached in memory (optionally spill to disk) | Lineage-based recompute (RDD lineage graph) |
| Flink batch | Batch is special case of streaming (bounded stream) | Pipelined execution, checkpoints | Checkpoint-based (from streaming engine) |
| dbt | SQL transformations compiled to warehouse queries | Warehouse tables (materialized) | Re-run SQL model; warehouse handles compute reliability |

## Where It Fits

- Sits at the **transform/compute layer** of the data stack, consuming from a data lake (S3/HDFS/GCS) or warehouse, producing derived tables/aggregates.
- Typical pipeline: **ingest** (Kafka/Kinesis/Fivetran) → **land** raw data (S3/data lake, Parquet/Iceberg) → **batch transform** (Spark/dbt) → **serve** (warehouse tables, BI tools, feature stores).
- Orchestrated by schedulers: Airflow, Dagster, or dbt Cloud triggering DAGs of jobs on a cadence (hourly/daily) or event trigger.
- Complements, doesn't replace, **stream processing** (Kafka Streams, Flink, Spark Structured Streaming) for low-latency needs; many architectures run both (Lambda/Kappa architecture).

## Common Patterns & Real-World Tools

- **Hadoop MapReduce**: legacy; still used in some enterprise ETL but largely replaced. Rare to write raw MapReduce jobs today.
- **Apache Spark**: DAG-based engine, in-memory RDD/DataFrame caching, unifies batch + micro-batch streaming + ML (MLlib) + graph (GraphX). Dominant general-purpose batch engine.
- **dbt (data build tool)**: doesn't move data — compiles SQL `SELECT` models into `CREATE TABLE/VIEW` statements executed by the warehouse (Snowflake, BigQuery, Redshift, Databricks SQL). Handles transformation, testing, lineage/docs; pushes compute down to warehouse engine rather than running its own cluster.
- **Presto/Trino**: interactive/batch SQL query engine over data lakes, federated across sources.
- **BigQuery/Snowflake**: serverless batch SQL engines abstracting away cluster management entirely.
- **Airflow/Dagster**: orchestrate multi-step batch DAGs (extract → Spark job → dbt run → export).

## Pros & Cons / Trade-offs

| Aspect | MapReduce (classic) | Spark |
|---|---|---|
| Iterative jobs (ML, graph) | Poor — re-reads/writes HDFS every iteration | Good — caches RDD in memory across iterations (10-100x faster reported for iterative ML) |
| Fault tolerance | Task re-execution from disk | Lineage-based recompute of lost partitions (cheaper, no full disk write needed) |
| Latency | High (seconds-minutes startup, disk-bound stages) | Lower (in-memory), but still not real-time |
| Programming model | Rigid map/reduce only | Rich DAG: map, filter, join, groupBy, window, SQL |
| Memory pressure | N/A (disk-based) | Can OOM/spill on skewed data or under-provisioned executors |
| Maturity/ecosystem | Very mature, stable, simple mental model | Larger surface area, more tuning knobs (partitions, memory fractions, shuffle configs) |

- **Batch vs Stream trade-off**: batch gives high throughput, simpler exactly-once semantics (idempotent overwrite of output partition), and easier debugging (rerun on same input); stream gives low latency but harder correctness (out-of-order events, watermarks, state stores).

## Real-World Scenarios

- **Daily revenue rollup**: Spark job reads a day's Parquet events from S3, joins with dimension tables, writes aggregated table to warehouse — classic embarrassingly parallel batch ETL.
- **ML feature engineering**: Spark computes rolling aggregates (7-day avg) over petabytes of historical data nightly, feeding a feature store for later online inference.
- **dbt transformation layer**: analytics engineers define `stg_orders.sql`, `fct_revenue.sql` models; dbt compiles and runs them as scheduled SQL batch jobs directly in Snowflake, no Spark cluster involved.
- **Word count / log analysis at Google-scale (historical)**: original MapReduce use case — index building, inverted index construction for search, still conceptually the canonical example.
- **Lambda architecture**: batch layer (Spark on full historical data) computes accurate long-window aggregates overnight; speed layer (Flink/Kafka Streams) gives approximate real-time view until batch catches up and overwrites it.

## Nuances & Gotchas

- **Shuffle is almost always the bottleneck**, not map or reduce compute — network + disk I/O + sort/serialization dominate. Watch shuffle read/write bytes in Spark UI before tuning anything else.
- **Data skew** kills parallelism: one hot key (e.g., a popular user_id) sends a disproportionate partition to one reducer/executor, causing a single straggler task to dominate job wall-clock time. Fix with salting keys, custom partitioners, or `skewJoin` hints (Spark 3+ adaptive query execution auto-handles some skew).
- **Small files problem**: many small map-side outputs or many small HDFS/S3 files create scheduling/metadata overhead disproportionate to data size; compact with `coalesce`/`repartition` or use table formats (Iceberg/Delta/Hudi) with auto-compaction.
- **Spark "in-memory" is not free**: without enough executor memory, RDDs spill to disk anyway, and it can be slower than expected; `spark.memory.fraction` and executor sizing matter a lot in practice.
- **Combiners are not guaranteed to run** exactly once in classic MapReduce — treat combiner logic as an optimization only (must be associative/commutative), never a correctness requirement.
- **Idempotency of batch writes**: reruns/backfills must overwrite (not append) output partitions, or you double-count; partition-by-date + `INSERT OVERWRITE` pattern is standard.
- **Lineage recompute in Spark can cascade expensively**: losing an executor deep in a long DAG with no checkpoint can trigger recomputation of a huge upstream chain; use `.checkpoint()` or persist to break long lineages for iterative algorithms.
- **dbt is not a compute engine** — all correctness/performance issues (skew, spill) live in the underlying warehouse; dbt failures are usually just bad SQL or misconfigured materializations (table vs incremental vs view).
- **Batch windows create staleness**: "daily batch" means dashboards are up to 24h stale — a common source of stakeholder confusion vs streaming dashboards; document SLAs explicitly.
- **Speculative execution can backfire** on jobs with side effects (e.g., writing to external non-idempotent APIs) — duplicate task execution assumes idempotent/output-only side effects.
