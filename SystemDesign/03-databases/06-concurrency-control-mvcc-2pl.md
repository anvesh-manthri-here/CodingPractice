# Concurrency Control — MVCC vs 2PL

> **TL;DR:** 2PL enforces serializability by blocking readers/writers with shared/exclusive locks; MVCC gives readers a consistent snapshot without blocking writers by keeping multiple row versions. Nearly every modern OLTP engine (Postgres, MySQL/InnoDB, Oracle, SQL Server RCSI) defaults to MVCC-style reads because read/write contention kills throughput at scale.

## Quick Reference

| Aspect | 2PL | MVCC |
|---|---|---|
| Reader vs Writer | Readers block writers (S-lock) | Readers never block writers |
| Writer vs Writer | Blocks / waits on X-lock | Blocks (still needs write lock on row) |
| Isolation basis | Lock scope + phase discipline | Snapshot of committed versions + txn IDs |
| Conflict detection | Prevented upfront (pessimistic) | Detected at commit (optimistic-ish) |
| Storage overhead | None (locks only) | Extra row versions until GC'd |
| Cleanup mechanism | N/A | VACUUM (Postgres), purge thread (InnoDB) |
| Deadlocks | Common, need detection/timeout | Rare (mostly write-write only) |
| Classic engines | Older RDBMS, DB2 (locking mode), 2PC coordinators | Postgres, MySQL InnoDB, Oracle, SQL Server (RCSI/SI) |
| Anomaly risk | Serializable achievable directly | Write skew possible under Snapshot Isolation |

## What It Is
- **2PL (Two-Phase Locking):** concurrency control protocol where a transaction acquires all locks before releasing any — guarantees conflict-serializability.
- **MVCC (Multi-Version Concurrency Control):** each write creates a new row version tagged with transaction metadata; reads see a consistent snapshot as of their start (or statement) time instead of locking rows.
- Both solve the same problem — isolating concurrent transactions — via opposite philosophies: pessimistic blocking vs optimistic versioning.

## Responsibilities
- Prevent **dirty reads** (reading uncommitted data), **non-repeatable reads**, **lost updates**, **phantom reads**.
- Provide a chosen **isolation level** (Read Committed, Repeatable Read, Serializable) with predictable performance characteristics.
- Manage the lifecycle of stale data/locks: lock release timing (2PL) or old-version garbage collection (MVCC).

## How It Works

### 2PL
- **Growing phase:** transaction acquires locks (S = shared/read, X = exclusive/write), never releases any.
- **Shrinking phase:** once first lock is released, no new locks may be acquired — releases happen (often all at commit = **Strict 2PL**, the practical variant used by real DBs).
- Lock compatibility: S-S compatible, S-X and X-X conflict → blocking.
- **Deadlock handling:**
  - *Detection:* wait-for graph, periodic cycle check, kill youngest/lowest-cost transaction (MySQL InnoDB does this even though it's MVCC underneath for write locks).
  - *Prevention:* timeouts, or ordering schemes (wound-wait, wait-die) using transaction timestamps to avoid cycles altogether.

### MVCC
- Every row version stores creation/deletion transaction IDs (xmin/xmax in Postgres; trx_id + rollback segment pointer in InnoDB).
- A transaction's snapshot = set of committed txn IDs visible "as of" a point in time; reads filter versions by visibility rules, ignoring in-flight/future writes.
- **Writers never block readers** — a writer creates a new version; old readers keep seeing their old version.
- **Writers still need write locks** on the row itself to serialize write-write conflicts (first-committer-wins or first-updater-wins).
- Old versions become garbage once no active snapshot needs them → reclaimed by **VACUUM** (Postgres) or the **purge thread** (InnoDB undo log).

```
2PL:  R1 --S-lock--> [row] <--X-lock-- W1   (W1 blocks until R1 releases)
MVCC: R1 reads v1 (snapshot) ---- W1 writes v2 (commits) ---- R2 reads v2
      R1 never blocked; v1 kept alive until R1 finishes, then vacuumed
```

## Types / Classifications
- **2PL variants:** Basic 2PL, Strict 2PL (locks held to commit — prevents cascading aborts), Conservative/Static 2PL (acquire all locks upfront — deadlock-free but low concurrency).
- **MVCC isolation flavors:**
  - *Snapshot Isolation (SI):* transaction sees one consistent snapshot for its whole duration (Postgres REPEATABLE READ, Oracle default READ COMMITTED per-statement).
  - *Statement-level snapshot:* new snapshot per statement (Postgres READ COMMITTED, Oracle default).
  - *Serializable Snapshot Isolation (SSI):* Postgres's true SERIALIZABLE — adds runtime conflict detection (rw-antidependency tracking) on top of SI to close write-skew holes.
- **Hybrid approach:** InnoDB uses MVCC for reads + 2PL-style row locks for writers (next-key locking to block phantoms in REPEATABLE READ).

## Where It Fits
- Sits inside the **transaction/storage engine layer**, beneath the SQL executor, above the WAL/undo-log and buffer pool.
- Interacts with the **isolation level** setting exposed to the app (`SET TRANSACTION ISOLATION LEVEL ...`).
- Distributed DBs (CockroachDB, Spanner, YugabyteDB) extend MVCC with **hybrid logical clocks / TrueTime** for cross-node snapshot consistency; still combine with locking for write conflicts (2PL-ish "intents" in CockroachDB).

## Common Patterns & Real-World Tools
| System | Approach |
|---|---|
| PostgreSQL | Pure MVCC, tuple versions in heap, xmin/xmax, VACUUM/autovacuum reclaims, SSI for true serializable |
| MySQL InnoDB | MVCC via undo log + rollback segments for reads; row-level X-locks (2PL-style) for writers; gap locks for phantom prevention |
| Oracle | MVCC via undo segments, read consistency, no read locks ever |
| SQL Server | Locking (2PL) by default; RCSI/SI optional (tempdb version store) |
| CockroachDB / Spanner | MVCC + distributed timestamp ordering (TrueTime/HLC) + write intents (2PL-like) |
| DB2 | Traditional locking-based (2PL), optional currently-committed mode mimics MVCC |

## Pros & Cons / Trade-offs
| | 2PL | MVCC |
|---|---|---|
| Pros | Simple mental model, strict correctness, no version bloat, works well for write-heavy short txns with low contention | High read concurrency, reporting/analytics don't block OLTP writes, no reader starvation |
| Cons | Read-write blocking tanks throughput under mixed workloads; deadlocks need detection/rollback; poor for long-running readers | Storage bloat (dead tuples), VACUUM/purge overhead, risk of **write skew** under SI, transaction ID wraparound risk (Postgres) |
| Best for | Simple embedded DBs, systems needing strict serializability cheaply, low-concurrency writes | High-concurrency OLTP with mixed read/write, reporting queries against live data |

## Real-World Scenarios
- **Postgres bloat incident:** long-running transaction (e.g., stuck analytics query) holds back `xmin` horizon → autovacuum can't reclaim dead tuples → table bloats 10x, index scans slow down. Fix: `idle_in_transaction_session_timeout`, monitor `pg_stat_activity`.
- **InnoDB deadlock storm:** high-concurrency updates on same rows in different order across transactions → frequent deadlocks; InnoDB auto-detects and kills the transaction with less undo work; app must retry.
- **Write skew bug:** two transactions under Postgres REPEATABLE READ (SI) each check "total on-call doctors >= 1" then both set themselves off-call — both commit because neither wrote a row the other read → constraint violated. Fixed by SERIALIZABLE (SSI) or explicit `SELECT ... FOR UPDATE`.
- **Transaction ID wraparound:** Postgres uses 32-bit xids; if `autovacuum_freeze_max_age` ignored, wraparound risk forces emergency shutdown — real production outage cause.
- **Reporting on live OLTP (MVCC win):** long analytical `SELECT` on Postgres/InnoDB runs against a snapshot without blocking concurrent order inserts — impossible cheaply under strict 2PL.

## Nuances & Gotchas
- **"MVCC has no locks" is a myth** — writers still lock rows (write-write conflicts), and gap/next-key locks in InnoDB REPEATABLE READ are genuine 2PL-style locks to block phantoms.
- **Long-running transactions are MVCC's Achilles heel**: they pin old versions alive, causing bloat (Postgres) or huge undo logs (Oracle/InnoDB) that slow down every other transaction's visibility checks.
- **Vacuum is not optional maintenance** — under-tuned `autovacuum` on high-churn tables is one of the top real-world Postgres performance incidents; watch `n_dead_tup` and table/index bloat ratios.
- **Snapshot Isolation ≠ Serializable** — SI prevents most anomalies but not write skew; many teams assume "REPEATABLE READ" is safe and get bitten by concurrent invariant violations.
- **Read Committed MVCC still allows non-repeatable reads** within a transaction (each statement gets a fresh snapshot) — surprises devs expecting txn-level consistency.
- **Deadlock detection cost scales with lock table size** — under extreme 2PL contention, the wait-for graph check itself becomes a bottleneck; some systems fall back to timeouts instead.
- **Index-organized MVCC weirdness (InnoDB):** secondary indexes don't carry version info directly; a lookup may need to consult the clustered index + undo log to determine visibility, adding read amplification vs Postgres's inline tuple versions.
- **Hot row contention persists under MVCC**: a single frequently-updated row (counter, queue head) still serializes writers one at a time — MVCC helps read scalability, not write scalability. Use sharding/sequences/`FOR UPDATE SKIP LOCKED` patterns instead.
- **Postgres HOT updates** avoid index bloat when updated columns aren't indexed — worth designing schemas to exploit this and reduce vacuum pressure.
