# Capacity Planning and Autoscaling

> **TL;DR:** Capacity planning sizes your baseline fleet from historical growth + peak multipliers; autoscaling handles the variance on top — but reactive triggers alone are too slow, so production systems combine headroom, predictive scaling, and carefully tuned policies to avoid both outages and thrash.

## Quick Reference

| Concept | Key Mechanism | Typical Tool |
|---|---|---|
| Capacity planning | Historical growth trend + peak/avg multiplier | Spreadsheet, `back-of-envelope-estimation.md` |
| Reactive autoscaling | Metric threshold breach → add/remove instances | K8s HPA, AWS ASG target tracking |
| Predictive/scheduled scaling | Pre-provision based on known/forecasted pattern | AWS Scheduled Scaling, Predictive Scaling |
| Scale-up lag | Cold start + warm-up before capacity is *useful* | JVM warm-up, connection pool fill, cache miss storm |
| Target tracking policy | Keep metric at setpoint (e.g., CPU 50%) | AWS ASG, HPA `averageUtilization` |
| Step scaling | Tiered response by breach magnitude | AWS ASG step adjustments |
| Scale-down thrash | Oscillation from aggressive shrink + no cooldown | Flapping HPA, ASG cooldown window |

## What It Is

- **Capacity planning**: the offline, longer-horizon exercise of deciding how much infrastructure you need — informed by historical traffic growth, seasonality, and known peak events (Black Friday, product launch).
- **Autoscaling**: the online, short-horizon mechanism that adjusts running capacity in near-real-time in response to (or anticipation of) load changes.
- They are complementary, not substitutes: capacity planning sets the *floor and ceiling* (min/max instance counts, reserved capacity); autoscaling fills the gap between baseline and peak.
- Sizing math (RPS, storage, bandwidth from user counts and growth rate) is covered in `back-of-envelope-estimation.md` — this file assumes you already have that number and focuses on *how to react to it in real time*.

## Responsibilities

- **Capacity planning owns**: baseline fleet size, reserved instance / savings-plan purchases, database and storage provisioning (which autoscale poorly or not at all), min/max autoscaler bounds, headroom budget.
- **Autoscaling owns**: minute-to-minute or hour-to-hour adjustment of stateless compute (web tier, workers, containers) within the bounds capacity planning set.
- **Neither owns**: hard dependencies that don't scale elastically — a single-writer Postgres primary, a fixed-size Kafka partition count, a downstream third-party API rate limit. These become the real ceiling regardless of how well autoscaling works.

## How It Works

1. **Capacity plan** produces: baseline RPS, growth curve (e.g., 15%/quarter), peak multiplier (e.g., 5x baseline for flash sales) → min/max instance bounds, reserved capacity commitment.
2. **Metrics pipeline** feeds autoscaler: CPU/memory (node-level), queue depth (SQS, Kafka consumer lag), request latency/concurrency (App Autoscaling custom metrics), custom business metrics (checkouts/sec).
3. **Controller loop** (HPA runs every 15s by default) compares current metric to target, computes desired replica count, applies scale-up/down within `minReplicas`/`maxReplicas`.
4. **Provisioning lag** — the gap most designs get wrong: metric breach detected → new instance requested → cloud API provisions VM/container → OS boot / image pull → app process start → JIT/cache warm-up → instance passes health check → added to load balancer rotation. Each hop adds seconds to minutes.
5. **Scale-down** applies a cooldown/stabilization window (HPA `stabilizationWindowSeconds`, ASG cooldown) before removing capacity, to avoid reacting to a transient dip.

```
Load spike ──▶ metric crosses threshold ──▶ scale decision
                                              │
                                    provision + boot + warm-up (LAG)
                                              │
                                    capacity actually absorbs load
```

## Types / Classifications

| Type | Trigger | Latency to Effect | Best For |
|---|---|---|---|
| **Reactive (threshold)** | CPU/mem/queue depth crosses set point | Seconds–minutes (+ boot lag) | Unpredictable, moderate-slope traffic |
| **Predictive** | ML forecast of near-future load (AWS Predictive Scaling) | Pre-provisions ahead of curve | Recurring daily/weekly patterns |
| **Scheduled** | Cron-like time window (9am weekday traffic) | Zero lag — capacity already there | Known events, deploy freezes, batch windows |
| **Target tracking** | Maintain metric at setpoint via PID-like control | Continuous, smooth | Steady-state workloads, default choice |
| **Step scaling** | Discrete add/remove tiers per breach magnitude | Faster response to large spikes | Bursty, spiky traffic needing aggressive response |
| **Simple/manual** | Fixed increment on alarm | Slowest, crudest | Legacy, low-maturity setups |

## Where It Fits

- **Stateless compute tiers** (API servers, web frontends, workers) autoscale well — no data affinity to preserve.
- **Stateful tiers** (databases, stateful caches) generally don't autoscale horizontally in real time; capacity planning must over-provision or use read replicas / sharding decided in advance.
- **Queue-based systems** (SQS + Lambda, Kafka + consumer groups) scale workers off backlog depth, decoupling producer spikes from consumer capacity — a natural buffer against scale-up lag.
- **CDN/edge** absorbs traffic spikes before they ever reach the autoscaled origin tier — reduces the load autoscaling needs to handle.
- Sits directly downstream of load balancing/health checks (`10-load-balancing...`) and upstream of the queuing/backpressure story — autoscaling is one lever among several for handling overload.

## Common Patterns & Real-World Tools

- **AWS ASG target tracking** — set CPU target 50%; ASG's own control loop adds/removes instances to hold that average.
- **Kubernetes HPA** — scales pods on CPU/memory or custom/external metrics (via Prometheus Adapter) using formula `desiredReplicas = ceil(currentReplicas × currentMetric / targetMetric)`.
- **KEDA** — event-driven autoscaling for K8s, scales on Kafka lag, SQS queue length, cron schedules — including scale-to-zero.
- **Cluster Autoscaler** (K8s) — scales *nodes* when pods are unschedulable, separate from HPA scaling *pods*; the two must be tuned together or pods wait on node provisioning.
- **AWS Predictive Scaling** — trains on 14 days of CloudWatch history, forecasts next 48h, pre-launches instances ahead of known peaks.
- **Warm pools** (AWS EC2 Warm Pool, pre-initialized Lambda provisioned concurrency) — keep pre-booted-but-stopped instances ready to cut scale-up lag from minutes to seconds.
- **Netflix/Amazon pattern**: overprovision by a fixed headroom % (e.g., always run 20% above current target) rather than scaling to exact predicted need.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Reactive only | Simple, no forecasting needed | Always lags the spike; risks SLA breach during ramp |
| Predictive/scheduled | Zero lag for known patterns | Blind to novel spikes; forecast drift on regime change |
| Target tracking | Smooth, self-correcting, low ops burden | Slow to react to step-function spikes |
| Step scaling | Fast, proportionate response to large breaches | More config complexity, tuning per step |
| Aggressive scale-down | Lower cost | High risk of flapping/thrash, capacity gap on next spike |
| Large fixed headroom | Absorbs sudden spikes, hides provisioning lag | Pure waste during trough — direct cost hit |

## Real-World Scenarios

- **Flash sale (predictable)**: capacity plan sizes 5x baseline via scheduled scaling starting 30 min before doors-open; reactive autoscaling handles only the unpredictable overshoot on top.
- **Viral traffic (unpredictable)**: CDN + queue absorb first minutes; reactive HPA on queue depth scales workers within 1–2 min; without a queue buffer, origin tier 503s during the boot-lag window.
- **JVM service cold start**: new pod passes K8s readiness probe in 5s but JIT hasn't warmed — first 60s of traffic to it is 3x slower; readiness probe alone is insufficient, need a warm-up/ramp-in period (Envoy's `slow_start_window`) before sending full traffic share.
- **Black Friday DB bottleneck**: app tier autoscales fine to 10x, but single-writer Postgres primary caps throughput regardless — capacity planning must pre-provision read replicas / connection pooler (PgBouncer) headroom since the DB can't autoscale reactively.
- **Midnight batch job spike**: scheduled scaling pre-warms worker fleet at 23:55 for a job that starts at 00:00, avoiding reactive lag entirely for a fully predictable event.

## Nuances & Gotchas

- **Scale-up lag is the real enemy, not the trigger threshold.** A perfectly tuned CPU threshold is useless if it takes 90s to boot + 60s to warm caches while p99 latency is already blown — design for *time-to-useful-capacity*, not time-to-alarm.
- **Headroom, not just reactivity.** Run steady-state utilization below 100% of target (e.g., target CPU 50% not 90%) so there's buffer to absorb the spike *during* the scale-up lag window — this is capacity planning bleeding into autoscaling config.
- **Thrashing/flapping**: scale-down too eagerly, load ticks back up, scale-up again, repeat — burns provisioning cost and destabilizes connection pools/caches on each churn. Fix with cooldown periods (ASG default 300s), HPA `stabilizationWindowSeconds` (default 300s on scale-down), and asymmetric policies (fast scale-up, slow scale-down).
- **Metric choice matters more than policy tuning.** CPU is a lagging, often misleading signal for I/O-bound or queue-based services — queue depth or in-flight request count reacts faster and correlates better with user-facing latency.
- **HPA + Cluster Autoscaler race condition**: HPA decides to add pods, but if nodes are full, pods sit `Pending` until Cluster Autoscaler provisions a node (can add 1–3 min) — effectively doubles the scale-up lag if not accounted for.
- **Cold cache stampede on scale-up**: new instances with empty local caches all miss simultaneously and hammer the DB/origin, sometimes causing a secondary outage right as you "fixed" capacity — mitigate with cache warm-up jobs or shared/remote caches (Redis) instead of local-only caching.
- **Scale-to-zero danger**: saves cost but reintroduces full cold-start lag on the very next request; only safe for latency-tolerant or async workloads (batch, event consumers), never for user-facing synchronous paths with tight SLAs.
- **Reserved capacity vs. autoscaling cost math**: pure on-demand autoscaling is expensive at sustained baseline; combine reserved instances/savings plans for the baseline floor with autoscaling only for the variable peak — capacity planning's multiplier estimate directly drives this split.
- **Load balancer connection draining**: scale-down must deregister and drain in-flight connections (ALB deregistration delay, K8s `preStop` hook + `terminationGracePeriodSeconds`) before killing the instance, or you drop live requests — a common source of "autoscaling caused errors" incidents.
