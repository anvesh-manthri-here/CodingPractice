# Availability and the Nines

> **TL;DR:** Availability = uptime / total time, but the number that actually matters is downtime budget in minutes/year — and MTTR, not MTBF, is what you control day-to-day.

## Quick Reference

**Formula:** `Availability = Uptime / (Uptime + Downtime) = MTBF / (MTBF + MTTR)`

| Availability | Nines | Downtime/year | Downtime/month | Downtime/week | Downtime/day |
|---|---|---|---|---|---|
| 90% | 1 nine | 36.5 days | 73 hr | 16.8 hr | 2.4 hr |
| 99% | 2 nines | 3.65 days | 7.3 hr | 1.68 hr | 14.4 min |
| 99.9% | 3 nines | 8.77 hr | 43.8 min | 10.1 min | 1.44 min |
| 99.95% | 3.5 nines | 4.38 hr | 21.9 min | 5.04 min | 43.2 sec |
| 99.99% | 4 nines | 52.6 min | 4.38 min | 1.01 min | 8.64 sec |
| 99.999% | 5 nines | 5.26 min | 25.9 sec | 6.05 sec | 0.86 sec |
| 99.9999% | 6 nines | 31.5 sec | 2.59 sec | 0.6 sec | 86 ms |

## What It Is

- Availability: fraction of time a system is able to correctly serve requests, over a defined window.
- Not the same as reliability (no failures at all) or correctness (right answer) — a system can be "up" and returning errors, and naive uptime checks won't catch it.
- Always defined relative to a **measurement window and method** — "99.9% over 30 days" is meaningless without knowing how downtime is detected and counted.

## Responsibilities

- Define the SLI (what's measured: HTTP 200s, successful probe, latency under threshold) precisely enough to be unambiguous during an incident.
- Set realistic SLO targets per dependency tier, not one blanket number for the whole org.
- Track error budget consumption and gate risky changes (deploys, migrations) when budget is low.
- Instrument MTTD/MTTR paths (alerting, runbooks, rollback tooling) since detection+recovery speed is the lever you actually pull.

## How It Works

- **MTBF** (Mean Time Between Failures): average time system runs before failing. Function of code quality, hardware, redundancy.
- **MTTR** (Mean Time To Recovery/Repair): average time from failure to restored service. Function of detection speed + diagnosis + mitigation.
- **MTTF** (Mean Time To Failure): like MTBF but for non-repairable components (disks you replace, not repair).
- **Why MTTR dominates:** availability math is `MTBF/(MTBF+MTTR)`. Doubling MTBF (harder, slower, capex-heavy) gives diminishing returns once it's already large; halving MTTR (better alerting, automated rollback, feature flags, runbooks) moves the needle faster and cheaper. A system that fails often but recovers in 10 seconds can beat one that fails rarely but takes an hour to fix.
- Practical MTTR levers: fast detection (SLO-based alerts, not just error counts), automated failover, canary+auto-rollback, feature flags to kill bad code paths without a deploy, clear runbooks so humans don't have to think under pressure.

## Types / Classifications

### Serial (dependency chain) — availabilities multiply, always worse than the weakest link
```
A(99.9%) -> B(99.9%) -> C(99.9%)  =>  0.999^3 = 99.7%  (not 99.9%!)
```
- Every hop in a synchronous call chain multiplies. 10 services at 99.9% each = 99.0% (~3.65 days/year down), even if each looks fine individually.
- This is why "each microservice hits 4 nines" doesn't imply the user-facing flow hits 4 nines.

### Parallel (redundancy) — combined unavailability multiplies, availability improves
- Two independent replicas each 99% available (1% down): combined unavailability = 0.01 × 0.01 = 0.0001 → 99.99% available, *if failures are independent*.
- Formula: `A_parallel = 1 - (1-A1)(1-A2)...(1-An)`.
- N+1 / N+2 redundancy, active-active multi-AZ, quorum reads/writes (Cassandra, etcd) all lean on this.

### Correlated vs independent failures
- Parallel math above assumes **independent** failure — often false. Shared power feed, shared AZ, shared config push, shared upstream DNS/CDN, same deploy rolled to all replicas simultaneously = correlated failure, redundancy buys nothing.
- Real incidents: us-east-1 regional outages take down "multi-AZ" services that all depend on a regional control plane (IAM, S3). A bad config pushed to all replicas at once defeats N+1.
- Mitigation: diversify failure domains (multi-region, multi-provider for critical paths), stagger rollouts (canary %, one AZ at a time), chaos testing to surface hidden shared dependencies.

### Measured vs perceived availability
- **Measured**: server-side metric — % of requests server returned 2xx/3xx within SLA latency.
- **Perceived**: what the user actually experienced — includes client-side failures, DNS, CDN edge issues, mobile network drops, retries masking or hiding errors.
- Gap sources: synthetic monitoring from one region ≠ global user experience; server "success" can still be a slow/broken page (JS error after 200 OK); load balancer health checks pass while app logic is broken (gray failure).
- Best practice: measure from the client/RUM (Real User Monitoring) as well as server-side, and treat elevated retries/timeouts as availability loss even if the eventual retry succeeds.

## Where It Fits

- Availability targets flow top-down: business SLA (external, contractual, often has financial penalties) → internal SLO (engineering target, stricter than SLA to leave margin) → SLI (the raw measurement).
- Each hop in a request's dependency graph needs its own budget allocation — you can't promise 99.99% at the edge if your DB is 99.9% and synchronous.
- Capacity planning, on-call staffing, and incident severity (SEV1-3) definitions are usually pegged to how much error budget an incident burns.

## Common Patterns & Real-World Tools

| Pattern/Tool | What it does differently |
|---|---|
| AWS Multi-AZ RDS | Sync replica in second AZ, automatic failover (~60-120s) — protects against AZ failure, not region failure |
| Kubernetes PodDisruptionBudget + multiple replicas | Parallel redundancy at pod level within a cluster; doesn't help if cluster control plane dies |
| Circuit breakers (Hystrix, resilience4j, Envoy) | Stop cascading failure across a serial chain — fail fast instead of exhausting threads/timeouts upstream |
| Load balancer health checks (ALB, Envoy, HAProxy) | Remove unhealthy nodes from parallel pool automatically; only as good as the health check's fidelity |
| Google's SRE error budget model | Formalizes SLO + budget burn rate as the release-gating mechanism |
| Chaos Engineering (Chaos Monkey, Gremlin, AWS FIS) | Surfaces correlated-failure assumptions before they cause real outages |
| Quorum systems (etcd/Raft, Cassandra QUORUM) | Parallel availability with consistency guarantees; tolerates f failures of 2f+1 nodes |
| Multi-region active-active (DynamoDB Global Tables, Cloudflare) | Defends against regional correlated failure, at cost of consistency/latency trade-offs |

## Pros & Cons / Trade-offs

- **Higher nines cost non-linearly**: going 99.9% → 99.99% often costs far more than 10x the engineering effort (multi-region failover, active-active data stores, chaos testing programs) for 10x the uptime.
- **Five nines (99.999%) is usually the wrong target** because:
  - 5.26 min/year budget is consumed by a *single* bad deploy or DNS TTL propagation — leaves no room for planned maintenance or human error.
  - Requires eliminating single points of failure everywhere, including deploy pipelines, DNS, certs, load balancers — the whole org's process maturity has to match, not just the architecture.
  - Diminishing user-perceptible value: humans often can't tell 99.95% from 99.999% day-to-day; the cost is better spent on feature velocity or MTTR tooling.
  - Appropriate only for narrow, well-isolated components (e.g., a stateless edge cache, DNS) — not entire multi-tier user journeys.
- **Serial chains punish nines-stacking**: adding more microservices to a synchronous request path silently lowers effective availability even if each new service is individually excellent — favor async/eventual patterns or bulkheading to cap blast radius.

## Real-World Scenarios

- **Checkout flow**: API gateway (99.99%) → auth service (99.95%) → payment service (99.9%) → inventory (99.9%), all synchronous = combined ~99.75%, i.e., ~22 hr/year down — far worse than any single component's stated SLA. Fix: cache auth tokens, make inventory check async/eventual, add fallback for payment provider timeout.
- **"Multi-AZ" that wasn't independent**: DB primary/replica in different AZs but both behind one regional NAT gateway; NAT outage took down both — redundancy existed on paper, not in the actual failure domain.
- **Retries hiding perceived downtime**: server reports 99.95% (measured), but client-side p99 latency spikes caused silent retries; RUM data showed 2% of real users saw failed/slow page loads — the gap is invisible without client-side telemetry.

## Nuances & Gotchas

- **MTTR math has a floor**: detection time (alert delay) + escalation + human context-switch often dominates actual fix time. A 5-nines target implies detecting and mitigating within seconds — usually requires automated remediation, not paging a human.
- **Maintenance windows count as downtime** unless explicitly excluded from the SLA — check the fine print; "scheduled maintenance excluded" can hide a lot of real unavailability from the headline number.
- **Availability ≠ durability**: S3's 99.99% availability SLA is separate from its 99.999999999% (11 nines) durability — don't conflate "can I read it right now" with "will the data ever be lost."
- **Load balancer health checks lie**: a shallow TCP/HTTP 200 check can pass while the app is in a gray-failure state (DB connection pool exhausted, returning cached stale errors) — deep health checks that exercise real dependencies catch this.
- **Averaging windows hide burst outages**: a 3-hour outage in month 1 and zero downtime months 2-12 both average to the same annual %, but user/business impact is wildly different — always look at incident distribution, not just the rolled-up number.
- **Error budgets can be gamed**: excluding "known issues" or third-party outages from SLI calculation inflates the number without improving actual user experience — be strict about what counts.
- **Composite SLAs from cloud vendors**: e.g., "99.99% for compute, 99.9% for storage" — your effective SLA is the serial combination across every managed service you depend on, often lower than any single vendor's headline number.
- **Deploys are the biggest correlated-failure risk**: most outages trace to a recent change, not random hardware failure — progressive rollout (canary, staged regions) and fast automated rollback matter more than raw redundancy for real-world MTTR.

## Self-Check

1. A request path goes through three synchronous services at 99.95%, 99.9%, and 99.99% availability. What's the combined availability, and why isn't it just the lowest individual number?
2. The formula `MTBF/(MTBF+MTTR)` treats MTBF and MTTR symmetrically. Why does reducing MTTR generally move availability more than increasing MTBF by the same proportion?
3. Why does a 5-nines (99.999%) SLA target usually fail even with strong redundancy, per the MTTR-floor gotcha?
4. You depend only on AWS services individually rated 99.99%. Why can your effective SLA still be lower than 99.99%?
5. A team ran DB primary/replica in two AZs and called it redundant, but a single incident took both down. What was the actual failure domain, and what does this say about the parallel-availability formula's assumption?

<details><summary>Answers</summary>

1. ~99.84% (0.9995 × 0.999 × 0.9999 ≈ 0.9984). Serial availabilities multiply, so the chain is always worse than its weakest link, not equal to it.
2. MTBF is already large and hard to grow further (capex-heavy, diminishing returns), while MTTR is small and cheap to cut via alerting, auto-rollback, and feature flags — the same absolute improvement in MTTR moves the ratio more.
3. The 5.26 min/year budget requires detecting and mitigating failures within seconds; alert delay + escalation + human context-switch alone usually exceeds that, so automated remediation is required, not just redundant hardware.
4. Your effective SLA is the serial combination across every managed service in the request path (compute, storage, network, etc.), so composing several 99.99% services multiplies down below 99.99%, same as any other synchronous chain.
5. Both AZs shared one regional NAT gateway, so the real failure domain was the NAT, not the DB. The parallel formula `1-(1-A1)(1-A2)` assumes independent failures; a shared dependency violates that assumption and the redundancy buys nothing.
</details>

---
**Related:** [Scalability](01-scalability-vertical-vs-horizontal.md) · [CAP Theorem](03-cap-theorem.md) · [Load Balancers](../02-core-components/01-load-balancers.md)

*Last reviewed: 2026-08*
