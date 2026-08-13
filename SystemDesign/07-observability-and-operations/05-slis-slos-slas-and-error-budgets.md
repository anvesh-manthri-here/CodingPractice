# SLIs, SLOs, SLAs, and Error Budgets

> **TL;DR:** An SLI is a measured metric ("what % of requests succeeded"), an SLO is an internal target for that metric ("99.9% over 30 days"), and an SLA is an external contractual promise with consequences for missing it. The gap between 100% and your SLO is the **error budget** — a quantified, spendable allowance for risk that turns "should we deploy this risky change" into a data question instead of a political one.

## Quick Reference

| Term | Definition | Audience | Example |
|---|---|---|---|
| SLI (Indicator) | A measured value of service behavior | Internal, engineering | "% of HTTP requests returning 2xx/3xx within 300ms" |
| SLO (Objective) | Internal target for an SLI over a window | Internal, eng + product | "99.9% of requests meet the SLI over rolling 30 days" |
| SLA (Agreement) | External contract with consequences | Customer-facing, legal/sales | "99.9% uptime or customer gets service credits" |
| Error budget | `1 - SLO`, the allowed failure rate | Internal, decision-making tool | 99.9% SLO → 0.1% budget → ~43 min downtime/month |
| Burn rate | How fast the error budget is being consumed | Internal, alerting | "Burning budget 10x normal rate — will exhaust in 3 hours" |

## What It Is

- **SLI**: a precise, measurable proxy for "is the service doing its job" — always a ratio (good events / total events) or a percentile (p99 latency ≤ threshold), computed from real telemetry (usually metrics).
- **SLO**: the target value for an SLI that the team commits to internally, always with a time window ("99.9% over 30 days," not "99.9% right now") because instantaneous availability is meaningless — a single bad second isn't an outage.
- **SLA**: an SLO that has been turned into a customer-facing promise, usually with a *looser* target than the internal SLO (so there's margin before contractual penalties kick in) and defined financial/contractual consequences for breach.
- **Error budget**: the quantified amount of "badness" allowed by the SLO — not a bug, but a deliberate management tool. 100% reliability is neither achievable nor economically sensible; the budget makes the trade-off explicit.

## Responsibilities

- SRE/platform teams own defining SLIs that actually reflect user-perceived experience, not just what's easy to measure (a load balancer's health check passing is not the same as the user's page loading correctly).
- Error budget policy must be pre-agreed and followed mechanically: e.g., "if budget is exhausted, feature launches freeze until it recovers" — the point is removing this from ad hoc/political debate during an incident.
- Product and engineering jointly own the *target number* — reliability targets are a product decision (cost/risk trade-off), not a purely technical one.

## How It Works

```
Time window: 30 days = 43,200 minutes
SLO: 99.9% availability
Error budget = 0.1% × 43,200 min ≈ 43 minutes of allowed "bad" time

Day 1-15: one incident consumes 20 minutes of budget → 23 min remaining
Day 16: team wants to ship a risky migration
  → budget still positive → ship allowed, but monitor burn rate closely
Day 25: a second incident consumes 30 more minutes → budget exhausted (over by 7 min)
  → error budget policy triggers: freeze non-critical releases until window rolls
    forward and budget recovers, focus shifts to reliability work
```

- **Burn rate** = (rate of budget consumption) / (rate that exactly exhausts budget at window end). A burn rate of 1x means "on pace to exactly use 100% of budget by window end" — normal. A burn rate of 10x means the budget will be gone in 1/10th the window time — this is what multi-window burn-rate alerts fire on (see file 07), because it's an early-warning signal long before the SLO itself is technically breached.
- SLOs are typically defined and evaluated via a **query over metrics** (Prometheus recording rules, Datadog SLO objects) — this is why SLIs need clean, reliable metrics as a prerequisite (file 03).

## Types / Classifications

| SLI category | Example | Common target range |
|---|---|---|
| Availability | % of requests not erroring | 99.9%–99.99% |
| Latency | % of requests under a threshold (not raw p99, which fluctuates too much for a threshold-based SLI) | 95–99% under Xms |
| Throughput | % of time system can handle expected load | Rare as primary SLI, more a capacity metric |
| Correctness/Freshness | % of data within acceptable staleness bound | Common for pipelines/caches (e.g., "95% of events processed within 5 min") |
| Durability | Probability data isn't lost (often cited, not measured in real time) | 99.999999999% (S3-style "11 nines") |

## Where It Fits

- Sits above raw metrics (file 03) as the layer that gives them business meaning — a metric alone is just a number; an SLO says whether that number is *acceptable*.
- Directly drives **alerting policy** (file 07): the best practice is to alert on SLO burn rate, not on raw metric thresholds, because burn-rate alerts are inherently tied to user impact and budget consequence.
- Ties into **capacity planning and autoscaling** (Section 06, file 12) — SLO headroom is a primary input to how aggressively you can scale down / how much buffer capacity to keep.
- Frames decisions elsewhere in this curriculum: whether to add a circuit breaker, whether a cache stampede mitigation is worth the complexity, whether a migration is "safe enough to ship" — all ultimately trade against the error budget.

## Common Patterns & Real-World Tools

| Tool | Role |
|---|---|
| Google SRE workbook / "Implementing SLOs" | Origin of the modern SLO/error-budget framework |
| Prometheus recording rules + Grafana | DIY SLO computation and dashboards |
| Datadog SLOs, Nobl9, Sloth | Purpose-built SLO tracking and burn-rate alerting products |
| OpenSLO | Emerging open spec for defining SLOs as code (YAML), portable across tools |
| PagerDuty/Opsgenie | Consume burn-rate alerts to page on-call (file 07) |

## Pros & Cons / Trade-offs

| Aspect | Pros | Cons |
|---|---|---|
| SLO-based alerting | Directly tied to user impact; fewer noisy low-value alerts | Requires investment to define good SLIs first; not a drop-in replacement for all alerting |
| Error budget policy | Removes reliability-vs-velocity debate from politics into data | Requires organizational buy-in to actually honor the freeze — toothless if leadership overrides it every time |
| Strict SLA | Clear customer trust signal, competitive differentiator | Real financial/legal risk if breached; tends to push SLO targets conservative, which costs more infra |
| 100% reliability target (anti-pattern) | — | Economically irrational — the last 9s cost exponentially more, and it disincentivizes any risk-taking/velocity entirely |

## Real-World Scenarios

- **Google SRE origin story**: SLOs and error budgets were formalized specifically to end the recurring conflict between Dev (wants to ship fast) and Ops (wants stability) — the budget makes "how much risk is left this month" an objective, shared number both sides look at.
- **Multi-window burn-rate alert**: an alerting rule fires only if burn rate is high over *both* a 5-minute and 1-hour window — catches fast, severe incidents in minutes while not paging on brief blips (see file 07 for the underlying pattern).
- **SLA vs SLO gap in practice**: an internal SLO of 99.95% but a customer SLA of 99.9% gives the team a buffer — minor SLO misses don't trigger customer-facing financial penalties, but the team still treats SLO breaches as an internal signal to act on.
- **Freeze in action**: an e-commerce team burns 80% of its monthly error budget in a single bad deploy in week one; per policy, all non-critical feature launches freeze for the rest of the month while the team focuses purely on reliability fixes — a decision made automatically by policy, not by a VP overriding a launch date.

## Nuances & Gotchas

- **Instantaneous "5 nines" claims are usually meaningless without a window** — always ask "over what period"; a service can be "99.999% available" measured over 5 minutes and still have had a real 10-minute outage last month if the window resets.
- **Picking the wrong SLI is worse than no SLI**: a load-balancer-level health check passing doesn't mean the user's request actually succeeded end-to-end (it might 500 after passing the LB check) — SLIs should be measured as close to the user's actual experience as feasible (client-side/RUM when possible).
- **Latency SLIs as raw percentiles don't compose well as pass/fail targets** — better practice is "% of requests under threshold X" (a ratio, same shape as availability SLIs), not "p99 < 300ms" as a binary target, because a single percentile is noisy and doesn't tell you *how much* of your traffic is affected.
- **Error budgets can be gamed by loosening the SLO** — if a team keeps missing its SLO, quietly lowering the target instead of fixing reliability defeats the entire point; SLO changes should go through the same review as the policy that depends on them.
- **100% budget consumption ≠ site is down** — it means the *cumulative* allowed bad-time for the window is used up; the site might be fine right now but the team is over-budget for making it worse until the window rolls forward.
- **New/immature services often can't sustain aggressive SLOs yet** — a common failure mode is copy-pasting a mature service's 99.99% target onto a service six weeks old; start looser, tighten as reliability work matures the service.
- **Dependencies compound**: a service calling three downstream services each at 99.9% has a theoretical ceiling below 99.9% for its own SLO (99.9%³ ≈ 99.7%) unless it has fallback/degradation paths — SLOs must account for the reliability of the whole dependency chain, not be set in isolation.
