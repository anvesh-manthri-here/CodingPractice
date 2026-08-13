# Cache Eviction and Invalidation

> **TL;DR:** Eviction decides what to remove when the cache is full (LRU/LFU/ARC/W-TinyLFU); invalidation decides when cached data becomes wrong and must be removed even though it fits. Get invalidation wrong and users see stale data forever; get eviction wrong and hit rate collapses under real workloads.

## Quick Reference

| Concept | Best default | Notes |
|---|---|---|
| General-purpose eviction | W-TinyLFU (Caffeine) | Beats LRU on almost all traces, low overhead |
| Redis eviction | `allkeys-lru` or `allkeys-lfu` | Approximated via random sampling, not exact |
| Scan-resistant | ARC, LFU, W-TinyLFU | Plain LRU thrashes on one-time scans |
| Simple/predictable | FIFO | O(1), no recency tracking, weak hit rate |
| TTL-only invalidation | Simplest | Bounded staleness = TTL window |
| Strongest consistency | Write-through / sync purge | Highest latency & complexity cost |
| CDN purge granularity | Tag-based (surrogate keys) | Fastly/Cloudflare purge-by-tag |
| Thundering herd fix | TTL jitter + stale-while-revalidate | Spreads/absorbs expiry spikes |
| Memory-full, no eviction | `noeviction` | Writes error out (OOM) — availability risk |

## What It Is

- **Eviction**: reclaiming space from a *full* cache by choosing a victim entry — a memory-management problem.
- **Invalidation**: marking cached data *wrong* (source changed) regardless of memory pressure — a correctness problem.
- Both exist because caches trade an authoritative source (DB) for a fast, bounded, possibly-stale copy.

## Responsibilities

- Bound memory/storage use so the cache doesn't OOM or evict the origin's headroom.
- Maximize hit rate for the actual access pattern (temporal vs frequency locality).
- Keep staleness within an acceptable, ideally explicit, bound (SLA: "up to 60s stale").
- Avoid correlated failure modes: synchronized expiry, purge storms, cache stampedes.

## How It Works

```
        write to origin
              |
              v
     invalidate/update cache  --(miss)-->  read origin --> populate cache
              |                                             |
     (TTL clock also running) -----------------------> evict on expiry
              |
     memory pressure --> eviction policy picks victim --> evict on capacity
```

- Every cached entry has two independent clocks: a **capacity clock** (am I the least valuable entry when we need room?) and a **freshness clock** (is my TTL/version still valid?).
- Eviction policies approximate "value" using recency (LRU), frequency (LFU), or both (ARC, W-TinyLFU).
- Invalidation policies approximate "still correct" using time (TTL), explicit signals (purge, CDC), or indirection (versioned keys).

## Types / Classifications

### Eviction policies

| Policy | Idea | Good for | Weak point |
|---|---|---|---|
| FIFO | Evict oldest inserted | Simple queues, log buffers | Ignores usage entirely |
| LRU | Evict least-recently-used | Recency-biased workloads | Thrashes on large sequential scans |
| LFU | Evict least-frequently-used | Stable popularity (hot items) | Slow to adapt; new items die before counted |
| ARC | Adaptive blend of recency + frequency lists, self-tunes split | Mixed workloads, no tuning needed | Patented (IBM), rarer in OSS |
| W-TinyLFU | TinyLFU frequency sketch + LRU window to admit new items | General purpose, high churn | More moving parts (sketch + admission) |
| Redis approximated LRU/LFU | Sample N random keys (default 5), evict best-of-sample | Redis at scale (exact LRU too costly) | Approximation quality ~ sample size |

### Invalidation approaches

| Approach | Mechanism | Consistency | Complexity |
|---|---|---|---|
| TTL-only | Expire after fixed time | Weak (stale up to TTL) | Very low |
| Explicit purge/delete | App deletes key on write | Medium (race-prone) | Low-medium |
| Write-through | Write goes to cache+DB synchronously | Strong | Medium-high (write latency) |
| Versioned keys | Key embeds version/hash (`user:42:v7`) | Strong for readers, old versions just orphan/expire | Medium |
| Event/CDC-driven | DB change stream (Debezium/Kafka) triggers invalidation | Strong, async (eventual, seconds) | High (infra) |
| Generational namespace bump | Bump a global/prefix version to logically evict a whole class | Strong, O(1) "clear" without deleting keys | Low-medium |

## Where It Fits

- **In-process cache** (Caffeine, Guava, `functools.lru_cache`): per-instance, no cross-node coordination — cheapest but each node can disagree.
- **Distributed cache** (Redis, Memcached): shared view across app nodes; invalidation must reach all app-side local caches too (two-tier problem).
- **CDN edge cache** (Fastly, Cloudflare, Akamai, Varnish): geographically distributed; purge is a fan-out control-plane operation, not a data-plane write.
- **HTTP layer**: `Cache-Control`, `ETag`/`If-None-Match`, `stale-while-revalidate` headers let the client/CDN self-manage freshness.

## Common Patterns & Real-World Tools

- **Redis `maxmemory-policy`**: `noeviction`, `allkeys-lru`, `volatile-lru`, `allkeys-lfu`, `volatile-lfu`, `allkeys-random`, `volatile-random`, `volatile-ttl`. `volatile-*` only evicts keys with a TTL set, protecting permanent keys.
- **Caffeine (Java)**: implements W-TinyLFU by default; supports size-based, time-based (`expireAfterWrite`/`expireAfterAccess`), and reference-based eviction.
- **Varnish bans**: lazy invalidation — a ban is a predicate checked at lookup time, not an eager sweep; cheap to issue, cost paid on read until GC compacts the ban list.
- **Fastly/Cloudflare purge-by-tag (surrogate keys)**: tag responses (e.g. `product:123`, `category:shoes`) at origin via header; one purge call invalidates every cached object carrying that tag across the whole edge network.
- **Cache-aside + explicit delete**: most common app pattern — write DB, then `DEL` the key (not update-in-place, to avoid write-write races).
- **Generational bump**: e.g. store `schema_version` in Redis; prefix all keys with it; bump the version to instantly "invalidate" millions of keys without touching them (old ones just age out via eviction/TTL).

## Pros & Cons / Trade-offs

| Choice | Pros | Cons |
|---|---|---|
| LRU | Simple, good default, O(1) with linked list+hash | Scan-vulnerable, ignores frequency |
| LFU | Protects hot items long-term | Cold-start penalty, needs decay to forget old popularity |
| TTL-only invalidation | Zero coordination, self-healing | Staleness window always exists; picking TTL is a guess |
| Write-through | Cache never stale on the happy path | Every write pays cache latency; complex failure handling |
| Event/CDC-driven | Decouples cache from write path, scales writers | Operational overhead, eventual (not immediate) consistency |
| CDN tag purge | Coarse, fast, network-wide | Purge fans out globally — expensive/rate-limited if overused |

## Real-World Scenarios

- **E-commerce product page**: cache-aside + Redis `volatile-lru`, TTL 5 min + jitter, plus explicit purge-by-tag on price update via Fastly surrogate keys.
- **User session store**: Redis with TTL only (`volatile-ttl` eviction), no manual invalidation needed — session expiry *is* the business rule.
- **Feature flags / config**: generational namespace bump — flip one version key to invalidate every cached config across thousands of app instances instantly.
- **Search index snippets behind Varnish**: tag-based bans per document ID; reindex triggers a ban on that tag instead of flushing the whole cache.
- **Multi-region read replicas + local Caffeine cache**: CDC stream (Kafka/Debezium) publishes invalidation events consumed by each region to evict local entries — avoids polling.

## Nuances & Gotchas

- **"There are only two hard things in CS"** — the joke ("cache invalidation and naming things") is really about this: *when* to invalidate is a distributed-agreement problem in disguise (who knows the data changed, and did everyone hear about it?).
- **Two-node invalidation race**: Node A reads DB (stale value in flight) while Node B writes DB then deletes cache key; A's stale read then repopulates the cache *after* B's delete — cache is now permanently stale until TTL. Mitigate with short TTL as a backstop, or write-through, or delayed double-delete.
- **Thundering herd on synchronized TTL expiry**: thousands of keys set with identical TTL expire in the same millisecond, all miss simultaneously, all hammer the DB. Fix: add TTL jitter (`ttl = base ± random(0, base*0.1)`).
- **Stale-while-revalidate**: serve the stale value immediately, kick off async refresh in background — trades brief staleness for zero read-latency spikes; standard HTTP header and common Redis/Varnish pattern.
- **Purge storms**: bulk/global purges (e.g. "clear everything" on deploy) cause a correlated mass cache-miss across the whole fleet — same failure shape as synchronized TTL, but self-inflicted. Stagger or pre-warm instead.
- **`noeviction` + unbounded memory**: with `maxmemory-policy=noeviction`, once memory is full *writes* start failing (OOM errors) instead of quietly evicting — a common prod surprise; fine for a system-of-record cache, dangerous as a default.
- **LRU thrash under scan workloads**: a full-table scan or backup job touches every key once, evicting the actual hot working set — classic LRU failure; ARC/LFU/W-TinyLFU resist this via frequency signal or admission filters.
- **Global purge fan-out cost**: a CDN purge-by-tag isn't a single cheap op — it propagates to every PoP worldwide; Cloudflare/Fastly rate-limit purge APIs and recommend tag-scoped over full-zone purges for exactly this reason.
- **Redis sampling quality**: `maxmemory-samples` (default 5) trades CPU for eviction accuracy — raising it approaches true LRU/LFU behavior at a cost; too low and "approximated LRU" barely beats random.
- **Versioned keys leak memory**: old versions aren't deleted, just orphaned — need TTL or eviction to actually reclaim them, or a version key explodes cache size over time.

## Self-Check

1. Walk through the two-node invalidation race step by step: Node A reads the DB, Node B writes and deletes the cache key, then A repopulates the cache. Name one mitigation.
2. Why does `noeviction` make writes fail instead of evicting, and why might that be the correct trade-off for a session store but wrong default elsewhere?
3. A cache is backed by a nightly full-table backup scan hitting every key once. Under plain LRU, what happens to the hot working set, and which policies avoid this?
4. You're caching product prices with occasional bulk price updates and need instant, coarse invalidation across millions of keys without deleting them one by one. Which invalidation approach fits and why?
5. Redis is set to `allkeys-lfu` with `maxmemory-samples=5`. Why is this "LFU" only approximate, and what's the lever to make it more accurate (and its cost)?

<details><summary>Answers</summary>

1. A reads the DB and gets the stale value in flight; B writes the DB then deletes the cache key; A's read completes after B's delete and repopulates the cache with the stale value — now permanently stale until TTL. Mitigate with a short TTL backstop, write-through, or delayed double-delete.
2. With `noeviction`, once memory is full there's no victim to reclaim space, so the write itself errors out rather than silently evicting data — this protects a system-of-record cache from silent data loss, but for a session store (or general cache) it turns a capacity problem into an availability outage instead of just dropping a stale/cold entry.
3. The scan touches every key exactly once, so LRU treats each scanned key as "most recent" and evicts the actual hot working set to make room — classic LRU thrash. ARC, LFU, and W-TinyLFU resist this because they weigh frequency (or an admission filter), not just recency.
4. Generational namespace bump — bump a global/prefix version key so all old keys are logically invalidated in O(1) without touching them; they just orphan and age out via TTL/eviction. Explicit per-key purge doesn't scale to millions of keys instantly.
5. LFU approximation samples only N (5) random keys and evicts the best-of-sample rather than tracking exact global frequency, so it can miss the true least-frequently-used key. Raising `maxmemory-samples` approaches true LFU accuracy at the cost of more CPU per eviction.
</details>

---
**Related:** [Caching Fundamentals](04-caching-fundamentals.md) · [CDN](06-cdn.md) · [Consistency Models](../01-fundamentals/05-consistency-models.md)

*Last reviewed: 2026-08*
