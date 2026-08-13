# Indexing — B-Tree, LSM-Tree, Hash Index

> **TL;DR:** B-trees give balanced read/range performance with in-place updates (Postgres, InnoDB default); LSM-trees trade read amplification for sequential-write throughput via memtable + SSTable compaction (Cassandra, RocksDB, LevelDB); hash indexes are O(1) equality-only, no ranges.

## Quick Reference

| Index Type | Write Pattern | Read Pattern | Range Scans | Used By | Write Amp | Read Amp | Space Amp |
|---|---|---|---|---|---|---|---|
| B-Tree | Random in-place | O(log n) | Excellent | InnoDB, Postgres, SQL Server | Moderate | Low (1 seek/level) | Low |
| LSM-Tree | Sequential append | O(log n) but multi-level | Good | RocksDB, LevelDB, Cassandra, HBase | High (compaction) | High (multi-SSTable) | Moderate (until compaction) |
| Hash Index | O(1) insert | O(1) equality only | None (unordered) | Postgres HASH, Redis, DynamoDB partition key | Low | Low | Low |

## What It Is

- **Index**: auxiliary data structure mapping key → row location (or storing data itself, clustered), traded against write cost and storage to speed reads.
- **B-Tree**: self-balancing n-ary tree, all leaves at same depth, disk-page-aligned nodes (e.g., 8KB/16KB fit ~100s of keys per node).
- **LSM-Tree (Log-Structured Merge-Tree)**: writes buffered in memory, flushed as immutable sorted files, merged in background; optimizes for sequential disk/SSD writes.
- **Hash Index**: hash function maps key to bucket/slot holding pointer to row; no ordering preserved.

## Responsibilities

- Bound the number of disk I/Os per lookup (B-tree: O(log_b n) with large fanout b ⇒ 3-4 levels for billions of rows).
- Preserve sort order to serve range queries and ORDER BY without extra sort (B-tree only).
- Absorb high write throughput without blocking on random disk seeks (LSM).
- Provide fastest possible exact-match lookup with minimal memory/CPU (hash).

## How It Works

### B-Tree
- Nodes = fixed-size pages; each internal node holds keys + child pointers, leaf nodes hold actual row data or (key, rowid) pairs.
- Insert: locate leaf via root-to-leaf traversal, insert key; if node overflows, **split** and push median up (may cascade to root, increasing height).
- Delete: may **merge/rebalance** underflowed siblings.
- B+Tree variant (what DBs actually use): only leaves store data, leaves linked via sibling pointers for fast sequential range scans.
- Updates are in-place → requires **write-ahead log (WAL)** for crash safety since a torn page write corrupts the structure.

### LSM-Tree
1. Write goes to **WAL** (durability) then into an in-memory sorted structure, the **memtable** (skip list/red-black tree).
2. When memtable hits size threshold (e.g., 64MB RocksDB default), it's frozen and flushed to disk as an immutable **SSTable** (Sorted String Table) — sequential write.
3. Reads check memtable, then SSTables newest-to-oldest (Bloom filters skip SSTables that can't contain the key).
4. **Compaction** merges SSTables in the background, dropping tombstones/overwritten values, reducing SSTable count.
   - *Leveled compaction* (RocksDB/LevelDB default): SSTables organized into levels L0…Ln, each ~10x larger; bounds read amp and space amp, higher write amp.
   - *Size-tiered compaction* (Cassandra default, STCS): merge similar-sized SSTables; lower write amp, higher space/read amp.
5. Deletes are **tombstones** (marker records), physically removed only during compaction.

### Hash Index
- Hash(key) → bucket index; bucket holds pointer(s) to record(s); collisions via chaining or open addressing.
- In-memory hash indexes (Bitcask/Riak model): append-only log + in-memory hash map of key→file offset; compaction merges log segments.
- Postgres HASH index: on-disk buckets, WAL-logged since v10, but still limited to `=` predicates.

## Types / Classifications

| Sub-type | Notes |
|---|---|
| Clustered (B-tree) index | Table data physically ordered by index key (InnoDB primary key) — only one per table |
| Secondary/non-clustered B-tree | Leaf stores pointer/rowid back to clustered index; extra lookup hop |
| Covering index | Includes all columns a query needs so engine never touches base table ("index-only scan") |
| LSM with Bloom filters | Per-SSTable Bloom filter avoids disk read for absent keys, cuts read amp significantly |
| Hash + separate chaining vs open addressing | In-memory tuning choice, irrelevant to on-disk DB indexes mostly |

## Where It Fits

```
Query planner
   |
   +-- equality predicate, no range/order --> Hash index (if available) or B-tree
   +-- range / ORDER BY / prefix match      --> B-tree (only structure that preserves order)
   +-- write-heavy ingestion, append logs   --> LSM-tree (Cassandra, RocksDB used inside MyRocks, TiDB)
```
- OLTP relational engines (Postgres, MySQL/InnoDB, SQL Server) default to B+Tree for both PK and secondary indexes.
- Wide-column/NoSQL and embedded KV stores (Cassandra, HBase, RocksDB, LevelDB, ScyllaDB) use LSM for the storage engine itself, not just an index.
- Hash indexes show up as: Postgres `USING hash`, in-memory caches (Redis hash table), DynamoDB partition-key routing, join hash tables (query execution, not storage).

## Common Patterns & Real-World Tools

- **MyRocks** (Facebook): swaps InnoDB's B-tree for RocksDB's LSM under MySQL — cuts storage ~2x via better compression, trades some read latency.
- **Postgres**: B-tree default; GIN/GiST for full-text/spatial; BRIN for huge append-only tables with correlated data (cheap, low-res index).
- **Cassandra**: memtable + SSTables + compaction strategy configurable per table (STCS vs LCS vs TWCS for time-series).
- **RocksDB**: tunable via `level0_file_num_compaction_trigger`, `max_bytes_for_level_base` — classic knobs for write vs read amp trade-off.
- **Covering index example**: `CREATE INDEX idx ON orders(customer_id, order_date) INCLUDE (total)` — avoids heap fetch for `SELECT total WHERE customer_id=? ORDER BY order_date`.
- **Composite index column order**: put equality-filter columns first, then range/sort columns last — index on `(a, b, c)` serves `WHERE a=? AND b=?`, `WHERE a=? AND b>?`, and `WHERE a=? ORDER BY b`, but NOT `WHERE b=?` alone (leftmost-prefix rule).

## Pros & Cons / Trade-offs

| | B-Tree | LSM-Tree | Hash |
|---|---|---|---|
| Pro | Predictable single-seek reads, mature, in-place update simplicity | High write throughput, good compression (sorted runs), sequential I/O friendly to SSD | Fastest possible exact-match, O(1) |
| Con | Random writes cause page splits + fragmentation, write amp from WAL+page rewrites | Read/space amp until compacted, compaction is CPU/IO spike ("stalls"), tombstone bloat | No range queries, no ordering, hash collisions degrade to O(n) |
| Amplification | Write amp moderate; ~1 write per update (buffer pool absorbs) | Write amp high — same key rewritten across every compaction level (can be 10-30x) | Minimal, but no compaction concept |

## Real-World Scenarios

- **E-commerce order history (range queries by date, moderate write rate)** → B-tree secondary index on `(customer_id, created_at)`; Postgres/MySQL fits.
- **IoT telemetry ingestion (millions of writes/sec, append-only, rare updates)** → LSM-backed store (Cassandra/ScyllaDB) absorbs write bursts via memtable, background compaction smooths I/O.
- **Session store / cache lookups by exact session ID** → Redis hash table or DynamoDB partition key — O(1), no range needed.
- **Time-series with TTL expiry** → Cassandra TWCS (time-window compaction) groups SSTables by time bucket so whole expired SSTables get dropped without rewriting — avoids full compaction write amp.
- **Analytics on huge append-only fact table with correlated insert order** → Postgres BRIN index instead of B-tree — index is KB-sized vs GB-sized B-tree.

## Nuances & Gotchas

- **LSM read latency tail**: worst case touches memtable + every SSTable level; without Bloom filters a miss can mean N disk reads. Bloom filter false-positive rate tuning (e.g., 1%) directly trades memory for read amp.
- **Compaction stalls**: if write rate exceeds compaction throughput, SSTable count balloons (L0 pile-up in RocksDB), causing write stalls/backpressure — classic Cassandra "too many SSTables" incident.
- **Tombstone accumulation**: deletes in Cassandra not compacted within `gc_grace_seconds` (default 10 days) risk "zombie" data resurrection if compaction/repair lags — must run repair before tombstones are purged.
- **B-tree write amplification underestimated**: a single row update can dirty a full 8-16KB page; on SSDs this multiplies actual bytes written (measure via `iostat`), plus WAL doubles it.
- **Index bloat in Postgres**: MVCC means updates create new row versions; B-tree indexes accumulate dead entries until `VACUUM` — un-vacuumed tables silently degrade index scan performance.
- **Leftmost-prefix trap**: composite index `(a,b,c)` is useless for `WHERE b=5` alone — a common query-plan surprise; check `EXPLAIN` for unexpected seq scans.
- **High-cardinality column first vs equality-first debate**: general rule is equality columns before range columns regardless of cardinality — putting a range column before an equality column breaks index usability for later columns entirely.
- **Hash index on Postgres pre-v10**: not WAL-logged, unsafe on replicas/crash recovery — now fixed but legacy warnings persist in older docs.
- **LSM space amplification**: until compaction runs, deleted/overwritten data still occupies disk — can temporarily 2-3x actual dataset size, matters for capacity planning.
- **Secondary index double-lookup cost (InnoDB)**: non-covering secondary index scan requires a second B-tree traversal into the clustered index per row — can dominate query cost vs a covering index.
