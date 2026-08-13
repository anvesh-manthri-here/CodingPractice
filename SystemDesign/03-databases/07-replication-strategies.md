# Replication Strategies

> **TL;DR:** Replication trades consistency, latency, and availability against each other — pick a leader topology (single, multi, leaderless) and a durability mode (sync/async/quorum) based on which failure you're willing to tolerate: stale reads, lost writes, or reduced write availability.

## Quick Reference

| Strategy | Write path | Consistency | Availability on node loss | Conflict handling | Example systems |
|---|---|---|---|---|---|
| Single-leader, async | 1 leader, followers catch up later | Eventual, can lose data | Followers readable; leader loss = failover + possible data loss | N/A (single writer) | MySQL (default), Postgres streaming replication |
| Single-leader, sync | Leader waits for follower ack | Strong (no data loss on leader failover) | Write blocks if sync follower down | N/A | Postgres `synchronous_commit=on`, MySQL semi-sync (1 replica) |
| Single-leader, semi-sync | Leader waits for ≥1 of N acks | Bounded staleness | Better than full sync, weaker than full sync | N/A | MySQL semi-sync replication |
| Multi-leader | Multiple leaders accept writes, replicate to each other | Eventual, conflicts possible | High — any datacenter can write | Required (LWW, CRDT, app merge) | MySQL multi-source, CouchDB, AD, geo-replicated DBs |
| Leaderless/quorum | Client writes to W of N replicas | Tunable via R+W>N | High — no single point of failure | Read repair, vector clocks, LWW | Dynamo, Cassandra, Riak, Voldemort |

## What It Is

- Replication = keeping copies of the same dataset on multiple nodes for **availability**, **read scaling**, and **geographic locality**.
- Core dimension 1: **topology** — who accepts writes (single-leader, multi-leader, leaderless).
- Core dimension 2: **durability contract** — when a write is considered "done" (sync, async, quorum).
- Core dimension 3: **transport format** — how changes propagate (statement-based, row-based, logical/trigger-based, WAL shipping).

## Responsibilities

- Guarantee data survives single-node failure (durability).
- Serve reads without hitting the write bottleneck (scalability).
- Provide a path to promote a replica when the leader dies (failover).
- Bound replication lag to an SLA the application can tolerate (consistency).
- Detect and resolve conflicting concurrent writes (multi-leader/leaderless only).

## How It Works

**Single-leader:**
1. Client writes go only to the leader.
2. Leader appends to its write-ahead log (WAL) / binlog.
3. Followers pull or receive the log stream and apply it in order.
4. Reads can go to leader (fresh) or followers (may be stale).

- **Async**: leader acks client immediately, ships log after. Fast, but leader crash before shipping = lost writes.
- **Sync**: leader waits for follower(s) to confirm write applied before acking client. Safe, but leader write latency = slowest replica; that replica becoming unreachable stalls all writes.
- **Semi-sync**: leader waits for ack that ≥1 replica has *received* (not necessarily applied) the log, then acks client, then rest replicate async. Balances safety and latency — MySQL and PostgreSQL (`synchronous_standby_names` with `ANY 1`) support this natively.

**Multi-leader:**
- Each leader replicates its writes to every other leader asynchronously (usually).
- Used across datacenters (each DC has a local leader) or offline-capable clients (each device is a "leader").
- Conflict problem: two leaders accept writes to the same record concurrently → diverging state must be reconciled.
  - Last-Write-Wins (LWW) by timestamp — simple, silently drops data.
  - Version vectors / vector clocks — detect concurrency, surface conflict to app.
  - CRDTs (conflict-free replicated data types) — merge automatically for counters, sets, etc.
  - Application-level merge (e.g., 3-way merge, custom business logic).

**Leaderless (Dynamo-style quorum):**
- No designated leader; client (or coordinator node) writes to N replicas directly, waits for W acks.
- Reads query R replicas, return the newest version (via version vector/timestamp) — client or coordinator does read-repair by writing the latest value back to stale replicas.
- Quorum rule: if **W + R > N**, every read overlaps at least one up-to-date replica — "guarantees" freshness assuming no sloppy quorum.
- Anti-entropy background process (Merkle trees in Cassandra/Riak) repairs divergence proactively without waiting for reads.
- Sloppy quorum + hinted handoff: if the "right" nodes are unreachable, write to other nodes temporarily and hand off later — boosts availability but breaks the strict quorum guarantee.

## Types / Classifications

**By log transport format:**

| Format | What's shipped | Pros | Cons |
|---|---|---|---|
| Statement-based | SQL statements (`INSERT`, `UPDATE`) | Compact | Breaks on `NOW()`, `RAND()`, auto-increment, triggers — nondeterministic statements diverge replicas (MySQL deprecated as default) |
| Row-based (RBR) | Actual before/after row values | Deterministic, safe | Larger log volume, less human-readable |
| WAL / physical shipping | Byte-level disk block changes | Exact replica, fast | Tied to exact DB version/engine (Postgres streaming replication) |
| Logical (trigger/log-based) | Row changes decoded to logical format, decoupled from storage engine | Cross-version, cross-engine possible, usable by CDC | More CPU to decode; slight lag; Postgres logical decoding, MySQL row-based binlog + Debezium |

**By leader count:** single-leader, multi-leader, leaderless (see Quick Reference).

## Where It Fits

```
        Clients
          |
     [Load Balancer]
      /    |    \
 Leader  Follower Follower   <- single-leader: writes->leader, reads spread
  (RW)    (RO)     (RO)
   |  replicates (async/sync/semi-sync)
   v
 Replicas ---- CDC (Debezium) ----> Kafka ----> analytics/search index
```
- Sits between the application and physical storage; orthogonal to sharding (you replicate *each* shard).
- Feeds CDC pipelines (Debezium, MySQL binlog, Postgres logical replication slots) to sync search indexes (Elasticsearch), caches, or data warehouses.
- Read replicas offload reporting/analytics queries from the OLTP leader.

## Common Patterns & Real-World Tools

- **Postgres**: streaming replication (WAL shipping, async default), synchronous_commit for sync, logical replication (`pglogical`, native since PG10) for selective table replication.
- **MySQL**: binlog-based, async default, semi-sync plugin, Group Replication for multi-primary with consensus (Paxos-based conflict avoidance).
- **MongoDB**: replica sets, single primary + secondaries, automatic failover via replica set election (Raft-like).
- **Cassandra / DynamoDB / Riak**: leaderless, tunable consistency (`QUORUM`, `ONE`, `ALL` per query).
- **Kafka**: leader-follower per partition, ISR (in-sync replica) set — a form of semi-sync; `acks=all` + `min.insync.replicas` mirrors quorum write.
- **Debezium**: logical/CDC replication layer bolted onto MySQL/Postgres/SQL Server for downstream streaming.

## Pros & Cons / Trade-offs

| Choice | Pro | Con |
|---|---|---|
| Async single-leader | Low write latency | Data loss window on leader crash |
| Sync single-leader | Zero data loss on failover | Write availability tied to slowest/all replicas |
| Semi-sync | Good balance | Still has small loss window; complexity |
| Multi-leader | Multi-region write availability, low local write latency | Conflict resolution complexity, eventual consistency |
| Leaderless/quorum | No SPOF, tunable, high availability | Complex client logic, weaker guarantees under sloppy quorum, harder to reason about |
| Statement-based | Small log size | Nondeterminism bugs |
| Row-based | Deterministic | Bigger logs, opaque diffs |
| Logical | Decoupled, CDC-friendly | Extra decode overhead, slot bloat if consumer lags |

## Real-World Scenarios

- **E-commerce checkout**: use sync or semi-sync single-leader for the orders table (can't lose a paid order); async replicas fine for product catalog reads.
- **Global chat app / collaborative doc**: multi-leader per region + CRDTs (like Google Docs OT/CRDT, Riak) so each user edits locally without waiting on cross-region round trips.
- **Shopping cart at Amazon-scale (original Dynamo use case)**: leaderless with sloppy quorum — availability for "add to cart" matters more than perfect consistency; conflicts resolved at read time (merge carts).
- **Analytics offload**: async read replica or logical replication into a warehouse (Debezium → Kafka → Snowflake) so heavy OLAP queries don't touch the OLTP leader.
- **Financial ledger**: strict sync replication or even consensus-based (Raft/Paxos, e.g., CockroachDB, Spanner) — async single-leader is unacceptable due to lost-write risk.

## Nuances & Gotchas

- **Replication lag symptoms are the real interview material**: read-your-writes violation (user posts a comment, refresh doesn't show it because it hit a lagging replica), monotonic-read violation (user sees a comment, refreshes, comment disappears because second read hit a *different*, more-lagged replica), and causality violation (see an answer before the question in a lagging replica). Fix with read-your-writes stickiness (route user's own reads to leader for N seconds, or track a version/LSN and require replica to catch up to it), or sticky sessions pinned to one replica for monotonic reads.
- **Split-brain**: failover promotes a new leader while the old leader is still alive (e.g., network partition, not actually dead — just slow/unreachable to the orchestrator). Both leaders accept writes → silent data divergence/loss. Mitigate with fencing tokens (monotonically increasing epoch number that storage/clients reject if stale), STONITH ("shoot the other node in the head"), or consensus-based leader election (Raft term numbers) instead of naive heartbeat timeouts.
- **Failover timing trade-off**: too-short timeout → false positives → unnecessary failovers → split-brain risk; too-long timeout → extended write unavailability. Production systems (Patroni for Postgres, MySQL Orchestrator) use external consensus stores (etcd/Consul/ZooKeeper) to arbitrate leadership rather than trusting a single observer.
- **Async replication + failover = silent data loss**: promoted follower may be missing the last few committed transactions; old leader rejoining as a follower may have writes that never made it out — must be discarded (or manually reconciled), which is often the actual outage story, not the failover itself.
- **Sync replication cascading failure**: if the single synchronous replica goes down, writes block entirely unless the DB auto-demotes to async (MySQL semi-sync `rpl_semi_sync_master_timeout` falls back to async — silently weakening your durability guarantee without alerting anyone).
- **Quorum overlap isn't a true guarantee**: with sloppy quorum + hinted handoff, W+R>N no longer guarantees freshness because the "handoff" nodes aren't the canonical replica set — Dynamo/Cassandra explicitly trade this away for availability during partitions.
- **Statement-based replication landmines**: `INSERT ... SELECT NOW()`, auto-increment IDs, `UPDATE ... LIMIT 1` (row choice depends on storage engine's internal order), triggers/stored procs firing again on the replica — this is why MySQL row-based/mixed became the default over pure statement-based.
- **Multi-leader conflict resolution is a silent-data-loss trap too**: naive LWW discards one side of a genuine concurrent edit with no record it happened — fine for a "last click wins" UI setting, unacceptable for financial or inventory counts.
- **Replication lag under load spikes non-linearly**: a burst of writes plus a slow replica (I/O contention, vacuum/compaction pause) can cause lag to balloon from milliseconds to minutes; monitor lag as a first-class SLO (Postgres `replay_lag`, MySQL `Seconds_Behind_Master`), not an afterthought.
- **Logical replication slot bloat**: if a logical replication consumer (e.g., Debezium) disconnects, Postgres retains WAL indefinitely for that slot until it's dropped or catches up — can fill disk and take down the primary if unmonitored.
