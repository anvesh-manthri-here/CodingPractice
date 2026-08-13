# Rate Limiting and Throttling

> **TL;DR:** Rate limiting caps request rate per key (user/IP/tenant) to protect capacity and enforce fairness/billing tiers; the algorithm choice trades burst tolerance, memory, and accuracy, while distributed enforcement trades latency/SPOF risk (centralized) against precision (local).

## Quick Reference

| Aspect | Key Fact |
|---|---|
| Core algorithms | Fixed window, Sliding window log, Sliding window counter, Token bucket, Leaky bucket |
| Best all-rounder | Sliding window counter (good accuracy, O(1) memory) |
| Best for bursts | Token bucket (allows controlled burst up to bucket size) |
| Best for smoothing | Leaky bucket (constant output rate, queues/drops excess) |
| Distributed store | Redis + Lua script for atomic check-and-increment |
| Standard response | HTTP 429 Too Many Requests + `Retry-After` header |
| Common headers | `X-RateLimit-Limit`, `-Remaining`, `-Reset` |
| Key dimensions | API key > authenticated user > tenant > IP (last resort) |
| Common tools | NGINX `limit_req`, Envoy RLS, Redis+Lua, Kong, Cloudflare, AWS WAF |

## What It Is

- **Rate limiting**: hard cap on requests/events per key per time unit (e.g., 100 req/min per API key) — protects backend and enforces fair use/billing tiers.
- **Throttling**: broader term — includes delaying, queuing, or degrading requests rather than only rejecting; rate limiting is often the mechanism throttling uses.
- Sits at the edge (gateway/LB) or in-service, distinct from capacity-based controls like load shedding and concurrency limits.

## Responsibilities

- Protect shared resources (DB, downstream APIs, compute) from overload by any single caller.
- Enforce contractual/billing tiers (free vs paid quotas).
- Prevent abuse: scraping, credential stuffing, DoS from a single client.
- Provide predictable, fair degradation — signal clients to back off instead of silently failing.
- Preserve capacity for other tenants when one misbehaves (noisy-neighbor isolation).

## How It Works

Generic flow: identify key -> look up/update counter or bucket state -> allow or reject -> emit headers.

```
client -> [gateway: extract key] -> [rate limiter store] -> allow? -> upstream
                                          |-> reject -> 429 + Retry-After
```

- **State** lives in-memory (single node), local + async sync (eventually consistent), or centralized (Redis, strongly consistent per key).
- **Atomicity** matters: increment-then-check must be a single atomic op (Lua script in Redis, or `INCR` + `EXPIRE` with care) to avoid race conditions under concurrent requests.
- **Decision** returns allow/deny plus metadata (remaining quota, reset time) so clients can self-throttle.

## Types / Classifications

### The Five Algorithms

| Algorithm | Mechanism | Burst Tolerance | Memory Cost | Accuracy |
|---|---|---|---|---|
| Fixed window | Counter reset every T seconds | Poor — 2x burst at boundary | O(1) per key | Low |
| Sliding window log | Store timestamp of every request, count in trailing window | Precise, none extra | O(N) — N = requests in window | Perfect |
| Sliding window counter | Weighted average of current + previous fixed window | Good, smoothed | O(1) per key | High (approx) |
| Token bucket | Tokens refill at fixed rate; request consumes token; bucket has max capacity | Controlled burst up to bucket size | O(1) per key | High |
| Leaky bucket | Requests queue, drain at constant rate; overflow dropped | None — smooths to constant rate | O(1) + queue size | High |

### Fixed Window Boundary Burst Problem

- Limit: 100 req/min, window resets at :00.
- Client sends 100 requests at 11:59:59, then 100 more at 12:00:01.
- Both windows individually under limit, but 200 requests land in a 2-second span — 2x the intended rate slips through.
- Sliding window counter fixes this by weighting the previous window's count proportionally to overlap: `count = curr_window_count + prev_window_count * (overlap_fraction)`.

## Where It Fits

- **Edge/gateway layer**: API gateway, CDN, WAF — first line, cheap to reject before hitting app servers.
- **Service mesh/sidecar**: Envoy rate limit service — per-route, per-upstream policies.
- **Application layer**: fine-grained, business-aware limits (e.g., per-feature quotas) using Redis.
- **Client SDKs**: proactive client-side throttling to avoid ever hitting server limits (token bucket in SDK).

## Common Patterns & Real-World Tools

- **NGINX `limit_req`**: leaky-bucket-style, per-IP, config-driven (`limit_req_zone`, `burst=N nodelay`).
- **Envoy Rate Limit Service (RLS)**: gRPC service, descriptors-based, centralized decision, used heavily at Lyft/Google-style meshes.
- **Redis + Lua**: `EVAL` script does read-modify-write atomically (e.g., `INCR` + `PEXPIRE` or full token-bucket logic) — avoids race conditions across app instances.
- **Kong / Apigee / AWS API Gateway**: managed plugin/policy-based rate limiting per API key/plan.
- **Cloudflare**: edge-level, IP + behavioral (bot score) based, absorbs volumetric attacks before origin.
- **AWS WAF rate-based rules**: counts requests per IP over 5-min window, auto-blocks over threshold.

### Distributed Enforcement Strategies

| Strategy | Mechanism | Trade-off |
|---|---|---|
| Centralized Redis + Lua | All nodes check shared counter atomically | Accurate, but adds network hop + SPOF/latency risk |
| Local buckets, no sync | Each node enforces limit/N independently | Fast, no SPOF, but effective limit = N x per-node limit under uneven load |
| Local buckets + periodic sync | Nodes gossip/reconcile counts every few seconds | Balances accuracy and latency; eventually consistent |
| Sticky routing | LB hashes key to same node consistently | Local enforcement becomes accurate for that key; breaks on rebalance/node failure |

## Pros & Cons / Trade-offs

- **Fixed window**: + trivial to implement, O(1) memory; − boundary burst (2x), unfair to bursty-but-compliant clients.
- **Sliding log**: + perfectly accurate; − memory scales with request volume, expensive at high RPS.
- **Sliding counter**: + near-accurate, O(1); − approximation assumes uniform distribution within prior window.
- **Token bucket**: + allows legitimate bursts, smooth long-term rate; − slightly more state (tokens + timestamp), burst can still spike downstream briefly.
- **Leaky bucket**: + perfectly smooth output, protects downstream from any burst; − adds latency/queuing, can drop/delay legitimate bursts users expect (e.g., page load doing 10 parallel calls).
- **Centralized store**: + globally accurate across fleet; − extra network hop per request, new failure point.
- **Local-only**: + zero extra latency, no SPOF; − inaccurate under fleet-wide skew, effective limit multiplies by node count.

## Real-World Scenarios

- **Public API platform (e.g., Stripe/GitHub-style)**: token bucket per API key, headers expose remaining quota; burst allowed for legitimate batch clients, sustained abuse throttled.
- **Login endpoint brute-force protection**: sliding window per username + per-IP combined, tight limit (5/min), because IP alone is bypassed by botnets and username alone is bypassed by IP rotation.
- **Multi-tenant SaaS**: per-tenant token bucket sized by pricing tier; without this, one tenant's traffic spike (e.g., a batch job) starves smaller tenants sharing the same backend pool.
- **CDN edge under DDoS**: Cloudflare/AWS WAF absorb volumetric floods with coarse IP/ASN-based rate-based rules before traffic reaches origin, where finer per-user limits take over.

## Nuances & Gotchas

- **IP alone is broken**: NAT/CGNAT (mobile carriers, corporate networks) puts thousands of real users behind one IP — IP-only limiting either blocks legitimate users collectively or is trivially evaded via IP rotation/VPNs. Prefer API key or authenticated user ID; fall back to IP only for unauthenticated/anonymous traffic, combined with device fingerprint if possible.
- **Retry storms**: clients that ignore `Retry-After` and hammer immediately on 429 amplify load exactly when the system is already stressed — mitigate with exponential backoff + jitter enforced client-side, and consider temporary harder blocks (soft ban) for repeat offenders.
- **Per-node limits multiply by fleet size**: setting "100 req/min" as a local in-memory limit on each of 20 app servers yields an effective 2000 req/min if traffic isn't sticky — always divide by expected fleet size or centralize state.
- **Redis as a new SPOF**: putting the rate limiter in the hot path means Redis latency/outage now affects every request; mitigate with fail-open (allow on Redis error, log it) vs fail-closed (reject) decided explicitly per system criticality, plus Redis Cluster/replicas for HA.
- **Clock skew in sliding windows**: distributed nodes with drifted clocks compute inconsistent window boundaries — use NTP-synced time, or let Redis's server-side `TIME` command be the single source of truth inside the Lua script rather than trusting client/app-server clocks.
- **Wrong dimension starves others**: a single global limit (not per-tenant/per-user) lets one heavy caller consume the entire budget, denial-of-service-ing everyone else — always scope limits to the dimension that maps to a billing/fairness unit, and consider hierarchical limits (global AND per-tenant AND per-endpoint).
- **Rate limiting vs load shedding vs quotas vs concurrency limits** — easy to conflate:
  - *Rate limiting*: caps events/time, resets over time (429).
  - *Load shedding*: rejects work based on current system health/queue depth, independent of caller identity (503) — protects the server, not fairness.
  - *Quotas*: caps total usage over a long period (e.g., 1M calls/month), often billing-driven, not about instantaneous rate.
  - *Concurrency limits*: caps simultaneous in-flight requests per key, not requests-per-second — better for long-running/streaming calls where RPS is meaningless.
- **Burst param tuning**: NGINX `limit_req burst=N nodelay` — omitting `nodelay` queues bursty requests (adds latency) instead of rejecting; know which behavior you want.
- **Header consistency**: return `X-RateLimit-*` even on success (not just 429) so well-behaved clients can self-throttle proactively before ever getting rejected.

## Self-Check

1. A login endpoint limits by IP alone at 5/min. Why does this fail for both a corporate office and an attacker, and what's the fix?
2. You deploy a "100 req/min" limit as an in-memory counter on each of 20 app servers, no sync. What is the effective fleet-wide limit under uneven load, and why?
3. Limit is 100 req/min, fixed window resetting at :00. A client sends 100 requests at 11:59:59 and 100 more at 12:00:01. How many requests land in that 2-second span, and why do the per-window counters not catch it?
4. You put Redis in the hot path for every rate-limit check. What new failure mode does this introduce, and what are the two explicit design choices for handling a Redis outage?
5. A service rejects requests with 503 when its queue depth exceeds a threshold, regardless of caller identity. Is this rate limiting? Name the actual mechanism and how it differs from a quota and from a concurrency limit.

<details><summary>Answers</summary>

1. IP alone is broken both ways: CGNAT/corporate NAT puts thousands of legitimate users behind one IP (collective block), while an attacker evades it via IP rotation/VPNs. Fix: key on username + IP combined (or API key/auth'd user ID), falling back to IP only for anonymous traffic.
2. Effective limit is up to 2000 req/min (100 x 20), not 100, because each node enforces its own local counter independently — without sticky routing or centralized state, traffic skew lets the sum across nodes far exceed the intended cap.
3. All 200 land within the 2-second span, 2x the intended rate. Each fixed window (11:59:00-11:59:59 and 12:00:00-12:00:59) individually stays under the 100 limit, so neither counter trips — the algorithm only checks within-window totals, not the trailing rolling window across the boundary.
4. Redis becomes a new SPOF/latency risk on every request's hot path. The two explicit choices: fail-open (allow requests through on Redis error, logging it) vs fail-closed (reject on error) — decided per system criticality, plus Redis Cluster/replicas for HA.
5. No — this is load shedding, not rate limiting: it rejects based on current system health/queue depth (503), independent of caller identity, protecting the server rather than enforcing per-caller fairness. A quota caps total usage over a long period (e.g., 1M calls/month); a concurrency limit caps simultaneous in-flight requests per key rather than requests-per-second.
</details>

---
**Related:** [API Gateway](03-api-gateway.md) · [Load Balancers](01-load-balancers.md) · [Message Queues](07-message-queues.md)

*Last reviewed: 2026-08*
