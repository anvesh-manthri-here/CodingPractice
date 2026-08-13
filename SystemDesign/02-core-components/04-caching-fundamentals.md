# Caching Fundamentals

> **TL;DR:** A cache trades memory (and staleness risk) for latency — cheap only if hit ratio is high; the pattern you pick (aside/through/behind) determines who owns consistency and what happens when it fails.

## Quick Reference

| Tier | Rough latency | Size | Shared? |
|---|---|---|---|
| CPU L1/L2/L3 | 1-20 ns | KB-MB | Per core/socket |
| RAM (local process, e.g. Caffeine) | 50-200 ns | MB-GB | Single process |
| Distributed cache (Redis/Memcached, same DC) | 0.5-2 ms | GB-TB | Fleet-wide |
| CDN edge (Varnish/CloudFront/Fastly) | 10-50 ms | TB+ | Global, per-POP |
| Browser cache / disk | 0-5 ms (local disk) | MB-GB | Per user |
| Origin DB/service (cache miss) | 20-200+ ms | — | — |

## What It Is

- A cache is a fast, smaller copy of data kept closer to the consumer to avoid recomputing or refetching from a slower source of truth.
- Core bet: access patterns are skewed (Zipfian) — a small hot subset accounts for most requests, so caching it captures most of the benefit.
- Every cache introduces a second copy of truth; the whole discipline is managing the gap between the two.

## Responsibilities

- Absorb read traffic so the origin (DB, service, upstream API) sees only misses.
- Cut tail latency by serving from memory/edge instead of disk/network hops.
- Smooth load spikes (thundering herds) away from stateful backends.
- Reduce cost — fewer DB IOPS, less compute for repeated work, less cross-region bandwidth.

## How It Works

```
Client -> Browser cache -> CDN edge -> App/local cache -> Distributed cache -> Origin (DB/service)
          (ms)             (10-50ms)   (ns-us)            (0.5-2ms)            (20-200ms)
```
- Each tier is checked in order; a miss falls through to the next, slower tier, then populates the tiers above it on the way back.
- Key steps per request: hash key → lookup → hit (return) or miss (fetch, store, return).

### Hit ratio math

- Origin load ≈ `request_rate × (1 - hit_ratio)`. Going from 90% → 95% hit ratio *halves* origin load (10% miss → 5% miss).
- 95% → 99% hit ratio is a **5x** reduction in origin load — small ratio gains near 100% matter disproportionately.
- Effective latency ≈ `hit_ratio × cache_latency + miss_ratio × (cache_latency + origin_latency)` — at 99% hit ratio with a 1ms cache and 100ms origin, effective latency ≈ 2ms, not 100ms.
- Implication: monitor hit ratio as a first-class SLO, not just latency — a small hit-ratio drop (e.g., after a deploy resets a local cache) can double or triple DB load instantly.

## Types / Classifications

### Read/write patterns

| Pattern | Read path | Write path | Consistency | Failure behavior |
|---|---|---|---|---|
| Cache-aside (lazy load) | App checks cache, on miss reads DB and populates cache | App writes DB, then invalidates/deletes cache key | Eventual; window for stale reads | Cache down → all reads hit DB (survivable, slow) |
| Read-through | Cache itself loads from DB on miss (app only talks to cache) | Same as aside, or paired with write-through | Same as aside | Cache down → reads fail unless app has DB fallback |
| Write-through | N/A | App writes to cache, cache synchronously writes DB | Strong between cache and DB | Write latency = cache + DB; DB down blocks writes |
| Write-behind (write-back) | N/A | App writes cache only; cache async-flushes to DB | Weak — DB lags cache | Cache crash before flush = data loss |
| Refresh-ahead | Cache proactively refetches hot keys before TTL expiry | N/A | Reduces stale-read window vs TTL expiry | Extra load if refresh predicts wrong keys |

- Cache-aside is the default for most systems (Redis + app code); read/write-through need a cache provider that supports a loader (e.g., Redis with a plugin, or a library like Ehcache).
- Write-behind buys write latency at the cost of durability — use only when some loss is tolerable (metrics, counters) or paired with a durable queue.

### What to cache / never cache

- **Cache**: read-heavy, expensive-to-compute, tolerant-of-slight-staleness data — rendered pages, DB query results, session data, computed aggregates, external API responses.
- **Never cache (naively)**: data requiring strict real-time accuracy (account balance mid-transaction), per-request unique data (no reuse = no hit), secrets/PII without strict TTL+encryption, and anything where staleness causes a security decision to be wrong (auth tokens, permissions — cache short-TTL only).

## Where It Fits

- **CPU cache**: hardware, invisible to app code, matters for tight loops/HFT.
- **Local/in-process (Caffeine, Guava, LRU dict)**: per-instance, zero network hop, but N replicas = N copies, inconsistent across a fleet.
- **Distributed (Redis, Memcached)**: shared state across a fleet, single source of "cached truth," adds a network hop and a dependency.
- **CDN (Varnish, CloudFront, Akamai, Fastly)**: caches HTTP responses at edge POPs near users; best for static assets and cacheable API GETs.
- **Browser**: HTTP cache headers (`Cache-Control`, `ETag`) — zero network cost when it hits, fully client-controlled.
- Typical layered stack: browser → CDN → app-local (Caffeine) → distributed (Redis) → DB, each layer shaving off traffic before the next.

## Common Patterns & Real-World Tools

- **Redis**: distributed, rich data structures (hash, sorted set, list), persistence options, pub/sub for invalidation broadcast, clustering for horizontal scale.
- **Memcached**: simpler, pure key-value, multithreaded, slightly lower per-op overhead — good for pure lookaside caching without needing data structures.
- **Caffeine (Java)**: in-process, window-TinyLFU eviction (better hit rate than LRU), used inside services (e.g., as L1 in front of Redis L2).
- **Varnish**: HTTP accelerator/reverse proxy cache, VCL for custom caching logic, common in front of web servers.
- **CDNs (Fastly, CloudFront, Akamai)**: managed edge caching, often with instant purge APIs.
- **Multi-level caching**: L1 (local, ns) + L2 (Redis, ms) is a common combo — check L1 first, fall back to L2, fall back to origin.

### Key design & namespacing

- Convention: `{namespace}:{entity}:{id}:{version}` e.g. `user:profile:12345:v2` — version suffix lets you bump schema without manual flush.
- Include all inputs that affect the value (locale, currency, feature flag state) or you'll serve wrong variants to the wrong users.
- Keep keys short — key overhead multiplies across millions of entries and eats into node memory.

## Pros & Cons / Trade-offs

| | Local (in-process) | Distributed |
|---|---|---|
| Latency | Nanoseconds, no network | Sub-ms to few ms, network hop |
| Consistency across fleet | Poor — each instance diverges | Good — one shared view |
| Capacity | Bound by single host RAM | Scales horizontally |
| Failure blast radius | Small (one instance) | Large (shared dependency for all instances) |
| Ops overhead | None (just a library) | Cluster to run/monitor/upgrade |

- Local cache wins for very hot, small, latency-critical data (auth flags, feature configs).
- Distributed wins when consistency across replicas or dataset size matters more than the last microseconds.

## Real-World Scenarios

- **Product page reads**: cache-aside with Redis, TTL 5-15 min, absorbs 95%+ of reads for a catalog DB.
- **Session store**: Redis as source of truth (not just a cache) — write-through-like, since losing it logs users out.
- **Rate limiter counters**: Redis with atomic INCR + TTL, write-behind unsuitable (needs strong per-request accuracy).
- **Static assets (JS/CSS/images)**: CDN with long TTL + content-hashed filenames for instant cache-busting on deploy.
- **Search/aggregation results**: refresh-ahead for top queries (trending searches) to keep p99 low without stale spikes at expiry.

*(Invalidation strategies, eviction policies (LRU/LFU/TTL), and stampede protection are covered in the dedicated eviction/invalidation notes — not duplicated here.)*

## Nuances & Gotchas

- **Cache-aside race**: thread A misses, reads stale DB value, thread B writes new value + invalidates, then A writes its stale read back into cache → cache now permanently wrong until TTL expiry. Mitigate with short TTLs, write-through for hot keys, or versioned/CAS writes.
- **Unbounded key growth**: no TTL + high-cardinality keys (e.g., keying by full query string or user+timestamp) silently grows memory until eviction storms or OOM. Always set a default TTL and monitor `maxmemory` + eviction rate.
- **Hot keys**: a single celebrity key (viral post, flash-sale SKU) can saturate one Redis shard even though the cluster overall has capacity — fix with local L1 cache in front, key sharding (`key:0..N`), or request coalescing.
- **Serialization cost dominates for small values**: for tiny objects, JSON/protobuf (de)serialization + network round-trip can cost more than the DB lookup avoided — measure before caching trivially cheap reads.
- **Caching negative results**: forgetting to cache "not found" lets an attacker or bug hammer the origin with misses for nonexistent keys (cache penetration) — cache negatives with a short TTL, or use a Bloom filter to short-circuit known-absent keys.
- **Cache becomes a hard dependency**: read-through/write-through designs that never handle a cache outage turn an optimization into a SPOF; always design a degraded-but-correct path, and load-test a cold start (empty cache) — a full-fleet restart with 0% hit ratio can be indistinguishable from a DDoS on the origin.
- **Thundering herd on expiry**: many keys with the same TTL expire simultaneously, causing a synchronized stampede to the origin — jitter TTLs (`ttl ± random%`) to spread expiry.
- **Clock skew / TTL drift**: distributed cache nodes and app servers disagreeing on time can cause premature or delayed expiry — rely on the cache server's clock, not client-side expiry logic, where possible.

## Self-Check

1. A service at 10,000 req/s uses a 1ms cache in front of a 150ms origin. A deploy resets the local cache, dropping hit ratio from 99% to 95%. What happens to origin load and effective latency?
2. Walk through the cache-aside race: thread A reads a stale value from the DB right as thread B writes+invalidates. How does the cache end up permanently wrong, and what stops it?
3. Why can a full-fleet restart with a cold (empty) cache be indistinguishable from a DDoS on the origin, and how do you defend against it?
4. A flash-sale SKU goes viral and one Redis shard saturates even though the cluster has spare capacity overall. What's happening, and what are two fixes?
5. When does cache-aside beat write-through, and why?

<details><summary>Answers</summary>

1. Origin load goes from 100 req/s (1% miss) to 500 req/s (5% miss) — a 5x increase. Effective latency goes from ~2.5ms (0.99×1 + 0.01×151) to ~8.5ms (0.95×1 + 0.05×151) — roughly 3.4x worse from a 4-point hit-ratio drop.
2. A misses, reads the old value from the DB, then B writes a new value and invalidates the key; A's delayed cache-populate then overwrites the cache with its now-stale read, and the entry stays wrong until TTL expiry. Short TTLs, write-through for hot keys, or versioned/CAS writes prevent the stale write from landing.
3. With 0% hit ratio every request falls through to the origin at once, producing the same sudden multiplied request volume the origin would see under an actual DDoS. Defend by load-testing cold starts explicitly, warming caches before traffic cutover, and staggering fleet restarts.
4. One celebrity key concentrates all traffic on the single shard that owns it, so cluster-wide headroom doesn't help. Fix with a local L1 cache in front of the shard, or shard the key itself (`key:0..N`) with request coalescing.
5. Cache-aside beats write-through when you need graceful degradation and don't want the cache in the write's critical path: on cache failure, cache-aside just falls back to reading the DB directly (slow but correct), while write-through blocks writes entirely if the DB is down and requires a cache provider with loader support.
</details>

---
**Related:** [Cache Eviction and Invalidation](05-cache-eviction-and-invalidation.md) · [CDN](06-cdn.md) · [Consistency Models](../01-fundamentals/05-consistency-models.md)

*Last reviewed: 2026-08*
