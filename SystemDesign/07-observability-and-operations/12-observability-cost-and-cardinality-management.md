# Observability Cost and Cardinality Management

> **TL;DR:** Observability data grows faster than the systems it observes — logs/metrics/traces scale with request volume *and* instrumentation richness, so unmanaged telemetry becomes one of the largest infra line items at scale. Cardinality (the number of unique label/field combinations) is the single biggest cost and stability lever: one careless high-cardinality label can 10-100x a metrics backend's cost or crash it outright.

## Quick Reference

| Cost driver | Pillar most affected | Primary mitigation |
|---|---|---|
| Cardinality (unique label combos) | Metrics (severe), traces/logs (less, different cost model) | Bounded label sets, drop/aggregate high-cardinality dimensions |
| Ingestion volume | Logs (most volume-sensitive) | Sampling, filtering at source, log level discipline |
| Retention duration | All three | Tiered storage (hot/warm/cold), shorter default retention |
| Query/index cost | Logs (full-text index), traces (unsampled) | Label-indexed storage (Loki-style), tail-based sampling |
| Per-unit vendor pricing | All (SaaS billed per GB/per host/per span) | Usage audits, sampling, self-hosted OSS for high-volume tiers |

## What It Is

- **Cardinality** = the number of distinct time series (for metrics) or distinct field values (for logs/traces) produced by a given metric name or field. `http_requests_total{status="200"}` has low cardinality (a handful of status codes); `http_requests_total{user_id="..."}` has cardinality equal to the number of users — potentially millions.
- For **metrics** specifically, every unique label combination is a separately stored, separately indexed time series — cardinality growth is close to the worst-case cost driver in observability because it multiplies storage *and* query cost simultaneously, and can degrade query performance for *everyone* sharing that backend, not just the offending team.
- **Cost management** is the ongoing discipline of keeping telemetry volume/cardinality proportional to its actual investigative value — not an afterthought bolted on once a bill or an outage forces the issue.

## Responsibilities

- Engineers adding instrumentation own not introducing unbounded-cardinality labels (raw user IDs, raw URLs with path params, raw IPs) into metrics — this is a code-review-time responsibility, not something platform teams can fully police after the fact.
- The observability platform team owns setting and enforcing sane defaults: retention tiers, sampling rates, cardinality limits/alerts on the metrics backend itself (Prometheus/Cortex support hard cardinality limits per tenant).
- Both share ownership of periodically auditing "what are we actually querying/using" versus "what are we paying to store" — unused high-cardinality data is pure waste.

## How It Works

**Cardinality explosion, concretely**:
```
Metric: http_requests_total{service, endpoint, method, status, user_id}
  service: 50 values
  endpoint: 200 values
  method: 4 values
  status: 10 values
  user_id: 1,000,000 values
  → theoretical max unique series = 50 × 200 × 4 × 10 × 1,000,000 = 4 * 10^11

Same metric without user_id:
  → 50 × 200 × 4 × 10 = 400,000 series — six orders of magnitude smaller
```
- Removing just one unbounded label is usually the difference between "runs fine" and "crashes the metrics backend" — this is why Prometheus/Cortex/Mimir ship built-in per-tenant series limits as a safety net, not just a suggestion.

**Sampling as a volume lever** (traces, and increasingly logs):
```
Head-based: sample 1% of all traces at creation time — simple, but may miss rare
            errors (99% chance a specific rare error trace is never sampled)
Tail-based: buffer all spans for a trace, decide after seeing outcome — keep 100%
            of errors/slow traces, 1% of the rest — much better signal-to-cost ratio
```

**Tiered retention** (all pillars):
```
Hot (0-7 days):   full fidelity, fast query, most expensive per GB
Warm (7-30 days): downsampled/compacted, slower query, cheaper
Cold (30+ days):  object storage (S3), aggregate-only queries, cheapest,
                   often for compliance/trend-analysis, not incident response
```

## Types / Classifications

| Mitigation | Applies to | Trade-off |
|---|---|---|
| Label/field allowlisting | Metrics | Prevents accidental cardinality bombs, requires discipline in review |
| Recording rules (pre-aggregation) | Metrics | Cheap to query at dashboard-time, loses raw per-series detail |
| Log level discipline (prod = INFO+) | Logs | Reduces volume drastically, loses DEBUG detail unless dynamically re-enabled |
| Dynamic log level (per-request override) | Logs | Best of both — verbose only when actively debugging a specific request | 
| Sampling (head or tail) | Traces, high-volume logs | Reduces cost near-linearly, some information loss (head-based) |
| Tiered/downsampled retention | All | Matches storage cost to actual query-recency needs |
| Self-hosted OSS vs SaaS | All | Self-hosted trades ops burden for much lower marginal cost at high volume |

## Where It Fits

- This is the operational tax on everything else in this section — every file (metrics, logging, tracing, alerting, APM, synthetics) generates data whose volume/cardinality must be actively managed, or the observability system itself becomes the outage (a metrics backend falling over from cardinality explosion is a real, common incident category).
- Directly informs which **sampling strategy** (file 04) and **retention tiers** get chosen, and feeds back into whether **SLOs** (file 05) can even be computed reliably if the underlying metric was dropped/aggregated away too aggressively.
- A frequent **postmortem action item** (file 11) is "we didn't have the data to debug this fast" *or*, just as often, the opposite: "we're paying $X/month for telemetry nobody has queried in 6 months" — cost management is a recurring two-sided finding.

## Common Patterns & Real-World Tools

| Tool/Feature | Role |
|---|---|
| **Prometheus/Cortex/Mimir per-tenant series limits** | Hard cardinality caps to protect shared backend stability |
| **Grafana Loki** | Cost model built around low-cardinality *labels* + unindexed log body — directly addresses the metrics-style cardinality trap for logs |
| **OpenTelemetry Collector processors** (`filter`, `attributes`, `tail_sampling`) | Drop/rewrite high-cardinality fields, apply sampling, all at the collection layer before it hits paid storage |
| **Recording rules (Prometheus)** | Pre-compute expensive/frequent queries into new lower-cardinality series, cutting both query cost and dashboard latency |
| **Honeycomb / dynamic sampling** | Sampling that adapively keeps more of the "interesting" (error/slow/rare) events, less of the routine ones |
| **Vendor cost-monitoring dashboards** (Datadog "Usage" pages, etc.) | Track ingestion volume/cardinality per team/service to attribute cost and catch regressions |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Aggressive sampling | Large cost reduction, often 10-100x | Some fraction of real incidents' detail is lost if sampling isn't tail-based/adaptive |
| Strict label allowlisting | Prevents outages/cost blowups proactively | Adds friction/review overhead to adding new instrumentation |
| Self-hosted OSS observability stack | Much lower marginal cost at scale | Real ops burden — the team now runs and scales a critical-path distributed system |
| Managed SaaS (Datadog, etc.) | No ops burden, fast to start | Cost scales directly and often non-linearly with cardinality/volume; easy to get an unpleasant bill surprise |
| Short default retention | Keeps storage cost bounded | Loses ability to investigate slow-burn issues or do year-over-year trend analysis without extra tiering |

## Real-World Scenarios

- **Accidental cardinality bomb from a URL label**: a team adds `path` as a metric label using the raw request path instead of the route template (`/users/12345` instead of `/users/:id`) — cardinality explodes with every unique user ID that hits the endpoint, and the shared Prometheus instance's memory usage triples overnight, degrading queries for every other team on the same instance.
- **Loki adoption specifically to dodge this trap for logs**: a team migrating from Elasticsearch to Loki does so explicitly because Elastic's full-text indexing cost scaled painfully with log volume, while Loki's label-only indexing (with the same low-cardinality discipline as metrics) cut costs by an order of magnitude for the same log volume.
- **Tail-based sampling cost win**: a company moves from 10% head-based trace sampling to tail-based sampling at effectively 2% overall volume (but keeping ~100% of errors/slow traces) — total tracing cost drops 5x while incident-relevant trace availability actually improves.
- **The "nobody queried this in 6 months" audit**: a quarterly telemetry cost review finds an entire category of DEBUG-level logs, shipped and indexed at full cost for a year, that zero dashboards or saved searches reference — turning it off saves a meaningful chunk of the monthly observability bill with zero investigative capability lost.

## Nuances & Gotchas

- **Cardinality damage isn't contained to the offending team**: on a shared multi-tenant metrics backend, one team's cardinality mistake can degrade query performance or even crash the backend for every other team — this is why platform teams enforce hard per-tenant limits rather than relying on voluntary discipline alone.
- **You can't recover cardinality-dropped detail retroactively**: if a high-cardinality label was never captured (dropped at ingestion for cost reasons), no amount of clever querying later recovers it — the sampling/dropping decision has to be made with full awareness of what it forecloses for future debugging.
- **Sampling bias compounds with rare-event debugging**: uniform sampling systematically under-represents exactly the rare error cases most valuable during an incident — tail-based/adaptive sampling exists specifically because naive uniform sampling optimizes the wrong thing.
- **"Just log everything, storage is cheap" ages badly**: storage itself may be cheap, but *indexing* (Elasticsearch-style) and *query* cost scale with volume too, and most SaaS vendors bill on ingestion, not just storage — the naive "log everything" default is usually the single largest preventable observability cost.
- **Cost pressure can perversely push teams to under-instrument exactly where it matters**: fear of a big bill sometimes leads teams to skip instrumenting a genuinely important high-cardinality dimension (e.g., per-tenant metrics in a multi-tenant SaaS) — the fix is smarter aggregation/sampling for that dimension, not avoiding instrumenting it at all, since tenant-level blind spots are often exactly where the next incident hides.
- **Recording rules trade flexibility for cost**: pre-aggregating a query into a recording rule makes the dashboard cheap and fast, but if you later need to slice that data by a dimension you didn't pre-aggregate on, you're stuck re-querying the (possibly already-dropped) raw series — plan recording rules around genuinely stable, well-understood query patterns.
- **Retention policy changes need a grace period communicated broadly**: silently shortening retention from 90 to 30 days to cut cost can blindside a team mid-investigation into a 45-day-old regression — retention changes are a cross-team communication problem as much as a technical one.
