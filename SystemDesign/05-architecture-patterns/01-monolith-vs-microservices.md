# Monolith vs Microservices

> **TL;DR:** The real axis isn't "how many services" — it's deployment unit, failure isolation, and team topology. Microservices trade in-process function calls for network calls and buy independent deploys at the cost of massive operational tax; most orgs pay that tax before they need to.

## Quick Reference

| Dimension | Monolith | Microservices | Modular Monolith |
|---|---|---|---|
| Deployment unit | 1 artifact, all-or-nothing | N artifacts, independent | 1 artifact, internally modular |
| Failure isolation | None (1 crash = all down) | Per-service (with bulkheads) | None, but crash blast radius smaller if well-designed |
| Inter-module calls | Function call (~ns) | Network call (~ms, can fail) | Function call, enforced via interfaces |
| Team topology | 1 team or many teams, 1 codebase | 1 team per service (Conway) | 1+ teams, module ownership boundaries |
| Data | 1 shared DB, ACID txns | DB-per-service, sagas/eventual consistency | 1 DB, schema-per-module |
| Scaling | Scale whole app | Scale hot service only | Scale whole app |
| Observability | Logs + stack traces suffice | Distributed tracing required (Jaeger, OTel) | Logs suffice mostly |
| Deploy risk | 1 bad commit blocks everyone | Isolated, but version skew across services | 1 bad commit blocks everyone |
| Infra cost | Low (1 runtime) | High (N runtimes, service mesh, CI/CD per svc) | Low |
| Right team size | <20 engineers, unclear boundaries | 50+ engineers, stable boundaries, dedicated platform team | 5-50 engineers, want optionality |

## What It Is

- **Monolith**: single deployable artifact (one process or one container image) containing all business logic, typically one shared database.
- **Microservices**: application decomposed into independently deployable services, each owning its own data store, communicating over the network (HTTP/gRPC/messaging).
- **Modular monolith**: single deployable artifact, but internally partitioned into modules with enforced boundaries (separate packages/schemas, no cross-module DB access) — deployment topology of a monolith, code topology closer to microservices.

## Responsibilities

What actually changes when you split a monolith into services — this is the part people skip:

- **Deployment unit**: monolith ships as one thing; a bug in checkout blocks a fix to search. Microservices decouple release cadence per team — search team ships 10x/day independent of checkout team.
- **Failure isolation (blast radius)**: monolith — an OOM in the recommendation module can crash the whole process, taking checkout down with it. Microservices — recommendation service crash-loops, checkout stays up (if you built timeouts/circuit breakers; if not, it cascades anyway).
- **Team topology (Conway's Law)**: system architecture mirrors org communication structure, whether you plan it or not. If you have 8 teams, you'll get roughly 8 major service boundaries whether you draw them intentionally or not — microservices make this explicit and ownership-enforced (one team, one service, one on-call).
- **Scaling granularity**: monolith scales as one unit — need more CPU for the image-processing endpoint, you scale 50 replicas of the entire app including the parts that didn't need it. Microservices scale the image-processing service to 50 replicas and leave auth at 3.

## How It Works

**Monolith call path**: `Controller → Service → Repository → DB` — all in-process, function calls, shared transaction, single stack trace on error.

**Microservices call path**:
```
Client → API Gateway → Order Svc --gRPC--> Inventory Svc --gRPC--> Payment Svc
                              |--async--> Kafka --> Notification Svc
```
Each arrow is a network hop: serialization, TLS handshake (or reused connection), DNS/service-discovery lookup, timeout risk, partial failure risk. A call that was a nanosecond function call becomes a call with p99 latency, retry logic, and its own failure mode.

**Distributed transactions**: monolith gets ACID for free via one DB transaction (`BEGIN; debit account; credit account; COMMIT;`). Microservices with DB-per-service can't do a cross-service ACID transaction — use **Saga pattern** (orchestrated or choreographed) with compensating actions, or accept eventual consistency. This is the single biggest hidden cost of splitting a monolith around a domain with strong consistency needs (e.g., financial ledgers).

## Types / Classifications

- **Layered monolith**: classic MVC, layers (controller/service/DAO) but no enforced module boundaries — the default "big ball of mud" outcome.
- **Modular monolith**: enforced internal boundaries (Java modules, Go internal packages, NestJS modules), each module owns its schema/tables, communicates via in-process interfaces not shared tables.
- **Microservices, fine-grained**: services scoped to a single responsibility (e.g., "pricing service") — high network chatter, high ops overhead, max independent scalability.
- **Microservices, domain-scoped ("macroservices")**: services scoped to a bounded context (e.g., "order management" covering order + line items + fulfillment status) — fewer network hops, easier consistency, still independently deployable.
- **Service-oriented architecture (SOA)**: precursor to microservices, typically with a shared ESB (enterprise service bus, e.g., MuleSoft) for integration — heavier middleware, more centralized governance.

## Where It Fits

```
Startup / <10 eng, unclear domain  ─────────────► Monolith
Growing / 10-50 eng, boundaries firming up ─────► Modular Monolith
Scale-up / 50+ eng, multiple teams, stable
  domain boundaries, independent scaling needs ─► Microservices
```
- Monolith sits in the request path as one unit behind a load balancer (NGINX/ALB) — trivial to reason about.
- Microservices sit behind an **API gateway** (Kong, AWS API Gateway) for north-south traffic and a **service mesh** (Istio, Linkerd) for east-west traffic (mTLS, retries, circuit breaking between services).
- Modular monolith sits exactly where a monolith does — the module boundaries are a code-organization and DB-schema concern, invisible to infra.

## Common Patterns & Real-World Tools

- **Strangler fig**: incrementally carve services out of a monolith behind a routing layer (NGINX/gateway) until the monolith is "strangled" — how Shopify, Amazon historically migrated.
- **Database-per-service** + **Saga** (Netflix Conductor, Temporal, AWS Step Functions) for cross-service workflows without distributed 2PC.
- **API Gateway** (Kong, Amazon API Gateway) for auth, rate limiting, routing at the edge.
- **Service mesh** (Istio, Linkerd) for mTLS, retries, circuit breaking, traffic shifting between services — the "microservices tax" made manageable.
- **Distributed tracing** (Jaeger, Zipkin, OpenTelemetry) — mandatory once a request crosses 3+ services, otherwise debugging is guesswork.
- **Event-driven decoupling** (Kafka, RabbitMQ) to avoid synchronous service chains and reduce cascading failure.
- **Modular monolith frameworks**: Moduliths/Spring Modulith (Java), NestJS modules, Rails engines — enforce boundaries without paying network cost.
- **Shopify** (majority modular monolith, Ruby on Rails, "modular monolith at scale" — deliberately resisted full microservices), **Amazon** (canonical microservices at extreme scale), **Netflix** (microservices pioneer, hundreds of services + Hystrix for resilience), **Segment** (famously wrote a widely-cited postmortem on going microservices→monolith and back).

## Pros & Cons / Trade-offs

**Monolith**
- \+ Simple local dev (clone, run, debug with a single debugger attach), ACID transactions free, no network latency between modules, cheap infra.
- − Deploy coupling (1 team's bug blocks all releases), full blast radius on crash, must scale the entire app to scale one hot path, large codebases slow builds/tests over time, tech-stack lock-in for the whole org.

**Microservices**
- \+ Independent deploys/releases per team, fault isolation (if bulkheads/circuit breakers built correctly), scale only what's hot, teams can pick different stacks per service, smaller codebases per service.
- − Network calls replace function calls (latency + partial failure everywhere), distributed transactions require sagas/eventual consistency, operational complexity multiplies (N CI/CD pipelines, N on-calls, N databases to back up), **observability tax** — you need tracing/correlation IDs/service maps just to answer "why is checkout slow" (impossible with logs alone once 5+ services are in a request path), version-skew and contract-breakage risk between services, higher cloud spend (idle capacity per service, service mesh sidecars).

**Modular monolith**
- \+ Most microservices' organizational benefit (clear ownership, enforced boundaries) without network cost; DB stays ACID; trivially split into real services later because boundaries are already explicit.
- − Doesn't give independent deploy cadence or independent scaling; requires discipline (nothing stops a lazy engineer from reaching across module boundaries without tooling enforcement, e.g., ArchUnit/Spring Modulith tests).

## Real-World Scenarios

- **E-commerce checkout**: payment needs ACID-like guarantees — either keep it in the monolith/single service with a real DB transaction, or use a Saga with compensating "refund" actions if split (Stripe-style idempotency keys become mandatory once split).
- **Segment (2018)**: split into ~100s of microservices, hit exactly the predicted tax — debugging cross-service data pipeline issues became untenable, consolidated back into a few services ("majestic monolith" — actually a modular monolith). Widely cited cautionary tale.
- **Netflix**: hundreds of microservices justified by scale (200M+ users, thousands of engineers) — built Hystrix (circuit breaker library) specifically because network calls between services fail constantly at that scale; this is not a starting-point architecture.
- **Startup MVP**: team of 4, unclear domain model — monolith wins outright; premature microservices here is the #1 cited cause of early-stage engineering velocity death.
- **Reporting/analytics service split off a monolith**: good microservice candidate — different scaling profile (batch, read-heavy), different failure tolerance (can lag, doesn't need to be up 24/7), low coupling to core transactional flow.

## Nuances & Gotchas

- **Conway's Law bites both ways**: if your org has 3 teams but you build 30 microservices, ownership is ambiguous and on-call fatigue skyrockets — service count should roughly track team count, not domain-entity count.
- **The network is not reliable**: a function call never times out; a gRPC call does. Every synchronous inter-service call needs a timeout + retry + circuit breaker (Hystrix/resilience4j/Envoy) or one slow downstream service cascades into a full outage (the classic "one service's latency becomes everyone's latency" failure).
- **Distributed transactions are a trap**: teams that split a monolith around a domain requiring strong consistency (ledgers, inventory counts) end up rebuilding ACID badly with sagas, or silently accepting data drift. Check consistency requirements *before* choosing service boundaries, not after.
- **Shared database anti-pattern**: splitting the deployment but keeping one shared DB gives you all the network latency of microservices with none of the isolation — worst of both worlds, extremely common failure mode in "fake microservices" migrations.
- **Observability is not optional past ~3 services in a call chain**: without distributed tracing (trace ID propagated via headers, W3C traceparent), a single slow request becomes an unsolvable mystery — budget for OTel/Jaeger from day one of any split.
- **Version skew**: Service A v2 calling Service B v1's old contract silently breaks in production if you don't enforce contract testing (Pact) or backward-compatible schema evolution (protobuf field rules, avoid removing/renumbering fields).
- **The "distributed monolith" trap**: services that are deployed independently but can't actually be deployed independently because of tight coupling (shared libraries with breaking changes, synchronous call chains requiring lock-step releases) — you pay full microservices tax for zero microservices benefit.
- **Modular monolith boundary erosion**: without automated enforcement (ArchUnit, Spring Modulith verification tests, custom lint rules), module boundaries decay within ~6-12 months as deadline pressure causes engineers to reach across the boundary "just this once."
- **Rewrite risk**: full "big bang" monolith-to-microservices rewrites have a bad track record (see: multiple public postmortems) — strangler fig (incremental extraction with a routing facade) has a much higher success rate than stop-the-world rewrites.
- **Reversibility asymmetry**: going monolith → microservices is far more expensive than modular-monolith → microservices, because the modular monolith already forces you to define the module boundaries and data ownership that microservices require — treat the modular monolith as the default "optionality-preserving" choice absent a proven need for independent scaling or deploy cadence.
