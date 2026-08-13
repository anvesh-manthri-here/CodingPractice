# Structured Logging and Log Aggregation

> **TL;DR:** Emit logs as structured key-value records (JSON), not free-text sentences, so they're machine-parseable at query time — then ship them off-host through an aggregation pipeline (agent → buffer → indexer) so they survive the instance dying and are searchable across the whole fleet.

## Quick Reference

| Aspect | Detail |
|---|---|
| Format | JSON lines (most common), logfmt (key=value), Protobuf (high-throughput internal) |
| Required fields | timestamp (ISO8601/UTC), level, service, trace_id, message, + context fields |
| Shipping agent | Fluentd/Fluent Bit, Filebeat, Vector, Logstash, Promtail |
| Pipeline shape | App → local agent → buffer/queue (Kafka) → indexer/storage → query UI |
| Storage/query | Elasticsearch/OpenSearch (full-text), Loki (label-indexed, log content unindexed), ClickHouse |
| Retention | Hot (fast query, days) → warm → cold/archive (S3, cheap, slow) tiering |
| Log levels | TRACE < DEBUG < INFO < WARN < ERROR < FATAL |

## What It Is

- **Structured logging**: every log line is a record with named fields (`{"level":"error","user_id":123,"latency_ms":450,"msg":"payment failed"}`) instead of an interpolated string (`"payment failed for user 123 after 450ms"`).
- **Log aggregation**: the infrastructure that collects logs from every host/container/pod, ships them centrally, indexes them, and makes them searchable — because logs written to local disk are useless once the instance is gone (autoscaling, spot termination, container restart).

## Responsibilities

- Structured logging must: use consistent field names across services (a shared logging library/schema), avoid logging PII/secrets in plaintext, include correlation IDs (trace_id/request_id) on every line, and keep messages queryable without regex gymnastics.
- The aggregation pipeline must: tail logs reliably even if the app crashes mid-write, buffer against backend outages without losing data or blocking the app, parse/enrich (add host/pod metadata), and route to the right index/retention tier.

## How It Works

```
App writes JSON line to stdout/file
        │
   Local agent (Fluent Bit / Filebeat) tails it
        │  parses, adds k8s metadata (pod, namespace)
        ▼
   Buffer (local disk queue or Kafka topic)
        │  decouples producer rate from indexer rate
        ▼
   Aggregator/processor (Logstash / Vector) — filter, enrich, redact
        ▼
   Storage + index (Elasticsearch / Loki / ClickHouse)
        │
        ▼
   Query UI (Kibana / Grafana) — search, alert, dashboard
```

- Twelve-Factor App principle: apps should write logs to **stdout/stderr unbuffered**, not manage log files themselves — the execution environment (container runtime, orchestrator) is responsible for capturing and routing that stream.
- **Push vs pull**: most log shipping is push (agent tails and forwards); metrics are typically pull (Prometheus scrapes) — this is a key operational difference between the two pillars.
- Sidecar vs. daemonset collection in Kubernetes: a **daemonset agent** (one per node, reads all pod logs via the container runtime) is more resource-efficient than a **sidecar** (one log-shipping container per pod) but has less per-pod customization.

## Types / Classifications

| Log type | Purpose | Retention pattern |
|---|---|---|
| Application logs | Business logic events, errors | Days–weeks hot, longer cold |
| Access/request logs | Every HTTP request in/out (often via LB/proxy) | Short hot retention, high volume |
| Audit logs | Security-relevant actions (who did what) | Long retention (compliance: 1–7 years), often write-once storage |
| Debug/trace-level logs | Verbose diagnostic detail | Usually disabled in prod, enabled dynamically per-request |
| System/infra logs | Kernel, container runtime, orchestrator events | Short retention, mainly for infra debugging |

## Where It Fits

- Sits alongside metrics/traces as one of the three pillars (file 01); the aggregation pipeline is the "operations" layer that makes logs from an ephemeral, horizontally-scaled fleet actually usable.
- Upstream of **alerting** (file 07) when alerts are log-pattern-based (e.g., "alert if ERROR rate in these logs exceeds X/min") rather than metric-based.
- Downstream of **structured error handling** in application code — logging quality is bounded by whether the app captures the right context (user_id, request_id, stack trace) at the point of failure.

## Common Patterns & Real-World Tools

| Tool | Role | Notes |
|---|---|---|
| **ELK/Elastic Stack** (Elasticsearch, Logstash, Kibana) | Full stack | Full-text indexing of every field is powerful but expensive at high volume |
| **Grafana Loki** | Storage + query | Indexes only labels (service, level), not log body — much cheaper at scale, "like Prometheus but for logs" |
| **Fluentd / Fluent Bit** | Shipping agent | CNCF graduated; Fluent Bit is the lightweight C rewrite for resource-constrained/edge collection |
| **Vector** | Shipping/processing agent | Rust-based, high throughput, increasingly replacing Logstash |
| **Datadog Logs / Splunk** | Managed SaaS full pipeline | No infra to run, but expensive at scale (often billed per GB ingested) |
| **CloudWatch Logs** | AWS-native | Simple integration with Lambda/ECS/EC2, weaker query ergonomics than Elastic/Loki |

## Pros & Cons / Trade-offs

| Choice | Pros | Cons |
|---|---|---|
| JSON structured logs | Machine-parseable, queryable by field, easy to pipe to any backend | Slightly more verbose, less human-friendly to `tail -f` raw |
| Free-text logs | Human-readable at a glance | Requires regex/grok parsing downstream, brittle to format changes, hard to aggregate |
| Full-text index (Elastic) | Search any field, any term, fast | Expensive: indexing cost scales with log volume and cardinality |
| Label-indexed (Loki) | Cheap at scale (only labels indexed) | Slower for "search everything for this string" queries across unindexed body |
| Centralized aggregation | Survives instance death, fleet-wide search | Another critical-path service; buffer/backpressure design needed so a log outage doesn't take down the app |

## Real-World Scenarios

- **Autoscaling group churn**: an instance handling a bad request scales down 30 seconds later — without shipped-off-host logs, that request's log lines are gone forever; this is why "SSH into the box and `tail`" doesn't work at scale.
- **PII leak via logs**: a stack trace inadvertently logs a full credit card number from an exception message — structured logging with an explicit redaction/allowlist step in the pipeline (Logstash filter, Vector transform) catches this before it's indexed and retained for years.
- **Kafka as log buffer**: LinkedIn/Uber-scale pipelines put Kafka between the shipping agent and the indexer so a slow/down Elasticsearch cluster doesn't cause backpressure all the way to application hosts — the buffer absorbs the mismatch.
- **Kibana query during incident**: on-call filters `level:error AND service:checkout AND trace_id:abc123` to jump straight from a trace ID (found via APM) to the exact log lines for that failing request, across however many pods handled parts of it.

## Nuances & Gotchas

- **Logging is not free**: high-volume DEBUG logging in a hot path can itself become the bottleneck (I/O, serialization cost) — sample or rate-limit verbose logs, don't log in tight loops.
- **Unbounded field cardinality in structured logs is fine** (unlike metrics) — but only if the *storage* is cardinality-tolerant (Elastic) or label-indexed correctly (Loki labels must stay low-cardinality even though log *content* can be high-cardinality).
- **Log levels drift over time**: teams that never revisit log levels end up with ERROR-level noise for expected conditions (cache miss logged as ERROR) — this trains on-call to ignore errors, which is how real incidents get missed.
- **Multi-line stack traces break naive line-based shippers**: a Python/Java stack trace spans many lines but is one logical event — agents need multi-line parsing configured (regex start pattern) or it gets split into fragments that don't correlate.
- **Clock/timestamp source matters**: logging client-side wall-clock time instead of using a monotonic/NTP-disciplined source can produce out-of-order logs in aggregation, confusing incident timelines.
- **Cost is usually billed by ingested volume**, not stored volume, for SaaS log platforms — a noisy DEBUG log left on in production is a direct line item, not just a performance concern; sampling high-volume, low-value logs (e.g., health-check hits) is a common cost lever.
- **GDPR/compliance right-to-be-forgotten**: PII embedded in structured log fields makes deletion-on-request hard if logs are append-only/immutable storage — design log schemas to reference user IDs, not embed deletable PII directly, wherever possible.
