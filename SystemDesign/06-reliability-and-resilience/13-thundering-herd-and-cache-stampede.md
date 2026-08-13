# Thundering Herd and Cache Stampede

> **TL;DR:** Any time many clients share a synchronized trigger — cache TTL expiry, DNS refresh, reconnect after an outage, a cron tick at :00 — they all retry/reload at once and overload the shared resource behind it. Fix by desynchronizing (jitter), deduplicating (single-flight/locking), or masking latency (stale-while-revalidate).

## Quick Reference

| Trigger | Typical Failure | Primary Fix | Secondary Fix |
|---|---|---|---|
| Cache key TTL expiry (Redis/Memcached) | DB/origin gets N simultaneous misses | Single-flight / lock-on-miss | Stale-while-revalidate |
| CDN edge cache expiry | Origin server overload | Request coalescing at edge | TTL jitter |
| DNS TTL expiry (many resolvers) | Auth server / origin spike | TTL jitter, low TTL + caching layer | Anycast to spread load |
| Client reconnect after broker/LB outage (WebSocket, gRPC) | Connection storm on recovery | Exponential backoff + full jitter | Staggered reconnect ramp |
| Cron / batch jobs at :00 | Shared DB/queue spike every hour | Staggered schedules (offset per job) | Jitter on job start |
| Config/flag cache refresh across fleet | Config service overload | Jitter refresh interval per host | Push instead of poll |
| Load balancer health-check sync | All backends probed simultaneously | Jitter health-check interval | Passive health checks |
| Mass cache eviction (deploy, restart, cold cache) | "Cold start stampede" on new node | Pre-warm cache before traffic cutover | Gradual traffic ramp (canary) |

## What It Is

- **Thundering herd**: general OS/distributed-systems term — many waiters wake up for one event, only one can proceed, rest contend for nothing (originated from `select()`/`accept()` wakeups on a single socket).
- **Cache stampede** (aka dog-piling): the cache-specific instance — a hot key expires, N concurrent requests all miss and hit the origin/DB simultaneously to recompute the same value.
- Root cause is always **synchronization of independent actors around a shared deadline or shared event**, not the resource itself being slow.

## Responsibilities

The mitigation layer (cache client, proxy, scheduler) must:
- Ensure only one (or few) requests actually do the expensive recompute/reconnect/refetch.
- Let the other N-1 requests either wait briefly, get a stale-but-valid result, or be spread out in time.
- Avoid introducing a new single point of failure (e.g., a lock that itself isn't fault-tolerant).

## How It Works

**Single-flight / request coalescing**: first request for a missing key acquires an in-process or distributed lock and fetches; concurrent requests for the same key attach to the in-flight call and share its result instead of issuing their own.
- In-process: Go's `golang.org/x/sync/singleflight`, Guava `LoadingCache`.
- Distributed: `SET key value NX EX ttl` in Redis as a mutex before recomputing; loser retries after short sleep or polls.

**Stale-while-revalidate (SWR)**: serve the expired/stale cached value immediately to all callers while exactly one background request refreshes it. Used by HTTP `Cache-Control: stale-while-revalidate=N`, CDNs (Fastly, Cloudflare), and Varnish `grace` mode.

**Jitter**: add randomness to a deadline so N clients don't fire at the same instant.
- TTL jitter: `ttl = base_ttl + random(0, base_ttl * 0.1)` so keys expire over a spread window, not all at once.
- Backoff jitter: AWS's "full jitter" — `sleep = random(0, min(cap, base * 2^attempt))` — beats plain exponential backoff for reconnect storms.

**Locking-on-miss with early expiry**: store a logical expiry earlier than the physical TTL; first request past logical expiry recomputes (holding a lock) while others still get the (not-yet-physically-expired) value — this is effectively SWR implemented manually in app code.

**Staggered scheduling**: assign each job/host a fixed offset (`hash(hostname) % 60` seconds) instead of a shared cron boundary, spreading load deterministically without randomness.

```
Without jitter:        With jitter:
|||||||||  <- spike     |  |   | |  |   | |  <- spread
t=TTL                   t=TTL..TTL+jitter
```

## Types / Classifications

| Category | Example | Distinguishing trait |
|---|---|---|
| Cache-miss stampede | Redis key expiry | Solved by coalescing at the cache layer |
| Connection storm | Broker/LB comes back after outage | Solved by jittered backoff, not coalescing |
| Polling storm | Fleet polling config service on fixed interval | Solved by jitter + push-based invalidation |
| Cold-start stampede | New pod/node with empty cache | Solved by pre-warming, gradual ramp |
| Retry storm | Client retries on 5xx/timeout in lockstep | Solved by jittered exponential backoff + circuit breaker |

## Where It Fits

- **Client → CDN → Origin**: CDN edge nodes coalesce and serve stale to protect origin; without this, a viral cache-busting event takes origin down.
- **App → Cache → DB**: cache-aside pattern is the classic stampede site; mitigations live in the cache client wrapper.
- **Service mesh reconnects**: Envoy/gRPC clients reconnecting to a recovering upstream need jittered backoff or they re-create the outage they're recovering from.
- **Distributed scheduling**: Kubernetes CronJobs, Airflow DAGs at top-of-hour — stagger via `startingDeadlineSeconds` and offset schedules.
- Ties into **circuit breakers** and **rate limiting** files — coalescing reduces the herd's size before it ever reaches the breaker/limiter.

## Common Patterns & Real-World Tools

| Tool/System | Mechanism |
|---|---|
| Varnish | `grace` + `saintmode` for stale-while-revalidate |
| Nginx | `proxy_cache_lock` + `proxy_cache_use_stale updating` |
| Redis | `SET NX EX` mutex pattern; Redisson distributed lock |
| Memcached | "gets"/CAS with app-level recompute lock |
| Fastly/Cloudflare | Native `stale-while-revalidate` / request collapsing |
| AWS SDKs | Full jitter backoff built into retry policies |
| Kubernetes | `startingDeadlineSeconds`, pod disruption spreading |
| Go `singleflight`, Java Guava `LoadingCache.refreshAfterWrite` | In-process request coalescing |

## Pros & Cons / Trade-offs

| Mitigation | Pros | Cons |
|---|---|---|
| Jitter | Trivial to add, no new infra | Doesn't eliminate load, just spreads it; needs correct bounds |
| Single-flight (in-process) | Zero extra infra, fast | Only helps within one process/host; N hosts still each fetch once |
| Distributed lock | Coalesces across the whole fleet | Lock service becomes new dependency; risk of deadlock/stale lock if holder crashes |
| Stale-while-revalidate | Zero latency spike for users | Serves slightly stale data; needs bounded staleness tolerance |
| Pre-warming | Eliminates cold-start stampede entirely | Extra deploy complexity; wasted work if data unused |
| Staggered scheduling | Deterministic, no randomness needed | Requires coordination/config; harder to reason about "when does X run" |

## Real-World Scenarios

- **2016-era Instagram/Twitter cache stampede**: a celebrity post cache key expires under massive read load; without coalescing, thousands of DB queries fire for the identical row.
- **DNS-based service discovery**: thousands of clients with synchronized DNS TTL (say, 60s) re-resolve simultaneously; a slow/overloaded DNS server compounds into a full outage. Fix: jittered TTL or client-side caching with jitter.
- **Post-incident reconnect storm**: Kafka broker restarts, 500 consumers reconnect in the same second, broker CPU spikes handling handshake/auth for all of them at once — worse than the original outage. Fix: client-side jittered exponential backoff.
- **Kubernetes cold cache after rolling deploy**: all pods restart together, local in-memory caches empty, DB gets N-way simultaneous full-table-scan-equivalent load. Fix: rolling deploy with readiness gates + pre-warm step, not big-bang restart.
- **Top-of-hour cron pile-up**: 200 cron jobs across a fleet all scheduled at `0 * * * *` hit the same shared DB connection pool, exhausting it every hour on the dot. Fix: per-job offset via hash of job name.

## Nuances & Gotchas

- **Locks can outlive their holder**: if the process holding a Redis mutex crashes before releasing it, use a TTL on the lock itself (`SET NX EX 5`) — otherwise every subsequent request stampedes anyway, now blocked on a dead lock.
- **Jitter bounds matter**: too little jitter (e.g., ±1% of TTL) doesn't meaningfully spread load; too much (e.g., ±50%) means some clients serve very stale data. Tune to the actual traffic pattern, not a copy-pasted constant.
- **SWR hides the problem, not fixes it**: if the origin is *permanently* slow (not just momentarily overloaded), SWR just means everyone gets stale data forever while the single revalidator keeps timing out — pair with a circuit breaker on the revalidation path.
- **Coalescing only works per-node unless distributed**: in-process single-flight in a 50-node fleet still produces 50 concurrent origin requests. If that's still too many, you need a cross-node lock or a dedicated cache-fill service.
- **Negative caching gets missed**: stampedes also happen on cache misses for *nonexistent* keys (e.g., "user not found") if you don't cache the negative result — every request re-hits the DB to confirm absence. Cache negatives with a short TTL.
- **Retry storms compound stampedes**: a stampede causes origin timeouts, clients retry immediately, retries add to the herd, origin gets worse — a positive feedback loop. Always combine jitter/coalescing with retry budgets and circuit breakers.
- **Cache warm-up races on deploy**: rolling out a new cache version/schema and flushing the whole cache at once (instead of per-key invalidation) manufactures an artificial stampede — prefer versioned keys over global flush.
- **Health-check synchronization**: multiple load balancers or sidecars probing the same backend on identical intervals can itself become a mini thundering herd against the backend — jitter health-check intervals too.
- **"Fixed" delay after failure is not backoff**: many naive retry implementations use `sleep(5)` on every client — this just re-creates the herd 5 seconds later. Jitter is not optional, it's the actual fix.
