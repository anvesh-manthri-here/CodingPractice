# Relational Databases and ACID

> **TL;DR:** Relational DBs organize data into tables with typed columns and enforce structural + transactional integrity (ACID) via WAL, locking/MVCC, and undo/redo logs; choose them when you need strong consistency, joins, and ad-hoc queries over structured data.

## Quick Reference
| Concept | Key Fact |
|---|---|
| Atomicity | All-or-nothing; enforced via undo log / rollback segments |
| Consistency | App-defined invariants (constraints, FKs) hold before/after txn — DB enforces constraints, not business logic |
| Isolation | Concurrent txns appear serial; enforced via locks or MVCC; level is tunable |
| Durability | Committed data survives crash; enforced via WAL (write-ahead log) fsync |
| Default isolation | Postgres/Oracle: Read Committed; MySQL InnoDB: Repeatable Read; SQL Server: Read Committed |
| WAL | Log written to disk before data pages (redo log) |
| MVCC | Postgres, Oracle, InnoDB use row versioning to avoid read locks |
| Primary keys | Unique, non-null, one per table, often clustered index (MySQL/SQL Server) |
| Foreign key | Enforces referential integrity between tables |
| Normalization | 3NF reduces redundancy; denormalize for read-heavy OLAP |
| CAP tradeoff | Single-node RDBMS = CA; distributed SQL (CockroachDB, Spanner) trades latency for CP |

## What It Is
- Data modeled as **tables** (relations): rows (tuples) x columns (attributes), each column typed and constrained.
- **Primary key (PK)**: uniquely identifies a row; **foreign key (FK)**: column referencing another table's PK, enforcing referential integrity.
- **Joins**: combine rows across tables via key equality (INNER, LEFT/RIGHT OUTER, FULL, CROSS) — the core operation that makes normalization practical.
- Schema is enforced at write time (schema-on-write), unlike document stores (schema-on-read).
- SQL is the query language: declarative, set-based, optimizer picks execution plan (index scan, hash join, nested loop, merge join).

## Responsibilities
- Enforce structural integrity: types, NOT NULL, UNIQUE, CHECK, FK constraints.
- Guarantee transactional correctness (ACID) across concurrent clients.
- Provide durable storage surviving process/OS/power crashes.
- Optimize and execute arbitrary declarative queries (query planner/optimizer, statistics, indexes).
- Manage concurrency control so readers/writers don't corrupt or block each other unnecessarily.

## How It Works
**Atomicity** — a multi-statement transaction either fully commits or fully rolls back.
- Implemented via **undo log** (rollback segments in Oracle/InnoDB): before modifying a page, old value is logged; on ROLLBACK or crash mid-txn, undo log reverts changes.
- Multi-statement failure (e.g., statement 3 of 5 errors) triggers automatic rollback of the whole txn unless savepoints used.

**Consistency** — txn moves DB from one valid state to another per constraints (PK/FK/CHECK/triggers).
- This is the *weakest* guarantee to reason about: DB enforces declared constraints only; it does NOT guarantee your business logic is correct (e.g., "balance can't go negative" needs an explicit CHECK or app-level enforcement).
- Technically a consequence of A+I+D, not an independently implemented mechanism.

**Isolation** — concurrent txns don't see each other's uncommitted or interleaved effects, controlled by isolation level.
- **Locking (2PL)**: shared/exclusive row & table locks, held until commit (two-phase locking) — used by SQL Server, MySQL (some paths).
- **MVCC**: each row has version(s) with txn IDs (xmin/xmax in Postgres); readers see a consistent snapshot without blocking writers. Used by Postgres, InnoDB, Oracle.
- Isolation levels (ANSI SQL), weakest to strongest: Read Uncommitted → Read Committed → Repeatable Read → Serializable. Higher = fewer anomalies, more blocking/aborts.
- Anomalies prevented per level: dirty read (RC+), non-repeatable read (RR+), phantom read (Serializable, or RR in InnoDB via next-key locks).

**Durability** — once committed, data survives crash.
- **WAL (write-ahead log)**: every change is appended to a sequential log and `fsync`'d to disk *before* the transaction is acknowledged as committed; data pages can be flushed later (lazy checkpointing).
- On crash recovery: **redo** replays committed-but-not-yet-flushed WAL entries; **undo** rolls back in-flight uncommitted txns.
- Group commit batches concurrent fsyncs to amortize disk I/O cost.

```
Client -> COMMIT -> WAL record appended + fsync -> ACK "committed"
                          |
                    (async) data pages flushed to disk / checkpoint
Crash -> replay WAL (redo committed, undo uncommitted) -> consistent state
```

## Types / Classifications
| Isolation Level | Dirty Read | Non-repeatable Read | Phantom Read | Typical Mechanism |
|---|---|---|---|---|
| Read Uncommitted | Possible | Possible | Possible | rarely used (MySQL only) |
| Read Committed | Prevented | Possible | Possible | per-statement snapshot |
| Repeatable Read | Prevented | Prevented | Possible (SQL std) / Prevented (InnoDB) | per-txn snapshot + next-key locks |
| Serializable | Prevented | Prevented | Prevented | SSI (Postgres), strict 2PL, or predicate locks |

- **OLTP vs OLAP**: OLTP (Postgres, MySQL) optimized for many small txns; OLAP (Snowflake, Redshift, ClickHouse) optimized for large scans/aggregations, often columnar.
- **Single-node vs distributed SQL**: traditional RDBMS (Postgres/MySQL) vs NewSQL (CockroachDB, YugabyteDB, Google Spanner) which add horizontal sharding + distributed consensus (Raft/Paxos) while keeping ACID + SQL.

## Where It Fits
- Sits as the system-of-record layer behind app servers; typically accessed via connection pool (PgBouncer, HikariCP) since connections are expensive (each ~5-10MB in Postgres).
- Read replicas (async/streaming replication) offload read traffic; writes go to primary — introduces replication lag, a consistency trade-off outside single-node ACID.
- Paired with caching (Redis) in front for hot reads, and CDC (Debezium reading WAL) to stream changes into Kafka/search indexes/data lakes.
- In microservices, often one DB per service (avoids cross-service joins/txns); cross-service consistency handled via sagas, not distributed ACID transactions.

## Common Patterns & Real-World Tools
| Engine | Isolation Default | Concurrency Model | Notable Traits |
|---|---|---|---|
| PostgreSQL | Read Committed | MVCC | Rich types (JSONB, arrays), extensible (extensions), strong standards compliance, no clustered index by default |
| MySQL (InnoDB) | Repeatable Read | MVCC + gap/next-key locks | Clustered index on PK (data stored in PK order), simpler replication (binlog), widely hosted (RDS/Aurora) |
| SQL Server | Read Committed | Locking (+ optional RCSI/MVCC-like snapshot) | Tight Windows/.NET integration, columnstore indexes, strong tooling (SSMS) |
| Oracle | Read Committed | MVCC (undo-segment based) | Enterprise features (RAC, partitioning, flashback query), highest licensing cost |
| Aurora / CockroachDB / Spanner | varies | distributed MVCC + consensus | Horizontal scale with ACID; Spanner uses TrueTime for external consistency |

- Migration tools: Flyway, Liquibase for schema versioning.
- CDC: Debezium taps WAL/binlog for event streaming.

## Pros & Cons / Trade-offs
**Pros**
- Strong correctness guarantees (ACID) — critical for money, inventory, bookings.
- Flexible ad-hoc querying via SQL/joins without redesigning schema.
- Mature tooling: backups (pg_dump, xtrabackup), observability, ORMs.

**Cons**
- Vertical scaling limits on single-node writes; sharding is manual and painful (unless NewSQL).
- Schema rigidity slows iteration for highly variable/nested data.
- Joins across huge tables are expensive; denormalization or caching often needed at scale.
- Distributed ACID (2PC/XA) across services is slow and operationally fragile — mostly avoided in practice.

## Real-World Scenarios
- **Banking ledger**: strict ACID (Serializable or at least RR) required — atomic debit/credit, durability non-negotiable. Postgres/Oracle typical.
- **E-commerce inventory**: row-level locking or optimistic concurrency (version column) to prevent overselling under concurrent checkout.
- **Analytics dashboard**: read replica or ETL into OLAP warehouse (Snowflake/BigQuery) so heavy queries don't contend with OLTP writes.
- **Global low-latency app**: consider CockroachDB/Spanner for geo-distributed ACID, or accept eventual consistency (DynamoDB/Cassandra) if strict consistency isn't required.
- **Rapidly evolving product schema / catalog with variable attributes**: MongoDB/DynamoDB may fit better than rigid relational schema.

## Nuances & Gotchas
- **"Consistency" in ACID != "Consistency" in CAP** — different concepts entirely; conflating them in interviews is a red flag.
- **Default isolation is rarely Serializable** — most apps run Read Committed and are exposed to non-repeatable reads/write skew without realizing it; audit-critical logic needs explicit `SELECT ... FOR UPDATE` or Serializable.
- **MVCC bloat**: Postgres doesn't reclaim old row versions immediately — long-running transactions block VACUUM, causing table bloat and eventual transaction ID wraparound risk.
- **Phantom reads under RR**: SQL standard allows them at Repeatable Read, but InnoDB's next-key locking actually prevents them — engine behavior diverges from spec.
- **Lock escalation & deadlocks**: high-concurrency writes on hot rows (e.g., counters) cause lock contention; deadlock detectors kill one txn — app must retry.
- **WAL fsync is the durability bottleneck**: disabling `synchronous_commit` (Postgres) or setting `innodb_flush_log_at_trx_commit=2` boosts throughput but risks losing the last ~1s of commits on crash — a common silent trade-off in "we made it faster" incidents.
- **Replication lag breaks read-your-writes**: reading from an async replica right after a write to primary can return stale data — need read-after-write routing or synchronous replicas for critical paths.
- **FK constraints have real cost**: they add lookup overhead on every insert/delete and can cause surprising deadlocks under concurrent writes to parent/child tables; some high-throughput systems drop FKs and enforce integrity in the app layer.
- **Distributed transactions (2PC/XA) are a trap**: coordinator failure can leave participants blocked indefinitely; most systems favor sagas/outbox pattern over true distributed ACID.
- **Connection limits are a hard wall**: Postgres default max_connections ~100; under load, missing a pooler (PgBouncer) causes connection exhaustion before any query-level issue appears.
- **"Serializable" isolation still isn't free of anomalies across app + cache**: caching a value alongside a Serializable DB read can reintroduce inconsistency the DB itself never had.
