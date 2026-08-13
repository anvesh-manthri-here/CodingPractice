# CDN (Content Delivery Network)

> **TL;DR:** A CDN is a geo-distributed cache-and-proxy layer that terminates client connections near the user, serves cacheable content from edge PoPs, and shields the origin from load — turning a global latency/scale problem into a cache-hit-ratio problem.

## Quick Reference

| Concept | Key Fact |
|---|---|
| PoP (Point of Presence) | Edge datacenter; Cloudflare ~300+ cities, Akamai ~4000+ nodes, CloudFront ~600+ edge locations |
| Routing | Anycast (same IP announced from every PoP, BGP picks nearest) — used by Cloudflare, most of CloudFront |
| Tiering | Edge (closest to user) → Shield/mid-tier (regional aggregator) → Origin |
| Push CDN | You upload content ahead of time (good for large static/media libraries) |
| Pull CDN | CDN fetches on first miss, caches it (good for large/changing catalogs, near-zero ops) |
| Key cache-control | `max-age`, `s-maxage`, `stale-while-revalidate`, `stale-if-error`, `immutable` |
| Dynamic accel. | TCP/TLS terminated at edge even for uncacheable responses (connection reuse to origin) |
| Auth | Signed URLs (S3/CloudFront), signed cookies, JWT/token auth at edge |
| Edge compute | Run small JS/Wasm functions at PoP (Cloudflare Workers, Lambda@Edge, Fastly Compute) |
| Big vendors | Cloudflare, Fastly, Akamai, Amazon CloudFront, Google Cloud CDN, Azure Front Door |

## What It Is

- A network of caching reverse proxies distributed globally, sitting between clients and origin servers.
- Reduces latency (serve from near user), reduces origin load (absorb repeat requests), improves availability (absorbs traffic spikes/DDoS), and can accelerate even non-cacheable traffic via connection optimization.
- Not just static files anymore — modern CDNs do dynamic site acceleration, API caching, edge compute, image optimization, and security (WAF, bot management).

## Responsibilities

- Terminate client TCP/TLS connections close to the user (fewer round trips for handshake).
- Cache and serve static/cacheable responses from edge; enforce freshness via cache-control semantics.
- Collapse duplicate concurrent origin requests (request coalescing / "dogpile" prevention).
- Route requests to the best PoP/origin (anycast, DNS geo-routing, load-aware routing).
- Enforce access control (signed URLs/tokens), rate limiting, WAF/bot filtering at the edge.
- Provide purge/invalidation APIs and observability (cache hit ratio, origin offload %).

## How It Works

```
Client --TLS--> Edge PoP --(miss)--> Shield/Mid-tier PoP --(miss)--> Origin
           |                    |
        cache hit           cache hit
        (fast, close)     (regional, still absorbs load)
```

1. Client resolves CDN via DNS (geo-DNS) or connects to an anycast IP — routed to nearest/healthiest PoP via BGP.
2. Edge PoP computes a **cache key** (method + host + path + selected query params + `Vary`-selected headers) and looks up cache.
3. On hit: serve immediately, decrement TTL-based freshness.
4. On miss: forward through **shield/mid-tier** (a designated regional PoP that all edges route misses through) rather than direct-to-origin.
5. Shield deduplicates concurrent misses for the same key (single origin fetch, fan-out to all waiting edges) — this is **origin shielding**, the main defense against thundering-herd on origin.
6. Response cached per `Cache-Control`/`Surrogate-Control` headers, then propagated back down to edge and client.

## Types / Classifications

| Type | Description | Use Case |
|---|---|---|
| Push CDN | Origin proactively uploads/syncs content to CDN storage | Large media libraries, infrequent updates, predictable content set |
| Pull CDN | CDN fetches from origin on cache miss, TTL-based | Dynamic catalogs, large/unknown content sets, easy to add (just point DNS) |
| Static acceleration | Cache-first delivery of images/JS/CSS/video | CSS/JS bundles, images, downloads |
| Dynamic site acceleration (DSA) | Optimizes uncacheable/personalized traffic — persistent origin connections, TCP optimization (BBR, larger initial cwnd), route optimization over CDN's private backbone | API responses, personalized HTML, checkout flows |
| Edge compute | Run logic at PoP (auth checks, A/B routing, header rewriting, SSR) | Personalization without full origin round-trip |

## Where It Fits

- Sits in front of origin/load balancers, behind DNS — typically the first hop for public web/API traffic.
- Common layering: Client → DNS (geo/anycast) → CDN edge → CDN shield → Origin LB → App servers → DB.
- For APIs: increasingly used as an API gateway substitute for read-heavy, cacheable GET endpoints (short TTL + `stale-while-revalidate`).
- Works alongside (not instead of) origin-side caches (Redis/Varnish) — CDN handles cross-region/user-facing caching, origin caches handle compute-heavy dedup.

## Common Patterns & Real-World Tools

- **Cloudflare**: anycast everywhere, Workers (V8 isolates) for edge compute, generous free tier, tiered cache (Argo).
- **Fastly**: VCL-based config, near-instant purge (~150ms), Compute@Edge (Wasm), popular for high-control dynamic caching (used by Reddit, GitHub docs).
- **Akamai**: largest PoP footprint, enterprise/media/broadcast heavy, strong DDoS/security suite.
- **CloudFront**: tight AWS integration (S3 origin, Lambda@Edge/CloudFront Functions, signed URLs/cookies via S3+IAM), regional edge caches as mid-tier.
- Patterns: image resizing at edge (Cloudify/Fastly IO), A/B testing via edge cookies, bot mitigation, WAF rules, DNS-based geo failover, multi-CDN (traffic split across 2 vendors for resilience, e.g. via Cedexis/NS1).

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Drastically lower latency for geo-distributed users | Adds a caching layer of consistency lag (stale reads possible) |
| Absorbs traffic spikes/DDoS, protects origin | Debugging harder — extra hop, cache-key bugs are non-obvious |
| Reduces origin infra cost (bandwidth + compute) | Purge is eventually consistent across PoPs (seconds to minutes) |
| TLS/TCP termination improves perf even for dynamic content | Vendor lock-in on edge-compute APIs (Workers vs Lambda@Edge) |
| Built-in security features (WAF, bot mgmt, rate limit) | Cost scales with bandwidth; can be expensive at high egress volume |

## Real-World Scenarios

- **Flash sale / viral traffic spike**: origin can't handle 100x traffic — CDN edge caches product pages with short TTL + `stale-while-revalidate`, origin shield collapses thousands of concurrent misses into one origin fetch.
- **Global SaaS dashboard**: static JS/CSS bundles on CDN with `immutable` + content-hashed filenames (cache forever); API calls bypass cache or use very short `s-maxage`.
- **Video streaming**: push CDN pre-populates edge with new episodes at release; adaptive bitrate segments cached with long TTL.
- **Paywalled media**: signed URLs with expiry + IP/referrer binding prevent hotlinking and link sharing past paywall.
- **Multi-region compliance**: EU user requests pinned to EU PoPs/origins for GDPR data residency via geo-routing rules.

## Nuances & Gotchas

- **Cache key explosion**: including every query param (utm_*, session ids) in the cache key fragments one logical resource into thousands of cache entries → near-0% hit rate. Fix: strip/allowlist query params in cache key config.
- **`Vary: User-Agent` (or `Vary: Cookie`) footgun**: creates near-infinite cache key variants since UA strings are highly unique → effectively disables caching. Prefer normalizing to a small device-class header instead.
- **Purge propagation delay**: invalidation isn't instant globally — Akamai/CloudFront can take tens of seconds to minutes; Fastly is near-instant (~150ms). Never assume purge = synchronous; design for eventual consistency (e.g., versioned URLs instead of purge-on-deploy).
- **Cache poisoning via unkeyed headers**: if a header (e.g., `X-Forwarded-Host`, `Accept-Encoding` variants) affects the origin response but isn't part of the cache key, an attacker can poison the cached response for all subsequent users. Always key on (or strip/normalize) any header that influences the response.
- **Origin overload on mass invalidation**: purging a broad path (or TTL cliff where many objects expire simultaneously) causes a synchronized stampede of misses hitting origin at once — mitigate with shield-level request coalescing, staggered TTL jitter, and `stale-while-revalidate` so edges serve stale while refreshing in background.
- **`stale-if-error`**: lets edge continue serving stale content if origin is down/erroring — critical for resilience during origin incidents, but silently masks outages if not monitored.
- **CORS caching surprises**: caching a response with `Access-Control-Allow-Origin: siteA.com` and serving it to siteB.com from cache is a security bug — must vary cache by `Origin` header when CORS is dynamic.
- **Redirect caching**: 301/302 responses get cached too; a redirect cached too long (or cached incorrectly across environments/staging) causes hard-to-debug "stuck" redirects — always set explicit, short TTLs on redirects.
- **`s-maxage` vs `max-age`**: `s-maxage` overrides `max-age` specifically for shared caches (CDN) — lets you cache aggressively at CDN while browser cache stays short/none, useful for content that needs fast global purge-independent updates at the client but long edge caching.
- **`immutable` directive**: tells browsers to skip revalidation entirely even on refresh — only safe for content-hashed, truly never-changing URLs (e.g., `app.a1b2c3.js`).
- **Anycast route flapping**: BGP route changes can shift a client to a farther PoP mid-session, causing latency spikes or (rarely) TCP resets — mostly invisible but worth knowing when debugging "random" tail latency.

## Self-Check

1. Your hit rate has silently dropped to near-0% after marketing added `utm_source`/`utm_campaign` tracking links to a product page. What happened, and what's the fix?
2. What does origin shielding actually do at the shield/mid-tier PoP, and why is it the key defense during a flash-sale traffic spike?
3. What's the difference between `max-age` and `s-maxage`, and when would you deliberately want them to differ?
4. A response varies its body based on `X-Forwarded-Host`, but that header isn't part of the cache key. What's the security risk, and what's the fix?
5. Your API sets `Access-Control-Allow-Origin` dynamically per-caller, and the CDN caches responses. What can go wrong, and what header fixes it?

<details><summary>Answers</summary>

1. Every unique combination of tracking query params is treated as a distinct cache key, fragmenting one logical page into thousands of near-unique entries — a cache key explosion. Fix: strip or allowlist query params in the cache key config so tracking params don't participate in cache lookups.
2. The shield PoP deduplicates concurrent cache misses for the same key into a single origin fetch, fanning the response out to all waiting edges (request coalescing) instead of letting every edge hit origin independently, preventing a thundering-herd stampede on origin.
3. `s-maxage` overrides `max-age` specifically for shared/CDN caches; `max-age` governs browser (private) caching. You'd want them to differ to cache aggressively at the CDN edge while keeping the browser cache short or absent, so purges/updates reach clients fast without losing edge-level offload.
4. This is cache poisoning via an unkeyed header — since `X-Forwarded-Host` affects the origin response but isn't in the cache key, an attacker can craft a request that gets a poisoned response cached and served to all subsequent users. Fix: key on (or strip/normalize) any header that influences the response.
5. Caching one `Access-Control-Allow-Origin: siteA.com` response and serving it from cache to siteB.com is a CORS security bug — siteB gets access it shouldn't have. Fix: vary the cache by the `Origin` request header whenever CORS is dynamic.
</details>

---
**Related:** [Caching Fundamentals](04-caching-fundamentals.md) · [Cache Eviction and Invalidation](05-cache-eviction-and-invalidation.md) · [Reverse Proxy and Forward Proxy](02-reverse-proxy-and-forward-proxy.md)

*Last reviewed: 2026-08*
