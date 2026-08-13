# Write-Ahead Log and Durability

> **TL;DR:** Append the intended change to a sequential log and fsync it before acknowledging a write; this turns durability into a cheap sequential-I/O problem and makes the log itself reusable as the replication and CDC stream.

## Quick Reference

| Concept | Key Fact |
|---|---|
| WAL rule | Log record must hit durable storage before the corresponding data-page write or commit ack |
| Why sequential | Sequential append ~10-100x faster than random writes on spinning disks; still faster on SSD due to fewer discrete fsync targets |
| fsync | Forces OS page cache buffers to physical media; without it, "written" data can vanish on power loss |
| Postgres knob | `synchronous_commit = on/off/local/remote_write/remote_apply` |
| Risky knob | `fsync = off` — never durable across crash, only for throwaway/bulk-load DBs |
| Checkpoint | Flushes dirty pages to data files so WAL before that LSN can be truncated/recycled |
| WAL reuse | Same log feeds crash recovery, streaming replication, and CDC (Debezium, Postgres logical decoding, MySQL binlog) |
| Postgres unit | WAL segment file, default 16 MB, named by LSN |
| MySQL equivalent | InnoDB redo log + binlog (binlog is the CDC/replication source, redo log is crash recovery) |
| Kafka analog | Partition log itself IS the durable WAL; `acks=all` + `min.insync.replicas` = fsync equivalent |

## What It Is

- A **Write-Ahead Log (WAL)** is an append-only, sequential record of every mutation, written and durably persisted *before* the corresponding in-memory/data-page change is considered committed.
- Core invariant (ARIES/WAL protocol): never let a data page hit disk before its log record does. Log first, data later.
- Distinct from the actual heap/B-tree data files — WAL is a redo journal, not the primary storage structure (except in log-structured engines, see below).

## Responsibilities

- **Crash recovery**: replay uncommitted-but-logged changes (redo) and undo uncommitted transactions after a crash, restoring the DB to a consistent state without waiting for every write to hit final data pages.
- **Durability guarantee**: the "D" in ACID — once a client gets a commit ack, the change survives process crash and (with fsync) power loss.
- **Decoupling write latency from data-page I/O**: data pages can be flushed lazily/asynchronously because the log already captured the intent.
- **Replication/CDC source of truth**: downstream systems replay the same log instead of re-deriving state.

## How It Works

1. Transaction modifies a page in memory (buffer pool / memtable).
2. Before commit returns to client, the WAL record describing the change is appended to the log buffer and **fsynced** to disk.
3. Data pages remain dirty in memory; a background process (bgwriter, checkpointer, flush thread) writes them out later.
4. On crash: recovery reads WAL from the last checkpoint LSN, **redoes** all logged changes (even for transactions not yet reflected in data files), then **undoes** anything not committed.
5. **Checkpoint**: periodically flush all dirty pages up to some LSN to data files, record that LSN, so WAL before it is provably no longer needed for recovery → can be archived/removed/recycled.

```
Client write -> append WAL record -> fsync WAL -> ack commit
                                   \-> (async) apply to data pages -> checkpoint -> truncate old WAL
```

## Types / Classifications

| WAL Style | Examples | Notes |
|---|---|---|
| Physical WAL | Postgres (byte-level page changes) | Exact-replay, enables physical (binary) streaming replication |
| Physical+logical | Postgres logical decoding on top of physical WAL | Same log, decoded into row-level changes for CDC |
| Logical/statement WAL | MySQL binlog (row/statement/mixed format) | Row-based binlog is the standard CDC feed (Debezium reads it) |
| Redo-only internal log | InnoDB redo log | Crash recovery only, not typically exposed for replication (binlog does that job) |
| Log-structured storage | LSM trees (RocksDB, Cassandra, HBase) | The log (memtable's WAL) doubles as *both* crash-recovery log and the append path into the storage engine itself |
| Log-as-database | Kafka, Kinesis | The log isn't auxiliary — it IS the durable store; consumers replay it like WAL replay |

## Where It Fits

- Sits between the transaction manager and the buffer pool / storage engine in any ACID RDBMS (Postgres, MySQL/InnoDB, SQLite journal, SQL Server).
- In distributed consensus, the **replicated log** (Raft log, Kafka partition) plays an identical role at the cluster level — durability = majority of replicas have fsynced the entry.
- Upstream of replication topology: streaming replicas, logical replication subscribers, and CDC connectors (Debezium, Maxwell, AWS DMS) all tail the WAL/binlog instead of polling tables.
- Upstream of backup/PITR: base backup + archived WAL segments = point-in-time recovery.

## Common Patterns & Real-World Tools

- **Postgres streaming replication**: standby fetches WAL segments over the replication protocol and replays them — same recovery codepath as crash recovery, just continuous.
- **Postgres logical decoding / `pgoutput` / `wal2json`**: decode physical WAL into row-level change events for CDC tools like Debezium.
- **MySQL**: InnoDB redo log for crash safety + separate binlog for replication/CDC — two logs, two purposes, easy to confuse.
- **LSM trees**: incoming writes go to an in-memory memtable *and* a WAL file; on flush, memtable becomes an immutable SSTable and that WAL segment is deleted — WAL here bridges the durability gap between "acked" and "flushed to SSTable."
- **Kafka as WAL**: producers with `acks=all` treat the leader+ISR fsync/replication as the durability boundary; consumers (including DB change-feed consumers) replay from an offset exactly like WAL redo.
- **SQLite**: WAL journal mode (`PRAGMA journal_mode=WAL`) trades the older rollback-journal for an append-only WAL file, improving concurrent read/write.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| WAL + fsync every commit (`synchronous_commit=on`) | Full durability, standard ACID guarantee | Every commit pays fsync latency (~ms on spinning disk, tens of µs–ms on SSD/NVMe depending on device) |
| `synchronous_commit=off` | Commit returns immediately, huge throughput gain | Up to `wal_writer_delay` (default 200ms) of committed transactions can vanish on OS/DB crash (not on data corruption though) |
| `fsync=off` | Fastest possible writes | Data file *and* WAL can be corrupted/lost on power loss — not just recent commits, potentially the whole DB; only acceptable for ephemeral/test/bulk-reload DBs |
| Group commit (batch fsync) | Amortizes fsync cost across many concurrent transactions | Slight added latency per transaction waiting for the batch window |
| Async replication (`remote_write`/off) | Low commit latency | Failover can lose committed transactions (RPO > 0) |
| Sync replication (`remote_apply`) | Zero data loss on failover | Commit latency includes network RTT to replica |

## Real-World Scenarios

- **Postgres primary crash**: on restart, WAL replay from last checkpoint restores all committed-but-not-flushed transactions; recovery time roughly proportional to WAL volume since last checkpoint — tune `checkpoint_timeout`/`max_wal_size` to bound it.
- **CDC pipeline outage**: Debezium connector down for hours; Postgres WAL accumulates because the replication slot pins WAL retention — disk fills up (`pg_wal` growth) until connector resumes or slot is dropped. Classic production incident.
- **Financial ledger writes**: force `synchronous_commit=on` (or even synchronous replication) on the ledger table's transactions while leaving `off` for less critical audit-log tables in the same cluster (per-transaction override via `SET LOCAL synchronous_commit`).
- **Bulk data load**: temporarily set `fsync=off` / `synchronous_commit=off` / use `UNLOGGED` tables in Postgres to speed up a one-time ETL import, then re-enable before serving production traffic.
- **LSM compaction lag**: RocksDB WAL grows if memtable flush falls behind; operators cap WAL size (`max_total_wal_size`) to force earlier flushes and bound recovery time.

## Nuances & Gotchas

- **Replication slots pin WAL forever if unused**: an inactive/forgotten Postgres replication slot (dead consumer, crashed Debezium) prevents WAL truncation — disk fills up silently until "no space left on device" takes down the primary. Monitor `pg_replication_slots` lag.
- **fsync ≠ what you think on some filesystems/cloud disks**: older Linux+ext3, some NAS/EBS configurations historically had fsync bugs or write-back caching that silently ignored the flush (the infamous 2018 Postgres "fsyncgate" — Postgres didn't retry failed fsyncs and could lose data even with `fsync=on`, fixed by panicking on fsync failure).
- **Checkpoint storms**: a big checkpoint flushing many dirty pages at once causes I/O spikes and write latency jitter; `checkpoint_completion_target` spreads the flush over the checkpoint interval instead of bursting.
- **Group commit hides latency, not throughput cost**: many small transactions each still pay fsync unless the workload naturally batches; explicitly batching application writes (multi-row inserts, larger transactions) reduces fsync count more reliably than relying on group commit.
- **`synchronous_commit=off` is not `fsync=off`**: still durable against DB crash for the *previous* fsync'd point, only loses the last few hundred ms — a very different risk profile than `fsync=off`, but frequently confused in incident postmortems.
- **WAL as CDC source has schema-evolution gotchas**: DDL changes (column drops/type changes) mid-stream can break logical decoding plugins or binlog row-format parsing; CDC connectors need explicit handling or restart with new snapshot.
- **Async replication RPO is nondeterministic under load**: replica lag isn't just network latency — a busy replica applying WAL slower than it arrives means failover during a traffic spike loses more data than during quiet periods; alert on replay lag (`pg_last_wal_replay_lsn` delta), not just connection status.
- **Log-structured engines conflate WAL and storage**: in an LSM tree, corrupting/truncating the WAL loses data not yet flushed to an SSTable — unlike a B-tree DB where WAL is purely transient, here it's briefly the *only* copy of recent writes, raising the stakes of fsync correctness.
- **Standby promotion needs full WAL replay first**: promoting a lagging replica too early (before it catches up) can serve stale reads as if authoritative — check `pg_last_wal_receive_lsn` vs `pg_last_wal_replay_lsn` before promotion in automated failover tooling.
