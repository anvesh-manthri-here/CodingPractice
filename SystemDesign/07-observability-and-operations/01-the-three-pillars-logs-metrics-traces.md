# The Three Pillars: Logs, Metrics, Traces

> **TL;DR:** Logs tell you *what happened* in detail for one event, metrics tell you *how the system is behaving* in aggregate over time, and traces tell you *where time went* for one request across services. Observability is using all three together to answer questions you didn't predict in advance — monitoring is just watching known failure modes.

## Quick Reference

| Pillar | Answers | Shape | Cardinality | Cost driver |
|---|---|---|---|---|
| Logs | What exactly happened at this point in time? | Unstructured/structured text events | Very high (any field) | Storage volume, ingestion |
| Metrics | How is the system trending? Is it healthy right now? | Numeric time series + labels | Low-medium (label combinations) | Cardinality × retention |
| Traces | Where did this one request spend its time, across which services? | Tree of timed spans with context | High (per-request) | Sampling rate × span count |
| Events (4th pillar, emerging) | Wide structured record combining fields of all three per request | Single wide row per unit of work | High | Storage + query engine |

## What It Is

- **Monitoring** answers questions you thought to ask in advance (dashboards, known alerts) — it tells you *that* something is wrong.
- **Observability** is the property of a system that lets you answer questions you *didn't* anticipate, by exploring high-cardinality, high-dimensionality telemetry after the fact — it tells you *why*.
- The three pillars are the traditional data types used to achieve observability; none alone is sufficient, and there's real redundancy/overlap by design — you cross-reference them during an investigation.

## Responsibilities

Each pillar has a distinct job so instrumentation doesn't have to make everything do everything:
- **Logs**: capture discrete, timestamped facts — a specific error, a specific decision branch, a specific payload.
- **Metrics**: capture aggregate, cheap-to-store numeric health signals sampled/summed over time windows, suitable for alerting and dashboards.
- **Traces**: capture causal/temporal structure of a single unit of work as it crosses process and network boundaries.

## How It Works

```
Request hits Service A → Service B → Service C
        │                   │             │
   trace span A        trace span B   trace span C   ← one trace, 3 spans, causal tree
        │                   │             │
   log lines emitted   log lines emitted  log lines    ← many discrete facts per span
        │                   │             │
  request_count++      request_count++  request_count++  ← counters bumped, aggregated later
  latency_histogram    latency_histogram latency_histogram
```

- Typical investigation flow: an alert fires from a **metric** (p99 latency breached SLO) → you find the **trace** for a slow request in that window to see which span/service is slow → you pull the **logs** for that specific span/request ID to see the exact error or query that caused it.
- The link between pillars is **correlation IDs**: a `trace_id`/`span_id` embedded in every log line and propagated through headers lets you pivot from a metric spike to a specific trace to the exact logs for that trace.
- Metrics are the cheapest to store long-term (pre-aggregated), traces are the most expensive per-event (so usually sampled), logs sit in between (usually filtered/sampled at high volume, kept raw at low volume).

## Types / Classifications

| Pillar | Sub-type | Example |
|---|---|---|
| Logs | Unstructured | Free-text `printf`-style lines — hard to query |
| Logs | Structured | JSON/key-value with consistent fields — queryable, aggregable |
| Logs | Audit logs | Who did what, when — compliance-focused, append-only |
| Metrics | Counter | Monotonically increasing (requests served) |
| Metrics | Gauge | Point-in-time value that can go up/down (queue depth) |
| Metrics | Histogram/Summary | Distribution of values (latency buckets, percentiles) |
| Traces | Distributed trace | Spans across services for one logical request |
| Traces | Profiling trace | Spans within one process (function-level timing) |

## Where It Fits

- Sits above raw infrastructure signals (CPU, memory, disk from node exporters) and below business-level dashboards/alerting.
- **Client → LB → Service mesh → Services → DB**: each hop can emit a span (trace), bump counters (metrics), and write structured events (logs); the mesh/sidecar often auto-instruments this without app code changes.
- Ties directly into **circuit breakers**, **health checks**, and **rate limiting** (Section 06) — those components' state transitions are exactly the kind of event that should be a metric *and* a log line.
- Feeds **SLIs/SLOs** and **alerting** (this section, files 05 and 07) — metrics are the primary input; traces/logs are the debugging follow-through after an alert.

## Common Patterns & Real-World Tools

| Pillar | Open standard | Common backends |
|---|---|---|
| Logs | — (no single standard; JSON conventions vary) | ELK/Elastic, Loki + Grafana, Splunk, Datadog Logs, CloudWatch Logs |
| Metrics | OpenMetrics / Prometheus exposition format | Prometheus, Datadog, CloudWatch Metrics, InfluxDB, VictoriaMetrics |
| Traces | OpenTelemetry (OTel) traces, W3C Trace Context | Jaeger, Zipkin, Tempo, Datadog APM, AWS X-Ray, Honeycomb |
| Unified | OpenTelemetry (all three pillars via one SDK/Collector) | Vendor-agnostic export to any of the above |

- **OpenTelemetry** is the dominant modern approach: a single vendor-neutral SDK and Collector that instruments logs, metrics, and traces together and exports to any backend, replacing older siloed agents (StatsD, older APM SDKs).

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Logs-only | Simple, ubiquitous, no new infra | Expensive to query at scale; no causal structure across services; easy to over-log and drown signal |
| Metrics-only | Cheap, great for alerting/dashboards, low cardinality | Can't answer "why did *this specific* request fail" — only aggregate trends |
| Traces-only | Best for latency debugging and service dependency mapping | Expensive if unsampled; doesn't capture business-logic detail well |
| All three (correlated) | Full investigative loop: detect → localize → root-cause | Most instrumentation and infra cost; requires consistent correlation IDs everywhere |

## Real-World Scenarios

- **p99 latency alert fires** (metric) → on-call opens the trace waterfall for a slow request in that time window → sees span for `checkout-service → inventory-service` taking 4s → pulls logs filtered by that trace_id → finds a specific DB query timing out due to a missing index.
- **Silent data corruption bug**: metrics show nothing wrong (requests succeed, latency normal) — only structured logs with the actual payload reveal a field was silently defaulted to null, something no metric or trace would surface.
- **Google/Twitter-style scale**: traces are sampled at 0.1–1% of traffic (full tracing would be cost-prohibitive), but 100% of requests still get metrics counted, and error-path requests are often force-sampled at 100% regardless of the global rate ("tail-based sampling").
- **Honeycomb's "wide events" pitch**: instead of three separate pipelines, emit one wide structured event per request containing what would've been log fields, metric-worthy timings, and trace context together — argues the 3-pillar split is itself a historical/tooling artifact, not a fundamental requirement.

## Nuances & Gotchas

- **Monitoring vs observability isn't just semantics**: a system can have dashboards for every known failure mode and still be unobservable if you can't ask an ad hoc question ("show me all requests from tenant X that touched shard 7 and took >2s") without shipping new instrumentation first.
- **Cardinality explosion is the universal trap**: adding `user_id` as a metric label turns a cheap counter into millions of unique time series — this belongs in logs/traces (high cardinality is fine there), not metrics (see file 12).
- **Correlation IDs must be propagated, not regenerated**: if a service starts a *new* trace_id instead of continuing the parent's, you lose the causal chain — this is the most common instrumentation bug in polyfilled/legacy services.
- **Sampling bias**: uniform random trace sampling under-represents rare slow/error requests — tail-based sampling (decide after seeing the full trace) captures the interesting 1% without the cost of tracing 100%.
- **Logs as a crutch for missing metrics**: teams that skip metrics and `grep` logs for counts don't scale — log-derived counting is orders of magnitude more expensive than a pre-aggregated counter.
- **Clock skew ruins trace waterfalls**: spans from different hosts with unsynchronized clocks (NTP drift) can show impossible orderings (child span starting before parent) — NTP/PTP discipline is a prerequisite for trusting trace timing.
- **Don't conflate "observability" with "a vendor bill"**: buying Datadog/New Relic doesn't make a system observable if instrumentation is sparse or inconsistent — the tooling is necessary but not sufficient; the instrumentation discipline is the actual work.
