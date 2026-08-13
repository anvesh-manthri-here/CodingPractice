# Message Queues

> **TL;DR:** A message queue decouples producers from consumers with an async buffer, giving load leveling, retry, and failure isolation — but it forces you to choose delivery semantics (almost always at-least-once) and to trade ordering for throughput.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Default delivery guarantee | At-least-once (dedup + idempotency = "effective exactly-once") |
| SQS visibility timeout | Default 30s, max 12h; must exceed p99 processing time |
| SQS FIFO throughput | 300 msg/s (3000 batched) per message group; standard SQS: nearly unlimited |
| RabbitMQ ack modes | auto-ack, manual ack/nack, `requeue` flag |
| DLQ trigger | `maxReceiveCount` (SQS) / `x-death` count (RabbitMQ) exceeded |
| Ordering unit | Message group (SQS FIFO), routing key + single consumer (RabbitMQ) |
| Key backlog metrics | Queue depth, **oldest message age**, consumer lag, DLQ depth |
| Delay/scheduled msg | SQS delay queue (max 15 min), RabbitMQ delayed-message plugin, Beanstalkd `delay` |
| Priority support | Beanstalkd (native), RabbitMQ (priority queue, 0-255 levels), SQS (none — simulate w/ multiple queues) |

## What It Is

- A **broker-mediated buffer**: producer writes a message, broker stores it durably, consumer pulls (or gets pushed) and acknowledges.
- Point-to-point semantics by default — one message is (logically) consumed by one worker, unlike pub/sub fan-out (see `08-publish-subscribe-and-event-streaming.md`).
- Core value: **temporal decoupling** — producer and consumer don't need to be up at the same time.

## Responsibilities

- **Decoupling**: producer/consumer scale, deploy, and fail independently.
- **Load leveling**: absorb bursty producer traffic, let consumers drain at sustainable rate (peak shaving).
- **Buffering/backpressure**: queue depth becomes the shock absorber instead of consumer OOMs or producer 503s.
- **Retry & failure isolation**: failed messages redeliver instead of being lost; poison messages get quarantined via DLQ.
- **Async work offload**: move slow/non-critical-path work (email send, thumbnail generation) out of the request path.

## How It Works

```
Producer --enqueue--> [ Queue: durable log/store ] --deliver--> Consumer
                                                         |
                                              ack (delete) | nack/timeout (requeue)
```

1. Producer publishes; broker persists (disk/replicated) before ack'ing producer.
2. Consumer receives message; it becomes **invisible** to other consumers for a **visibility timeout** window (SQS) or is held unacked (RabbitMQ).
3. Consumer processes, then **acks** (delete) or **nacks** (explicit reject) or lets the timeout expire (implicit failure).
4. On failure/timeout, message becomes visible again → redelivered → potential **duplicate delivery**.
5. **In-flight limit**: broker caps concurrently-leased-but-unacked messages (SQS: 120k in flight per standard queue) to bound consumer concurrency and memory.

## Types / Classifications

- **Standard vs. FIFO** — standard: at-least-once, best-effort ordering, unlimited throughput; FIFO: exactly-once-ish (dedup window) + strict per-group order, throughput-capped.
- **Push vs. pull** — RabbitMQ pushes to subscribed consumers; SQS is pull (long-polling) only.
- **Priority queues** — multiple priority levels so urgent messages jump the line (Beanstalkd native, RabbitMQ via `x-max-priority`).
- **Delay queues** — message invisible until a future time (scheduled jobs, backoff-based retry).
- **Dead-letter queues (DLQ)** — sink for messages exceeding max receive/retry count; enables **redrive** (replay from DLQ after fixing root cause).
- **Work queue vs. request-reply** — most queues are fire-and-forget; RPC-over-queue uses a `reply-to` + correlation ID (RabbitMQ direct-reply-to).

## Where It Fits

- Sits between API/service layer and background workers, or between microservices for async command handoff.
- Common position: web tier → **queue** → worker fleet → DB/downstream API.
- Complements, doesn't replace, a message bus/event log — queues model **tasks to be done once**; logs (Kafka) model **events to be replayed by many**. See `08-publish-subscribe-and-event-streaming.md` for fan-out/streaming contrast.
- Often paired with autoscaling: consumer fleet scales on queue depth or oldest-message-age metric.

## Common Patterns & Real-World Tools

| Tool | Notes |
|---|---|
| **RabbitMQ** | AMQP broker; exchanges (direct/topic/fanout) route to queues; strong ack/nack + priority + delayed-message plugin; clustering + quorum queues for HA. |
| **Amazon SQS** | Managed, standard (at-least-once, high throughput) or FIFO (ordered, dedup via `MessageDeduplicationId`); visibility timeout + redrive policy built in. |
| **ActiveMQ / Artemis** | JMS-based, supports queues + topics, transactions, XA; common in Java/enterprise stacks. |
| **Redis Streams** | Consumer groups (`XREADGROUP`), `XACK`, `XPENDING` for in-flight tracking; low-latency, in-memory (persistence via AOF/RDB), good for lightweight task queues. |
| **Beanstalkd** | Simple, fast, native priority + delay + TTR (time-to-run); minimal feature set, no clustering out of the box. |
| **Kafka (contrast)** | Log-based, not a queue: consumers track offsets, messages aren't deleted on read, supports replay and massive fan-out — use when many independent consumer groups need the same event stream. |

**Patterns**: retry with exponential backoff via delay queue; circuit breaker + DLQ for poison messages; competing consumers for horizontal scale; outbox pattern (DB txn + queue publish) for exactly-once-ish producer semantics.

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Decouples producer/consumer lifecycles | Added operational component (broker HA, monitoring) |
| Smooths traffic spikes, protects downstream | Extra latency vs. direct call (ms-seconds) |
| Built-in retry/backoff/DLQ | At-least-once means consumers must be idempotent |
| Horizontal scale via competing consumers | Scaling consumers destroys global ordering |
| Survives consumer outages (durability) | Unbounded retries can amplify an outage (retry storm) |

## Real-World Scenarios

- **Order processing**: checkout API enqueues `OrderPlaced`; inventory, payment, and email workers each pull from their own queue — a payment provider outage doesn't block checkout.
- **Image/video transcoding**: upload triggers enqueue; worker fleet autoscales on SQS `ApproximateNumberOfMessagesVisible`.
- **Rate-limited third-party API calls**: queue + delay-based backoff throttles outbound calls to a partner API with a strict quota.
- **SQS FIFO for financial ledger events**: message group = account ID, guarantees per-account event order while allowing parallelism across accounts.

## Nuances & Gotchas

- **True exactly-once delivery is impossible** in a distributed system (two-generals problem) — brokers advertise "exactly-once" only within a dedup window (SQS FIFO: 5 min) or via idempotent consumer design. Real answer: at-least-once delivery + **idempotency key** + dedup store on the consumer side.
- **Visibility timeout shorter than processing time = guaranteed duplicate work**: message reappears mid-processing, a second consumer picks it up, both finish → double side effects. Always set timeout > p99 processing time, or heartbeat/extend it (`ChangeMessageVisibility`).
- **Poison messages loop forever** without a DLQ + max-receive-count: one malformed message can pin a worker in a crash-retry loop, starving the queue.
- **Unbounded retry amplifies outages**: naive immediate-retry-on-failure during a downstream outage multiplies load exactly when the dependency is weakest — use exponential backoff + jitter + circuit breaker, not tight retry loops.
- **Queue depth is a lagging indicator**: a queue can be "empty" while still failing SLAs if consumers are slow-draining old messages; **oldest-message age** (SQS `ApproximateAgeOfOldestMessage`) is the better alerting signal.
- **Ordering evaporates the moment you add consumers**: a single queue with N parallel consumers delivers no global order guarantee — FIFO queues/message groups only preserve order *within* a group, and a group is inherently single-consumer-at-a-time (throughput ceiling).
- **Ack-before-process vs. process-before-ack**: auto-ack (RabbitMQ) or early ack risks message loss on crash; ack-after-process risks duplicate redelivery on crash — pick per durability/duplication trade-off you can tolerate.
- **Redrive is not automatic recovery**: moving messages from DLQ back to the main queue after a fix requires manual/scripted intervention (SQS `StartMessageMoveTask`) — decide who owns that runbook before the incident.
- **Batching hides partial failures**: SQS `SendMessageBatch`/`DeleteMessageBatch` can partially succeed — always check per-message results, don't assume all-or-nothing.

## Self-Check

1. Why is true exactly-once delivery impossible in a distributed queue, and what's the real-world substitute?
2. A worker takes 45s to process a message but the visibility timeout is set to 30s. What happens, and how do you fix it without just guessing a bigger number?
3. Your SQS queue depth reads near-zero but downstream SLAs are being missed. What metric should you actually be alerting on instead, and why does queue depth mislead here?
4. You scale a standard queue's consumer fleet from 1 to 10 workers to improve throughput. What guarantee do you lose, and how does SQS FIFO's message-group model contain the damage?
5. One malformed message keeps crashing your worker on every redelivery. What mechanism prevents it from starving the whole queue, and what config value controls when it kicks in?

<details><summary>Answers</summary>

1. It's the two-generals problem — a distributed system can't atomically confirm both delivery and processing across a network. Brokers only offer "exactly-once" via a dedup window (e.g., SQS FIFO's 5-min window); the real substitute is at-least-once delivery plus an idempotency key and dedup store on the consumer.
2. The message becomes visible again mid-processing, a second consumer picks it up, and both finish — duplicate side effects. Fix by setting the timeout above measured p99 processing time, or by heartbeating/extending it via `ChangeMessageVisibility` rather than picking a bigger static number.
3. Alert on oldest-message age (SQS `ApproximateAgeOfOldestMessage`), not queue depth — a queue can look empty while consumers slow-drain old messages, so depth is a lagging indicator that hides SLA-breaking staleness.
4. You lose global ordering — N parallel consumers on one queue give no cross-message order guarantee. FIFO message groups contain this by preserving order only within a group, and each group is inherently single-consumer-at-a-time, trading throughput for that guarantee.
5. A dead-letter queue combined with a max-receive-count check (SQS `maxReceiveCount`, RabbitMQ `x-death` count) quarantines the poison message after it exceeds that threshold, freeing the worker instead of looping forever.
</details>

---
**Related:** [Publish-Subscribe and Event Streaming](08-publish-subscribe-and-event-streaming.md) · [Job Schedulers and Cron at Scale](13-job-schedulers-and-cron-at-scale.md) · [Rate Limiting and Throttling](09-rate-limiting-and-throttling.md)

*Last reviewed: 2026-08*
