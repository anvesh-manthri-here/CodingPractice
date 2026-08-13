# Transactions and Isolation Levels

> **TL;DR:** Isolation levels trade correctness for concurrency; the SQL standard defines four levels by which anomalies they permit, but "Repeatable Read" means genuinely different things in Postgres (snapshot isolation, no phantoms) vs MySQL InnoDB (next-key locking, no phantoms either, but via a different mechanism) — and only true Serializable (or SSI) catches write skew.

## Quick Reference

| Level | Dirty Read | Non-Repeatable Read | Phantom Read | Write Skew |
|---|---|---|---|---|
| Read Uncommitted | Possible | Possible | Possible | Possible |
| Read Committed | Prevented | Possible | Possible | Possible |
| Repeatable Read (standard) | Prevented | Prevented | Possible | Possible |
| Serializable | Prevented | Prevented | Prevented | Prevented |

| Engine | Default Level | RR = Phantoms? | Serializable Mechanism |
|---|---|---|---|
| PostgreSQL | Read Committed | RR blocks phantoms too (true snapshot isolation) | SSI (Serializable Snapshot Isolation) |
| MySQL InnoDB | Repeatable Read | RR blocks phantoms via next-key locks | Locking (2PL) + gap locks |
| Oracle | Read Committed | N/A (no true RR level exposed) | Locking-based, `SERIALIZABLE` = snapshot-based |
| SQL Server | Read Committed | Snapshot isolation available (`SNAPSHOT`) | Locking-based `SERIALIZABLE` |
| MongoDB (multi-doc txn) | Snapshot | N/A | `SERIALIZABLE` read concern + causal consistency |

## What It Is

- **Transaction**: a unit of work with ACID guarantees — Atomicity, Consistency, Isolation, Durability.
- **Isolation** specifically governs what concurrent transactions can observe of each other's uncommitted or concurrently-committed changes.
- The SQL-92 standard defines four levels as a *permission matrix* of anomalies, not as prescribed implementations — engines are free to implement stricter guarantees under a given name.

## Responsibilities

- Isolation level implementation decides: whether readers block on writers, whether writers block on readers, and what snapshot (if any) a transaction sees.
- Concurrency control mechanism (MVCC vs 2PL/locking) determines the *cost* of a given isolation guarantee.
- Anomaly prevention is the contract; the mechanism (locks, snapshots, predicate locks) is the implementation detail engineers must still understand for performance and correctness.

## How It Works

### The anomalies, defined
- **Dirty read**: T1 reads a row T2 wrote but hasn't committed; T2 rolls back → T1 read data that never existed.
- **Non-repeatable read**: T1 reads a row twice, gets different values because T2 committed an update between the two reads.
- **Phantom read**: T1 runs a range query twice, gets a different *set of rows* because T2 inserted/deleted rows matching the predicate.
- **Write skew**: two transactions each read overlapping data, then each write to *disjoint* rows based on what they read, violating an invariant that spans both rows — no single-row conflict is ever detected. Classic example: on-call doctors, both check "≥1 other doctor on call" and both go off duty simultaneously, violating "≥1 doctor on call."

### Two implementation families
- **Locking (2PL)**: shared/exclusive locks, held until commit (strict 2PL). Readers block writers and vice versa. MySQL InnoDB, SQL Server default `SERIALIZABLE`.
- **MVCC (Multi-Version Concurrency Control)**: each transaction sees a consistent snapshot; readers never block writers. Postgres, MySQL InnoDB (for RC/RR), Oracle.
- **SSI (Serializable Snapshot Isolation)**: MVCC snapshot + runtime tracking of read/write dependencies to detect and abort transactions that would create a serialization anomaly (used by Postgres's true `SERIALIZABLE`).

## Types / Classifications

1. **Read Uncommitted** — no isolation; reads can see uncommitted writes. Rarely used (some reporting workloads that tolerate dirty reads for speed).
2. **Read Committed** — each *statement* sees a fresh snapshot of committed data at statement-start. Default in Postgres, Oracle, SQL Server.
3. **Repeatable Read** — the *transaction* sees one snapshot for its entire duration (in snapshot-isolation engines) or holds locks on read rows (in locking engines).
4. **Serializable** — transactions behave *as if* executed one at a time in some serial order; strongest and most expensive.

## Where It Fits

- Sits between the application/ORM transaction boundary (`BEGIN`/`COMMIT`) and the storage engine's MVCC/lock manager.
- ORMs (Hibernate, ActiveRecord, SQLAlchemy) usually default to the DB's default level and rarely surface it — a common source of latent bugs.
- Distributed/NewSQL systems (CockroachDB, Google Spanner, YugabyteDB) implement **Serializable as the only or default level**, using clock synchronization (TrueTime, hybrid logical clocks) instead of a single-node lock manager.
- Read replicas and eventual consistency layers (Kafka consumers, async replicas) sit "outside" transactional isolation entirely — a different, weaker consistency model.

## Common Patterns & Real-World Tools

- **Postgres RC + explicit `SELECT ... FOR UPDATE`**: pattern to prevent lost updates without paying for full RR/Serializable.
- **MySQL InnoDB RR + gap locks**: prevents phantoms on indexed range scans by locking the "gaps" between index entries, not just existing rows.
- **Optimistic concurrency**: version column / `ROWVERSION` compared at commit, used with RC to emulate serializable-like guarantees cheaply (common in Django, EF Core).
- **Retry-on-serialization-failure**: standard pattern for Postgres `SERIALIZABLE`/SSI and CockroachDB — app must catch `40001` and retry the whole transaction.
- **Advisory locks** (`pg_advisory_lock`): app-level locking to serialize specific business logic without escalating the whole transaction's isolation.

## Pros & Cons / Trade-offs

| Level | Pros | Cons |
|---|---|---|
| Read Uncommitted | Max throughput, no blocking | Dirty reads = data integrity risk; almost never worth it |
| Read Committed | Good throughput, intuitive, low deadlock risk | Non-repeatable reads/phantoms can break multi-step invariants |
| Repeatable Read | Stable view for whole transaction | Higher abort/lock-wait rate; write skew still possible |
| Serializable | Strongest correctness guarantee | Highest abort rate (SSI) or lock contention (2PL); requires retry logic |

## Real-World Scenarios

- **Bank transfer double-check**: reading balance twice in RC can see it change mid-transaction (non-repeatable read) — use RR or `SELECT FOR UPDATE`.
- **Inventory oversell**: two transactions each read stock=1, both decrement — a **lost update**, prevented by RR-with-locking or optimistic version checks, not by plain RC.
- **On-call scheduling / meeting room double-booking**: classic write skew — only true Serializable (or an explicit constraint/exclusion constraint in Postgres) prevents it.
- **Postgres `EXCLUDE` constraints**: real-world workaround to catch write-skew-shaped bugs (e.g., overlapping bookings) at the DB level without paying for Serializable everywhere.
- **Reporting query on RU**: analytics dashboard reads uncommitted rows from a batch job mid-load — historically used to avoid blocking, now largely replaced by MVCC snapshots.

## Nuances & Gotchas

- **"Repeatable Read" is not one thing.** Postgres RR = full snapshot isolation, no phantoms, no non-repeatable reads, but write skew *is* still possible. MySQL InnoDB RR also blocks phantoms (via gap/next-key locking) — stricter than the SQL standard requires — but write skew is still possible in both.
- **Snapshot isolation ≠ Serializable.** This is the single most common staff-interview trap: SI prevents dirty/non-repeatable/phantom reads but NOT write skew, because it only checks for conflicts on rows actually written, not on the read set that informed the decision.
- **MySQL default is RR, Postgres default is RC.** Porting an app between them without setting isolation explicitly is a real source of production bugs (lost updates that "worked" on MySQL fail silently on Postgres).
- **Postgres `SERIALIZABLE` can abort with serialization failures (`SQLSTATE 40001`) under normal load** — app code MUST implement retry loops or transactions silently fail; this is often missed in code review.
- **Locking Serializable (SQL Server, MySQL) risks deadlocks** vs Postgres SSI which risks aborts — different failure mode, both need retry logic, teams often only handle one.
- **Long-running RR transactions cause bloat.** In Postgres MVCC, an old open snapshot prevents `VACUUM` from reclaiming dead tuples — a forgotten `BEGIN` in a debugging session can bloat a table for hours.
- **`SELECT FOR UPDATE` under RC vs RR behaves differently on concurrent updates**: in Postgres RC, `FOR UPDATE` re-reads the latest committed row after acquiring the lock (can silently change what you thought you locked); under RR it raises a serialization error instead of silently switching rows.
- **Isolation level is a session/transaction setting, not schema-wide** — `SET TRANSACTION ISOLATION LEVEL ...` per connection; ORM connection pooling can leak a non-default level across pooled connections if not reset.
- **Read replicas add a second axis of "staleness"** orthogonal to isolation level — a Serializable transaction on a stale replica still returns stale data; isolation guarantees are per-node, not cluster-wide unless the system is Spanner/CockroachDB-style externally consistent.
