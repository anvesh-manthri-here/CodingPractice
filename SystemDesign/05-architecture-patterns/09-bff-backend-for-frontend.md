# Backend-for-Frontend (BFF)

> **TL;DR:** Give each client type (web, iOS, Android, partner API) its own thin backend that aggregates and shapes data from downstream services specifically for that client, instead of forcing all clients through one general-purpose API.

## Quick Reference

| Aspect | Detail |
|---|---|
| Pattern origin | Sam Newman / SoundCloud, ~2015, popularized with microservices |
| Cardinality | 1 BFF per client experience (web-BFF, ios-BFF, android-BFF, partner-BFF) |
| Typical owner | Frontend/mobile team, not the core backend team |
| Sits behind | API Gateway (gateway routes `/web/*`, `/mobile/*` to respective BFF) |
| Protocol to client | REST/JSON, GraphQL, or gRPC-Web — client-optimized |
| Protocol to services | gRPC/REST/Kafka to internal microservices |
| Deployment | Independently deployable per BFF, own release cadence |
| Anti-pattern risk | Duplicated logic across BFFs if shared code isn't factored out |

## What It Is

- A dedicated, thin server-side layer per front-end client that composes calls to multiple downstream microservices and returns a response tailored to that client's screen/UX.
- Not a data store — stateless orchestration/aggregation layer, usually no business logic of its own beyond shaping and composition.
- Contrast: a single "generic API" (or API gateway acting as the API) trying to serve web, mobile, and partners with the same payload shape.

## Responsibilities

- **Aggregation** — fan out to N services (user, orders, inventory), merge into one response, cutting client round-trips.
- **Shaping/projection** — return only fields the client needs (mobile home screen needs 5 fields, web dashboard needs 40).
- **Client-specific logic** — screen-driven pagination sizes, image URL variants (thumbnail vs. full-res), device-specific auth flows.
- **Protocol translation** — e.g., expose GraphQL to web SPA while calling gRPC services internally.
- **Resilience for that client** — timeouts, fallbacks, caching tuned to that client's latency budget (mobile networks tolerate less).
- Does **not** own core business logic, data ownership, or cross-client invariants — those stay in domain services.

## How It Works

```
        ┌────────────┐
Web  →  │            │→ web-BFF   → [User Svc] [Order Svc] [Catalog Svc]
Mobile→ │ API Gateway│→ mobile-BFF→ [User Svc] [Order Svc] [Catalog Svc]
Partner→│ (authN, TLS│→ partner-BFF→[Order Svc] [Catalog Svc]
        │  rate-limit)│
        └────────────┘
```

1. Client hits API Gateway (or edge/CDN) for TLS termination, authN, global rate limiting, routing.
2. Gateway routes to the client-specific BFF based on path/host/header (`api.example.com/mobile/v2/home`).
3. BFF makes parallel/sequential calls to backend microservices (often via gRPC or internal REST), applies GraphQL resolvers or hand-written aggregation code.
4. BFF shapes response: drops unused fields, renames, flattens nested structures, resizes images.
5. BFF applies client-tuned caching (e.g., Redis with short TTL for mobile home feed) and circuit breakers per downstream dependency.
6. Response returned to client — one round trip instead of 5.

## Types / Classifications

| Variant | Description | Example |
|---|---|---|
| Per-platform BFF | One per device/platform | web-BFF, ios-BFF, android-BFF |
| Per-team BFF | One per product team's frontend, regardless of device | checkout-BFF, search-BFF |
| GraphQL-as-BFF | Single GraphQL gateway lets each client query exactly the fields it needs, reducing need for N separate BFFs | Apollo Federation, Netflix DGS |
| Micro-BFF | BFF split per bounded context/page, composed via edge-side includes or micro-frontends | Spotify, Zalando |

## Where It Fits

- **Sits behind the API Gateway**, not instead of it. Gateway = cross-cutting infra concerns (TLS, authN, WAF, global rate limits, routing). BFF = client-specific business/UX shaping.
- Sits **in front of** domain microservices — never called directly by other services (avoid becoming a shared dependency).
- In a layered view: `Client → CDN/Edge → API Gateway → BFF → Service Mesh → Domain Microservices → DB`.
- Complements (does not replace) an API Composition or Aggregator pattern used server-to-server.

## Common Patterns & Real-World Tools

- **Netflix** — pioneered BFF at scale; each device team (TV, mobile, web) owns its own API adaptation layer on top of shared services.
- **SoundCloud** — original public write-up of the pattern (Sam Newman, 2015).
- **Spotify** — squads own BFFs for their vertical; avoids "God API" bottleneck.
- **GraphQL gateways** (Apollo Federation, Netflix DGS) — often used to implement BFF-like field selection without maintaining N REST BFFs.
- **Node.js/Express or Go** — common BFF implementation stack since it's I/O-bound orchestration, benefits from async concurrency.
- **Kong / AWS API Gateway / Envoy** — the gateway layer BFFs sit behind, handling routing to `web-bff-service` vs `mobile-bff-service`.
- **BFF + Micro-frontends** — each micro-frontend calls its own BFF slice, keeping vertical team ownership end-to-end (frontend to orchestration).

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| No over-fetching — mobile gets lean payloads, saves battery/data | Code duplication across BFFs (auth checks, error mapping) unless shared libs extracted |
| No client-conditional branching (`if (platform == mobile)`) in shared services — keeps domain services clean | More services to deploy, monitor, on-call for |
| Frontend team can iterate/deploy independently of backend team | Risk of BFF becoming a dumping ground for business logic ("smart BFF, dumb services" anti-pattern) |
| Fewer round trips (aggregation happens server-side, closer to services) | N+1 downstream call fan-out inside BFF can amplify latency if not parallelized |
| Failure isolation — mobile BFF outage doesn't take down web | Cross-BFF consistency harder (two BFFs each caching same data differently) |
| Enables per-client SLAs/caching/timeouts | Team boundaries can blur — who owns partner-BFF when partner team doesn't exist? |

## Real-World Scenarios

- **E-commerce mobile home screen**: generic `/products` API returns 40 fields including internal SKUs, tax metadata, supplier IDs. Mobile-BFF returns 6 fields (name, price, thumbnail, rating, id, stock flag) — cuts payload from ~15KB to ~2KB per item, critical on 3G/4G.
- **Partner integration API**: partner-BFF exposes stable versioned contract (rate-limited, API-key auth) decoupled from rapidly-changing internal web-BFF, so internal refactors don't break partner SLAs.
- **GraphQL migration**: company replaces 3 REST BFFs with one Apollo Federation gateway; each frontend team still owns its schema/resolvers (subgraph), preserving the ownership model while cutting infra duplication.
- **Checkout flow**: web-BFF aggregates cart + shipping + payment-methods in one call for a single checkout page; mobile-BFF splits it into 2 lighter calls to match a multi-step mobile wizard UI.

## Nuances & Gotchas

- **"Smart BFF" drift**: teams start putting business rules (discount calculation, inventory reservation logic) into the BFF because it's fast to ship — creates duplicated, diverging business logic across web/mobile/partner BFFs. Keep BFFs to orchestration + shaping only; business rules belong in domain services.
- **N+1 fan-out latency**: naive BFF code calling 5 services sequentially instead of `Promise.all`/goroutines turns a 50ms budget into 250ms. Always parallelize independent downstream calls; use timeouts + partial-response fallback (e.g., show product without reviews if reviews service times out).
- **Duplicated cross-cutting code**: authN token validation, error-to-HTTP-status mapping, retry/circuit-breaker config copy-pasted across BFFs and drift out of sync — extract into a shared internal SDK/library, not copy-paste.
- **Ownership ambiguity kills the benefit**: if the backend team ends up owning "the mobile BFF" instead of the mobile team, you've recreated the shared-API bottleneck with extra hops. The pattern's value is organizational (Conway's Law alignment), not just technical.
- **Chatty BFF-to-service calls amplify blast radius**: a single client request fanning out to 8 services means 8 potential failure points; without bulkheads/circuit breakers (e.g., Resilience4j, Envoy outlier detection) one slow dependency degrades the whole BFF.
- **Versioning sprawl**: web-BFF v3 and mobile-BFF v3 evolve independently and diverge from a shared domain model, making it hard to reason about "what does a user see" holistically — mitigate with a shared internal schema registry or contract tests (Pact) against domain services.
- **GraphQL-as-BFF isn't free**: solves over-fetching but shifts complexity to query cost analysis (a malicious/naive deep query can fan out to dozens of resolvers) — needs query depth/complexity limits (e.g., graphql-cost-analysis).
- **Too many BFFs = ops burden**: each new client (smart TV, voice assistant, wearable) tempts a new BFF; evaluate whether GraphQL field selection or a configurable response-shaping layer (e.g., server-driven UI) reduces the N-BFF explosion.
- **Caching inconsistency**: if web-BFF and mobile-BFF cache the same underlying entity independently with different TTLs, users on different platforms can see different prices/inventory simultaneously — sync cache invalidation via event bus (Kafka) rather than per-BFF TTLs alone.
