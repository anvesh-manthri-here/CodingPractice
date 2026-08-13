# Metrics and Time-Series Fundamentals

> **TL;DR:** A metric is a numeric measurement with a name, a timestamp, and labels, sampled repeatedly over time. Counters, gauges, and histograms are the three shapes almost every metric fits into, and the pull-based scrape model (Prometheus) is the dominant pattern for collecting them cheaply at scale.

## Quick Reference

| Metric type | Behavior | Example | Valid operations |
|---|---|---|---|
| Counter | Monotonically increasing, resets on restart | `http_requests_total` | `rate()`, `increase()` — never read raw value alone |
| Gauge | Goes up or down, point-in-time | `queue_depth`, `memory_used_bytes` | Read directly, `avg`, `max` |
| Histogram | Distribution across configurable buckets | `http_request_duration_seconds` | Percentile estimation (`histogram_quantile`), sum/count |
| Summary | Client-side pre-calculated quantiles | Same use case as histogram | Cannot aggregate quantiles across instances (major limitation) |
| Collection model | Pull (Prometheus scrapes `/metrics`) vs Push (StatsD/Graphite, app pushes to agent) | | Pull = simpler service discovery, no dropped-agent blind spot |

## What It Is

- A **time series** is a stream of `(timestamp, value)` pairs identified by a metric name plus a set of key-value **labels** (dimensions) — e.g. `http_requests_total{method="GET", status="200", service="checkout"}`.
- Every unique combination of label values is a **distinct time series** stored and queried independently — this is the root of the cardinality cost model (file 12).
- Metrics are cheap because they're pre-aggregated at the source (a counter increment is O(1), not a stored event per request) — this is what makes them viable for high-frequency alerting and long retention, unlike raw logs/traces.

## Responsibilities

- The instrumentation library (client SDK: `prometheus_client`, Micrometer, OpenTelemetry Metrics) must expose current values cheaply and thread-safely.
- The collection system must scrape/receive values on a fixed interval, store them efficiently (time-series database), and support aggregation queries (`sum by (service) (rate(...))`).
- The label schema must stay bounded — the app owns *what* labels exist, and that decision directly determines infra cost.

## How It Works

**Pull model (Prometheus)**:
```
Prometheus server --HTTP GET /metrics (every 15s)--> App exposes current
                                                       counter/gauge/histogram
                                                       values in plaintext
Prometheus stores each scrape as a new timestamped sample per series
```
- Service discovery (Kubernetes API, Consul) tells Prometheus which targets to scrape — no app-side config of "where to send metrics to."
- If a scrape is missed (app down), that's itself informative (a gap = target down) rather than a silently missing push.

**Push model (StatsD)**:
```
App → UDP fire-and-forget → StatsD agent (local) → aggregates over flush
interval → pushes to backend (Graphite/Datadog)
```
- Lower app-side overhead (fire-and-forget UDP, no HTTP server to expose), but no built-in "is this target even alive" signal — a dead app just silently stops emitting.

**Counter → rate conversion**: counters reset to 0 on process restart; querying the raw value is meaningless across restarts. `rate(http_requests_total[5m])` computes per-second increase over a window, correctly handling resets — this is the single most common Prometheus query mistake for beginners (reading raw counters instead of `rate()`).

**Histogram → percentile**: a histogram buckets observations (`le="0.1"`, `le="0.5"`, `le="1"`, `le="+Inf"`) with cumulative counts; `histogram_quantile(0.99, ...)` interpolates the p99 from bucket boundaries — an *approximation* bounded by bucket granularity, not an exact percentile.

## Types / Classifications

| Storage model | Example | Trade-off |
|---|---|---|
| Pull-based TSDB | Prometheus, VictoriaMetrics | Simple, self-contained, but single-server Prometheus has scaling limits (solved via Thanos/Cortex/Mimir for federation) |
| Push-based | StatsD + Graphite, Datadog agent | Works well for ephemeral/short-lived jobs (Lambda) where nothing sticks around to be scraped |
| Managed/SaaS | Datadog, CloudWatch Metrics, New Relic | No infra to run; cardinality/retention billed directly |
| Long-term storage layer | Thanos, Cortex, Mimir, M3DB | Add horizontal scale + long retention on top of Prometheus's local-only model |

## Where It Fits

- Sits below **dashboards** (Grafana) and **alerting** (Alertmanager, file 07) — metrics are the raw fuel; dashboards/alerts are queries over them.
- Feeds **SLIs** directly (file 05) — an SLI is almost always defined as a query over metrics (e.g., `sum(rate(errors[5m])) / sum(rate(requests[5m]))`).
- Complements **health checks** (Section 06) — health checks answer "is this instance alive right now"; metrics answer "how has this instance/fleet behaved over time."
- Push-based metrics are common for **serverless/FaaS** (Section 05 architecture-patterns) where there's no long-lived process for a scraper to hit.

## Common Patterns & Real-World Tools

| Tool | Model | Notes |
|---|---|---|
| **Prometheus** | Pull | De facto standard for Kubernetes-native metrics; PromQL query language; single-node storage (scale via federation/remote-write) |
| **Grafana** | Query/visualization layer | Backend-agnostic (Prometheus, Loki, Elastic, CloudWatch all as data sources) |
| **StatsD** | Push (UDP) | Simple text protocol, originated at Etsy, still common for app-level custom metrics |
| **OpenTelemetry Metrics** | Push or pull (via Collector) | Emerging unified standard; can export to Prometheus format or any backend |
| **CloudWatch Metrics** | Push (AWS-native) | Default for AWS services, coarser granularity (1-min) unless "detailed monitoring" enabled |
| **Datadog / New Relic** | Push (agent-based) | Managed, easy custom-metric submission, cardinality-based pricing |

## Pros & Cons / Trade-offs

| Choice | Pros | Cons |
|---|---|---|
| Pull (Prometheus) | Central control of scrape interval; missing target is visible; simple app-side (just expose an endpoint) | Needs service discovery; harder for short-lived/serverless workloads |
| Push (StatsD) | Works for ephemeral processes; app doesn't need to run a server | No "is the app even alive" signal; agent becomes a dependency |
| Histogram | Aggregatable across instances (sum buckets, then quantile) | Bucket boundaries must be chosen upfront; wrong boundaries lose precision |
| Summary | Exact client-side quantiles | Cannot merge/aggregate across instances — p99 "summary" per-pod is not a fleet-wide p99 |

## Real-World Scenarios

- **Prometheus + Kubernetes**: pods self-register via annotations, Prometheus auto-discovers and scrapes every pod's `/metrics`; a rolling deploy shows old pods' series naturally aging out and new pods' series appearing — no manual metric endpoint management.
- **Wrong counter usage bug**: a dashboard shows a metric dropping to zero periodically and a team panics — it's just the counter resetting on pod restart (deploys, OOM kills); `rate()` would have masked this correctly, but the raw value was graphed by mistake.
- **CloudWatch 1-minute granularity surprise**: a team debugging a 10-second traffic spike can't see it in default CloudWatch metrics because standard resolution is 60s — they had to switch to high-resolution custom metrics (1s) for that specific signal.
- **Thanos/Cortex for multi-cluster**: a company running Prometheus per-Kubernetes-cluster federates all of them into Thanos for a single global query view and long-term (years) retention beyond what local Prometheus storage can hold.

## Nuances & Gotchas

- **Never graph a raw counter**: always `rate()`/`increase()` it first — this is the single most common PromQL mistake and produces charts that look like sawtooth garbage.
- **Summaries can't be aggregated**: if you need a fleet-wide p99 (not per-pod), use histograms, not summaries — summing 50 pods' individual p99s is mathematically meaningless.
- **Histogram bucket choice is a one-way door**: changing bucket boundaries after the fact makes historical data incomparable to new data; pick boundaries based on actual SLO thresholds (e.g., if SLO is "200ms," have a bucket boundary near 200ms, not just round numbers).
- **Scrape interval vs. alerting latency**: a 60s scrape interval means an alert can be up to ~60-90s late to fire on a real spike — tune interval to how fast you need to detect, balanced against storage cost.
- **Gauges sampled between scrapes can miss spikes**: a queue depth gauge that spikes and recovers between two 15s scrapes is invisible in the metric — for spiky signals, consider a counter of "times threshold exceeded" instead, or push-based instant capture.
- **Label cardinality is the #1 cost/outage cause**: adding a label with unbounded values (user_id, request_id, raw URL path with IDs in it) can 10-100x a Prometheus server's memory footprint and even crash it — normalize/bucket high-cardinality dimensions before they become labels (see file 12).
- **Down != zero**: a scrape gap (target down) should render as "no data," not silently as 0 — dashboards/alerts that treat missing data as zero can mask outages instead of surfacing them (`absent()` in PromQL exists specifically to alert on this).
