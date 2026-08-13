# API Gateway

> **TL;DR:** A single entry point that centralizes cross-cutting edge concerns (auth, rate limiting, routing, protocol translation) so backend services don't each reimplement them — powerful, but easy to turn into a distributed monolith if business logic creeps in.

## Quick Reference

| Aspect | Key Facts |
|---|---|
| Core job | Route + protect + observe traffic between clients and services |
| Layer | L7 (HTTP/gRPC/WebSocket aware), sits at the edge or between internal services |
| Not a | Load balancer (L4/L7 traffic distribution only), service mesh (east-west sidecar), BFF (client-specific façade) |
| Managed tools | AWS API Gateway, Apigee (Google), Azure API Management, Kong Konnect |
| Self-hosted tools | Kong, Envoy (+Ambassador/Contour), Traefik, Netflix Zuul (legacy) |
| Typical added latency | 1-10ms per hop (more with heavy transformation/aggregation) |
| Auth patterns | JWT validation, OAuth2 token introspection, API keys, mTLS |
| Rate limit granularity | Per API key, per user, per IP, per route, global |
| Failure mode risk | Single point of failure — must run N+1 replicas behind LB, no local state |

## What It Is

- A reverse proxy purpose-built for APIs: terminates client connections, applies policy, forwards to backend services.
- Decouples **what clients see** (stable public contract) from **what backends expose** (internal services, versions, protocols).
- Two flavors by placement: **edge gateway** (north-south, internet-facing) and **internal/API gateway** (service-to-service, often paired with a mesh).

## Responsibilities

- **AuthN/AuthZ**: validate JWT/OAuth tokens, API keys, mTLS certs; enforce scopes/roles before request reaches backend.
- **Rate limiting & quota**: token bucket / sliding window per client, tiered plans (free/pro), burst vs sustained limits.
- **Routing**: path/host/header-based routing to correct service version or region.
- **Protocol translation**: REST↔gRPC, WebSocket upgrades, GraphQL federation, SOAP↔REST for legacy.
- **Request/response transformation**: header injection, payload reshaping, field filtering, legacy contract adaptation.
- **API key management**: issuance, rotation, revocation, per-key metering for billing.
- **Caching**: response caching at edge (short TTL) to cut backend load for read-heavy idempotent endpoints.
- **Observability**: centralized access logs, request tracing (trace-id injection), metrics (latency, error rate, RPS) per route.

## How It Works

```
Client → [TLS term] → [AuthN] → [Rate limit] → [Route match]
       → [Transform] → [Backend call, protocol translate]
       → [Transform resp] → [Cache write] → Client
```

- Plugin/filter chain architecture: Kong (Lua plugins), Envoy (HTTP filters written in C++/WASM), Apigee (policy XML) — each request flows through an ordered pipeline.
- Config is typically declarative (YAML/JSON) and pushed via control plane (e.g., Envoy's xDS API) rather than hardcoded.
- Circuit breaking and retries live here too — but must mirror upstream service's own timeout budget or they fight each other.

## Types / Classifications

| Type | Scope | Example Use |
|---|---|---|
| Edge/Public gateway | Internet → your system | Mobile/web clients hitting public API |
| Internal gateway | Service → service | Cross-team API contracts inside org |
| BFF (Backend-for-Frontend) | Client-type specific | Separate gateway per mobile/web/partner |
| Aggregating gateway | Fan-out + compose | One call → multiple downstream calls merged |
| Managed (SaaS) | Vendor-hosted | AWS API Gateway, Apigee, Azure APIM |
| Self-hosted | You run it | Kong, Envoy, Traefik on your infra/k8s |

## Where It Fits

| vs. | Difference |
|---|---|
| **Load Balancer** | LB distributes traffic across healthy instances (L4/L7, no app-awareness); gateway adds auth/transform/routing logic on top — gateways often sit behind a LB, not instead of one. |
| **Service Mesh** (Istio/Linkerd) | Mesh handles east-west (service-to-service) traffic via sidecars: mTLS, retries, service discovery internally. Gateway handles north-south (client-to-system) edge traffic. Many architectures use both — Envoy is the data plane for both. |
| **BFF** | BFF is client-specific (one per frontend type), owns UI-shaping logic and can hold light orchestration. Gateway is protocol/infra-focused and shared across all clients — BFF often sits *behind* the gateway. |

```
Internet → [Edge Gateway] → [BFF-web] → [Service Mesh] → microservices
                          → [BFF-mobile] ↗
```

## Common Patterns & Real-World Tools

| Tool | Notes |
|---|---|
| **Kong** | Nginx/OpenResty-based, plugin ecosystem, popular self-hosted choice, Kong Gateway + Konnect (managed control plane) |
| **Envoy + Ambassador/Contour** | CNCF, xDS dynamic config, basis for Istio's data plane, k8s-native ingress via CRDs |
| **AWS API Gateway** | REST/HTTP/WebSocket APIs, tight Lambda integration, usage plans + API keys built in |
| **Apigee** | Enterprise-grade, strong analytics/monetization, policy-based (XML), good for API productization |
| **Netflix Zuul** | JVM-based, Zuul 1 blocking/Zuul 2 async — largely superseded by Envoy/Spring Cloud Gateway |
| **Traefik** | Auto-discovery (Docker/k8s labels), popular for smaller/dynamic deployments |

- **Aggregation/composition** (gateway fans out to N services, merges response): reduces client round-trips, but controversial — it embeds orchestration/business logic in infra layer, creates hidden coupling, and makes the gateway a deploy dependency for feature work. Many teams push this to a BFF or dedicated aggregation service instead.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Single place to enforce security policy | Single point of failure / large blast radius if misconfigured |
| Backend services stay simple (no repeated auth code) | Extra network hop = latency tax |
| Client contract decoupled from internal topology | Config sprawl as routes grow (100s of routes = ops burden) |
| Centralized observability/analytics | Can become a "distributed monolith" if logic creeps in |
| Enables gradual migration (strangler fig routing) | Team coupling — gateway changes require cross-team coordination/deploys |

## Real-World Scenarios

- **Public SaaS API**: Apigee/AWS API Gateway enforces per-customer quota + API key billing, routes `/v1/*` to versioned Lambda/EKS backends.
- **Microservices migration (strangler fig)**: gateway routes old paths to monolith, new paths to extracted services — toggle via config, no client change.
- **Mobile + web with different needs**: edge gateway does authn/rate-limit; BFF layer behind it aggregates/shapes payloads per client type to cut mobile payload size.
- **gRPC internal, REST external**: gateway (Envoy) does REST↔gRPC transcoding so public clients use JSON/HTTP while internal services stay gRPC for perf.
- **Multi-region failover**: gateway does latency-based or health-based routing across regional backend clusters.

## Nuances & Gotchas

- **Distributed monolith trap**: once business logic (validation rules, orchestration, workflow) lands in gateway plugins, every feature change requires a gateway deploy — coordination cost of a monolith with none of its simplicity. Keep gateway = infra concerns only.
- **SPOF/blast radius**: a bad plugin or config push can take down *all* traffic. Mitigate: canary config rollout, N+1 redundant instances across AZs, circuit breakers, no single global config push without staged rollout.
- **Latency tax compounds**: each additional hop (gateway → BFF → mesh sidecar → service) adds ms; in p99-sensitive paths this adds up — measure end-to-end, not per-hop.
- **Config sprawl**: hundreds of routes/plugins in YAML becomes unreviewable; mitigate with GitOps, schema validation, per-team route ownership/namespacing.
- **Coupled deploys**: centralizing routing in one repo/config store means teams block on each other for gateway changes — solve with per-route ownership tooling or delegate to mesh/ingress-per-namespace.
- **Timeout/retry misalignment**: gateway retry policy (e.g., 3 retries × 2s timeout) can multiply load on an already-struggling upstream, or worse, retry non-idempotent calls — always align gateway timeout ≤ sum of upstream timeout + margin, and gate retries on idempotency.
- **Auth caching staleness**: caching JWT validation/introspection results for performance means revoked tokens/permissions remain valid until cache TTL expires — balance perf vs. security freshness (e.g., 30-60s TTL, push-based revocation for critical cases).
- **Aggregation is a trap disguised as a feature**: fan-out logic in the gateway means partial-failure handling (what if 1 of 3 backend calls fails?) becomes gateway code — usually better owned by a service/BFF that can be tested and deployed independently.
- **Version skew**: gateway plugin/config versions must stay compatible with backend API versions — treat gateway config changes with the same rigor (tests, staged rollout) as service deploys, not as "just config."

## Self-Check

1. Your team keeps adding validation rules and orchestration logic to the gateway's Lua plugins because it's "faster than a service deploy." Six months later, what problem have you created, and why is it worse than a monolith?
2. A gateway route has 3 retries at a 2s timeout, but the upstream service's own timeout is 5s. Under upstream slowness, what happens to load on that service, and what's the fix?
3. You cache JWT introspection results for 5 minutes to cut auth latency. A user's access is revoked at t=0. What's the exposure window, and what would you change for a critical permission downgrade?
4. The gateway aggregates 3 downstream calls into one response for a mobile client. One of the 3 calls fails. Who ends up owning that partial-failure handling logic, and why is that considered a trap?
5. Draw the request path for a mobile client hitting a public endpoint that's backed by internal microservices, placing the load balancer, API gateway, BFF, and service mesh in order — what does each layer own that the others don't?

<details><summary>Answers</summary>

1. You've built a distributed monolith: every feature change now requires a gateway deploy, so teams block on the gateway repo/team just like a monolith — but without the monolith's single-codebase simplicity, since logic is scattered across plugins owned by an infra team.
2. Retries multiply load on an already-struggling service (up to 3x), and since the gateway timeout (2s) is shorter than the upstream's own timeout (5s), it may retry calls that were still going to succeed, worsening the pile-up. Fix: align gateway timeout to upstream timeout + margin, and only retry idempotent calls.
3. The revoked user keeps valid access for up to the cache TTL (5 minutes) after revocation. For critical downgrades, use push-based revocation (invalidate the cache entry immediately) rather than relying on TTL expiry.
4. The gateway itself, in gateway plugin code — which is hard to test and deploy independently of the infra layer. It's a trap because partial-failure/orchestration logic is business logic that usually belongs in a BFF or dedicated aggregation service, not the edge infra layer.
5. Client → Load Balancer (distributes to healthy gateway instances, L4/L7, no app awareness) → API Gateway (authn, rate limit, edge routing, north-south) → BFF (client-specific payload shaping/orchestration) → Service Mesh sidecars (east-west mTLS, retries, service discovery between internal microservices) → microservices.
</details>

---
**Related:** [Reverse Proxy and Forward Proxy](02-reverse-proxy-and-forward-proxy.md) · [Rate Limiting and Throttling](09-rate-limiting-and-throttling.md) · [Load Balancers](01-load-balancers.md)

*Last reviewed: 2026-08*
