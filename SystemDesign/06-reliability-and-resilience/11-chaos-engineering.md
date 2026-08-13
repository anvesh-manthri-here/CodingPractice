# Chaos Engineering

> **TL;DR:** Deliberately inject controlled failure into a system (ideally production) to surface hidden assumptions and weak dependencies before they cause an uncontrolled outage — a scientific discipline, not "randomly breaking things."

## Quick Reference

| Aspect | Detail |
|---|---|
| Core loop | Define steady-state → hypothesize → inject 1 variable → measure → minimize blast radius → fix → repeat |
| Prerequisites | Observability (metrics/traces/alerts), fast rollback, low-traffic canary env first |
| Classic tool | Netflix Chaos Monkey (kills instances at random during business hours) |
| Suite | Netflix Simian Army — Chaos Monkey, Latency Monkey, Conformity Monkey, Chaos Kong (region failure) |
| Commercial | Gremlin — attack library, blast-radius controls, "GameDay" scheduling |
| Cloud-native | AWS Fault Injection Simulator (FIS) — API/IAM-integrated, SSM-based, safety stop conditions |
| Kubernetes | Litmus, Chaos Mesh, PowerfulSeal — CRD-driven experiments, pod/network/IO faults |
| Experiment types | Instance kill, latency injection, CPU/disk/memory saturation, network partition, DNS failure, region/AZ failover, clock skew |
| Blast radius control | Start with 1 host / 1% traffic / staging; expand only after confidence |
| Org practice | GameDays — scheduled, cross-team chaos exercises with an incident-commander dry run |
| Anti-pattern | Injecting chaos with no monitoring, no hypothesis, or no abort mechanism |

## What It Is

- A **discipline for building confidence** in a distributed system's ability to withstand turbulent, real-world conditions — coined and popularized by Netflix (2010, Chaos Monkey; formalized 2015, Principles of Chaos Engineering).
- Treats resilience as an empirically tested property, not an assumed one — you don't know your system tolerates a broker crash until you've killed a broker and watched it recover.
- Distinct from traditional testing: unit/integration tests verify *known* behavior against *known* inputs; chaos experiments probe *unknown* failure modes in a live, complex system where full state is unobservable ahead of time.
- Complements, does not replace, disaster recovery drills, load testing, and fault-tolerant design (circuit breakers, retries, bulkheads).

## Responsibilities

- Validate that redundancy actually works (e.g., does traffic really fail over to the replica, or does the health check lie?).
- Expose hidden dependencies — a "stateless" service that silently depends on one Redis instance with no failover.
- Test human/operational readiness: do on-call runbooks, alerts, and dashboards actually catch the failure in time?
- Quantify blast radius and recovery time (MTTR) under controlled conditions instead of during a live customer-facing incident.
- Build organizational muscle memory — engineers who've practiced failure respond faster and calmer during real ones.

## How It Works

**The scientific method, applied to production:**

1. **Define steady state** — a measurable output (e.g., checkout success rate ≥ 99.9%, p99 latency < 300ms), not internal system health.
2. **Hypothesize** — "if the payment service's primary DB node dies, steady state holds because of automatic failover."
3. **Inject a single variable** — one fault type, one blast-radius scope, one point in time. Never combine multiple unknowns.
4. **Run and observe** — compare steady-state metrics before/during/after via existing observability (Datadog, Prometheus/Grafana, distributed tracing).
5. **Minimize blast radius** — start in staging or with 1 instance / low-traffic segment; use feature flags or traffic percentage to cap exposure.
6. **Abort criteria** — predefined automatic rollback trigger (error-rate threshold, SLO breach) — a "big red button."
7. **Learn and fix** — file the gap as a bug/design issue, retest after remediation, then broaden scope (more instances, more traffic, prod).

```
steady state --> hypothesis --> inject fault --> observe --> abort if breach --> fix --> re-run wider
```

## Types / Classifications

| Category | Examples |
|---|---|
| **Resource exhaustion** | CPU spin, memory leak simulation, disk fill, file-descriptor exhaustion |
| **State/process** | Kill process/instance, force pod eviction, corrupt cache entry |
| **Network** | Inject latency, packet loss, DNS resolution failure, network partition, black-hole a dependency |
| **Infrastructure** | AZ/region failover (Chaos Kong), zone outage simulation, spot-instance reclamation |
| **Dependency** | Simulate 3rd-party API timeout/5xx, degrade a downstream service's response time |
| **Time/Clock** | Clock skew, NTP drift, certificate expiry simulation |
| **Application-level** | Feature-flag-driven fault injection in code paths (e.g., force exception in payment SDK) |

By scope: **GameDays** (scheduled, human-run, cross-team) vs **continuous automated chaos** (Chaos Monkey running unattended in prod every weekday).

## Where It Fits

- Sits alongside SRE practice: after SLOs/SLIs are defined and observability is mature, chaos engineering becomes the verification loop for reliability targets.
- Runs in CI/CD as a gate for some orgs (chaos experiments as part of pre-prod pipeline) and as scheduled/continuous jobs in prod for mature orgs.
- Operates *on top of* resilience mechanisms already built — circuit breakers (Hystrix/resilience4j), retries with backoff, bulkheads, load shedding — chaos engineering tests whether those mechanisms actually trigger correctly.
- Feeds back into architecture reviews and postmortems: findings become backlog items, not just reports.

## Common Patterns & Real-World Tools

| Tool | Highlights |
|---|---|
| **Chaos Monkey** (Netflix) | Randomly terminates VM instances in prod during business hours only, forcing services to tolerate instance loss |
| **Simian Army** | Latency Monkey (injects delay), Conformity Monkey (flags non-best-practice instances), Chaos Kong (simulates full AWS region failure) |
| **Gremlin** | SaaS, attack catalog (resource, state, network), scheduled GameDays, halt/abort safety controls, blast-radius targeting by tag |
| **AWS Fault Injection Simulator (FIS)** | Native AWS integration, targets EC2/ECS/EKS/RDS, IAM-scoped, stop-conditions tied to CloudWatch alarms |
| **Litmus / Chaos Mesh** | Kubernetes-native (CRDs), pod-delete, network-chaos, IO-chaos, integrates with Argo workflows |
| **Toxiproxy** (Shopify) | TCP-level proxy for injecting latency/timeouts between services in test envs |
| **PowerfulSeal** | K8s chaos + policy-driven autonomous experiments |

## Pros & Cons / Trade-offs

| Pros | Cons / Costs |
|---|---|
| Finds real gaps before customers do | Real risk of causing an actual outage if blast radius misjudged |
| Builds confidence in failover/redundancy claims | Requires mature observability first — chaos without visibility is just sabotage |
| Improves incident response readiness (muscle memory) | Cultural resistance — teams fear "breaking prod on purpose" |
| Uncovers cascading-failure risks (retry storms, thundering herd) | Engineering investment: tooling, safe abort mechanisms, scheduling |
| Cheaper to fix in a controlled experiment than in 3am incident | Can generate noisy false alarms if steady-state metrics are poorly chosen |

## Real-World Scenarios

- **Netflix**: Chaos Monkey kills instances continuously in prod; Chaos Kong once simulated an entire AWS region outage to validate multi-region failover — found and fixed real gaps before any actual region event.
- **E-commerce checkout**: Inject 2s latency into the payment gateway dependency to verify the circuit breaker trips and the UI degrades gracefully (e.g., "try again" message) instead of hanging the whole checkout flow.
- **Kubernetes cluster**: Use Litmus to delete a random pod of a StatefulSet during peak load to confirm the readiness probe and PodDisruptionBudget prevent a cascading capacity loss.
- **Database failover drill**: Kill the primary Postgres node via AWS FIS, measure actual failover time against the documented RTO of 30s — often reveals it's really 90s+ due to DNS TTL caching.
- **GameDay exercise**: Cross-team scheduled event simulating a Kafka broker loss, verifying consumer lag alerts fire and on-call runbook steps are current and executable.

## Nuances & Gotchas

- **No chaos without observability** — if you can't see the blast radius in real time (dashboards, alerts, tracing), you're not experimenting, you're gambling; build monitoring maturity first.
- **The "big red button" must actually work** — test the abort/rollback mechanism *before* running the experiment; a broken kill-switch turns an experiment into an incident.
- **Steady-state metric choice matters** — measuring internal health (CPU, pod count) instead of user-facing outcomes (checkout success, login latency) hides the failures that actually matter to customers.
- **Blast radius creep** — teams that skip the "start small" step and go straight to full-traffic prod experiments are the ones who cause real outages; always graduate staging → 1% → 10% → 100%.
- **Correlated/compound failures are the real danger zone** — single-fault experiments are safe; combined faults (AZ outage + deploy in progress + on-call asleep) is where real incidents live, but is much harder and riskier to simulate deliberately.
- **False confidence from partial coverage** — passing chaos tests for the services you *think* to test says nothing about the untested dependency graph; maintain a live service-dependency map to prioritize experiments.
- **Business-hours-only rule (Netflix's own policy)** — Chaos Monkey deliberately runs only when engineers are awake and available to respond, not nights/weekends — don't inject chaos when nobody can react.
- **Stateful systems are the hardest and riskiest target** — killing a stateless web server is low-risk; killing a database primary or message-queue leader can cause data loss or split-brain if replication/quorum isn't actually correct — verify data-layer experiments in staging first, extensively.
- **Chaos engineering is not a substitute for good design** — it finds gaps, it doesn't fix them; teams that run experiments but don't feed findings back into architecture/backlog get no lasting benefit.
- **Regulatory/compliance environments** (finance, healthcare) often require chaos experiments to run only in shadow/staging environments with production-mirrored traffic rather than live prod — know your constraints before choosing a tool.
