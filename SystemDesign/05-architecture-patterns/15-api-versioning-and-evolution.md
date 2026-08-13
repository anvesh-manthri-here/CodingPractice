# API Versioning and Evolution

> **TL;DR:** Prefer additive, backward-compatible changes so you never need a version bump; when you must break compatibility, version explicitly (URI path is the pragmatic default), publish a deprecation timeline with `Sunset`/`Deprecation` headers, and cap concurrent major versions at 2 — each one is a standing operational tax.

## Quick Reference

| Concern | Recommendation |
|---|---|
| Default strategy | URI path (`/v1/orders`) for public APIs; header-based for internal/service-mesh APIs |
| Never break | Removing a field, renaming a field, changing a field's type/semantics, changing enum meaning |
| Always safe | Adding optional fields, adding new endpoints, adding new enum values (if client tolerates unknowns) |
| Deprecation notice | `Deprecation: true` + `Sunset: <date>` + `Link: <docs>; rel="deprecation"` headers, min 6-12 months |
| Max concurrent majors | 2 (current + previous); 3rd triggers forced migration |
| Internal RPC versioning | Protobuf/Avro field numbers + reserved fields, no URI versioning needed |
| Version bump trigger | Breaking change to request/response contract, not every feature release |

## What It Is
- The discipline of evolving an API's contract over time without breaking existing consumers, while giving you a controlled path to make breaking changes when unavoidable.
- Two halves: **compatibility discipline** (write changes that never need a version bump) and **versioning mechanics** (how to signal and route when a bump is unavoidable).
- Applies to REST, gRPC, GraphQL, event schemas (Kafka/Avro) — same principles, different transport.

## Responsibilities
- Preserve existing client behavior across deploys (zero-downtime, no coordinated client/server rollout required for non-breaking changes).
- Provide a clear signal (version identifier) when behavior *does* change incompatibly.
- Give consumers advance notice and a migration window before removing old behavior — deprecation is a process, not an event.
- Bound the number of contract variants the server must simultaneously support (cost control).

## How It Works

### Additive-change discipline (avoid the bump entirely)
- **Add, don't remove**: new fields are optional with sane defaults; old clients ignore unknown fields (JSON/protobuf both tolerate this natively).
- **Never repurpose a field**: don't change `status: string` semantics from `"active"/"inactive"` to also mean `"pending"` without consumers opting in — add a new field instead.
- **Never change a field's type**: `price: int` (cents) → `price: string` breaks every strict-typed client. Add `price_v2` or a new endpoint instead.
- **Enums**: adding a new value can break clients with exhaustive `switch` statements (Java, Rust, TS strict unions) — document "expect unknown values" as a contract requirement, or treat new enum values as a breaking change requiring opt-in.
- **Same discipline as wire-format compatibility (protobuf/Avro field numbers, reserved tags)** — API-contract evolution is this same rule enforced at the HTTP/GraphQL layer instead of the binary layer.
- Use JSON Schema / OpenAPI diffing tools (`oasdiff`, `openapi-diff`) in CI to catch accidental breaking changes before merge.

### Versioning mechanics (when a bump is unavoidable)

| Strategy | Example | Pros | Cons |
|---|---|---|---|
| URI path | `GET /v2/orders/123` | Explicit, cacheable per-version, easy routing/load-balancer rules, debuggable from logs/curl | "Not RESTful" purists complain; URI churn; resource identity conflated with version |
| Header-based | `Accept: application/vnd.api+json;version=2` or custom `X-API-Version: 2` | Clean URIs, resource identity stable, good for content-negotiation-heavy APIs | Invisible in logs/browser, harder to test manually, proxies/CDNs may strip headers |
| Query param | `GET /orders/123?version=2` | Easy to default/omit, simple to add retroactively | Easily forgotten by clients, pollutes caching keys, looks like a filter not a contract |
| Media type versioning | `Accept: application/vnd.github.v3+json` | Ties version to representation, supports fine-grained per-resource versioning | Complex, steep learning curve (GitHub API does this) |

- **Routing**: URI-path versions route trivially at the load balancer/ingress (NGINX `location /v2/`, API Gateway path mapping) to different backend fleets — enables true parallel major-version deployments.
- **Header versions** require app-layer routing (can't cheaply split at L7 LB without header inspection rules — doable in Envoy/Kong but adds config complexity).

## Types / Classifications
- **Major (breaking)**: incompatible contract change — requires version bump and client opt-in.
- **Minor (additive)**: new optional fields/endpoints — no bump needed, same version serves both.
- **Patch**: bug fixes, no contract change at all.
- **Semantic versioning for APIs**: many teams version only the major (`/v1`, `/v2`) and handle minor/patch via normal deploys — full semver (`/v1.2.3`) in the URL is rare and usually overkill.

## Where It Fits
```
Client --Accept/URI version--> API Gateway (Kong/Envoy/AWS API GW)
                                   |
                     routes by version to:
                     v1 fleet ---- v2 fleet
                        |              |
                   legacy DB view   new schema
```
- API Gateway or ingress is the natural place to enforce version routing, strip deprecated-version traffic metrics, and inject `Sunset` headers centrally rather than per-service.
- Internal service-to-service (gRPC) typically skips URI versioning entirely — protobuf's field-number compatibility handles 95% of evolution; a new `rpc` method or new proto package (`orders.v2`) covers true breaks.
- Event-driven systems (Kafka) version the **schema** (Avro/Protobuf + Schema Registry with BACKWARD/FORWARD compatibility modes) rather than a topic name, except for genuinely incompatible redesigns (`orders-v2` topic).

## Common Patterns & Real-World Tools
- **Stripe**: date-based versioning (`Stripe-Version: 2024-06-20`), account pinned to a version at signup, changelog documents every dated change — avoids `/v1` `/v2` proliferation entirely.
- **GitHub API**: media-type versioning via `Accept` header, one version live at a time historically, now mostly additive.
- **AWS APIs**: mostly additive-only within a service version; breaking changes ship as a new service or explicit API version in SDK.
- **Kong / Apigee / AWS API Gateway**: gateway-level version routing, request/response transformation to bridge v1 clients to v2 backend (strangler pattern at the edge).
- **Schema Registry (Confluent)**: enforces BACKWARD/FORWARD/FULL compatibility checks on Avro/Protobuf schemas at publish time — rejects breaking producer changes automatically.
- **GraphQL**: famously version-less by convention — deprecate fields with `@deprecated(reason: "...")`, never remove until usage hits zero (tracked via field usage analytics, e.g., Apollo Studio).

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Additive-only, no versioning | Zero client migration cost, simplest ops | Contract can only grow, eventually accumulates cruft (dead fields you can never remove) |
| URI versioning | Simple infra, obvious to consumers | N versions = N backend code paths/deploys to maintain |
| Date-based versioning (Stripe) | Fine-grained, no forced batch migrations | Requires per-request version-transform logic server-side |
| Aggressive deprecation (support 1 version) | Low maintenance cost, forces modern clients | High client churn risk, breaks slow-moving integrators (enterprise/mobile with app-store review lag) |
| Generous deprecation (support 3+ versions) | Low client friction | Multiplies test matrix, security patch burden, on-call cognitive load |

## Real-World Scenarios
- **Mobile app clients**: can't force-upgrade (app store review + user adoption lag of weeks-months) — must support old API version for 6-12+ months minimum after new release; this alone often dictates "2 major versions" as the floor.
- **B2B/partner APIs**: enterprise clients integrate once and rarely touch it again — Stripe/Twilio-style long-tail support (years) with per-account version pinning is standard.
- **Internal microservices**: aim for zero long-lived major versions — enforce additive-only via contract testing (Pact) and protobuf field-number linting in CI; a service running 3 API versions internally usually signals process failure, not a feature.
- **Event schema migration in Kafka**: adding a required field breaks all downstream consumers simultaneously at deploy time — must be optional-with-default first, consumers upgraded, *then* made required (expand-contract pattern), never a single atomic breaking deploy.

## Nuances & Gotchas
- **"Non-breaking" JSON changes that actually break clients**: reordering fields (some naive parsers positional), changing null to omitted-key or vice versa, changing number formatting (`1.0` vs `1`), changing string date format (ISO-8601 vs epoch) — test with real client SDKs, not just schema validators.
- **Sunset header is advisory, not enforcement** — clients silently ignore it; pair with active monitoring (log `X-API-Version` per request, alert when deprecated-version traffic doesn't trend to zero) and eventually hard-cutoff with a clear error response (`410 Gone` + migration link), not silent failure.
- **Version proliferation is a hidden cost multiplier**: each live major version needs its own test suite, security patches, on-call runbook knowledge, and often a full duplicate backend code path — teams that promise "we support all versions forever" eventually can't ship features safely.
- **The "invisible field" trap**: adding a field is safe until a strict client-side schema validator (OpenAPI `additionalProperties: false`, strict protobuf/JSON Schema on the client) rejects unknown fields — always default to permissive schemas on the *consumer* side, document this requirement explicitly for partners.
- **Query-param and header versioning break HTTP caching**: CDNs/reverse proxies key cache by URL by default; a query-param version pollutes cache keys (fine), but a header-based version with no `Vary: X-API-Version` causes v1 responses to be served to v2 clients from cache — a classic production incident.
- **GraphQL's "no versioning" claim leaks in practice**: deprecated-but-still-used fields never get removed because no one tracks real usage — without field-level analytics (Apollo Studio, GraphQL Inspector) deprecation becomes permanent debt, not a transition.
- **Expand-contract for internal breaking changes**: (1) add new field/behavior alongside old, (2) migrate all consumers, (3) verify old path has zero traffic, (4) remove old path — skipping step 3 verification is the most common cause of "surprise" outages when the "unused" old field turns out to have one straggler consumer.
- **Version pinning without expiry is a support trap**: Stripe-style date pinning is powerful but requires you to actually track and contact accounts stuck on ancient versions — an account pinned to a 5-year-old version with no forcing function becomes permanent legacy code you can never delete.
