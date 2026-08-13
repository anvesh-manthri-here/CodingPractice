# Disaster Recovery — RTO and RPO

> **TL;DR:** RTO caps how long you're down; RPO caps how much data you can lose. Every dollar spent moving down the DR spectrum (backup/restore → pilot light → warm standby → active-active) buys lower RTO/RPO — and DR plans nobody tests are just theories.

## Quick Reference

| Concept | Definition | Driven by |
|---|---|---|
| **RTO** (Recovery Time Objective) | Max acceptable time from disaster to service restored | Failover automation, infra readiness |
| **RPO** (Recovery Point Objective) | Max acceptable data loss, measured in time | Backup/replication frequency |
| Backup & Restore | Periodic backups, restore on disaster | Cheapest, slowest |
| Pilot Light | Core infra idle in DR region, scaled up on failover | Minutes-hours RTO |
| Warm Standby | Scaled-down but live replica running | Minutes RTO |
| Active-Active (Hot) | Full duplicate serving live traffic | Seconds RTO, highest cost |
| Game Day | Scheduled simulated disaster drill | Validates the plan actually works |

```
Cost/Complexity  ─────────────────────────────►
Backup&Restore → Pilot Light → Warm Standby → Active-Active
RTO: hours-days →  10s min-hr →   minutes    →  seconds
RPO: hours      →  minutes    →   seconds    →  near-zero
```

## What It Is
- **RTO**: "How long can the business tolerate the system being down?" Measured from incident declared to service restored to users.
- **RPO**: "How much data can we afford to lose?" Measured as a time window — e.g. RPO of 15 min means last 15 min of writes may vanish.
- Both are **business decisions**, not engineering ones — finance/product should set targets per system tier (payments vs. internal wiki have wildly different tolerances).
- They are independent axes: you can have low RTO/high RPO (fail over fast to stale data) or high RTO/low RPO (slow but lossless recovery via backups).

## Responsibilities
- **RPO drives**: backup schedule, snapshot frequency, replication topology (async vs sync), WAL shipping interval, cross-region replication lag budget.
- **RTO drives**: automation of failover (manual runbook vs. automated health-check + DNS/traffic shift), standby infra readiness (cold vs warm vs hot), DNS TTLs, orchestration tooling (Kubernetes multi-cluster failover, AWS Route 53 health checks).
- **Org responsibility**: define RTO/RPO per service tier in an SLA/DR policy doc; engineering implements the matching strategy; SRE/ops runs drills to prove it.

## How It Works
1. Business impact analysis assigns RTO/RPO targets per system (Tier 0 payments: RTO 5 min/RPO 0; Tier 3 internal tool: RTO 24h/RPO 24h).
2. Engineering picks a DR pattern from the spectrum that meets those numbers at acceptable cost.
3. RPO is satisfied by **data protection mechanism**: snapshot interval, DB replication mode (Postgres streaming replication async lag, MySQL semi-sync, DynamoDB Global Tables), object storage cross-region replication (S3 CRR, ~15 min typical lag).
4. RTO is satisfied by **recovery mechanism**: infra-as-code to rebuild (Terraform + AMI/image restore), pre-provisioned standby, automated failover (Route 53 failover routing, RDS Multi-AZ automatic failover ~60-120s).
5. Failover is triggered — manually (declared incident, runbook executed) or automatically (health check threshold breach → traffic cutover).
6. Failback (returning to primary once healthy) is often the harder, less-tested half.

## Types / Classifications

| Strategy | RTO | RPO | Cost | Mechanism |
|---|---|---|---|---|
| Backup & Restore | Hours–days | Hours (backup interval) | $ | Nightly snapshots, S3 Glacier, restore on demand |
| Pilot Light | 10s of min–hours | Minutes | $$ | Core DB replicated live, app servers off until needed |
| Warm Standby | Minutes | Seconds–minutes | $$$ | Scaled-down full stack running, scale up on failover |
| Multi-Site Active-Active | Seconds | Near-zero (sync replication) | $$$$ | Both regions serve live traffic, sync or quorum writes |

- **Sync replication** (e.g., Postgres synchronous_commit, Spanner, CockroachDB) → RPO ≈ 0 but adds write latency and can block on cross-region partition.
- **Async replication** (default MySQL/Postgres replicas, most cross-region setups) → RPO = replication lag (seconds to minutes), no latency penalty.

## Where It Fits
- Sits above **HA (high availability)**: HA handles single-node/single-AZ failure automatically within a region; DR handles region-level or catastrophic loss requiring a distinct failover target.
- Complements **backup strategy** (3-2-1 rule: 3 copies, 2 media types, 1 offsite) which underpins RPO for backup/restore-tier strategies.
- Feeds into **incident response**: DR runbook is invoked as part of a Sev1 declared-disaster incident, distinct from routine on-call remediation.
- Ties to **SLA/error budgets**: RTO/RPO targets often become contractual (e.g., 99.9% availability with 4h RTO for enterprise tier).

## Common Patterns & Real-World Tools
- **AWS**: Route 53 failover routing + health checks, RDS Multi-AZ (sync, RTO ~60-120s) vs cross-region read replica (async, higher RPO), S3 Cross-Region Replication, AWS Elastic Disaster Recovery (CloudEndure) for pilot-light VM replication.
- **GCP**: Cloud SQL cross-region replicas, Spanner multi-region (RPO≈0 via Paxos), GKE multi-cluster with Anthos.
- **Databases**: Postgres streaming replication + `pg_rewind`, MySQL semi-sync, MongoDB replica sets with priority-based failover, Cassandra multi-DC with tunable consistency.
- **Chaos/testing**: Netflix Chaos Monkey/Chaos Kong (region evacuation drills), Gremlin for scheduled failure injection.
- **Backup tooling**: Velero (Kubernetes cluster backup/restore), pgBackRest/WAL-G (Postgres continuous archiving for point-in-time recovery).

## Pros & Cons / Trade-offs
- **Backup/Restore**: cheapest, simplest to reason about; but RTO in hours means real revenue/reputation loss for critical systems.
- **Pilot Light**: good middle ground; but "scale up on demand" often fails first drill because AMIs are stale or capacity isn't reserved (no on-demand instance guarantee during regional disaster).
- **Warm Standby**: reliable RTO; costs ~2x infra spend running duplicate (scaled-down) stack continuously.
- **Active-Active**: best RTO/RPO; but doubles operational complexity — data conflict resolution, split-brain risk, sync replication latency tax on every write.
- General trade-off: **lower RTO/RPO always costs more** — in infra spend, in engineering complexity, or in write latency. There's no free lunch; the job is matching spend to actual business tolerance, not minimizing numbers blindly.

## Real-World Scenarios
- **Payments processor**: RTO 5 min / RPO near-zero → active-active multi-region with synchronous consensus (e.g., Spanner) or quorum writes; even seconds of lost transactions are unacceptable and reconciliation is costly.
- **SaaS analytics dashboard**: RTO 4h / RPO 1h acceptable → warm standby with async replication; customers tolerate a maintenance-window-like outage.
- **Internal wiki/tools**: RTO 24h / RPO 24h → nightly backup/restore is sufficient; not worth standby infra spend.
- **2017 AWS S3 us-east-1 outage**: companies with only backup/restore in a single region had multi-hour outages; those with cross-region replication degraded gracefully.
- **GitLab 2017 data loss incident**: backup automation had silently been failing for weeks — RPO target existed on paper but was never actually met because backups weren't verified/tested.

## Nuances & Gotchas
- **Untested backups are not backups.** GitLab's 2017 incident: 5 different backup mechanisms, all failing, discovered only during the actual disaster — restore from the one manual snapshot that existed, losing ~6 hours of data.
- **RTO on paper vs. RTO in practice diverge hugely** — DNS TTL caching by ISPs/clients can add 10-30 min beyond your configured TTL; connection pools and client-side caching delay actual cutover perception.
- **Failback is usually untested** and often harder than failover — replaying divergent writes from the DR site back to primary risks conflicts/data loss if not planned (dual-write reconciliation, CDC-based resync).
- **Game days are the part everyone skips** — a DR plan that hasn't been executed end-to-end (not just tabletop-reviewed) will have wrong runbook steps, expired credentials, missing IAM permissions, stale AMIs. Netflix's Chaos Kong literally kills a region on schedule to force this.
- **Dependencies outside your control break DR**: DNS providers, cert issuance (Let's Encrypt rate limits during mass reissue), third-party SaaS APIs (Auth0, Stripe) may not have matching DR postures — your RTO is bounded by your slowest critical dependency.
- **Capacity isn't guaranteed during regional disasters** — if the whole region fails, everyone else is also requesting standby capacity; without reserved instances/capacity reservations, pilot-light "scale up" can hit availability limits exactly when needed most.
- **RPO must be independently verified**, not assumed from replication config — async replication lag can silently balloon under load; monitor actual lag metrics, not just "replication is enabled."
- **Split-brain in active-active**: network partition between regions can cause both sides to accept writes independently; needs conflict resolution (CRDTs, last-write-wins with vector clocks) or a consensus layer, or you get silent data corruption instead of the loss you planned for.
- **Cost creep**: warm/active-active setups often get quietly downgraded post-incident-response ("we'll right-size it later") until the next disaster reveals the standby was never actually kept in sync with prod schema/config changes.
