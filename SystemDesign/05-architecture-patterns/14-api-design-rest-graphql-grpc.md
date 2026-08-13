# API Design — REST, GraphQL, gRPC

> **TL;DR:** REST is resource-oriented and HTTP-cache-friendly but suffers over/under-fetching; GraphQL lets clients shape the query but shifts cost to the server (N+1, complexity attacks, cache-busting); gRPC is a typed binary RPC protocol for internal service-to-service calls. Pick per audience, not per hype.

## Quick Reference

| Dimension | REST | GraphQL | gRPC |
|---|---|---|---|
| Data model | Resources + HTTP verbs | Single schema graph, client-picked fields | Typed RPC methods (proto services) |
| Transport | HTTP/1.1 or 2, JSON | HTTP POST (usually), JSON | HTTP/2, Protobuf binary |
| Fetch shape | Fixed per endpoint | Client-defined query | Fixed per RPC (can use field masks) |
| Caching | Native (HTTP GET, ETags, CDN) | Hard (single POST endpoint) | N/A (point-to-point, use app cache) |
| Browser support | Native | Native (fetch/POST) | Needs grpc-web/proxy |
| Best audience | Public/partner APIs | Frontend/mobile aggregation | Internal microservices |
| Tooling maturity | Universal | Apollo, Relay, GraphiQL | protoc, grpc-gateway, buf |
| Versioning | URL/header versioning | Schema evolution (deprecate fields) | Proto field numbers, backward-compat rules |

## What It Is

- **REST**: architectural style — resources identified by URIs, manipulated via HTTP verbs (GET/POST/PUT/PATCH/DELETE), stateless, uses HTTP status codes as protocol semantics.
- **GraphQL**: query language + runtime (Facebook, 2015) where the server exposes one schema (types + resolvers) and clients send queries specifying exactly which fields/nested relations they want.
- **gRPC**: Google's RPC framework — client calls a remote method as if local, using Protobuf-defined service contracts over HTTP/2. See serialization-formats.md (Protobuf details) and network-protocols.md (HTTP/2 multiplexing) for the substrate — not repeated here.

## Responsibilities

- Define the **contract** between client and server (types, operations, errors).
- Control **fetch granularity** — how much data crosses the wire per request.
- Provide **discoverability/tooling** (OpenAPI/Swagger for REST, introspection for GraphQL, .proto files for gRPC).
- Enforce **versioning/evolution** rules so client and server can deploy independently.

## How It Works

**REST over/under-fetching:**
- Over-fetching: `GET /users/42` returns 40 fields when the mobile screen needs 3 → wasted bandwidth, especially on cellular.
- Under-fetching: rendering a user's profile + their last 5 orders needs `GET /users/42` then `GET /users/42/orders` — N round trips, classic "N+1 over the network" for nested UI.
- Mitigations: sparse fieldsets (`?fields=id,name`), embedding (`?include=orders`), BFF (Backend-for-Frontend) layer per client.

**GraphQL query-shape model:**
- Client sends one POST with a query tree; server resolves each field via a **resolver function**, walking the graph.
- Solves over/under-fetching: one round trip, exact fields requested (`{ user(id:42){ name orders(first:5){ total } } }`).
- **N+1 resolver problem**: naive resolver for `orders` on each of 100 users issues 100 separate DB queries. Fix with **DataLoader** (batches + caches requests within a single tick) — same pattern as ORM lazy-loading N+1.
- **Query complexity/cost limiting**: a deeply nested or wide query can force the server to do exponential work (denial-of-service via a single valid query). Mitigate with:
  - static query cost analysis (assign cost per field/depth, reject if over budget — e.g., GitHub's GraphQL API uses a points system, 5000 pts/hour).
  - max query depth limits (e.g., depth ≤ 10).
  - persisted queries (client sends a hash, not raw query text — server only allows pre-registered queries in production).
  - timeouts per resolver, pagination enforcement (no unbounded `first`).
- **Caching difficulty**: REST GETs are cacheable by URL at CDN/browser/reverse-proxy layer for free (ETag, Cache-Control). GraphQL is a single `POST /graphql` endpoint — no URL variance, no native HTTP caching. Workarounds: persisted queries turned into GET+hash (cacheable), Apollo normalized client-side cache (object-id based), CDN caching of specific persisted-query GETs (e.g., Fastly + Apollo).

**gRPC internal RPC (pointer, not repeated):**
- Strongly typed contracts via `.proto`, code-gen for client/server stubs in many languages.
- 4 call types: unary, server-streaming, client-streaming, bidi-streaming (enabled by HTTP/2 multiplexed streams — see network-protocols.md).
- Binary Protobuf payload — smaller/faster than JSON but not human-readable (see serialization-formats.md for wire format, schema evolution rules).
- Not browser-native; needs grpc-web + Envoy proxy translation for browser clients.

## Types / Classifications

| Style | Sub-variant | Notes |
|---|---|---|
| REST | Richardson Maturity Model L0–L3 | L3 = HATEOAS (rare in practice) |
| REST | JSON:API, OData | Standardized conventions on top of REST |
| GraphQL | Query / Mutation / Subscription | Subscriptions = WebSocket-based push |
| gRPC | Unary / Streaming (4 modes) | See above |
| Hybrid | BFF (Backend-for-Frontend) | REST/GraphQL facade tailored per client, backed by gRPC internally |
| Hybrid | gRPC-Gateway | Auto-generates REST/JSON facade over gRPC services |

## Where It Fits

```
 Mobile/Web Client
        |
   [BFF / API Gateway]  <-- REST or GraphQL (client-facing)
        |
   ---------------------------
   |          |              |
 Service A  Service B     Service C   <-- gRPC (internal, typed, low-latency)
   |
 Postgres/Redis/Kafka
```
- Public/partner-facing edge: REST (simplicity, caching, curl-ability) or GraphQL (rich client needs).
- Internal service mesh: gRPC (low latency, strong typing, streaming, codegen across polyglot services).
- Many orgs run **all three**: gRPC internally, GraphQL as a BFF aggregation layer, REST for simple public webhooks/integrations.

## Common Patterns & Real-World Tools

- **Netflix**: GraphQL-like GraphQL Federation (via Apollo Federation) at the edge, gRPC/Falcor internally for service calls.
- **GitHub**: GraphQL v4 API (public) alongside REST v3 (still maintained) — cost-point rate limiting on GraphQL.
- **Google**: gRPC internally across virtually all services; public APIs mostly REST/JSON with gRPC option (Cloud APIs support both).
- **Shopify**: GraphQL Admin API with explicit query cost scoring, replacing REST for third-party apps.
- **Envoy/Istio**: sidecar proxies that speak gRPC/HTTP2 natively, do L7 routing, retries, circuit breaking for gRPC mesh traffic.
- **Apollo Server + DataLoader**: canonical GraphQL N+1 fix.
- **grpc-gateway / Connect (buf.build)**: generate REST/JSON facades from proto definitions so one contract serves both worlds.

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| REST | Simple, cacheable, universal tooling, stateless, easy debugging (curl) | Over/under-fetching, endpoint sprawl for complex UIs, versioning via URL is clunky |
| GraphQL | Exact data shape, single round trip, strong typed schema + introspection, great for aggregating multiple backends | N+1 resolver risk, hard to cache, complexity/DoS risk, resolver perf can hide N calls behind 1 request, harder rate limiting |
| gRPC | Fast (binary, HTTP/2 multiplexing), strict contracts, streaming support, great codegen | Not browser-native, binary payload not human-debuggable, harder to expose publicly, proto versioning discipline required |

## Real-World Scenarios

- **Mobile app on flaky 3G**: GraphQL or BFF-REST to minimize round trips and payload size — raw REST with many endpoints is too chatty.
- **Public partner integration (webhooks, simple CRUD)**: REST — partners expect curl-able, cacheable, well-understood semantics; GraphQL learning curve is a liability for external devs.
- **Microservice mesh doing 50k RPS internal calls**: gRPC — typed contracts prevent drift, HTTP/2 multiplexing cuts connection overhead, streaming supports real-time data sync.
- **Dashboard aggregating data from 6 microservices**: GraphQL BFF layer with resolvers fanning out to gRPC backends — client gets one query, server handles fan-out + DataLoader batching.
- **CDN-cached product catalog for a storefront**: REST GET endpoints — leverage HTTP caching (Varnish/CloudFront) directly; GraphQL's single POST endpoint would bypass CDN caching entirely.

## Nuances & Gotchas

- **GraphQL "one endpoint" breaks standard ops tooling**: WAFs, rate limiters, and CDNs that key off URL path see only `/graphql` — you lose per-operation visibility unless you parse the query body or use persisted-query IDs as the cache/rate-limit key.
- **N+1 doesn't disappear, it moves**: GraphQL turns client-side chattiness (many REST calls) into server-side chattiness (many DB/resolver calls) — without DataLoader batching you've just relocated the latency problem, often making it worse (server fan-out inside one request timeout budget).
- **Query complexity attacks are real production incidents**: a single nested query requesting `friends.friends.friends.posts.comments` can fan out to millions of DB rows — always ship depth limits + cost analysis before opening a GraphQL API publicly, not after.
- **GraphQL errors are HTTP 200**: partial failures return `"errors": [...]` alongside partial `"data"` with status 200 — naive REST-style error handling (checking status code) silently misses failures; clients must inspect the errors array.
- **Persisted queries are the real caching answer**: production GraphQL at scale (GitHub, Shopify) doesn't cache raw ad-hoc queries — it forces clients to register queries ahead of time and calls them by hash, turning GraphQL calls into cacheable, rate-limitable, denyable operations.
- **gRPC proto field number reuse is a silent corruption bug**: removing a field and reassigning its number to a new field causes old binary data to be misinterpreted — always reserve retired field numbers (`reserved 4;`).
- **gRPC deadlines don't propagate automatically across languages/frameworks** unless explicitly wired — a client deadline of 500ms can be ignored deep in a call chain, causing resource leaks under load; always propagate context/deadline explicitly.
- **REST "REST-ish" APIs aren't actually RESTful**: most production "REST APIs" are levels 1–2 (resources + verbs, no HATEOAS) — that's fine and expected; don't over-invest in hypermedia unless you have autonomous client discovery needs.
- **Mixing paradigms at the edge doubles the contract surface**: running both REST and GraphQL publicly means maintaining two auth models, two rate limiters, two docs sets — only justify this if audiences genuinely differ (e.g., webhook consumers vs. app frontend).
- **gRPC-Web needs a proxy (Envoy/Connect) for browsers** — you can't call raw gRPC from JS; forgetting this leads to "works from Postman/native client, fails from web" surprises late in a project.
