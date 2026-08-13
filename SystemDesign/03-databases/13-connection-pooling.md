# Connection Pooling

> **TL;DR:** Opening a DB connection is expensive (TCP+TLS+auth handshake, server-side memory), so reuse a small, bounded pool instead of creating one per request — but size it by contention math (cores, disk I/O), not by "more = faster," and always account for fleet-wide multiplication against the DB's `max_connections`.

## Quick Reference

| Concept | Value / Rule of Thumb |
|---|---|
| Cost of new Postgres connection | ~1.5–10ms local, higher over WAN/TLS; forks a new OS process (~5-10MB RSS) |
| Cost of new MySQL connection | New thread, ~256KB-1MB stack/buffers per thread |
| Pool size formula (PostgreSQL project) | `connections = ((core_count * 2) + effective_spindle_count)` |
| Typical app pool size | 10–20 per app instance (not hundreds) |
| PgBouncer transaction pooling | Connection returned to pool after each transaction; best multiplexing |
| PgBouncer session pooling | Connection held for client's whole session; safest, least multiplexing |
| Danger zone | `N app servers × pool size > DB max_connections` |
| Postgres default `max_connections` | 100 |
| Symptom of over-provisioning | Rising p99 latency + falling throughput as pool size grows |

## What It Is

- A **connection pool** is a pre-established, reusable set of live DB connections held in a client-side (or middleware) cache instead of opened/closed per query.
- Lives in-process (HikariCP in JVM apps, `psycopg2.pool`, Go `database/sql` pool) or as a standalone proxy (PgBouncer, pgpool-II, ProxySQL, RDS Proxy).
- Goal: amortize the fixed cost of connection establishment across many logical requests.

## Responsibilities

- Acquire/lease a connection to a caller, block or queue when none are free.
- Return connection to pool on release; optionally reset session state (`DISCARD ALL`, `RESET`).
- Enforce max/min pool bounds, idle timeout, max lifetime (prevent stale/leaked connections).
- Health-check connections (validation query or lightweight ping) before handing out.
- Multiplex many client connections onto fewer backend DB connections (proxy-level pools like PgBouncer).

## How It Works

**Why opening a connection is expensive:**
1. **TCP handshake** — SYN/SYN-ACK/ACK, 1 RTT minimum (more over WAN/cross-AZ).
2. **TLS handshake** — additional 1-2 RTTs, asymmetric crypto (cert validation, key exchange) — CPU-heavy on both ends.
3. **Auth handshake** — password/SCRAM exchange, LDAP/Kerberos lookup, or IAM token validation (RDS IAM auth adds a full STS round trip).
4. **Server-side session setup** — Postgres forks a new backend *process* per connection (not a thread); MySQL spawns a thread. Both allocate per-connection memory: `work_mem`, sort buffers, prepared statement cache, session variables.
5. Net effect: a fresh connection can cost single-digit to tens of ms and several MB of server RAM — ruinous if done per-request at high QPS.

**Pool sizing math:**
- Sizing isn't "however many concurrent requests you expect." Past the number of CPU cores (+ disk parallelism), additional connections cause **contention**, not throughput.
- PostgreSQL's own guidance: `connections = ((core_count * 2) + effective_spindle_count)`. On modern SSD/NVMe, spindle count ≈ small; the core term dominates.
- Reasoning: each active connection running a query competes for CPU, lock manager, buffer pool latches, and I/O queue depth. Beyond the point where the DB can genuinely run that many things in parallel, extra connections just queue inside the DB (context switching, lock waits) instead of the pool — you've moved the queue, not eliminated it, and added overhead.
- Little's Law framing: `pool_size = throughput (req/s) × avg_service_time (s)`, then cap by CPU/IO capacity, whichever is lower.

## Types / Classifications

| Type | Where | Notes |
|---|---|---|
| **In-process pool** | App runtime (HikariCP, Go `sql.DB`, Tomcat JDBC, SQLAlchemy pool) | One pool per app instance; simplest, no extra hop, but multiplies with fleet size |
| **External proxy pool** | PgBouncer, pgpool-II, ProxySQL, Odyssey | Sits between app fleet and DB; decouples client count from backend connection count |
| **Managed proxy** | AWS RDS Proxy, Azure SQL connection pooling, GCP Cloud SQL Auth Proxy | Managed multiplexing + IAM auth caching + failover-aware |

### PgBouncer pooling modes (the classic exam question)

| Mode | Connection returned to pool... | Session state (temp tables, `SET`, prepared stmts, advisory locks) | Use case |
|---|---|---|---|
| **Session pooling** | After client disconnects | Fully preserved | Safest default; behaves like direct connection; least multiplexing benefit |
| **Transaction pooling** | After each `COMMIT`/`ROLLBACK` | **Broken** — session state not guaranteed across transactions | Best multiplexing (1000s of clients → tens of backend conns); most common in production |
| **Statement pooling** | After each statement, no multi-statement transactions | Even more restrictive | Rarely used; PgBouncer supports but breaks transactions entirely |

- **pgpool-II** additionally does query load balancing (read replicas), connection pooling, and automatic failover — heavier than PgBouncer, which does pooling only.

## Where It Fits

```
[App instance 1]--\
[App instance 2]---> [PgBouncer/RDS Proxy] --(few dozen conns)--> [Postgres/MySQL]
[App instance N]--/     (transaction pooling,
                          multiplexes 1000s -> tens)
```
- Sits between the application's own in-process pool and the database. Layering is common: app has small HikariCP pool → talks to PgBouncer → PgBouncer holds the real backend connections.
- In serverless (Lambda, Cloud Functions), an external proxy (RDS Proxy) is close to mandatory — each invocation would otherwise open its own connection, exploding `max_connections`.

## Common Patterns & Real-World Tools

- **HikariCP** (Java) — fastest JVM pool, `maximumPoolSize` default 10; explicitly documents "pools should be small."
- **PgBouncer** — single-threaded (historically), extremely lightweight, transaction-mode default in most high-scale Postgres shops (Instagram, GitLab).
- **RDS Proxy / Cloud SQL Proxy** — managed transaction-level pooling + IAM token caching + connection draining across failover, avoids app restarts on primary failover.
- **ProxySQL** (MySQL) — pooling + query routing + caching, popular at Booking.com, GitHub scale.
- **Read/write split pools** — separate pools per replica, sized independently (writer pool smaller, reader pool larger).

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Large in-process pool per app instance | Simple, no extra hop | Multiplies by fleet size; risk of exhausting `max_connections`; contention past core count |
| Small in-process pool + external proxy (transaction mode) | Decouples client scaling from DB connection count; DB sees few, stable connections | Breaks session-level features (prepared statements, advisory locks, `SET` session vars, temp tables) |
| Session-mode proxy pooling | Full compatibility with session features | Multiplexing benefit ~0; doesn't solve the fleet-multiplication problem |
| No pooling (open per request) | Zero pool-management complexity | Handshake cost dominates latency; DB process/thread churn; falls over under load |

## Real-World Scenarios

- **Serverless fan-out**: 500 concurrent Lambda invocations each opening a raw Postgres connection → instantly exceeds `max_connections=100` → "too many connections" errors. Fix: RDS Proxy or PgBouncer in front, transaction pooling mode.
- **Microservices over-provisioning**: 50 microservice pods × pool size 20 = 1000 potential connections against a DB configured for 200. Works fine at low traffic (pools never fill), then a traffic spike or slow query causes every pod to open more connections simultaneously → DB rejects connections fleet-wide, cascading failure.
- **"Bigger pool = faster" regression**: team bumps HikariCP `maximumPoolSize` from 10 to 100 hoping to fix latency; throughput drops because the DB (8 cores) now context-switches across 100 concurrent queries instead of running ~16-20 efficiently — classic thrashing.

## Nuances & Gotchas

- **The fleet-multiplication trap is the #1 production incident cause**: nobody does `app_instances × pool_size` math until an autoscaling event doubles pod count and the DB starts rejecting connections. Always compute this explicitly and alert on `pg_stat_activity` count vs `max_connections`.
- **Transaction-mode pooling silently breaks features**: `SET search_path`, session-level `SET`, `LISTEN/NOTIFY`, advisory locks, and prepared statements (`PREPARE`) don't survive across pooled transactions because the underlying backend connection can change between transactions. Apps that assume session affinity get intermittent, hard-to-reproduce bugs.
- **Prepared statement caching + PgBouncer transaction mode** is a known landmine: JDBC/asyncpg driver-level prepared statement caches assume a stable backend connection; PgBouncer ≥1.21 added `max_prepared_statements` support to handle this, older versions require disabling driver-side statement caching.
- **Contention beats parallelism past core count**: more connections than the DB can genuinely parallelize just means longer internal queues (lock waits, buffer pool contention) — you get worse p99 latency, not more throughput. Benchmark before assuming "bigger pool fixes timeouts."
- **Connection leaks masquerade as pool exhaustion**: a code path that acquires but never releases (missing `finally`/`try-with-resources`) slowly starves the pool; symptoms look identical to "pool too small" and teams mistakenly increase pool size instead of fixing the leak.
- **Failover invalidates pooled connections**: on primary failover (RDS Multi-AZ, Patroni), all pooled connections to the old primary become stale/erroring. In-process pools need validation-on-borrow or `testOnBorrow`; RDS Proxy handles this transparently by draining and re-routing.
- **Idle-in-transaction connections hold locks**: a pooled connection left mid-transaction (buggy code, no timeout) can hold row/table locks indefinitely — set `idle_in_transaction_session_timeout` (Postgres) to auto-kill these.
- **Pool warm-up matters**: cold pools (min-idle=0) cause a latency spike on traffic ramp-up as connections are established on demand; set `minimumIdle`/`min_pool_size` to pre-warm.
- **Different pool per workload**: mixing OLTP (short, latency-sensitive) and reporting/batch (long-running) queries in one pool lets a few slow queries starve the pool for everyone — use separate pools/proxies per workload class.
