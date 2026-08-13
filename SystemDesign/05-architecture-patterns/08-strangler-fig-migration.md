# Strangler Fig Migration

> **TL;DR:** Incrementally replace a legacy system by routing traffic for individual capabilities to new implementations, capability by capability, until the old system handles nothing and can be deleted — never a big-bang rewrite.

## Quick Reference

| Aspect | Detail |
|---|---|
| Core mechanism | Routing layer (proxy/gateway) intercepts requests, forwards by path/feature/header to old or new system |
| Named after | Strangler fig vine — grows around a host tree, eventually replaces it entirely |
| Typical routing tools | NGINX, Envoy, Kong, AWS ALB/API Gateway, Spring Cloud Gateway, Istio (service mesh) |
| Data strategy | Dual writes, CDC (Debezium), or shared DB during transition; single source of truth at cutover |
| Phases | 1) Identify seams 2) Build facade/router 3) Migrate slice 4) Verify 5) Cut traffic 6) Retire old code |
| Success metric | % of traffic/endpoints routed to new system, trending to 100% |
| Biggest risk | Migration stalls at 60-80%, routing layer becomes permanent architecture |
| Typical duration | Months to years for large monoliths (not a sprint-sized effort) |
| Rollback mechanism | Feature flag / router config flip back to legacy — must stay cheap throughout |

## What It Is

- A migration pattern (coined by Martin Fowler, 2004) for replacing legacy systems without a risky full cutover.
- New system is built alongside the old one; a routing layer decides, per request/feature, which system serves it.
- Over time, more traffic shifts to the new system as capabilities are reimplemented and verified — the old system is "strangled" until it does nothing.
- Applies to monolith-to-microservices decomposition, framework migrations (e.g., Struts to Spring), legacy mainframe replacement, or database re-platforming.

## Responsibilities

- **Routing layer**: intercept all inbound traffic, decide old vs. new per request, handle fallback/rollback.
- **Anti-corruption layer (ACL)**: translate between old and new data models/APIs so neither side is corrupted by the other's assumptions.
- **Data synchronization**: keep old and new stores consistent during the overlap window (dual writes, CDC, event sourcing).
- **Observability**: track parity (response diffing, shadow traffic) between old and new implementations before full cutover.
- **Governance**: track migration progress explicitly (dashboard of % endpoints migrated) — this is a project management responsibility, not just technical.

## How It Works

```
Client → [Router / Facade] ──path A──> Legacy System (shrinking)
                            └─path B──> New System (growing)
                                            │
                                     shared/synced data
```

1. **Identify a seam** — a capability with a clean boundary (e.g., "checkout", "/api/users/*").
2. **Build the facade** — a reverse proxy/gateway in front of the legacy system that all traffic must pass through first.
3. **Implement the new slice** — build the replacement service for that one capability.
4. **Route incrementally** — start with shadow traffic (mirror requests, compare outputs, don't serve), then canary (1% → 100%) via router rules.
5. **Verify parity** — diff responses, monitor error rates/latency, use feature flags for instant rollback.
6. **Decommission** — once 100% routed and stable for a burn-in period, delete legacy code path and remove routing rule.
7. Repeat per capability until legacy system is empty, then retire it entirely (including its infra/licenses).

## Types / Classifications

| Strategy | Description | Best for |
|---|---|---|
| **URL/path-based routing** | Router splits by URL path (`/v2/orders` → new, `/orders` → old) | Web apps, REST APIs |
| **Feature-flag routing** | Router/app checks a flag (LaunchDarkly, Unleash) per user/tenant | Gradual rollout, A/B testing |
| **Event interception** | New system subscribes to legacy's event/message stream, takes over processing | Event-driven / async systems |
| **Database strangling** | Views, triggers, or CDC redirect reads/writes table-by-table to new schema | Data layer migrations |
| **Branch by abstraction** | Code-level interface swaps implementation via config, no separate infra router | In-process/library migrations, single codebase |
| **UI strangling** | Reverse proxy serves new frontend for specific pages/routes, legacy UI for the rest | Frontend modernization (e.g., micro-frontends) |

## Where It Fits

- Sits at the **edge/gateway tier** of the architecture — typically the same layer as API gateways or ingress controllers.
- Used during **modernization initiatives**: monolith decomposition, cloud migration, tech-stack upgrades, M&A system consolidation.
- Complements **domain-driven design**: seams for strangling usually align with bounded contexts.
- Works with **CDC pipelines** (Debezium, AWS DMS) to keep data layers in sync without dual-write bugs.
- Distinct from **blue-green deployment** (whole-system instant switch) and **big-bang rewrite** (all-at-once cutover) — strangler fig is granular and gradual, at the capability level, not the whole-deployment level.

## Common Patterns & Real-World Tools

- **NGINX/Envoy weighted routing**: percentage-based traffic split by upstream, adjusted via config reload or xDS API (Envoy).
- **AWS**: ALB path-based rules + API Gateway for REST, Route 53 weighted routing for DNS-level splits.
- **Service mesh (Istio/Linkerd)**: VirtualService/traffic-split resources for fine-grained, header/path-based routing without app changes.
- **Shadow traffic / dark launch**: mirror production requests to new system, compare outputs offline (e.g., GitHub's Scientist library, diffy).
- **Debezium + Kafka**: CDC from legacy DB feeds new system's data store in near real-time during dual-write window.
- **Feature flags**: LaunchDarkly, Unleash, homegrown flags — used for both routing decisions and safe rollback.
- **Case studies**: Amazon's monolith-to-microservices migration, Shopify's modular monolith extraction, Segment's "strangling" of a Ruby monolith into Go services.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Continuous validation — each slice is tested in production before the next | Requires running two systems + sync logic simultaneously (higher infra cost during transition) |
| Reduced blast radius — a bad slice affects one capability, not everything | Routing/facade layer adds latency and operational complexity |
| Revenue/business continuity — system stays live throughout | Slower than a rewrite in wall-clock time if scoped aggressively |
| Rollback is cheap (flip router rule) vs. rollback of a big-bang cutover | Data consistency across two stores is genuinely hard (dual writes, race conditions) |
| Team can reprioritize mid-migration (business seams shift) | Risk of migration stalling — org loses discipline/funding partway |
| Encourages proper domain boundary discovery (seams = bounded contexts) | Legacy system must be kept alive, patched, and staffed longer than expected |

## Real-World Scenarios

- **E-commerce checkout migration**: route `/checkout/*` to new payments microservice while `/catalog/*`, `/account/*` still hit the monolith; verify with shadow traffic comparing transaction totals before cutover.
- **Mainframe decommission**: legacy COBOL system fronted by an API facade; new Java/Kotlin services take over one batch job at a time, using CDC to mirror ledger data until the mainframe processes zero transactions.
- **API versioning as strangling**: `/v1/*` (old monolith) vs `/v2/*` (new service) coexist behind API Gateway; clients migrated via deprecation notices, `/v1` retired after usage hits zero.
- **Frontend modernization**: legacy jQuery app served for most routes, but `/dashboard` served by new React app via reverse proxy path rule — incremental page-by-page rewrite.
- **M&A system consolidation**: two companies' user systems merged by routing new-tenant traffic to the acquirer's system while legacy tenants stay on the acquired company's system until migrated in batches.

## Nuances & Gotchas

- **The router becomes the new monolith**: routing rules accumulate special cases (user cohorts, feature flags, regional overrides) and become a tangled, undocumented decision tree nobody wants to touch — treat router config as code, version it, test it.
- **Migration stalls at 70-80%**: the easy/high-value seams get migrated first; what's left is the gnarliest, highest-risk legacy code with the least business incentive — budget/headcount often gets cut right when the hardest work remains. Set explicit executive-sponsored deadlines per remaining slice, not just an open-ended backlog.
- **"Temporary" dual-write logic outlives the migration by years**: sync code (CDC pipelines, dual-write shims) is treated as throwaway but nobody schedules its removal — audit and delete dead sync paths as part of each slice's "done" criteria, not as a someday cleanup.
- **Data consistency during overlap is the #1 source of bugs**: dual writes can partially fail (write to new succeeds, old fails, or vice versa) — prefer CDC/event-driven sync (single writer, async propagation) over synchronous dual writes where possible; always design idempotent replays.
- **Silent legacy dependency**: other internal systems/cron jobs/reports may query the legacy DB directly, bypassing the router entirely — these keep the "dead" system alive indefinitely. Audit all consumers (not just user-facing traffic) before decommissioning; use DB access logs/proxies to detect stragglers.
- **Verification is skipped under deadline pressure**: teams cut over to 100% traffic without adequate shadow-testing or canary burn-in because "it looks done" — enforce a minimum canary period (e.g., 2 weeks at 100% shadow, then staged 1%→100%) as a hard gate, not a suggestion.
- **Facade layer performance regression**: an extra network hop (router → legacy or router → new) adds latency; at high QPS this compounds — measure p99 latency added by the facade itself, not just end-to-end.
- **Org/team incentive misalignment**: the team that built the legacy system has no incentive to help decommission it (job security, sunk cost) — assign explicit ownership and OKRs for legacy retirement, not just new-feature velocity.
- **False sense of safety from rollback**: rollback via router flip doesn't undo data written by the new system during the window it was live — plan for irreversible data migrations (e.g., forward-only schema changes) separately from routing rollback.
