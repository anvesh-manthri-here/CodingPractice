# Multi-Tenancy Patterns

> **TL;DR:** Multi-tenancy is a spectrum from fully isolated (silo) to fully shared (pool) infrastructure per customer; the choice drives cost, noisy-neighbor risk, and blast radius, and most SaaS platforms end up on a hybrid/bridge model tiered by customer size or compliance needs.

## Quick Reference

| Model | Compute Isolation | Data Isolation | Cost Efficiency | Noisy Neighbor Risk | Blast Radius |
|---|---|---|---|---|---|
| Silo | Dedicated stack per tenant | Separate DB/instance | Low (idle capacity) | None | Single tenant |
| Pool | Shared stack, all tenants | Shared DB, `tenant_id` + RLS | High | High | All tenants |
| Bridge/Hybrid | Mixed (tiered by plan) | Mixed (schema or DB split for premium) | Medium-High | Medium | Segment of tenants |

| Data Isolation Approach | Isolation Strength | Ops Overhead | Typical Use |
|---|---|---|---|
| Separate DB per tenant | Strongest | High (N migrations, N backups) | Enterprise/regulated tenants |
| Separate schema, shared DB | Medium-strong | Medium (schema sprawl at scale) | Mid-market, moderate tenant count |
| Shared schema + `tenant_id` + RLS | Weakest by default, strong if enforced | Low (single migration path) | High-volume SMB SaaS |

## What It Is

- Architecture for serving many independent customers (tenants) from one software system while keeping their data, performance, and configuration logically or physically separated.
- A tenant = an organization/account with its own users, data, and SLAs — not an individual user.
- Core tension: shared infra lowers cost per tenant but couples tenants' fate (performance, security, availability) together.

## Responsibilities

- Guarantee **data isolation**: tenant A can never read/write tenant B's data, even under bugs or injection.
- Guarantee **performance isolation**: one tenant's traffic spike must not degrade others (the noisy-neighbor problem).
- Support **per-tenant configuration**: feature flags, quotas, branding, data residency, compliance tier.
- Enable **capacity planning and billing** attribution per tenant (usage metering, cost allocation).
- Provide **operational blast-radius control**: failures, bad deploys, or data corruption should be containable.

## How It Works

1. **Tenant context propagation**: every request carries a `tenant_id` (JWT claim, subdomain, API key) resolved at the edge/gateway and threaded through services, logs, and DB queries.
2. **Data layer enforcement**: DB driver or ORM middleware auto-injects `WHERE tenant_id = ?` on every query; Postgres Row-Level Security (RLS) policies enforce it even if app code forgets.
3. **Rate limiting**: token-bucket or sliding-window limiter keyed by `tenant_id` (not just IP/user) at the gateway (e.g., Envoy, Kong, API Gateway) so one tenant's burst is capped independently.
4. **Capacity planning**: track per-tenant p99 latency, QPS, and storage growth; use tiered quotas (free/pro/enterprise) to size shared pools and trigger tenant migration to silo when a tenant exceeds pool SLOs.
5. **Routing**: control-plane maps tenant → shard/pool/cell; large or regulated tenants get pinned to dedicated cells.

```
Request → Gateway (resolve tenant_id, rate-limit per tenant)
        → Service (stateless, tenant_id in context)
        → DB (RLS filters by tenant_id, or routes to tenant-specific DB/schema)
```

## Types / Classifications

- **Silo (single-tenant per stack)**: dedicated VPC/DB/compute per tenant. Common for enterprise/regulated (healthcare, finance) tenants requiring contractual isolation.
- **Pool (shared everything)**: one app fleet, one DB, tenant discriminated by `tenant_id` column/claim. Standard for SMB/PLG SaaS at scale (Slack workspaces within shared clusters, Salesforce's original pod model evolution).
- **Bridge/Hybrid**: mix — shared compute + siloed DB per tenant, or shared DB + siloed compute; often tiered: free/pro tenants pooled, enterprise tenants siloed or in dedicated "cells."
- **Cell-based / sharded pooling**: group N tenants per cell (shard), each cell independently scaled and deployed — bounds blast radius without full per-tenant silo cost (used by Slack, Salesforce "pods," Fly.io).
- **Bridge by data only**: shared compute, separate schema/DB per tenant (common middle ground before scale justifies full silo).

## Where It Fits

- Sits at the intersection of the data layer, API gateway, and deployment topology — not a single component but a cross-cutting concern.
- Gateway/edge layer: tenant resolution + rate limiting + routing.
- Data layer: isolation mechanism (DB/schema/row).
- Control plane: tenant metadata service (plan, region, quotas, feature flags) — often its own microservice backing tenant lookups.
- Observability: per-tenant dashboards/alerts (Datadog/Grafana tags by `tenant_id`) to detect noisy neighbors before they page on-call.

## Common Patterns & Real-World Tools

- **Postgres RLS**: `CREATE POLICY tenant_isolation ON orders USING (tenant_id = current_setting('app.tenant_id')::uuid);` — defense-in-depth even with app-level filtering.
- **Schema-per-tenant**: Postgres `search_path` switching, Citus for distributed multi-schema at scale.
- **DB-per-tenant automation**: Terraform/Crossplane to provision per-tenant RDS instances; common in enterprise B2B SaaS.
- **Cell-based architecture**: AWS's own guidance ("Cell-Based Architecture" whitepaper); Slack shards workspaces across "shards"/cells.
- **Rate limiting**: Kong/Envoy rate-limit service keyed by tenant plan tier; Stripe uses per-account rate limits on its API.
- **Kubernetes multi-tenancy**: namespace-per-tenant + `ResourceQuota`/`LimitRange` for pooled clusters; dedicated node pools for premium tenants.
- **Feature flag/config service**: LaunchDarkly-style per-tenant flags to gate rollout and isolate blast radius of bad deploys.

## Pros & Cons / Trade-offs

| | Silo | Pool | Hybrid |
|---|---|---|---|
| Cost per tenant | High | Low | Medium |
| Onboarding speed | Slow (provisioning) | Instant | Fast for pooled tier |
| Upgrade/patch effort | N deployments | 1 deployment | Mixed |
| Compliance (data residency, SOC2 isolation) | Easiest to prove | Hardest to prove | Achievable for regulated tenants only |
| Noisy neighbor | Eliminated | Primary risk | Contained to cell/tier |
| Custom per-tenant scaling | Trivial | Requires quotas/throttling | Available for silo'd tier |

## Real-World Scenarios

- **PLG SaaS with 100k free-tier orgs**: pooled shared-schema Postgres + RLS + per-tenant rate limits; silo reserved for enterprise contracts requiring dedicated infra clauses.
- **Healthcare SaaS (HIPAA)**: silo or DB-per-tenant mandated by BAAs; cost absorbed via higher enterprise pricing tiers.
- **Slack**: workspace (tenant) traffic sharded across cells; a cell outage affects a bounded workspace subset, not the whole platform.
- **Multi-region data residency (GDPR)**: hybrid — EU tenants routed to EU-region silo/pool, US tenants to US pool, via control-plane tenant-to-region mapping.
- **Sudden enterprise customer 100x traffic spike**: pooled tenant hits rate limiter, degrades gracefully (429s) instead of starving other tenants' DB connections — validates why per-tenant limiting matters.

## Nuances & Gotchas

- **Forgotten `WHERE tenant_id`**: the #1 real-world data breach vector in pooled multi-tenancy is a single missing filter in one query path; RLS as a DB-enforced backstop is non-negotiable at scale, not optional hardening.
- **Connection pool exhaustion**: one tenant's slow query or lock contention in shared Postgres can starve the connection pool for all tenants — mitigate with per-tenant statement timeouts and pgbouncer pool limits, not just app-level rate limiting.
- **"Just add an index" isn't isolation**: a `tenant_id` index prevents full scans but doesn't stop a tenant with 10M rows from causing autovacuum storms or WAL bloat that hurts everyone else on the same instance.
- **Noisy neighbor isn't just CPU**: it's shared DB connections, shared cache eviction (one tenant's cold cache thrashes Redis for all), shared message queue partitions, shared disk IOPS — rate limiting API calls alone misses these.
- **Migration lock-in**: moving a tenant from pool to silo after they've grown large is a live-data migration project (schema export, replication, cutover) — plan the "graduation path" before you need it, not during an incident.
- **Backup/restore blast radius**: shared-DB pooling means a bad restore or point-in-time recovery affects every tenant simultaneously; siloed tenants can be restored independently.
- **Tenant_id spoofing**: if tenant context comes from a client-supplied header instead of a signed JWT claim, it's an authorization bypass waiting to happen — always derive tenant identity from a trusted, signed source.
- **Metrics cardinality explosion**: tagging every metric by `tenant_id` at 10k+ tenants blows up Prometheus/Datadog cardinality costs — aggregate by tier/cohort and sample per-tenant detail only on demand.
- **Schema migrations at scale**: schema-per-tenant means a single `ALTER TABLE` becomes N sequential migrations — batch with tooling (e.g., Citus, custom migration runners) or you'll be running deploys for hours.
- **"Fair" rate limiting isn't equal limiting**: flat per-tenant caps punish legitimately large customers; use tiered/plan-based limits plus burst credits, not one-size-fits-all thresholds.
