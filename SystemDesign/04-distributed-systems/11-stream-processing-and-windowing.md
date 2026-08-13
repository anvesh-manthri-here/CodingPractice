# Stream Processing and Windowing

> **TL;DR:** Stream processing continuously computes over unbounded, out-of-order event data using event-time semantics, windowing, and watermarks to get correct results despite network/clock skew — batch is just a special case (bounded stream).

## Quick Reference

| Concept | Key Mechanism | Example Engine |
|---|---|---|
| Unbounded processing | Continuous operators, no "end of data" | Flink, Kafka Streams |
| Event-time correctness | Timestamps embedded in events | Flink watermarks |
| Late data handling | Watermarks + allowed lateness | Flink, Beam |
| Tumbling window | Fixed, non-overlapping | 1-min traffic counts |
| Sliding window | Fixed size, overlapping, slide interval | 5-min avg every 1 min |
| Session window | Gap-based, dynamic size | User activity sessions |
| Exactly-once | Checkpoint barriers + 2PC sink | Flink, Kafka Streams (EOS v2) |
| Micro-batch model | Small batch intervals simulate streaming | Spark Structured Streaming |
| SQL-on-stream | Continuous queries over topics | ksqlDB |

## What It Is

- **Stream processing**: computation over data that arrives continuously and never "completes" — the pipeline runs indefinitely, emitting incremental results.
- Contrasts with **batch processing**: bounded input, job runs to completion, single final output (e.g., a nightly Spark job over yesterday's Parquet files).
- Core insight (Kappa architecture / Beam model): batch is a special case of streaming where the stream has a known end — one engine, one API, can handle both.
- Windowing is the mechanism that makes unbounded aggregation tractable: you can't "GROUP BY user_id and SUM forever," so you bucket by time into finite windows.

## Responsibilities

- Ingest unbounded, high-throughput event streams (Kafka topics, Kinesis streams) with low latency (sub-second to seconds).
- Assign events to time windows and trigger computation when a window is "complete enough."
- Reconcile **event-time** (when it happened) vs **processing-time** (when the engine saw it) — networks delay, retry, and reorder events.
- Guarantee correctness under failure: exactly-once or at-least-once semantics for stateful aggregations (counts, joins, sums).
- Handle unbounded state growth (windows, joins) via TTLs, watermark-based cleanup, and state backends (RocksDB).

## How It Works

**Event-time vs processing-time**
- *Event-time*: timestamp embedded in the record payload (e.g., mobile client's local clock when a tap occurred).
- *Processing-time*: wall-clock time of the machine executing the operator.
- Why it matters: a mobile app offline for 10 minutes sends a batch of events on reconnect — processing-time windowing dumps them all into "now," event-time windowing correctly places each in its original window. Processing-time is simpler/faster but non-deterministic and non-reproducible on replay; event-time gives correct, reproducible results but requires handling lateness.

**Watermarks**
- A watermark `W(t)` is an assertion: "no more events with event-time < t will arrive" (heuristic, not a hard guarantee).
- Generated from observed event timestamps minus a slack/bound (e.g., `max_event_time_seen - 5s`) or from punctuation in the source.
- When watermark passes a window's end, the window is considered "closed" and fires its result.
- Late events (event-time < current watermark) arriving after firing are handled via **allowed lateness** (keep window open N extra minutes, emit updates) or routed to a side output / dead-letter for manual handling.

```
event-time axis:  ---1---2---4---3---5--->  (3 arrives late, after 4)
watermark:              W=2   W=4  (late "3" triggers late-firing or side output)
```

## Types / Classifications

**Windowing strategies**

| Type | Definition | Use Case |
|---|---|---|
| Tumbling | Fixed-size, contiguous, non-overlapping (e.g., every 1 min) | Per-minute request counts, billing intervals |
| Sliding (hopping) | Fixed size, overlapping, defined slide < size | Rolling 5-min average, updated every 30s |
| Session | Dynamic size, closes after inactivity gap (e.g., 30 min idle) | User session analytics, clickstream grouping |
| Global | One window for entire stream, custom trigger | Custom triggers, count-based aggregation |

**Time semantics**
- Event-time processing (correct, replay-safe)
- Processing-time processing (fast, simple, non-deterministic)
- Ingestion-time (compromise: timestamp assigned at source connector, avoids client clock skew)

**Delivery guarantees**
- At-most-once (fire and forget)
- At-least-once (retry until ack, may duplicate)
- Exactly-once (dedup + atomic commit — the hard one)

## Where It Fits

```
Producers → Kafka/Kinesis (durable log, partitioned) 
    → Stream Processor (Flink/Kafka Streams/Spark) 
        → stateful windowed aggregation 
    → Sink (another Kafka topic, DB, dashboard, alert system)
```

- Sits between the event log (Kafka) and serving layer — often part of a **Lambda** (batch + speed layer) or **Kappa** (streaming-only, replay from log for reprocessing) architecture.
- Feeds real-time dashboards, fraud detection, materialized views (CQRS read models), alerting, feature pipelines for ML.
- Upstream of it: CDC pipelines (Debezium) turning DB changes into a stream. Downstream: OLAP stores (Druid, ClickHouse) or caches (Redis) for low-latency reads.

## Common Patterns & Real-World Tools

| Tool | Model | Notes |
|---|---|---|
| **Apache Flink** | True streaming, event-at-a-time | Best event-time/watermark support, exactly-once via distributed snapshots (Chandy-Lamport checkpoints) |
| **Kafka Streams** | True streaming, library (no cluster) | Embedded in your app JVM, uses Kafka itself for state changelog + EOS transactions |
| **Spark Structured Streaming** | Micro-batch (or continuous mode, limited) | Reuses Spark SQL engine/catalyst optimizer; batch interval trades latency for throughput |
| **ksqlDB** | SQL over Kafka Streams | Declarative `CREATE TABLE ... WINDOW TUMBLING (SIZE 1 MINUTE)`; good for ops teams without JVM code |
| **Apache Beam** | Unified batch/stream API | Portable across Flink/Spark/Dataflow runners; defines the windowing/trigger/watermark model most engines borrow from |

**Pattern: Windowed aggregation** — `stream.keyBy(userId).window(TumblingEventTimeWindows.of(Time.minutes(1))).sum("amount")`.
**Pattern: Stream-table join** — enrich clickstream with a KTable of user profiles (Kafka Streams) for stateful lookups without external DB calls.
**Pattern: Dedup via idempotent sink** — write with a deterministic key (event-id) to Postgres upsert or Kafka transactional producer to survive retries.

## Pros & Cons / Trade-offs

| Aspect | Streaming | Batch |
|---|---|---|
| Latency | Seconds or sub-second | Minutes to hours |
| Correctness with late data | Complex (watermarks, triggers) | Trivial (all data present) |
| Resource usage | Always-on cluster cost | Bursty, can scale to zero |
| Reprocessing/backfill | Harder (needs replay from log) | Natural (rerun on full dataset) |
| Exactly-once cost | Checkpoint overhead, added latency | N/A (idempotent by nature of full rerun) |
| Operational complexity | High (state backends, backpressure, watermark tuning) | Lower |

- Micro-batch (Spark) trades a few hundred ms–seconds of latency for simpler fault tolerance and reuse of batch optimizations — fine for most dashboards, not fine for sub-100ms fraud blocking.
- True streaming (Flink) gives lowest latency and best event-time correctness but demands more careful capacity planning (state size, checkpoint duration) to avoid backpressure collapse.

## Real-World Scenarios

- **Fraud detection**: Flink CEP (complex event processing) pattern-matches sequences (e.g., login from country A then purchase from country B within 5 min) using event-time to avoid false positives from network delay.
- **Ad billing / impressions**: tumbling 1-hour windows aggregate impression counts; must be exactly-once because double-counting = overbilling advertisers — Flink checkpointing + transactional Kafka sink.
- **IoT sensor monitoring**: sliding windows compute rolling averages (5-min window, 10s slide) for anomaly detection on device telemetry; watermarks tolerate sensors with intermittent connectivity.
- **E-commerce cart abandonment**: session windows (30-min inactivity gap) in ksqlDB group clickstream events per user to trigger "abandoned cart" emails.
- **Real-time leaderboard**: Kafka Streams KTable materializes running scores keyed by player, exposed via interactive queries for low-latency reads without a separate DB round-trip.

## Nuances & Gotchas

- **Watermarks are heuristics, not guarantees** — an aggressive watermark (small slack) gives low latency but drops/late-routes more legitimate late data; a lax watermark increases correctness but adds end-to-end latency and state retention. Tune per SLA, not defaults.
- **Unbounded state growth is the #1 production killer** — session windows or joins without TTL/watermark-triggered cleanup silently grow RocksDB state until checkpoints take minutes and the job falls over. Always set idle-state retention (Kafka Streams `retention`, Flink `State TTL`).
- **Exactly-once ≠ end-to-end unless the sink cooperates** — Flink's checkpointing gives exactly-once *within* the pipeline via barrier alignment and 2PC, but if the sink isn't transactional (e.g., a plain REST call) you get at-least-once in practice; pair with idempotent writes.
- **Checkpoint barrier alignment causes backpressure stalls** — under skewed load, slow operators delay barriers, stalling the whole pipeline; Flink's unaligned checkpoints (1.11+) mitigate this by letting barriers overtake buffered records.
- **Clock skew across producers breaks event-time assumptions** — a misconfigured client clock 2 hours ahead poisons watermark advancement for the whole partition; clamp/validate timestamps at ingestion (bounded-out-of-orderness extractor).
- **Reprocessing/replay changes results silently** — replaying from Kafka with a different watermark/lateness config produces different aggregates than the original run; version and pin your windowing config alongside code for audit trails.
- **Micro-batch "exactly-once" in Spark relies on idempotent/transactional sinks + WAL** — the guarantee is "effectively-once," contingent on sink support (e.g., foreachBatch with idempotent upserts); naive sinks (plain file append) will duplicate on retry.
- **Session windows with no upper bound are a DoS vector** — a bot pinging every 29 minutes (just under the 30-min gap) keeps one session window open indefinitely, accumulating unbounded state; cap max session duration explicitly.
- **Out-of-order != late** — an event can be out-of-order (arrives after a later event-time event) but still on-time (before its window's watermark closes); don't conflate the two when debugging "why did this get dropped."
