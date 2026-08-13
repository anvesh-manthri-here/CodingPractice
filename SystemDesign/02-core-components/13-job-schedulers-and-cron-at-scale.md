# Job Schedulers and Cron at Scale

> **TL;DR:** A crontab on one box is a SPOF with no retries, no visibility, and overlap risk; at scale you replace it with leader-elected or queue-based distributed schedulers, timer-wheel/delayed-queue engines for millions of future events, and idempotent, DAG-aware orchestration.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Single-box cron | SPOF, no retry, no dedup, no metrics, silent failure |
| Exactly-once triggering | Impossible in distributed systems — design for at-least-once + idempotency |
| Leader election | ZooKeeper/etcd/Consul lock; only leader fires jobs |
| Queue-based scheduling | Scheduler enqueues; workers pull; naturally HA & retryable |
| Timer wheel | O(1) insert/tick, buckets by delay, used in Kafka/Netty/Linux kernel timers |
| Delayed queue | Redis ZSET score=trigger time; poller does `ZRANGEBYSCORE now` |
| DAG orchestration | Airflow, Temporal, Dagster — dependencies between tasks |
| Simple periodic | k8s CronJob, Quartz, Celery Beat, EventBridge Scheduler |
| Concurrency policy | Allow / Forbid / Replace (k8s CronJob terms) |
| Backfill | Re-run missed intervals for a historical range, `catchup=True/False` in Airflow |
| DST gotcha | Local-time schedules skip or double-fire during clock change |
| Dead-man's switch | Alert fires if job did NOT check in by expected time |

## What It Is

- The subsystem that fires work at a specific time, on a recurring schedule, or after a delay — at fleet scale, not one host.
- Spans two axes: **when** (cron expression, interval, one-shot delay) and **what** (single task vs multi-step DAG).
- Distinct from a message queue: queues react to events; schedulers *manufacture* events from time.

## Responsibilities

- Compute next-fire time from a schedule spec (cron expr, rrule, interval).
- Guarantee (at-least-once) delivery of the trigger even across node failure.
- Prevent duplicate/overlapping execution of the same job instance.
- Track job state: scheduled, running, succeeded, failed, retrying, skipped.
- Surface visibility: last run, next run, duration, failure alerts.
- Support backfill/catch-up and manual re-trigger.

## How It Works

**Single-box cron (why it fails):**
- `cron` daemon reads `/etc/crontab`, forks a process at match time. If the box dies, reboots, or is mid-deploy, the trigger is silently lost — no retry, no record.
- Two jobs scheduled to overlap (e.g., a 10-min job on a 5-min cadence) pile up processes with shared resource contention.
- No built-in distributed lock, no metrics/alerting, no audit trail of what ran.

**Leader-election approach:**
- N scheduler replicas race for a lock (etcd lease, ZK ephemeral node, Redis `SET NX PX`). Only the leader evaluates schedules and fires.
- On leader crash, lease expires (~5-15s typically) and a follower takes over — bounded gap, not zero.
- Simple mental model, but leader is a bottleneck for very high job counts and failover causes a blip.

**Queue-based approach:**
- A lightweight "trigger service" only decides *when*; it pushes a message to a durable queue (SQS, Kafka, Redis Streams) instead of executing directly.
- Stateless worker pool consumes and executes; queue provides retry, dedup (via message ID), backpressure, and horizontal scaling for free.
- Decouples scheduling cadence from execution capacity — preferred pattern at scale (used by EventBridge Scheduler → Lambda/SQS, Celery Beat → broker → workers).

**Exactly-once is impossible:**
- Network partition between trigger-decision and execution-confirmation means you can never be 100% sure a fire didn't happen twice (or zero times) without infinite wait.
- Practical answer: at-least-once delivery + idempotent job logic (dedup key, upsert instead of insert, conditional writes, idempotency token per scheduled interval).

**Timer wheel (millions of future events):**
- Circular array of buckets, each representing a time slot (e.g., 1s granularity); a pointer advances per tick, executing/enqueuing whatever is in that bucket. O(1) insert, O(1) per-tick execution amortized.
- Hierarchical wheels (like Linux kernel timers, Kafka's `DelayQueue` + wheel, Netty `HashedWheelTimer`) handle far-future events by cascading from coarse to fine wheels as time approaches.
- Far cheaper than a sorted heap of millions of timers (`O(1)` vs `O(log n)` per op).

**Delayed queue (Redis ZSET pattern):**
- `ZADD delayed_jobs <trigger_epoch> <job_id>`; a poller loop runs `ZRANGEBYSCORE delayed_jobs -inf now`, atomically pops due items (Lua script for atomicity), pushes to an execution queue.
- Simple, durable if Redis persistence/replication is on; scales to millions of members; polling interval trades latency vs load.

```
producer --ZADD score=fireAt--> [Redis ZSET]
                                     |
                      poller: ZRANGEBYSCORE now  (every N ms)
                                     v
                          execution queue --> workers
```

## Types / Classifications

| Type | Description | Example |
|---|---|---|
| Fixed cron | `min hr dom mon dow` recurring | k8s CronJob, Quartz `CronTrigger` |
| Fixed interval | Every N seconds/minutes, no calendar semantics | Celery Beat `timedelta` schedule |
| One-shot delayed | Fire once at T+delay | SQS delay queue, EventBridge one-time schedule |
| DAG / workflow | Ordered tasks with dependencies, branching, retries per node | Airflow, Dagster, Temporal Workflows |
| Durable-execution | Code-as-workflow with automatic replay/state recovery | Temporal, AWS Step Functions |

## Where It Fits

- Sits between application code and either a queue/broker or a compute target (Lambda, container, HTTP endpoint).
- Upstream of ETL pipelines, report generation, cache warms, TTL cleanups, retry sweepers, SLA-timeout watchers.
- In microservices, often a shared platform service (not per-team crontabs) so retries/observability/alerting are centralized.
- DAG orchestrators sit above per-task schedulers — they call into k8s, Spark, dbt, etc. as execution engines.

## Common Patterns & Real-World Tools

| Tool | Model | Notes |
|---|---|---|
| Kubernetes CronJob | Leader = control plane; API object | `concurrencyPolicy`, `startingDeadlineSeconds`, controller misses fire if `>100` missed schedules backlog |
| Apache Airflow | DAG scheduler + executor pool | `schedule_interval`, `catchup`, Celery/Kubernetes executor, DAG runs keyed by logical date |
| Temporal | Durable execution, workflow-as-code | Automatic retry/backoff, replay from event history, built-in cron workflows |
| Quartz (Java) | In-JVM or clustered via DB lock table | `JDBCJobStore` uses row-lock for cluster coordination |
| Celery Beat | Single scheduler process → broker → workers | Beat itself is a SPOF unless run with `django-celery-beat` DB lock or leader election |
| AWS EventBridge Scheduler | Managed, serverless, per-schedule targets | Up to millions of schedules, built-in retry/DLQ, no infra to run |
| Redis sorted-set delayed queue | DIY building block | Pattern above; needs Sentinel/Cluster for HA |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Single-box cron | Trivial to set up | SPOF, no retry, no visibility, overlap risk |
| Leader election | Simple execution model, strong ordering | Leader is throughput ceiling, failover gap |
| Queue-based | Scales horizontally, retry/backpressure free | More moving parts, eventual consistency in scheduling |
| DAG orchestrator | Dependency graphs, backfills, lineage | Heavier ops burden, scheduler latency (Airflow scheduler loop ~seconds) |
| Managed scheduler (EventBridge) | Zero ops, scales to millions | Vendor lock-in, less control over execution semantics |

## Real-World Scenarios

- **Nightly billing job** duplicated by a k8s CronJob during a slow pod termination → `concurrencyPolicy: Forbid` prevents overlap; idempotent upsert prevents double-charging if it still slips through.
- **Airflow backfill**: onboarding a new metric requires computing 2 years of daily partitions — `airflow dags backfill -s 2024-01-01 -e 2026-08-13` replays historic logical dates instead of writing custom scripts.
- **EventBridge Scheduler** firing 5M per-customer trial-expiration reminders — infeasible with a single crontab process; managed timer-wheel-backed service handles it natively.
- **Temporal** for a multi-day order fulfillment saga: workflow survives process crashes/deploys because state is reconstructed from event history, not held in memory.
- **Redis ZSET** used as a lightweight "retry-after" mechanism for a webhook delivery system — cheaper than standing up Airflow for a single delayed-retry use case.

## Nuances & Gotchas

- **DST double/skipped fire**: a job scheduled for local 2:30 AM either runs twice (fall-back) or never (spring-forward) unless the scheduler is UTC-anchored; Airflow/Quartz support `timezone=` but still warn about this — prefer scheduling in UTC when semantics allow.
- **Thundering herd at :00**: every cron using `0 * * * *` fires simultaneously across thousands of tenants/services, spiking downstream DBs/APIs; mitigate with jitter (`sleep random(0,60)`), staggered per-tenant offsets, or scheduler-side rate limiting.
- **Long-running job overlaps next trigger**: a 12-minute job on a 10-minute cadence causes concurrent runs unless `concurrencyPolicy: Forbid`/`Replace` (k8s) or a distributed lock (`SETNX` per job-run key) enforces mutual exclusion.
- **Missed runs during deploys**: rolling deploy of the scheduler pod can skip a tick; k8s CronJob has `startingDeadlineSeconds` to decide whether a late-fired job still counts as "on time" or is dropped.
- **Clock skew**: nodes with unsynced NTP can double-fire or drift trigger windows; always run chrony/NTP and treat >1s skew as an incident-worthy alert for time-sensitive schedulers.
- **Unbounded retry on permanently failing job**: a bad deploy makes every run fail; without exponential backoff + max-retry cap + circuit breaker, the queue/backlog grows unbounded and can DoS the executor pool — always pair retries with a DLQ.
- **No dead-man's-switch**: a job that silently stops firing (misconfigured cron expr, deleted CronJob, crashed Beat process) produces *no* error — only absence of a heartbeat. Solve with an external watchdog (Healthchecks.io-style "ping on success, alert if no ping within window") rather than relying on the scheduler's own error channel.
- **Idempotency is mandatory, not optional**: because exactly-once is unattainable, every job handler must tolerate replay — use dedup keys, `INSERT ... ON CONFLICT`, idempotency tokens keyed by scheduled logical time, not wall-clock execution time.
- **Backfill vs catch-up semantics differ**: Airflow `catchup=True` auto-runs every missed interval since `start_date` (can explode into thousands of runs if misconfigured); k8s CronJob has no catch-up concept by default — missed windows are just gone.
- **Logical time vs wall-clock time**: DAG frameworks key runs by "logical/execution date" (the interval being processed), which can differ from actual run wall-clock time — a frequent source of off-by-one confusion in Airflow (`execution_date` is the *start* of the interval, not when it ran).

## Self-Check

1. Why is exactly-once triggering fundamentally impossible in a distributed scheduler, and what does that force every job handler to do?
2. How does a timer wheel achieve O(1) insert/tick for millions of pending events where a sorted heap costs O(log n) per operation?
3. A job is scheduled for local time 2:30 AM. What goes wrong during a DST transition, and how do you avoid it?
4. Why does a cron expression like `0 * * * *` running across thousands of tenants create a thundering herd, and what mitigates it?
5. Why won't a scheduler's own error/alerting channel catch a job that silently stopped firing altogether, and what mechanism actually catches it?

<details><summary>Answers</summary>

1. A network partition between the trigger-decision step and the execution-confirmation step means the scheduler can never be 100% certain a fire happened exactly once without waiting forever, so distributed schedulers only guarantee at-least-once delivery. Every job handler must therefore be idempotent — dedup keys, `INSERT ... ON CONFLICT`, or idempotency tokens keyed by scheduled logical time — so a replayed trigger doesn't double-execute.
2. A timer wheel is a circular array of time-slot buckets that a pointer advances per tick, so inserting an event is just placing it in the right bucket (O(1)) and firing is just draining whatever bucket the pointer lands on (O(1) amortized). A sorted heap has to maintain full ordering across all n timers, costing O(log n) per insert/extract, which doesn't scale the same way at millions of entries.
3. During fall-back the 2:30 AM slot occurs twice, so the job fires twice; during spring-forward the clock jumps past 2:30 AM, so it never fires. The fix is to anchor schedules in UTC rather than local time, since Airflow/Quartz support `timezone=` but still warn this ambiguity exists.
4. Every tenant/service using the same top-of-hour expression fires simultaneously, spiking downstream DBs/APIs all at once. Mitigate with jitter (random sleep), staggered per-tenant offsets, or scheduler-side rate limiting.
5. A job that never fires produces no error event at all — there's nothing to catch, only an absence of a heartbeat, so the scheduler's own error channel has nothing to alert on. The fix is an external dead-man's-switch/watchdog (e.g., Healthchecks.io-style ping-on-success) that alerts if no ping arrives within the expected window.
</details>

---
**Related:** [Message Queues](07-message-queues.md) · [Publish-Subscribe and Event Streaming](08-publish-subscribe-and-event-streaming.md) · [Rate Limiting and Throttling](09-rate-limiting-and-throttling.md)

*Last reviewed: 2026-08*
