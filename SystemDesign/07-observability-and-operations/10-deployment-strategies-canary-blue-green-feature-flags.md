# Deployment Strategies: Canary, Blue-Green, and Feature Flags

> **TL;DR:** Never ship new code to 100% of traffic at once. Canary releases shift a small % of real traffic to the new version and watch metrics before proceeding; blue-green keeps two full environments and switches traffic atomically for instant rollback; feature flags decouple *deploying* code from *releasing* it, so a bad feature can be killed with a config flip, not a redeploy. All three exist to make "this change is bad" cheap and fast to detect and undo.

## Quick Reference

| Strategy | Mechanism | Rollback speed | Infra cost |
|---|---|---|---|
| Rolling deploy | Replace instances gradually, old and new coexist briefly | Minutes (redeploy old version) | Low (no extra capacity) |
| Blue-green | Two full environments; switch traffic atomically | Seconds (flip router back) | High (2x capacity during switch) |
| Canary | Small % of traffic to new version, ramp gradually if healthy | Seconds-minutes (route away from canary) | Medium (small extra capacity) |
| Feature flags | Code deployed but gated behind a runtime flag | Instant (flip flag, no deploy) | Low (flag service overhead) |
| Dark launch / shadow traffic | New version receives copied traffic but response discarded | N/A (no user impact by design) | Medium (duplicate processing) |

## What It Is

- **Rolling deploy**: instances are replaced one batch at a time (standard Kubernetes `Deployment` default) — old and new versions serve traffic simultaneously during the rollout window.
- **Blue-green**: two complete, identical production environments exist ("blue" = current live, "green" = new version); once green is verified, a router/load balancer switch flips 100% of traffic atomically; blue stays warm as an instant rollback target.
- **Canary**: a small subset of traffic (1%, then 5%, then 25%...) is routed to the new version while metrics are compared against the baseline (old version); only proceeds to full rollout if the canary's error rate/latency stay within acceptable bounds.
- **Feature flags**: application code checks a runtime flag (often via a flag service like LaunchDarkly) to decide whether to execute new logic — this separates the act of *deploying* code (always safe, code just sits there unused) from *releasing* a feature (a config change, reversible in milliseconds).

## Responsibilities

- The deployment system must be able to route a controlled fraction of traffic to a specific version (canary) or switch 100% atomically (blue-green) — this typically requires a smart load balancer, service mesh, or ingress controller, not just a naive round-robin.
- Canary analysis must compare against a **live baseline**, not a stale historical average, since traffic patterns shift constantly — comparing canary error rate to "last Tuesday" instead of "the old version serving the same traffic right now" produces false positives/negatives.
- Feature-flagged code must be cleaned up after full rollout — permanently-flagged code paths accumulate as technical debt (flag debt) if not retired once a feature is fully shipped and stable.

## How It Works

**Canary rollout with automated analysis**:
```
100% traffic → v1 (baseline)
        │
Deploy v2, route 1% traffic → v2
        │
Compare: v2 error_rate/latency vs v1 error_rate/latency over N minutes
        │
   Healthy? ──yes──▶ ramp to 5% → 25% → 50% → 100%
        │
        no
        ▼
   Auto-rollback: route traffic back to v1, alert team
```
- This loop is often automated (Flagger, Argo Rollouts) using exactly the RED-style metrics from file 06 as the pass/fail signal — canary analysis is a direct, practical application of that framework.

**Blue-green switch**:
```
Blue (v1, live) ◀── 100% traffic
Green (v2, staged, fully deployed but receiving zero/synthetic traffic)
        │  smoke tests pass on green
        ▼
Router switches: 100% traffic → Green
Blue stays warm, untouched, ready as instant rollback target
        │  (if issue found)
        ▼
Router switches back: 100% traffic → Blue
```

**Feature flag decoupling**:
```
Code with `if (flags.isEnabled("new-checkout-flow", user)) { ... }` deployed to 100% of
instances — but flag defaults to `false` for all users.
Flag service flips it to `true` for 1% of users → 10% → 100%, entirely via config,
zero redeploys, instant kill switch if something's wrong.
```

## Types / Classifications

| Strategy variant | Distinguishing trait |
|---|---|
| Rolling deploy | Simplest, default in most orchestrators, brief mixed-version window |
| Blue-green | Full duplicate environment, atomic switch, most expensive |
| Canary (manual) | Human watches dashboards and decides to proceed/rollback |
| Canary (automated) | Tooling (Flagger, Argo Rollouts) auto-analyzes metrics and auto-promotes/rolls back |
| Feature flag — release toggle | Short-lived, removed after full rollout |
| Feature flag — ops toggle | Long-lived kill switch for an operational concern (e.g., disable a heavy feature under load) |
| Feature flag — experiment toggle | A/B testing, tied to analytics rather than pure risk mitigation |
| Dark launch / shadow traffic | New code processes real traffic copies but results are discarded — tests performance/correctness with zero user-facing risk |

## Where It Fits

- Canary analysis is the direct downstream consumer of **RED metrics and SLOs** (files 05, 06) — "is the canary healthy" is exactly the same question as "is this service meeting its SLO," scoped to a traffic slice.
- Feature flags interact with **error budgets** (file 05): a bad feature caught mid-rollout via flag can be killed before it consumes meaningful budget, versus a full redeploy-to-rollback cycle that burns more budget during the fix window.
- Ties to **incident management** (file 11): "was this caused by a recent deploy" is often the first question in an incident, and deployment-strategy tooling (who deployed what, when, to what %) is a primary input to that timeline.
- Complements **circuit breakers and health checks** (Section 06) — a canary that starts tripping circuit breakers or failing health checks is an unambiguous automatic rollback signal.

## Common Patterns & Real-World Tools

| Tool | Category | Notes |
|---|---|---|
| **Argo Rollouts** | Kubernetes-native canary/blue-green | Progressive delivery controller, integrates with Prometheus for automated analysis |
| **Flagger** | Kubernetes-native canary | Works with service meshes (Istio, Linkerd) and ingress controllers for traffic shifting |
| **LaunchDarkly, Split, Unleash** | Feature flag platforms | Targeting rules, gradual rollout %, kill switches, experiment integration |
| **Spinnaker** | Multi-cloud deployment orchestration | Popularized canary analysis (Kayenta) at Netflix |
| **Istio / service mesh traffic splitting** | Underlying traffic-shifting mechanism | `VirtualService` weight-based routing is what most canary tools drive under the hood |

## Pros & Cons / Trade-offs

| Strategy | Pros | Cons |
|---|---|---|
| Rolling deploy | Simple, no extra infra cost | Rollback isn't instant (redeploy old version); brief mixed-version state can cause subtle bugs if versions aren't backward-compatible |
| Blue-green | Instant rollback, simple mental model, zero mixed-version window | 2x infra cost during switch; database schema changes are hard to do atomically alongside |
| Canary | Limits blast radius of a bad deploy to a small % of users; catches issues with real traffic before full exposure | Requires good metrics/automation to be fast; without automation, manual canary analysis is slow and error-prone |
| Feature flags | Fastest possible rollback (config, not deploy); enables gradual, targeted rollout by user segment | Flag debt accumulates if not cleaned up; adds a runtime dependency (flag service) and code complexity (conditional paths) |

## Real-World Scenarios

- **Netflix Kayenta**: automated canary analysis comparing dozens of metrics between canary and baseline clusters using statistical significance testing, not just eyeballing a dashboard — deploys that fail the automated judgment are rejected before any human even looks at them.
- **Database migration needs more than blue-green alone**: a schema change that's not backward-compatible breaks blue-green's instant-rollback promise (old version can't read new schema) — teams use the **expand/contract pattern** (add new column, dual-write, backfill, switch reads, drop old column later) alongside blue-green to keep rollback safe.
- **Feature flag as incident response**: a newly launched recommendation algorithm starts causing elevated latency; instead of an emergency rollback deploy (10+ minutes), on-call flips the feature flag off in seconds, immediately reverting to the old algorithm while the fix is prepared calmly.
- **Canary catches a region-specific bug rolling deploys would've missed**: a new version works fine in canary analysis on average metrics but a closer per-region breakdown shows it's failing specifically for EU traffic (a locale-parsing bug) — automated canary analysis segmented by region catches what an aggregate rolling deploy's post-hoc metrics wouldn't isolate as clearly.

## Nuances & Gotchas

- **Canary traffic must be representative**: canarying only internal/synthetic traffic first is safer but doesn't prove real-user behavior; canarying real user traffic is the actual test but means real users are exposed to risk — most mature setups canary a small % of *real* traffic specifically because synthetic-only canaries miss real-world edge cases.
- **Sticky sessions complicate canary/blue-green**: a user routed to canary v2 who then hits v1 on their next request (no session affinity) can see inconsistent behavior mid-session — session affinity/stickiness needs explicit design, especially for stateful flows like checkout.
- **Database changes are the hard part of every strategy**: code can roll back instantly with feature flags or blue-green, but a destructive schema migration cannot — always sequence schema changes to be backward-compatible with both old and new code versions before code deploy (expand/contract), independent of which deployment strategy is used.
- **Feature flag debt is real technical debt**: a codebase with hundreds of permanently-true flags nobody removed becomes a maze of dead conditional branches — track flag lifecycle explicitly (short-lived release flags should have an expiry/cleanup ticket created at flag-creation time).
- **Automated canary analysis needs enough traffic volume to be statistically meaningful**: a low-traffic service canarying at 1% might get too few requests to detect a real regression within a reasonable analysis window — low-traffic services often need either a longer analysis window or a higher initial canary percentage.
- **Blue-green's "instant rollback" isn't truly instant for stateful systems**: in-flight requests/connections during the switch can be dropped or need draining (connection draining/graceful shutdown) — a naive instant router flip without drain logic causes a brief error spike exactly during the "safe" rollback.
- **Feature flags evaluated client-side can leak unreleased features**: a flag check done entirely in frontend JS can be inspected/bypassed by a curious user before the feature is meant to be visible — security- or business-sensitive flags need server-side enforcement, not just client-side hiding.
