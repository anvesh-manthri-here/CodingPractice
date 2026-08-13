# Change Data Capture

> **TL;DR:** CDC streams every row-level insert/update/delete out of a database as it happens, most reliably by tailing the DB's transaction log (WAL/binlog), turning the DB into an event source for search sync, caches, and the transactional outbox pattern.

## Quick Reference

| Approach | Reads From | App Changes? | Captures Deletes? | Overhead on DB | Latency |
|---|---|---|---|---|---|
| Log-based | WAL (Postgres) / binlog (MySQL) / oplog (Mongo) | None | Yes | Low (async log read) | ms–sub-second |
| Trigger-based | AFTER INSERT/UPDATE/DELETE triggers → shadow table | Schema only | Yes | High (extra write per txn) | ms but slows writes |
| Polling/timestamp | `updated_at` column scans | Requires column | No (hard/impossible) | Medium (repeated queries) | seconds–minutes |
| Dual writes (anti-pattern) | App writes to DB + queue | Yes, every write path | N/A | N/A | Race-condition prone |

## What It Is
- Mechanism to capture and propagate every data-changing event (insert/update/delete) from a source-of-truth database to downstream consumers.
- Converts a database from a passive store into an event stream — "turn the database inside out" (Kleppmann).
- Core tools: **Debezium** (Kafka Connect source connectors for Postgres/MySQL/MongoDB/SQL Server/Oracle), AWS DMS, Maxwell's Daemon (MySQL binlog), Fivetran/Airbyte (batch-oriented), Postgres logical replication slots.

## Responsibilities
- Detect every committed row change exactly once per transaction, in commit order.
- Preserve before/after row images (old value + new value) for updates.
- Represent deletes as first-class events, not silent absence.
- Emit events with enough metadata (table, PK, LSN/binlog position, txn ID, timestamp) for downstream idempotency and ordering.
- Survive consumer/connector restarts without data loss (resumable offsets).

## How It Works
**Log-based (the winning approach):**
1. DB writes every change to its write-ahead log (Postgres WAL, MySQL binlog, MongoDB oplog) *before* it's visible in the table — this log already exists for crash recovery/replication.
2. CDC connector registers as a logical replica (Postgres: `pgoutput`/`wal2json` replication slot; MySQL: registers as a replica reading binlog via `ROW` format).
3. Connector parses log entries into structured change events, publishes to Kafka/Kinesis/Pulsar — one topic per table typically.
4. Consumers read the stream; connector tracks its position (LSN/GTID) so it resumes exactly where it left off after a crash.

```
App -> DB (commit) -> WAL/binlog -> Debezium connector -> Kafka topic -> [search indexer, cache invalidator, downstream DB]
```

**Trigger-based:** DB trigger fires on every write, copies old/new row into a shadow/audit table or queue; a separate poller drains it. Doubles write I/O, adds latency to the original transaction, complex to maintain per-table triggers.

**Polling/timestamp-based:** Periodic `SELECT * WHERE updated_at > last_poll_time`. Simple but misses hard deletes (row is just gone), misses rapid updates between polls (only last state seen), and clock skew/missing indexes cause missed rows.

## Types / Classifications
- **By capture mechanism:** log-based, trigger-based, query/polling-based, dual-write (avoid).
- **By delivery mode:** streaming (Kafka topics, near real-time) vs batch/micro-batch (Fivetran syncs every N minutes).
- **By granularity:** row-level (most CDC tools) vs statement-level (rare, harder to make idempotent).
- **By snapshot handling:** initial snapshot + streaming (Debezium snapshots existing table then switches to log-tailing) vs streaming-only (misses pre-existing data).

## Where It Fits
- Sits between OLTP database and messaging layer (Kafka Connect is the de facto host for Debezium connectors).
- Upstream of: search indexes (Elasticsearch/OpenSearch), caches (Redis), data warehouses (Snowflake/BigQuery via sink connectors), read replicas/materialized views, other microservices' local stores.
- Replaces brittle dual-writes and nightly ETL batch jobs in event-driven architectures.

## Common Patterns & Real-World Tools

**Transactional Outbox Pattern** — solves the "update DB + publish event atomically" problem:
1. Service writes business row AND an `outbox` row in the *same* local DB transaction (single ACID commit, no distributed transaction).
2. Debezium tails the WAL, picks up the outbox table's inserts, publishes to Kafka.
3. Outbox row deleted/archived after publish (Debezium supports this via the outbox event router SMT).
- Guarantees the event is published if and only if the business change committed — no dual-write race.

**Search index sync** — Debezium → Kafka → Kafka Connect Elasticsearch sink keeps a search index eventually consistent with Postgres/MySQL without dual writes from app code (used at scale by Shopify, Netflix DBLog).

**Cache invalidation** — CDC event on row change → consumer deletes/updates the corresponding Redis key, avoiding stale-cache bugs from forgotten manual `cache.del()` calls scattered across the codebase.

**Legacy system strangling** — CDC feeds new microservice's read model from the legacy monolith's DB without touching legacy code (strangler fig pattern).

**Cross-region/multi-DB sync** — AWS DMS or Debezium replicate Postgres → Aurora/Snowflake for analytics without impacting OLTP load.

## Pros & Cons / Trade-offs

| | Log-based | Trigger-based | Polling |
|---|---|---|---|
| Pros | No app/schema changes, captures deletes, minimal write-path overhead, ordered by commit | No log access needed (works on managed DBs without log access), simple mental model | Zero DB config, works anywhere, easy to reason about |
| Cons | Requires log access/replication privileges (some managed DBs restrict this), format changes across DB versions, needs Kafka/broker infra | Slows every write, trigger sprawl, doesn't scale, hard to evolve schema | Misses deletes, misses intermediate states, polling lag, load on DB from repeated scans |
| Ops cost | Kafka Connect cluster, connector monitoring, schema registry | Low infra, but DB-coupled logic | Cron/scheduler, low infra |

## Real-World Scenarios
- **Debezium + Postgres logical decoding**: e-commerce order service writes `orders` + `outbox` row transactionally; Debezium streams outbox events to Kafka for inventory, shipping, and notification services — no 2PC.
- **MySQL binlog → Elasticsearch**: product catalog changes in MySQL auto-sync to Elasticsearch within ~1s via Debezium MySQL connector + ES sink connector, keeping search results fresh without app-level double writes.
- **Cache invalidation at scale**: Uber/LinkedIn-style pattern — CDC event triggers precise Redis key invalidation instead of TTL-only expiry, cutting stale-read windows from minutes to sub-second.
- **DynamoDB Streams**: AWS-native log-based CDC (no external connector needed) feeding Lambda for downstream cache/search updates — same concept, managed.

## Nuances & Gotchas
- **Ordering is per-partition, not global**: Kafka topic partitioned by PK preserves per-row order, but cross-table/cross-row causal ordering (e.g., `orders` before `order_items`) is NOT guaranteed unless you architect for it (single topic, or join/buffer downstream).
- **Exactly-once is a myth end-to-end**: Debezium+Kafka give effectively-once via log offsets, but consumer-side effects (writing to ES, Redis) are typically at-least-once — downstream consumers MUST be idempotent (use PK + version/LSN as dedup key).
- **Snapshot + stream race**: initial table snapshot and log-streaming can double-emit or race if not coordinated; Debezium's incremental snapshotting (DBLog algorithm) mitigates but isn't foolproof under heavy concurrent writes.
- **Schema evolution breaks consumers**: adding/dropping a column changes the event schema; use a schema registry (Confluent Schema Registry with Avro/Protobuf) with compatibility rules, or consumers silently misparse fields.
- **WAL/binlog retention and connector lag**: if the CDC connector falls behind or dies, Postgres WAL grows unbounded (replication slot holds it) and can fill disk — monitor slot lag, set `max_slot_wal_keep_size`. MySQL binlog rotation can outrun a slow connector and lose data.
- **TOASTed/large columns in Postgres**: unchanged TOAST (large object) values may appear as `unchanged-toast-datum` placeholders in WAL events, not the real value — must configure `REPLICA IDENTITY FULL` to get complete before-images (at the cost of WAL volume).
- **Heartbeat needed for low-traffic tables**: if a table rarely changes, connector offset doesn't advance, WAL isn't reclaimed — Debezium heartbeat events solve this.
- **Managed DB restrictions**: some cloud DBs (early RDS, some serverless tiers) restrict logical replication slot access or binlog retention — verify before committing to log-based CDC; may force trigger/polling fallback.
- **Distributed transactions across services are still unsolved**: CDC gives reliable single-DB event emission, but sagas/compensating transactions are still needed for true cross-service consistency — CDC is a building block, not a full solution.
