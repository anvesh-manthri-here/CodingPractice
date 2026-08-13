# RED, USE, and the Golden Signals: Building Dashboards That Work

> **TL;DR:** RED (Rate, Errors, Duration) is the go-to framework for dashboarding *services*; USE (Utilization, Saturation, Errors) is the go-to framework for dashboarding *resources* (CPU, disk, queues). Google's four Golden Signals (latency, traffic, errors, saturation) roughly unify both. Pick a framework per dashboard instead of ad hoc panels — consistency is what makes a dashboard scannable during an incident at 3am.

## Quick Reference

| Framework | Applies to | Signals | Origin |
|---|---|---|---|
| RED | Request-driven services | **R**ate, **E**rrors, **D**uration | Tom Wilkie (Weaveworks), inspired by USE |
| USE | Resources (CPU, disk, memory, connection pools, queues) | **U**tilization, **S**aturation, **E**rrors | Brendan Gregg (performance engineering) |
| Golden Signals | Any service, Google's synthesis | Latency, Traffic, Errors, Saturation | Google SRE book |
| Four Keys (DORA) | Delivery/deployment performance, not runtime health | Deploy frequency, lead time, change failure rate, MTTR | DORA/Accelerate research |

## What It Is

- **RED**: for any service that handles requests, track the **Rate** of requests, the **Error** rate, and the **Duration** (latency) distribution — three panels per service, uniformly, so any two services' dashboards look and read the same way.
- **USE**: for any resource, track **Utilization** (% time busy), **Saturation** (how much queued/waiting work beyond capacity), and **Errors** (count of error events) — designed for root-causing performance problems in infrastructure, not user-facing services.
- **Golden Signals**: Google's four — Latency, Traffic, Errors, Saturation — is RED plus an explicit Saturation signal (RED assumes saturation shows up as latency/errors, which isn't always true early enough to matter).

## Responsibilities

- A good dashboard answers "is this healthy right now" in the first five seconds of looking at it — that requires consistent signal selection and layout, not "whatever metrics happened to be easy to add."
- RED panels belong on **service-level** dashboards (checkout-service, payment-service); USE panels belong on **resource-level** dashboards (this Postgres instance, this Kafka broker, this node's disk).
- Both frameworks exist to prevent the classic anti-pattern: a wall of 40 ungrouped graphs that nobody can parse under incident pressure.

## How It Works

**RED in practice** (per service, typically from load-balancer/ingress or app-level metrics):
```
Rate:     sum(rate(http_requests_total{service="checkout"}[5m]))
Errors:   sum(rate(http_requests_total{service="checkout", status=~"5.."}[5m]))
          / sum(rate(http_requests_total{service="checkout"}[5m]))
Duration: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{service="checkout"}[5m]))
```
- These three answer, respectively: is traffic normal, is anything actually broken, and is it slow — the three questions an on-call engineer asks first.

**USE in practice** (per resource, e.g. a DB instance):
```
Utilization: CPU % busy, disk I/O % busy, connection pool % in-use
Saturation:  run queue length, connection pool wait queue depth, disk I/O queue depth
Errors:      disk errors, dropped packets, connection refused count
```
- USE is diagnostic, not just observational: high utilization + low saturation is fine (resource is busy but keeping up); high utilization + rising saturation means it's about to fall behind — this distinction is the actual point of separating the two signals.

**Golden Signals** map roughly: Latency = Duration, Traffic = Rate, Errors = Errors, Saturation = the explicit "how close to capacity" signal RED leaves implicit — Google adds it back because a service can look fine on R/E/D right up until it falls off a cliff once saturation crosses 100%.

## Types / Classifications

| Dashboard tier | Framework | Audience |
|---|---|---|
| Service-level ("is checkout healthy") | RED / Golden Signals | On-call, during incidents |
| Resource-level ("is this DB the bottleneck") | USE | Deep-dive debugging, capacity planning |
| Business-level ("are we losing orders") | Custom, SLI-driven | Product, leadership, incident commander |
| Fleet/infra overview | USE aggregated across hosts | Infra/platform teams |

## Where It Fits

- Sits directly on top of **metrics** (file 03) — these frameworks are just principled ways to select and lay out which metrics/queries go on a dashboard.
- The Duration/Latency panel is exactly the input to **latency-based SLIs** (file 05); Rate and Errors similarly feed availability SLIs.
- USE panels are where you go *after* an alert fires from a RED/SLO dashboard to find the actual resource bottleneck — RED tells you *that* checkout-service is slow; USE on its DB tells you *why* (connection pool saturated).
- Complements **capacity planning and autoscaling** (Section 06, file 12) — saturation trends over weeks are the primary input to scaling decisions.

## Common Patterns & Real-World Tools

| Tool | Role |
|---|---|
| Grafana | Standard dashboard layer; RED/USE dashboards commonly built as reusable templated panels (one dashboard, `$service` variable) |
| Prometheus + PromQL | Most common backend for computing RED/USE queries |
| Node Exporter, cAdvisor | USE-style resource metrics for hosts/containers |
| Datadog "Service Catalog" / APM Service pages | Auto-generates RED-style views per service from trace/APM data |
| Grafana Mixins / kube-prometheus | Pre-built RED/USE dashboard definitions as code for common infra (Kubernetes, etcd, etc.) |

## Pros & Cons / Trade-offs

| Framework | Pros | Cons |
|---|---|---|
| RED | Simple, three panels, works for any request-driven service uniformly | Doesn't capture early-warning saturation; not suited to non-request resources |
| USE | Great for diagnosing *why* a resource is the bottleneck | Not directly meaningful to a product/business audience; more panels to build per resource type |
| Golden Signals | More complete (adds saturation explicitly) | Slightly more to define/instrument per service than RED alone |
| Ad hoc dashboards (no framework) | Fast to throw together | Inconsistent across services, slow to parse under pressure, prone to missing a critical signal entirely |

## Real-World Scenarios

- **Templated RED dashboard in Grafana**: one dashboard definition with a `$service` dropdown variable — switching services shows the same three-panel layout for any of 50 microservices, so on-call doesn't need to relearn a new dashboard layout mid-incident.
- **USE catches a saturating connection pool before errors appear**: utilization (DB CPU) looks fine at 60%, but saturation (connection pool wait queue) is climbing — USE surfaces this as a leading indicator; a RED-only dashboard on the *calling* service wouldn't show elevated errors/latency until the pool actually maxes out minutes later.
- **Golden Signals catching a saturation cliff**: a service's latency and error rate look completely normal until CPU saturation crosses ~90%, at which point latency spikes non-linearly (queueing theory) — a dashboard with an explicit saturation panel gives a warning several minutes before the RED panels would show anything.
- **Business dashboard vs RED dashboard mismatch during an incident**: RED shows checkout-service healthy (low errors, normal latency), but the business dashboard shows orders-per-minute cratering — root cause turns out to be a broken client-side JS bundle never reaching checkout-service at all; this is why a business/SLI-level dashboard matters as a check independent of service-level RED metrics.

## Nuances & Gotchas

- **RED without saturation misses the "about to fall over" case**: a service can have perfect RED numbers on a dashboard averaged over 5 minutes and still be one request away from a cliff if it's at 98% resource saturation — always pair RED with at least one saturation signal for the service's dominant resource.
- **Aggregated USE metrics hide single-instance problems**: fleet-average CPU utilization at 40% can hide one pod at 95% CPU throttled and failing — always have both fleet-aggregate and per-instance/per-shard views available, not just averages.
- **Percentile choice matters more than framework choice**: a Duration panel showing p50 looks great while p99 is terrible — always show multiple percentiles (p50/p95/p99) or a heatmap, not a single line, since averages and even single high percentiles hide bimodal latency distributions.
- **Dashboards rot**: a RED/USE dashboard built for a service's initial architecture silently stops reflecting reality after a rewrite (new bottleneck resource, deprecated metric name) — dashboards need the same review/ownership discipline as code, ideally defined as code (Grafonnet, Jsonnet, Terraform) and reviewed in PRs.
- **"Errors" in RED needs a clear definition upfront**: is a 4xx an error? A timeout? A degraded-but-200 response? Ambiguity here means different services measure "errors" inconsistently, defeating the purpose of a standardized framework across a fleet — pick a convention (5xx + timeouts = error; 4xx = client, tracked separately) and enforce it.
- **USE's "errors" bucket is often neglected**: teams build utilization and saturation panels but skip wiring up actual error counts (disk errors, dropped packets, driver-level errors) because they're less obviously actionable — this is exactly the signal that catches hardware-level degradation before it becomes a performance problem.
