# Layered, Hexagonal, and Clean Architecture

> **TL;DR:** Traditional N-tier layering lets business logic depend directly on infrastructure (DB, HTTP), causing tight coupling; Hexagonal and Clean Architecture invert that dependency so infrastructure depends on the domain instead — same core idea, different vocabulary/ceremony.

## Quick Reference

| Style | Core structure | Dependency direction | Key mechanism |
|---|---|---|---|
| N-Tier / Layered | Presentation → Business → Data Access | Top-down, business → data | Direct calls, often ORM entities leak everywhere |
| Hexagonal (Ports & Adapters) | Domain core + ports (interfaces) + adapters (impl) | Adapters → Domain (inward) | Dependency Inversion via interfaces defined by domain |
| Clean Architecture | Entities → Use Cases → Interface Adapters → Frameworks/Drivers | Outer → Inner only | Same DIP, formalized as concentric circles + "Dependency Rule" |
| Onion Architecture | Domain model → Domain services → App services → Infra | Outer → Inner | Near-identical to Clean/Hexagonal, earlier (Jeffrey Palermo, 2008) |

## What It Is

- **Layered (N-tier):** Code organized horizontally — Presentation (UI/controllers), Business Logic (services), Data Access (repositories/DAOs), each layer calling the one below.
- **Hexagonal:** Alistair Cockburn's "Ports and Adapters" (2005) — domain core exposes **ports** (interfaces) for what it needs (persistence, messaging) and what it offers (use cases); **adapters** plug into those ports from any "side" (DB, REST, CLI, tests).
- **Clean Architecture:** Robert C. Martin's (2012) synthesis of Hexagonal, Onion, and DCI into four concentric rings, unified by **The Dependency Rule**: source code dependencies point only inward, never outward.

## Responsibilities

- **Domain/Entities/Business layer:** Encodes business rules, invariants, and use cases — has zero knowledge of HTTP, SQL, or frameworks.
- **Ports (interfaces):** Contracts owned by the domain — e.g., `OrderRepository`, `PaymentGateway` — defined in domain terms, not infra terms.
- **Adapters/Infrastructure layer:** Implements ports against real tech — `PostgresOrderRepository implements OrderRepository`, `StripePaymentGateway implements PaymentGateway`.
- **Interface Adapters (Clean):** Controllers, presenters, gateways — translate between use cases and external formats (HTTP JSON, DB rows).
- **Frameworks & Drivers (Clean outermost ring):** Spring, Express, Postgres driver, message brokers — the "detail" layer, deliberately kept swappable.

## How It Works

```
   N-Tier (coupling problem):
   Controller -> Service -> Repository -> DB
   (Service imports Repository's concrete class; business logic knows about SQL/ORM)

   Hexagonal (inverted):
        [REST Adapter]        [DB Adapter]
              |                    ^
              v                    |
        [Port: UseCase]     [Port: Repository]  <- interfaces owned by domain
              \___________ Domain Core __________/
                    (entities, business rules)
```

- **Dependency Inversion Principle (DIP)** is the mechanism: instead of Business → Data, the domain defines an interface (`interface OrderRepository`), and the data layer implements it — arrow now points from infra into domain.
- Domain core has **zero import statements** referencing frameworks (no `javax.persistence`, no `express`, no `SqlConnection`).
- Wiring happens at the **composition root** (main/bootstrap) — a factory or DI container (Spring `@Configuration`, .NET `Startup.cs`, manual factory function) instantiates concrete adapters and injects them into the domain via constructor injection.
- Tests substitute a fake/in-memory adapter (`InMemoryOrderRepository`) implementing the same port — domain logic runs with zero DB.

## Types / Classifications

| Variant | Distinguishing trait |
|---|---|
| Transaction Script (simplest layered) | No domain model; procedural logic in service layer per operation |
| Anemic-domain N-tier | Entities are data bags (getters/setters); logic lives in "Service" classes — common anti-pattern |
| Hexagonal, symmetric ports | Driving ports (inbound, e.g., use-case API) vs driven ports (outbound, e.g., repository) — explicit split |
| Clean Architecture | 4 named rings + explicit DTOs crossing boundaries (no leaking ORM entities outward) |
| Onion Architecture | Domain model at the very center with no dependencies at all, even on domain services |
| Vertical Slice / Feature-based | Orthogonal to all above — organizes by feature not layer; often combined with CQRS instead |

## Where It Fits

- Sits inside a single service/bounded context (microservice or modular monolith) — orthogonal to distributed-systems concerns like service discovery or messaging.
- Pairs naturally with **DDD** (Domain-Driven Design): entities/aggregates/value objects live in the innermost ring; repositories are DDD ports.
- Often combined with **CQRS**: command/query handlers act as use cases, each depending on ports for read/write models.
- In a microservice, the *whole hexagon* is one service; adapters connect it to the outside world (Kafka consumer adapter, gRPC adapter, Postgres adapter) — the mesh/gateway layer (Envoy, API Gateway) sits entirely outside the hexagon.

## Common Patterns & Real-World Tools

- **Spring (Java):** `@Repository` interfaces in domain module, `@Component` JPA/JDBC implementations in infra module; Spring's DI container wires them — textbook hexagonal in enterprise Java.
- **.NET:** `IOrderRepository` interface in `Domain` project, `EfOrderRepository` in `Infrastructure` project, wired via `IServiceCollection` in `Program.cs`.
- **Go:** Idiomatic — small interfaces defined by the consuming package (domain), implemented by infra packages; no framework needed, just interface satisfaction.
- **NestJS:** Modules + `@Injectable()` providers + custom `provide`/`useClass` tokens emulate ports/adapters explicitly.
- **Testing:** In-memory/fake adapters (`FakeEventPublisher`, `InMemoryRepository`) replace Kafka/Postgres in unit tests — this is the single biggest practical payoff.
- **Contract testing:** Pact or similar validates that a real adapter (e.g., HTTP client to a partner API) actually satisfies the port's expected contract.

## Pros & Cons / Trade-offs

| | Layered (N-tier) | Hexagonal / Clean |
|---|---|---|
| Speed to build CRUD | Fast — minimal ceremony | Slower — interfaces, DTOs, mappers for even simple cases |
| Testability | Needs DB/mocks deep in stack; business logic often untestable in isolation | Domain tested with zero DB/network — pure unit tests |
| Swapping infra (e.g., Postgres → DynamoDB) | Touches business layer, high blast radius | Swap one adapter, domain untouched |
| Onboarding / readability | Familiar to most engineers, low learning curve | Requires understanding DIP, ports, composition roots |
| Boilerplate | Low | High — extra interfaces, mapping DTOs at every boundary |
| Risk of anemic domain | High (business logic leaks into controllers/services) | Lower — domain is protected/isolated by design |
| Fit for simple apps | Good | Often overkill — "hexagonal CRUD app" is a common overengineering smell |

## Real-World Scenarios

- **Payment processing service:** Domain defines `PaymentGateway` port; adapters for Stripe, PayPal, internal ledger swap without touching pricing/fraud-check logic — critical when adding a new PSP under deadline.
- **Migrating ORM (Hibernate → jOOQ) or DB (Postgres → CockroachDB):** With hexagonal, only the adapter package changes; with N-tier where services call `EntityManager` directly, the migration touches every service class.
- **Multi-channel input (REST + gRPC + Kafka consumer) into same use case:** Each is a separate driving adapter calling the same `PlaceOrderUseCase` port — avoids duplicating business rules per protocol.
- **Startup MVP under time pressure:** Deliberately choosing plain N-tier/Transaction Script to ship fast, planning a refactor to hexagonal once domain complexity and team size justify the ceremony.
- **Legacy monolith strangler migration:** Wrapping legacy DB access behind a repository port lets new use cases be built and tested against a fake while the real legacy adapter is incrementally replaced.

## Nuances & Gotchas

- **DTOs leaking through the boundary:** The #1 real-world violation — returning JPA/Hibernate entities directly from repositories lets ORM lazy-loading and DB constraints leak into domain/business logic, silently reintroducing coupling.
- **Fake "hexagonal" that isn't:** Defining the interface *next to* the implementation (`OrderRepository` + `PostgresOrderRepository` both in the infra package) instead of in the domain — the import still points the wrong way; check by asking "does domain import infra?"
- **Interfaces with only one implementation forever:** If a port never gets a second adapter and testing already uses the real thing (e.g., Testcontainers), the interface is pure ceremony — some teams deliberately skip ports for stable infra like the primary DB.
- **Anemic domain hiding inside "clean" structure:** Ceremony (rings, DTOs) doesn't guarantee rich domain modeling — logic can still pool in "use case" classes that are really just services in a trench coat.
- **Composition root complexity:** DI wiring can become its own maintenance burden (giant `Startup.cs`/config classes); mitigate with modular DI registration per bounded context.
- **Transaction boundaries crossing ports:** A use case spanning two repositories (e.g., debit + credit) needs explicit unit-of-work/transaction abstraction — naive port design breaks atomicity or leaks `DbContext`/session objects as a "port," defeating the abstraction.
- **Performance overhead is usually negligible** (interface dispatch, mapping) — the real cost is developer time/complexity, not runtime; don't cite perf as the reason to avoid it.
- **Overuse on simple CRUD services:** Wrapping a single-table admin tool in 4 Clean Architecture rings is a well-known anti-pattern — apply where domain logic is nontrivial and infra genuinely needs to be swappable/testable, not universally.
- **Mixing sync in-process adapters with async messaging:** An adapter calling `publish()` on an event port must clarify whether it's fire-and-forget or must succeed before the transaction commits (outbox pattern often needed) — the port abstraction can hide this critical detail.
