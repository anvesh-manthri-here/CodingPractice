# Publish-Subscribe and Event Streaming

> **TL;DR:** Pub/sub decouples producers from consumers via a broker; the fork in the road is queue (destructive read, one consumer per message) vs log (replayable, retained, many independent readers) — Kafka is the canonical log-based system and its partition is the true unit of parallelism, ordering, and scaling.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Queue semantics | Message deleted/invisible after ack; one consumer "wins" it (SQS, RabbitMQ) |
| Log semantics | Message retained for a window; many consumers replay independently (Kafka, Pulsar, Kinesis) |
| Ordering guarantee | Only within a partition/shard, never across the whole topic |
| Parallelism unit | Partition (Kafka/Pulsar) or shard (Kinesis) — #partitions caps consumer parallelism |
| Consumer group | Set of consumers sharing partitions, each partition owned by exactly one consumer in the group |
| Rebalancing | Reassigns partitions on join/leave; stop-the-world by default in older Kafka |
| Replication | Leader + followers (ISR = in-sync replicas); ack after `min.insync.replicas` write |
| Compaction | Keeps latest value per key forever; log grows unbounded by time, bounded by key count |
| Retention | Time- or size-based deletion (default 7 days in Kafka); independent of consumption |
| Key metric | Consumer lag = latest offset − committed offset, per partition |
| At-least-once | Commit offset **after** processing (default, safer, needs idempotency) |
| At-most-once | Commit offset **before** processing (risk of silent loss) |
| Pulsar split | Broker (stateless, serving) + BookKeeper bookies (stateful, storage) |

## What It Is

- **Pub/sub**: producers publish messages to a named channel (topic); subscribers receive them without producer knowing who's listening — decouples in time, space, and synchronization.
- **Event streaming**: pub/sub plus **durable, ordered, replayable** storage of the event history, not just in-flight delivery — the log *is* the source of truth, not a transient mailbox.
- Core distinction: **queue** = destructive read, competing consumers, message gone once consumed; **log** = append-only, retained, consumers track their own read position (offset), multiple groups replay same data independently.

## Responsibilities

- Decouple producer/consumer lifecycle, rate, and failure domains (buffer bursts, survive consumer downtime).
- Preserve ordering guarantees where defined (per-partition, not global).
- Durably persist events for replay, audit, reprocessing, and multiple downstream consumers (analytics, search index, cache, ML).
- Provide delivery semantics (at-least-once / at-most-once / effectively-once via idempotent producer + transactional consumer).
- Enable horizontal scaling of both ingestion and consumption independently.

## How It Works

```
Producer(s) --> [Partition 0 | Partition 1 | Partition 2] --> Consumer Group A (3 consumers, 1:1 with partitions)
                        (Topic)                            --> Consumer Group B (1 consumer, reads all 3)
```

- **Topic**: logical stream name, split into **partitions** — each an ordered, immutable append-only log.
- **Offset**: monotonically increasing per-partition sequence number; consumer position = last committed offset.
- **Producer** picks a partition via partition key hash (`hash(key) % numPartitions`) or round-robin if no key.
- **Consumer group**: Kafka assigns each partition to exactly one consumer within a group; multiple groups each get their own full copy of the stream (fan-out).
- **Rebalancing**: triggered by consumer join/leave/crash or partition count change; group coordinator reassigns partitions, consumers pause during it (eager) or transition incrementally (cooperative-sticky, KIP-429, minimizes stall).
- **Replication**: each partition has 1 leader + N-1 followers; leader handles all reads/writes, followers pull and ack; **ISR** = replicas caught up within `replica.lag.time.max.ms`. `acks=all` + `min.insync.replicas=2` = durability floor.
- **Log compaction**: background thread rewrites segments keeping only the latest record per key; a `null` value (**tombstone**) marks key-for-deletion, purged after `delete.retention.ms`.
- **Retention**: `retention.ms` / `retention.bytes` delete old segments regardless of whether every consumer has read them — slow consumers can lose data.

## Types / Classifications

| Model | Delivery | Replay | Ordering scope | Examples |
|---|---|---|---|---|
| Classic queue | Point-to-point, destructive | No (usually) | FIFO queues only (SQS FIFO) | RabbitMQ, SQS |
| Log/stream | Broadcast, retained | Yes, by offset/timestamp | Per partition/shard | Kafka, Pulsar, Kinesis |
| Topic-based pub/sub (managed) | Push or pull, ack-based | Limited (message retention window) | Best-effort / key-ordering key | Google Pub/Sub, NATS JetStream |
| In-memory/light log | Lightweight, TTL-based | Short window | Per stream | Redis Streams |

- **Fan-out patterns**: (1) multiple consumer groups on one topic (native log replay), (2) topic exchange fan-out to many queues (RabbitMQ), (3) Pub/Sub push subscriptions to many endpoints, (4) CDC-style single writer log feeding many materialized views.

## Where It Fits

- Sits between service boundaries as the **integration backbone**: microservice event buses, CDC pipelines (Debezium → Kafka), log aggregation, metrics pipelines, stream processing (Kafka Streams/Flink/ksqlDB) input.
- Feeds both **online** paths (notification fan-out, order state machines) and **offline** paths (data lake ingestion, analytics warehouses).
- Often paired with schema registry (Avro/Protobuf) for producer/consumer contract evolution.

## Common Patterns & Real-World Tools

| Tool | Notable trait |
|---|---|
| **Apache Kafka** | Partitioned log, ISR replication, compaction, KRaft (no ZK since 3.x/4.x default) |
| **Apache Pulsar** | Broker/bookie split — brokers stateless (serving), BookKeeper bookies own storage; enables independent scaling and fast broker failover (no data to move) |
| **AWS Kinesis** | Shards (~1MB/s in, 2MB/s out each); resharding is manual and non-trivial |
| **Google Cloud Pub/Sub** | No partitions exposed; ordering only via ordering keys; push or pull delivery, auto-scaled |
| **NATS JetStream** | Lightweight log on top of NATS core; streams + consumers, good for edge/low-latency |
| **Redis Streams** | Consumer groups (`XREADGROUP`), in-memory (persisted via AOF/RDB), simplest ops, smallest scale |
| **RabbitMQ** | Classic queue broker; exchanges (direct/topic/fanout) route to queues, destructive read |

- **Outbox pattern**: write DB change + event atomically via transactional outbox table + CDC connector, avoiding dual-write inconsistency.
- **Dead-letter topic/queue**: shunt unprocessable messages out of the main path so they don't block others.

## Pros & Cons / Trade-offs

| | Queue | Log |
|---|---|---|
| Pros | Simple competing-consumer scaling, built-in per-message ack/retry/DLQ | Replay, multiple independent consumers, audit trail, time-travel reprocessing |
| Cons | No replay, one consumer group model only | More consumer-side bookkeeping (offsets), storage cost, ordering only per-partition |
| Scaling knob | Add consumers up to queue depth (elastic) | Add consumers up to **partition count** (fixed ceiling until repartition) |
| Ops cost | Lower | Higher (replication, retention tuning, compaction, rebalancing) |

## Real-World Scenarios

- **E-commerce order events**: partition key = `order_id` → all state transitions for one order stay ordered; separate consumer groups for inventory, billing, notifications each replay independently.
- **CDC to search index**: Debezium publishes row changes keyed by primary key; compacted topic acts as a durable "latest snapshot" changelog, search indexer rebuilds by replay after outage.
- **IoT telemetry**: Kinesis/Kafka partitioned by `device_id`; skewed device (bot farm sensor spamming) creates a hot shard/partition, throttling the whole shard's throughput.
- **Payment processing**: at-least-once with idempotency key on consumer side (dedupe table) since offset commit-after-processing can redeliver on crash.

## Nuances & Gotchas

- **Hot partitions**: skewed key cardinality (e.g., one `tenant_id` = 80% of traffic) overloads one partition's leader while others idle — mitigate with salting keys, sub-keying, or Kafka's sticky/uniform-random default partitioner when key is absent.
- **Rebalance storms**: flapping consumers (slow processing → false-positive `session.timeout.ms` expiry → rejoin → rebalance → repeat) stall the whole group; tune `max.poll.interval.ms`, use cooperative-sticky assignor, or static group membership (`group.instance.id`) to avoid full reshuffle on restart.
- **Changing partition count breaks key affinity**: adding partitions changes `hash(key) % N` for every key — same key now maps to a different partition, silently breaking per-key ordering guarantees for events produced before vs after the change. Plan partition count for peak scale upfront.
- **Poison message blocks partition head**: a single malformed/unprocessable record halts consumption of that entire partition (offset can't advance) since ordering forces sequential processing — need per-message retry limits + DLQ routing, not just infinite retry.
- **Offset commit timing = delivery semantics**: commit before processing → at-most-once (crash after commit, before processing = message lost); commit after processing → at-least-once (crash after processing, before commit = reprocessed); true exactly-once needs idempotent writes or Kafka transactions (`isolation.level=read_committed`).
- **Retention vs slow consumers**: if a consumer group falls behind past `retention.ms`/`retention.bytes`, unread segments are deleted — consumer jumps ahead with silent data loss (monitor lag, alert well before retention window).
- **Tombstones and compaction surprises**: tombstones are only removed after `delete.retention.ms` AND only during compaction cycles — a slow/paused compaction thread means deleted keys resurrect in replays; also compaction only runs on closed segments, so recent writes to the active segment aren't compacted yet (log looks bigger than expected).
- **Consumer lag is the north-star metric**: measured per-partition in message count or time; sudden spike = slow consumer, GC pause, or downstream dependency stall — alert on lag growth rate, not just absolute value.
- **Backpressure**: log-based systems shift backpressure to the *consumer* (broker doesn't block producers meaningfully, just fills disk) — contrast with queue depth limits or Reactive Streams' explicit `request(n)` demand signaling; unbounded producer + slow consumer = disk pressure or retention-driven data loss, not natural throttling.
- **Pulsar's split pays off on broker failover**: since bookies own the data, a crashed broker's partitions can be served by another broker instantly (no data copy), unlike Kafka where a new leader election is fast but still bound to replicas that already have the data locally.
- **Idempotent producer ≠ exactly-once consumer**: `enable.idempotence=true` dedupes producer retries per partition, but doesn't make downstream side effects (DB write, HTTP call) exactly-once — that still needs consumer-side idempotency keys or transactional outbox.

## Self-Check

1. What caps consumer parallelism within a single consumer group, and why can't you exceed it just by adding more consumer instances?
2. A team commits offsets *before* processing to avoid duplicate work. What delivery semantic does this produce, and what's the failure scenario that causes data loss?
3. Traffic is skewed so one `tenant_id` accounts for 80% of a topic's volume. What happens at the partition level, and what are two mitigations?
4. Someone adds partitions to a topic to relieve a hot partition. Why can this silently break ordering for a given key, even though the topic still "works"?
5. A single malformed record shows up in a partition and the consumer can't process it. What happens to the rest of that partition's messages, and why does adding infinite retries not fix it?

<details><summary>Answers</summary>

1. Partition count — Kafka assigns each partition to exactly one consumer per group, so consumers beyond the partition count sit idle with nothing to read.
2. At-most-once — if the consumer crashes after the commit but before finishing processing, the message is never reprocessed and is silently lost.
3. The key's partition leader becomes a hot partition, overloading that broker while others idle; mitigate with key salting/sub-keying or letting the default partitioner spread unkeyed traffic evenly.
4. Adding partitions changes `hash(key) % N` for every key, so the same key can map to a different partition after the change — events produced before vs. after the resize land in different partitions, breaking per-key ordering.
5. Consumption of that entire partition halts because ordering forces sequential processing and the offset can't advance past the bad record; infinite retries just loop forever on the same message instead of unblocking it — you need per-message retry limits plus DLQ routing.
</details>

---
**Related:** [Message Queues](07-message-queues.md) · [Search Engines and the Inverted Index](12-search-engines-inverted-index.md) · [Serialization Formats](../01-fundamentals/12-serialization-formats-json-protobuf-avro-thrift.md)

*Last reviewed: 2026-08*
