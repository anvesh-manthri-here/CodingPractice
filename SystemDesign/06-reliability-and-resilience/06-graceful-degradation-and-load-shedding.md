# Graceful Degradation and Load Shedding

> **TL;DR:** Graceful degradation trades completeness for availability — serve a simplified/stale/cached response instead of an error when a dependency is unhealthy. Load shedding trades fairness-to-latecomers for system survival — reject excess work based on *system health* (queue depth, latency, CPU) rather than *who is asking*, which is what distinguishes it from rate limiting.

## Quick Reference

| Concept | Trigger | Decision basis | Goal |
|---|---|---|---|
| Graceful degradation | Dependency slow/down | Feature importance | Stay *usable*, not perfect |
| Load shedding | Local overload signal (queue depth, latency, CPU) | System health + request priority | Protect the server itself |
| Rate limiting | Per-client quota exceeded | Caller identity (API key, IP, user) | Fairness / abuse prevention |
| Circuit breaker | Downstream error rate | Downstream health | Stop calling a failing dependency |
| Backpressure | Buffer/queue near full | Local resource pressure | Slow producers before shedding |

## What It Is

- **Graceful degradation**: when a component or dependency is unhealthy, serve a reduced-quality response (cached, stale, default, partial) instead of propagating the failure up the stack.
- **Load shedding**: proactively reject a fraction of incoming requests *before* they exhaust resources, so the system stays responsive for the requests it does accept, instead of collapsing under load (thrashing, OOM, cascading timeouts).
- Both are admission/response strategies for the same underlying problem: finite capacity meeting variable demand or dependency failure.

## Responsibilities

- Detect unhealthy state early: latency percentiles (p99), queue depth, CPU/memory saturation, error rate — not just binary up/down.
- Define a fallback response per feature (cache hit, default value, empty result, reduced dataset) ahead of time — this is a design-time decision, not runtime improvisation.
- Classify requests by priority/criticality (checkout > browsing > analytics beacon) so shedding removes the least valuable work first.
- Shed load cheaply — rejecting must cost less than processing (e.g., reject at load balancer/ingress before deep queuing).
- Expose signals (metrics, headers like `Retry-After`) so clients/upstream services can back off.

## How It Works

1. **Health signal collection**: each service tracks local indicators — request queue length, in-flight request count, CPU utilization, GC pause time, thread-pool saturation.
2. **Threshold crossing**: when a signal exceeds a watermark (e.g., queue > 500, p99 latency > 200ms), the service enters a degraded/shedding state.
3. **Shed decision**: incoming request is classified (priority tier, cost estimate) and either accepted, degraded, or rejected (HTTP 503 / 429 with `Retry-After`) — cheap rejection at the front door (LB, API gateway, Envoy) avoids wasting downstream capacity.
4. **Degrade decision** (if accepted): if a dependency call is slow/failing (often via a circuit breaker already open), skip it and return a fallback: cached value, stale copy, computed default, or omit that section of the response entirely.
5. **Recovery**: signals drop below watermark → shedding relaxes; breakers half-open and probe dependency health before fully resuming.

```
Request → [LB/Gateway: shed by priority+load] → Service
                                                    │
                                          dependency healthy? ──no──> fallback (cache/stale/default)
                                                    │yes
                                                 normal path
```

## Types / Classifications

**Degradation strategies (by what you serve instead):**
- *Cached/stale data*: serve last-known-good response past its normal TTL (Netflix, CDNs stale-while-revalidate).
- *Reduced result set*: fewer search results, fewer recommendation slots, simplified ranking (skip expensive re-ranking model).
- *Static fallback*: default homepage, generic recommendations instead of personalized ones.
- *Feature toggle-off*: disable non-critical widgets (reviews, "recently viewed") under load — read-only static shell stays up.
- *Partial response*: return what's ready, mark missing sections as unavailable instead of failing the whole page.

**Load shedding strategies (by shedding criterion):**
- *Priority/criticality-based*: drop low-priority (analytics, prefetch, background sync) before high-priority (checkout, auth).
- *Cost-based*: shed requests estimated to be expensive (large queries, uncached lookups) first.
- *Random/probabilistic*: shed a percentage of all traffic uniformly (simplest, least fair).
- *Queue-based (CoDel-style / LIFO)*: drop oldest queued requests (already stale by the time they'd be served) or switch to LIFO under overload so newest requests get served first.
- *Client-tier based*: free tier sheds before paid tier — overlaps with rate limiting but decision still gated by system load, not just quota.

## Where It Fits

- **Ingress layer**: API gateway / load balancer (Envoy, NGINX, AWS ALB) sheds cheaply before backend is touched — first line of defense.
- **Service mesh**: Envoy's adaptive concurrency limits, Istio circuit breaking configs shed at the sidecar.
- **Application layer**: business logic decides *what* to degrade (which widget, which field) — gateway doesn't know domain semantics.
- **Data layer**: read replicas / caches (Redis, CDN) are the substrate that makes "serve stale" possible; without a cache, degradation degenerates to "serve nothing."
- Sits alongside circuit breakers (trigger for degradation), bulkheads (isolate blast radius so shedding in one pool doesn't starve others), and retries (retries must respect shed signals or amplify overload).

## Common Patterns & Real-World Tools

- **Netflix**: homepage falls back to a generic, non-personalized list if the recommendation service (personalization microservice) times out — uses Hystrix (historically) / resilience libraries for fallback methods per dependency.
- **Google Search**: under load or partial index-shard unavailability, returns fewer results or skips spelling-correction/knowledge-panel enrichment rather than failing the query.
- **Amazon**: product page degrades — reviews, "customers also bought" can disappear under stress while core price/buy-box stays.
- **Envoy**: adaptive concurrency limiter (gradient-based, like TCP congestion control) auto-tunes max in-flight requests per host.
- **Netflix Zuul / Concurrency limits (`Netflix/concurrency-limits`)**: library implementing AIMD-style client-side load shedding.
- **AWS**: API Gateway throttling + Lambda reserved concurrency; ALB returns 503 when target group unhealthy beyond threshold.
- **Kafka consumers**: shed by pausing partitions / dropping low-priority topics when consumer lag exceeds threshold.
- **CDNs (Cloudflare, Fastly)**: serve stale-while-revalidate or stale-if-error content when origin is down.

## Pros & Cons / Trade-offs

| Aspect | Benefit | Cost |
|---|---|---|
| Graceful degradation | Keeps core UX alive during partial outage | Extra code paths, fallback staleness must be bounded/communicated |
| Load shedding | Prevents total collapse (better than 100% failure) | Some legitimate users get errors even though capacity theoretically existed moments ago |
| Priority shedding | Protects revenue-critical paths | Requires upfront, org-wide agreement on priority tiers (political, not just technical) |
| vs rate limiting | Reacts to real-time health, not stale quotas | Harder to reason about/debug — non-deterministic based on load at that instant |

## Real-World Scenarios

- **Flash sale traffic spike**: checkout stays fully functional; "you may also like" and review sections are shed/degraded to static placeholders — protects the money path.
- **Downstream recommendation service outage**: homepage serves cached "trending now" list instead of 500ing the whole page (Netflix pattern).
- **Database replica lag/overload**: search returns top N results from a faster, less-complete index instead of full ranked results (Google/Elasticsearch under shard failure).
- **Black Friday traffic surge on an e-commerce gateway**: load shedding rejects bot/scraper and low-priority background sync traffic first via 429s, preserving capacity for buyers.
- **Regional outage failover**: traffic shifted to surviving region triggers shedding there too, so that region degrades gracefully (static content, cached catalog) rather than falling over from the surge.

## Nuances & Gotchas

- **Shedding too late is shedding never**: if you wait for CPU to hit 100%, the rejection logic itself competes for the same saturated resources — shed *early*, at the front door, using cheap checks (queue length is O(1), not a full health check).
- **Retry storms defeat shedding**: clients retrying rejected/degraded requests can turn a 10% shed into 30%+ effective load — always pair shedding with client-side exponential backoff + jitter and `Retry-After` headers.
- **Cache stampede on fallback**: if everyone falls back to "recompute and cache" simultaneously when the primary cache/dependency dies, the fallback path itself becomes the new bottleneck — use request coalescing/singleflight.
- **Silent staleness**: serving cached data indefinitely without a max-staleness bound turns "graceful" into "silently wrong" — e.g., stale pricing shown after a price change is a business risk, not just a UX one.
- **Priority inversion**: if "critical" tier isn't cleanly separable from "best-effort" at the queue level (same thread pool, same connection pool), a flood of low-priority requests can still starve high-priority ones — needs actual resource isolation (bulkhead), not just a priority label.
- **Fallback logic itself can fail**: a "simple" cached fallback path is still code that can throw, deadlock, or depend on something else unhealthy — test it as rigorously as the primary path (chaos engineering, GameDays).
- **Metrics blind spot**: shed/degraded requests often don't show up as "errors" in dashboards if you only track 5xx — track shed-rate and degraded-response-rate as first-class SLIs, or you'll be blind to how often users are getting the reduced experience.
- **Watermark flapping**: a threshold right at the boundary causes rapid on/off shedding (oscillation) — use hysteresis (different enter/exit thresholds) same as circuit breakers.
- **Load shedding vs rate limiting confusion in incident response**: seeing 429s doesn't tell you if it's quota-based (client problem) or health-based (systemic problem) unless you tag/label the rejection reason — always emit a distinct reason code.
