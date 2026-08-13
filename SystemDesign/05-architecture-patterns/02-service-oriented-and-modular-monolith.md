# Service-Oriented Architecture and the Modular Monolith

> **TL;DR:** SOA tried to solve integration-at-scale with a centralized ESB and heavyweight contracts, and collapsed under its own governance weight; the modular monolith is the pragmatic middle path — enforce module boundaries and internal API discipline inside one deploy unit, deferring the operational tax of microservices until team size or scaling needs actually force it.

## Quick Reference

| Aspect | Classic SOA (ESB) | Modular Monolith | Microservices |
|---|---|---|---|
| Integration style | Centralized bus (ESB) | In-process function/interface calls | Network calls (REST/gRPC/events) |
| Contract format | WSDL/SOAP, XML, canonical schemas | Language-level interfaces | OpenAPI/proto, versioned |
| Deploy unit | Many services + 1 ESB | 1 binary/process | Many independent services |
| Transaction model | Distributed (2PC, WS-AT) | Local ACID transactions | Sagas, eventual consistency |
| Team scaling | Central integration team = bottleneck | Single repo, module owners via CODEOWNERS | Independent team-per-service |
| Failure mode | ESB outage = global outage | Bug in one module can crash whole process | Partial failure, network is unreliable |
| Tooling example | IBM WebSphere ESB, MuleSoft, TIBCO | Modulith (Spring), NestJS modules, Ruby packwerk | Kubernetes, Istio, Kafka |
| Typical scale trigger | N/A (was default enterprise pattern ~2000s) | Fine to 10-30 devs / low-mid QPS | 50+ devs, independent scaling needs |

## What It Is

- **SOA**: architectural style where business capabilities are exposed as coarse-grained, network-addressable "services," typically integrated through a middleware bus (Enterprise Service Bus) that handles routing, transformation, orchestration, and protocol mediation.
- **Modular Monolith**: a single deployable application internally decomposed into modules with explicit, enforced boundaries (compile-time or lint-enforced), communicating via in-process interfaces instead of the network, sharing one database (often with schema-per-module).
- Both are reactions to the same problem — a tangled "big ball of mud" — but modular monolith rejects SOA's answer (distribute + middleware) in favor of "isolate logically, deploy together."

## Responsibilities

- **ESB (in SOA)**: message routing, protocol translation (SOAP↔JMS↔FTP), orchestration/choreography, data transformation (XSLT), centralized security/auditing.
- **Module boundary (in modular monolith)**: owns its own data access, exposes a narrow public interface/facade, hides internal types, enforces "no reaching into another module's tables/classes directly."
- **Build/lint tooling**: enforces boundaries that developers would otherwise erode under deadline pressure — this is the actual load-bearing mechanism, not documentation.

## How It Works

**SOA/ESB flow:**
```
Client -> ESB (route, transform, orchestrate) -> Service A (SOAP/XML)
                                               -> Service B (SOAP/XML)
```
Every cross-service call pays ESB hop latency + XML (de)serialization + canonical data model mapping.

**Modular monolith flow:**
```
[ Process ]
  Orders module  --(interface call, no network)-->  Inventory module
       |                                                  |
  orders_schema                                    inventory_schema
       \_______________ same Postgres instance ___________/
```
- Modules talk via Java interfaces / TS module exports / Python package APIs — compiler or linter fails the build on illegal imports (e.g., ArchUnit, Nx module boundaries, Ruby's Packwerk `TODO.yml` enforcement).
- Each module owns its own tables (or schema) even though it's one DB instance — no cross-module SQL joins, only calls through the module's public API. This is what makes later extraction possible.
- Transactions stay local ACID; cross-module consistency is handled with in-process patterns (e.g., synchronous calls within one DB transaction, or in-process event publishing that's still transactional via outbox-in-same-DB).

## Types / Classifications

- **SOA variants**: ESB-centric (heavyweight, IBM/TIBCO era), API-led SOA (lighter, REST-based, still governance-heavy), Web Services (SOAP/WSDL) vs later RESTful SOA.
- **Modular monolith variants**:
  - *Package-by-feature* (module = vertical slice: API + logic + data) vs package-by-layer (module = horizontal, weaker boundary).
  - *Shared DB, separate schemas* (most common) vs fully separate DBs per module (rare, closer to microservices already).
  - *Compile-enforced* (Java modules/JPMS, Rust crates) vs *convention/lint-enforced* (ESLint boundaries, Packwerk).

## Where It Fits

- SOA fit large enterprises circa 2000s integrating heterogeneous legacy systems (mainframes, vendor packages) where the ESB's protocol mediation had real value — it wasn't purely a mistake, it was a mismatch when applied to greenfield in-house systems.
- Modular monolith fits early-to-mid stage products and teams up to roughly 10-30 engineers, or any system where deployment/ops overhead of microservices isn't yet justified by team-scaling or independent-scaling needs.
- It sits between "big ball of mud" and microservices on the maturity path — Shopify, GitHub (historically), and Basecamp are commonly cited real-world examples of scaling far on a modular monolith before selectively extracting services.

## Common Patterns & Real-World Tools

- **ESB products**: IBM WebSphere ESB/App Connect, MuleSoft Anypoint, TIBCO BusinessWorks, Oracle SOA Suite, Apache ServiceMix.
- **Modular monolith enforcement tools**: Spring Modulith (JVM, verifies module boundaries + generates docs), ArchUnit (architecture unit tests), Ruby Packwerk (Shopify's tool, tracks/reduces boundary violations), Nx (JS/TS monorepo module boundaries), Java Platform Module System.
- **Strangler Fig pattern**: extract one module at a time into a real service once its interface is already clean — the standard migration path out of a well-built modular monolith.
- **Outbox pattern inside the monolith**: write domain event + state change in one local transaction, publish asynchronously — same technique reused later when the module becomes a real service, so adopting it early reduces extraction cost.
- **Facade/Anti-corruption layer per module**: the public interface a module exposes becomes, almost unchanged, the future service's API contract.

## Pros & Cons / Trade-offs

| | SOA (ESB) | Modular Monolith |
|---|---|---|
| Pros | Handles legacy protocol diversity; centralized governance/security | Simple ops (1 deploy, 1 log stream); local ACID transactions; fast refactors across module lines; cheap debugging (single stack trace) |
| Cons | ESB = single point of failure & bottleneck; heavyweight XML/WSDL contracts slow iteration; central team becomes change approval chokepoint; hard to test in isolation | Shared fate on deploy (one bug can take down everything); scaling is all-or-nothing (can't scale one hot module independently); boundary discipline erodes without tooling/CI enforcement; single DB can become a bottleneck |

## Real-World Scenarios

- **Startup at 8 engineers**: modular monolith with `orders`, `payments`, `catalog` modules in one Rails/Django/Spring app, one Postgres — ships fast, avoids premature distributed-systems tax.
- **Shopify's approach**: enforced modular monolith at massive scale using Packwerk, extracting only specific high-load components (e.g., checkout) into separate services when scaling demanded it.
- **Legacy enterprise circa 2008**: SOA with an ESB integrating a mainframe, a CRM, and a homegrown Java app — the ESB's mediation genuinely justified because the systems couldn't otherwise speak to each other.
- **Migration**: a `payments` module with a clean interface and its own schema gets extracted into a `payments-service` behind gRPC in a weekend; a tangled module with cross-schema joins takes months and needs a strangler-fig phase with dual writes.

## Nuances & Gotchas

- **The ESB became the new monolith, just distributed**: business logic crept into ESB orchestration flows (XSLT, BPEL) because it was the path of least resistance — you end up with a "smart pipe," which is the exact anti-pattern microservices later corrected for ("dumb pipes, smart endpoints").
- **Module boundaries rot without automated enforcement**: code review alone does not hold under deadline pressure — teams that skip ArchUnit/Packwerk-style CI gates end up with a monolith indistinguishable from a big ball of mud within 12-18 months.
- **Shared database is the real coupling risk, not the shared process**: even with clean module interfaces in code, if two modules' tables are joined directly in SQL or share a table, extraction is blocked — schema-per-module inside the single DB instance is the non-negotiable prerequisite for cheap extraction later.
- **"Modular" is necessary but not sufficient**: a module must also own its data and have no synchronous circular dependencies on other modules; circular module dependencies are what make extraction to independently-deployable services impossible without a rewrite.
- **Distributed transactions don't disappear, they just haven't arrived yet**: teams that build a modular monolith relying on multi-module local ACID transactions for consistency get blindsided when they extract a module and suddenly need sagas/compensating transactions — designing module boundaries around business capabilities (not just code organization) avoids this.
- **Scaling ceiling is real**: one hot module (e.g., search) forces scaling the entire process/DB even though only 5% of load needs it — this is the concrete trigger for extraction, not "microservices are trendy."
- **SOA's WS-* stack (WS-Security, WS-AtomicTransaction, WS-ReliableMessaging) added enormous per-call overhead** — a big reason lighter REST/JSON later displaced SOAP even before microservices as an org pattern took hold.
- **Extraction cost is proportional to interface cleanliness, not module size**: a small module with a messy, chatty internal API (many fine-grained calls) is harder to extract than a large module with one coarse-grained facade method — design for coarse-grained calls across module boundaries from day one, anticipating a future network hop.
