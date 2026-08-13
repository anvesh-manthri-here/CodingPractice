# Latency, Throughput, and Bandwidth

> **TL;DR:** Latency is time-per-request, throughput is requests-per-second, bandwidth is the channel's max capacity — they interrelate through concurrency (Little's Law) and queueing, and averages lie because tail latency is what users actually feel.

## Quick Reference

| Concept | Definition | Unit | Key formula |
|---|---|---|---|
| Latency | Time for one request to complete | ms/µs | p50, p99, p99.9 |
| Throughput | Requests processed per unit time | req/s (QPS/RPS) | = Concurrency / Latency |
| Bandwidth | Max data volume per unit time | Mbps/Gbps | ceiling on throughput |
| Little's Law | Concurrency in system | `L = λ × W` | arrival rate × latency |
| Utilization | Fraction of capacity used | ρ = λ/µ (0-1) | latency → ∞ as ρ → 1 |
| Coordinated omission | Measurement bias undercounting tail | — | fix: fixed-rate sampling |

## What It Is

- **Latency**: elapsed time for a single unit of work — network RTT + queueing + processing + serialization. Measured per-request, reported as a distribution, not a scalar.
- **Throughput**: aggregate rate of completed work — the system-level output. Bounded above by `1/service_time` per worker × number of workers (parallelism).
- **Bandwidth**: the physical/logical ceiling on data transfer rate (e.g., 10 Gbps NIC, 1 Gbps link). Bandwidth constrains throughput but doesn't equal it — protocol overhead, packet loss, and window sizes eat into effective throughput.
- These are independent axes: high bandwidth doesn't guarantee low latency (satellite links: high bandwidth, ~600ms RTT), and low latency doesn't guarantee high throughput (fast single-threaded DB, no parallelism).

## Responsibilities

Understanding this triad lets you:
- Size capacity (how many servers/threads to hit a QPS target at acceptable latency).
- Diagnose whether a slowdown is compute-bound, network-bound, or queueing-induced.
- Set SLOs that reflect user experience (percentiles), not misleading averages.
- Design fan-out/fan-in systems (search, microservices) without tail amplification killing p99.

## How It Works

**Little's Law**: `L = λ × W`
- L = average number of requests in the system (concurrency)
- λ = arrival rate (throughput, req/s)
- W = average time in system (latency)
- Rearranged: `Throughput = Concurrency / Latency`. To 2x throughput at fixed latency, you need 2x concurrency (more threads/connections/instances).
- Practical use: if you know your connection pool size (L) and average latency (W), you can compute max sustainable throughput (λ) — and size pools correctly (e.g., DB pool sizing formula, HikariCP).

**The utilization-vs-latency knee (queueing theory)**:
- Model service as M/M/1 or M/M/c queue. Mean wait time ∝ `ρ / (1 - ρ)` where ρ = utilization.
- At ρ = 50%, wait is small. At ρ = 80%, wait roughly 4x baseline. At ρ = 90%, ~9x. At ρ = 95%+, latency explodes — the "knee" in the curve.
- Implication: **never run production services near 100% CPU/utilization**. Target 60-70% steady-state to leave headroom for the queueing curve and traffic spikes.
- This is why autoscalers trigger at 60-70% CPU, not 95%.

```
latency
  |                                     |
  |                                    /
  |                                  /
  |                             ___/
  |___________________________/
  +------------------------------------ utilization
  0%          60%        80%   95%   100%  (the knee)
```

## Types / Classifications

**Latency percentiles** — why averages lie:
| Percentile | Meaning | Typical use |
|---|---|---|
| p50 (median) | Half of requests faster than this | "typical" experience |
| p95 | 1 in 20 requests slower | dashboards, alerting |
| p99 | 1 in 100 requests slower | SLOs for high-traffic services |
| p99.9 | 1 in 1000 requests slower | matters at scale (1M req/day = 1000 bad requests) |
| avg (mean) | Skewed by outliers | rarely representative — a single 10s outlier among 1000 10ms requests pulls avg to 19.9ms, hiding nothing but also revealing nothing about typical UX |

- Distributions are right-skewed (long tail from GC pauses, lock contention, cache misses, network retransmits) — mean sits below p90 typically, masking the pain most-affected users feel.
- Rule of thumb: at scale, "rare" tail events become routine — 1 request in a million at 1M QPS = one bad experience per second.

**Bandwidth types**: link bandwidth (physical, e.g. 25 Gbps NIC) vs. effective/goodput (after TCP overhead, retransmits, TLS framing — often 80-95% of link speed) vs. application-level throughput (further reduced by serialization, business logic).

## Where It Fits

- **Client → CDN → LB → App → Cache → DB**: each hop adds latency (serialization + network + queueing) and has its own throughput ceiling; bandwidth matters most on WAN/mobile hops and bulk transfer paths (backups, replication).
- **Capacity planning**: throughput targets (QPS) drive instance counts via Little's Law; latency SLOs drive timeout/circuit-breaker configuration; bandwidth sizing drives NIC/link selection and CDN offload decisions.
- **Load balancing**: least-connections/least-latency algorithms lean directly on these metrics to route around slow backends before the knee hits.

## Common Patterns & Real-World Tools

- **Load testing tail-aware**: `wrk2`, `hey`, `k6` with open-loop (constant arrival rate) load generation to avoid coordinated omission (see below); vs. closed-loop `ab`/`JMeter` default mode which under-measures tail latency.
- **Percentile tracking**: HDRHistogram (High Dynamic Range Histogram) — used in `wrk2`, Cassandra, Kafka client metrics — for accurate, memory-efficient percentile computation without losing tail resolution.
- **Latency budgets**: Google SRE practice — allocate a fixed ms budget across a call chain (e.g., 200ms total budget → auth 10ms, cache lookup 5ms, DB 50ms, downstream service 100ms, buffer 35ms); each hop gets a deadline propagated via context (gRPC deadlines, `context.Context` in Go).
- **Bandwidth optimization**: HTTP/2 multiplexing, gRPC + protobuf (compact wire format), compression (gzip/brotli/zstd), CDN edge caching to cut WAN bandwidth use.
- **Head-of-line blocking mitigations**: HTTP/2 stream multiplexing over one TCP connection still HOL-blocks at the TCP layer on packet loss; HTTP/3/QUIC uses independent streams over UDP to eliminate transport-level HOL blocking.
- **Fan-out mitigation**: hedged requests (send duplicate request after p95 wait, take first response — used by Google's "Tail at Scale" paper), request cancellation on first-N-of-M response, backup requests in gRPC.

## Pros & Cons / Trade-offs

| Approach | Benefit | Cost |
|---|---|---|
| Increase concurrency (more threads/connections) | Higher throughput (Little's Law) | More context switching, memory; latency may rise near knee |
| Lower utilization target (60-70%) | Predictable latency, headroom for spikes | Lower resource efficiency, higher $ cost |
| Hedged/backup requests | Cuts tail latency significantly | 1.05-2x more backend load |
| Batching (higher throughput per call) | Better amortized throughput, bandwidth efficiency | Adds latency per item (must wait for batch to fill) |
| Aggressive caching | Cuts both latency and backend throughput demand | Staleness, cache invalidation complexity |

## Real-World Scenarios

- **Search fan-out** (Elasticsearch/web search): query hits 100 shards in parallel; overall latency = **max** of all shard latencies, not average. If each shard has p99 = 50ms independently, and you fan out to 100 shards, probability *all* respond under 50ms drops sharply — this is **tail latency amplification**: `P(all N fast) = P(one fast)^N`. At N=100 and p99=1% slow-per-shard, ~63% of *queries* hit at least one slow shard.
- **Database connection pool sizing**: using Little's Law, if avg query latency W=10ms and you need throughput λ=5000 qps, you need L = 50 concurrent connections minimum — undersizing causes queueing (the knee), oversizing wastes DB resources/context-switch overhead (see HikariCP's "pool sizing" formula: `connections = cores × 2 + effective_spindle_count`, empirical not just Little's Law).
- **CDN vs. origin bandwidth**: video streaming origin has fixed bandwidth (e.g., 10 Gbps); serving all viewers directly saturates it fast — CDN edge caching offloads 90%+ of bandwidth demand, letting origin bandwidth be sized for cache-miss traffic only.

## Nuances & Gotchas

- **Coordinated omission**: closed-loop load testers (send next request only after prior response) systematically *undercount* tail latency — if the system stalls for 1s, the tester just sends fewer requests during the stall instead of recording that stall against many "missed" requests. Fix: use open-loop/constant-throughput generators (`wrk2`, `k6` with `constant-arrival-rate` executor) that track intended vs. actual request times.
- **Averages hide bimodal distributions**: a cache with 90% hit rate (1ms) and 10% miss rate (200ms) has avg ≈ 20.9ms — looks fine, but p95+ users are all hitting the miss path. Always look at the histogram shape, not just percentile numbers.
- **Head-of-line blocking** isn't just TCP: a single slow query holding a DB connection blocks all queued requests behind it in a connection pool; a single slow Kafka partition consumer blocks that partition's downstream ordering guarantee even if other partitions are healthy.
- **Percentile math doesn't compose linearly**: p99 of (A then B in sequence) ≠ p99(A) + p99(B) — actual value is typically lower because it's rare for both to be slow simultaneously, but *fan-out* p99 (parallel calls, wait for all) is **worse** than any individual p99, not better — don't naively add or average percentiles.
- **Utilization near 100% is not "efficient," it's dangerous**: it looks great on a cost dashboard right up until a traffic blip pushes ρ past the knee and latency goes vertical — this is a classic root cause in postmortems ("CPU was only at 92%, we didn't think it was the issue").
- **Bandwidth ≠ throughput ≠ goodput**: a "10 Gbps link" rarely delivers 10 Gbps of application throughput once you subtract TCP/IP headers (~5%), TLS overhead, retransmits under loss, and small-message overhead (many small requests waste bandwidth on per-packet headers vs. batched large payloads).
- **Latency budget violations cascade**: if one hop blows its budget, downstream hops either exceed the total deadline (client times out, wasting all upstream work) or must be cancelled — deadline propagation (gRPC context deadlines, `Timeout` headers) must be end-to-end or you get "zombie work" continuing after the client gave up.
- **Little's Law assumes steady state**: it breaks down under bursty/transient traffic (flash sale, retry storms) — instantaneous L can spike far above the steady-state average, which is exactly when queueing/knee effects bite hardest.

## Self-Check

1. A DB connection pool has 50 connections and average query latency is 10ms. Using Little's Law, what's the max sustainable throughput, and what happens if incoming load exceeds it?
2. Why does closed-loop load testing (e.g., default `ab`/JMeter) systematically undercount tail latency, and what's the fix?
3. A search query fans out to 100 shards in parallel, each with p99 = 50ms (1% slow). Why is the overall query's tail latency worse than any individual shard's p99, and what's the rough probability at least one shard is slow?
4. A dashboard shows CPU at 92% and average latency looks fine — why is a postmortem likely to name this as a root cause anyway?
5. A cache has 90% hit rate at 1ms and 10% miss rate at 200ms. What's the approximate average latency, and why is that average misleading?

<details><summary>Answers</summary>

1. λ = L/W = 50/0.01 = 5000 qps max. Beyond that, requests queue for a free connection, and per Little's Law/M-M-c queueing, wait time grows sharply (the knee) rather than throughput exceeding 5000 qps.
2. It sends the next request only after the prior response, so during a stall it just sends fewer requests instead of recording the stall against many missed requests — this hides exactly the tail events it should be measuring. Fix: open-loop/constant-arrival-rate generators (`wrk2`, `k6`) that track intended vs. actual send times.
3. Overall latency is the max of all shard latencies, and `P(all N fast) = P(one fast)^N`, so probabilities compound: at N=100 and 1% slow-per-shard, P(all fast) = 0.99^100 ≈ 37%, meaning ~63% of queries hit at least one slow shard.
4. Latency vs. utilization is nonlinear (ρ/(1-ρ)) — 92% is already past the knee where small traffic blips cause latency to go vertical, even though the CPU number alone looks tolerable on a dashboard.
5. Avg ≈ 0.9(1ms) + 0.1(200ms) = 20.9ms. It looks fine in isolation, but it's bimodal — 10% of users (the miss path) are actually experiencing ~200ms, not something near the average; the average hides who is in pain.
</details>

---
**Related:** [Scalability](01-scalability-vertical-vs-horizontal.md) · [Napkin Math](08-napkin-math-numbers-every-engineer-should-know.md) · [Load Balancers](../02-core-components/01-load-balancers.md)

*Last reviewed: 2026-08*
