# Napkin Math — Numbers Every Engineer Should Know

> **TL;DR:** Memorize orders of magnitude, not exact digits — NVMe and 25-100GbE NICs have shifted the classic 2010 "latency numbers every programmer should know" by 10-1000x in places. Derive throughput/cost from first principles (bandwidth × utilization, IOPS × queue depth) rather than recalling a table.

## Quick Reference

| Operation | Classic (2012, Jeff Dean) | Modern (2024-2026) | Delta |
|---|---|---|---|
| L1 cache ref | 0.5 ns | 0.5-1 ns | ~same |
| L2 cache ref | 7 ns | 3-5 ns | slightly better |
| Mutex lock/unlock | 25 ns | 15-25 ns (uncontended) | ~same |
| Main memory ref (DRAM) | 100 ns | 50-100 ns (DDR5 ~70ns) | ~same |
| Compress 1KB (Snappy/LZ4) | 3,000 ns | 300-500 ns (LZ4), zstd similar | **6-10x faster** |
| Send 1KB over 1Gbps net | 10,000 ns (10 μs) | ~0.1 μs wire time @ 100GbE (syscall/driver overhead dominates at this size) | wire time 100x faster |
| Send 1MB over network | *(not in original table)* — 8 ms @ 1Gbps | ~80 μs @ 100Gbps NIC | **100x faster (NIC upgrade)** |
| SSD random read | 150,000 ns (150 μs) | **NVMe: 10-50 μs**; enterprise SATA SSD ~100 μs | **3-15x faster** |
| Read 1MB sequential from memory | 250,000 ns (250 μs) | ~15-30 μs (DDR5 ~40GB/s+) | **8-15x faster** |
| Round trip same datacenter | 500,000 ns (500 μs) | **50-500 μs** (modern DC fabric, RDMA <10 μs) | varies widely |
| Read 1MB sequential from SSD | 1,000,000 ns (1 ms) | NVMe: **~25-100 μs** (GB/s+ sequential) | **10-40x faster** |
| Disk seek (spinning) | 10,000,000 ns (10 ms) | still ~4-10 ms (HDDs unchanged) | unchanged — HDDs are legacy now |
| Read 1MB from disk (HDD) | 20,000,000 ns (20 ms) | ~15-20 ms unchanged | unchanged |
| Send packet CA→Netherlands→CA | 150,000,000 ns (150 ms) | **~120-150 ms** (speed of light bound) | unchanged (physics) |

**Biggest 2010→2026 shifts:** SSD access latency (HDD→SATA SSD→NVMe: ~1000x), NIC bandwidth (1Gbps→100Gbps: 100x), core counts (4→64+ per socket), compression speed (LZ4/zstd vs zlib).

## What It Is

Napkin math (a.k.a. back-of-envelope estimation) is the skill of deriving order-of-magnitude answers to "will this design work / how many servers / how much will it cost" using a small set of memorized constants and simple arithmetic — no benchmarking, no profiler. Used in system design interviews and real capacity planning to catch architectures that are wrong by 10-1000x before writing code.

## Responsibilities

- Sanity-check a design's feasibility (latency budget, storage footprint, server count) in minutes.
- Catch order-of-magnitude errors (e.g., "can one Postgres handle 1M writes/sec?" → no, obviously).
- Set defensible SLAs and capacity plans before load-testing exists.
- Communicate trade-offs quantitatively in design reviews ("cross-region sync adds 150ms — unacceptable for this SLA").

## How It Works

1. **Pick the dominant cost.** In most systems it's network RTT or disk I/O, not CPU — compute is usually free by comparison.
2. **Convert everything to the same unit** (ns, or requests/sec) before comparing.
3. **Multiply, don't add precision.** Round to 1 significant figure; powers of 10 matter, the "3" vs "5" doesn't.
4. **Apply utilization derating.** Real systems run at 30-70% of theoretical max (queueing, GC, contention, tail latency) — never plan at 100% of a peak spec.
5. **Cross-check with a second method.** E.g., derive requests/sec both from "QPS × payload size = bandwidth" and independently from "cores × requests-per-core" — they should agree within an order of magnitude.

## Types / Classifications

### Throughput ceilings (single unit, realistic sustained numbers)

| Subsystem | Ceiling (rule of thumb) | Notes |
|---|---|---|
| 1GbE NIC | ~120 MB/s (~1 Gbps) | rarely used now for servers |
| 10GbE NIC | ~1.2 GB/s | common baseline |
| 25/40GbE NIC | ~3-5 GB/s | modern cloud instance default |
| 100GbE NIC | ~12 GB/s | high-end cloud (AWS/GCP large instances) |
| NVMe SSD (single device) | 2-7 GB/s sequential, 0.5-1M IOPS (4KB random) | PCIe4 x4 typical |
| SATA SSD | ~500-550 MB/s, ~90K IOPS | legacy |
| HDD | ~150-250 MB/s sequential, ~100-200 IOPS random | archival only |
| Single CPU core | ~1-3 GB/s memcpy; ~1-10K "business logic" req/s | depends heavily on work per request |
| Single Postgres node | ~5K-20K simple TPS (write), ~50K+ read QPS w/ cache | disk-bound on writes, WAL fsync is the ceiling |
| Single Redis node | ~100K-1M ops/sec (single-threaded core) | network I/O usually the real ceiling, not CPU |
| Single Kafka broker | ~10-50 MB/s per partition write; **~600MB/s-1GB/s aggregate/broker** | scales via partition count, not per-partition speed |
| Single gRPC/HTTP service (JVM/Go) | ~5K-50K req/s per core for lightweight handlers | I/O-bound work is 10-100x lower |

### Cost ceilings (rough, cloud list-price order of magnitude, 2025-26)

| Resource | Cost | Notes |
|---|---|---|
| Object storage (S3 Standard) | ~$0.02-0.023/GB-month | + egress ~$0.05-0.09/GB |
| Block storage (EBS gp3 / persistent SSD) | ~$0.08-0.10/GB-month | |
| Managed Postgres/MySQL storage | ~$0.10-0.25/GB-month | includes replication overhead |
| DRAM (cloud instance-hour equiv.) | ~$3-6/GB-month | 50-100x pricier than disk |
| Egress bandwidth | ~$0.05-0.12/GB | dominant line item at scale; intra-region often free |
| Compute, generic API request | ~$0.05-$0.50 per **million** simple requests (compute only, serverless) | Lambda/Cloud Run tier |
| LLM inference request (mid-size model) | ~$1-$20 per million requests | wildly workload-dependent (token count) |
| Managed Kafka/Kinesis | ~$0.50-$2 per **million** messages (small payload) | plus per-hour broker/shard cost |

## Where It Fits

Applied earliest in the design lifecycle — before architecture is finalized — to prune obviously infeasible options: capacity planning, SLA-setting, interview whiteboard estimates, incident postmortems ("could 10K RPS have saturated this NIC? yes"), and cost forecasting for a new feature.

## Common Patterns & Real-World Tools

| Pattern | Purpose | Tools |
|---|---|---|
| Rule of thumb tables | Fast lookup during design | Jeff Dean's original list (dated), `colin-scott.github.io/personal_website/research/interactive_latency.html` (updated interactive version) |
| Load testing to validate estimate | Confirm napkin math against reality | `wrk`, `k6`, `locust`, `pgbench` |
| Capacity planning spreadsheets | Formalize the derivation | back-of-envelope calculators, internal wikis |
| Little's Law | Convert latency+concurrency↔throughput | `L = λ × W` (concurrency = arrival rate × latency) |
| Universal Scalability Law | Model why throughput saturates before linear | used to explain Postgres/Kafka multi-node ceilings |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Napkin math only | Fast, cheap, catches gross errors | Off by 2-5x on real workloads (cache effects, contention) |
| Full load test | Accurate, catches tail latency & GC pauses | Expensive, slow, needs realistic data/traffic shape |
| Vendor benchmark numbers | Convenient, often accurate for the *tool* | Rarely reflects *your* schema/query mix/network topology |

## Real-World Scenarios

**1. "Can a single Postgres primary handle our write load?"**
Target: 50K orders/day, each order = 3 row writes, peak = 5x average over 1 hour.
- Avg: 50,000×3 / 86,400s ≈ 1.7 writes/sec — trivial.
- Peak: (50,000×3×5) / 3,600s ≈ 208 writes/sec.
- Single Postgres node ceiling ~5-20K TPS (simple writes, SSD-backed WAL) → **208 TPS is <2% of ceiling, single node is fine**, no need for sharding. The real risk is fsync latency (~1-5ms per commit) capping *serial* single-row-per-transaction chains, not raw throughput — batch writes if using an ORM that commits per-row.

**2. "Will cross-region replication blow our 200ms p99 write SLA?"**
Sync-replicating writes from us-east-1 (N. Virginia) to eu-west-1 (Ireland), ~5,500 km great-circle. Theoretical one-way in fiber ≈ 5,500 km ÷ 200,000 km/s ≈ **28 ms**, so theoretical RTT ≈ 56 ms; measured RTT is **~70-80 ms** (routing/fiber path is ~1.3-1.5x the straight line). A synchronous write (leader→replica ack) costs **at least 1 full RTT ≈ 70-80ms**, plus local fsync (~1-5ms) and serialization (~1ms) → **~80-90ms minimum, consuming ~45% of the 200ms budget** before touching app logic or queueing under load. Conclusion: sync cross-region replication is marginal — prefer async replication + regional read replicas, or budget the SLA up to 300-400ms.

## Nuances & Gotchas

- **The classic table's network row is about 1 *KB*, not 1 MB** — "Send 1K bytes over 1 Gbps network = 10,000 ns" is correct (1 KB ÷ 125 MB/s ≈ 8 µs). People routinely misremember it as 1 MB and then propagate a 1000x error. Never quote a network number from memory; derive it: `time = size ÷ bandwidth`.
- **NVMe queue depth matters more than raw IOPS spec**: a drive rated for 1M IOPS needs QD=32-128 to hit that; at QD=1 (typical single-threaded random read) expect only ~10-20K IOPS, i.e., latency ~50-100μs, not the marketing number.
- **"Same-DC RTT" varies 50x** depending on hop count: same-rack (<50μs), same-AZ (~200-500μs), cross-AZ same-region (~1-2ms). Don't treat "the datacenter" as one number.
- **DRAM bandwidth is not infinite**: DDR5 dual-channel ~40-80GB/s aggregate — a single core memcpy'ing gets nowhere near that (~10-20GB/s) due to per-core memory controller limits; multi-threaded aggregate throughput is what saturates the bus.
- **Compression is a latency/CPU trade, not free**: zstd level 3 ≈ LZ4 speed with better ratio; zstd level 19 can be 50-100x slower than level 1 — "we use zstd" says nothing about the actual cost without the level.
- **Network egress, not compute, dominates cloud bills** at scale — a service moving 1PB/month egress pays ~$50-90K/month just in bandwidth, often exceeding compute cost; always model egress explicitly.
- **Little's Law catches a common estimation error**: if p99 latency is 200ms and you need 10K concurrent in-flight requests, required throughput ≈ 10,000/0.2s = 50K req/s — teams often estimate throughput and latency independently and get inconsistent numbers.
- **Tail latency ≠ average latency, and napkin math defaults to average**: a p50 of 5ms with p99 of 200ms means SLA-relevant capacity planning must derate for the tail — use p99/p999 in budgets, not the friendly average from a table.
- **Speed of light is the one number that hasn't changed and never will**: ~200,000 km/s in fiber → theoretical min cross-continent (NY-London, ~5,600km) ≈ 28ms one-way; observed is 70-90ms due to routing — this floor is a permanent design constraint, no hardware generation fixes it.
- **Single-threaded Redis means CPU napkin math is deceptive**: "100K ops/sec" per core is right, but a multi-core box doesn't scale that linearly without clustering/multiple instances — check whether the workload is pipelined (higher throughput) or synchronous round-trip (network RTT-bound, often <50K ops/sec effective).
- **Derive, don't memorize the cost tables** — cloud pricing changes quarterly; the durable skill is knowing DRAM costs ~50-100x more than disk per GB, and egress is usually the surprise line item, not the specific dollar figures above.

## Self-Check

1. Using `time = size ÷ bandwidth`, how long does sending 1KB take over a 1Gbps (125 MB/s) link, and what's the common misquote of this classic table row?
2. A drive is rated for 1M IOPS but you're issuing single-threaded random reads (QD=1). What throughput should you actually expect, and why?
3. us-east-1 to eu-west-1 is ~5,500 km. Using 200,000 km/s as the speed of light in fiber, compute the theoretical one-way latency and RTT, then compare to the measured ~70-80ms.
4. Target: 50,000 orders/day, 3 row writes each, peak = 5x average over 1 hour. What is the peak writes/sec, and what fraction of a single Postgres node's ~5-20K TPS ceiling is that?
5. If p99 latency is 200ms and you need 10,000 concurrent in-flight requests, what throughput does Little's Law imply is required?

<details><summary>Answers</summary>

1. 1KB ÷ 125 MB/s ≈ 8µs ≈ 10,000 ns (10µs). The row is often misremembered as 1MB, which inflates the answer by 1000x.
2. ~10-20K IOPS (latency ~50-100µs), not 1M — the 1M spec needs QD=32-128 to saturate; QD=1 leaves most of the drive's parallelism unused.
3. One-way ≈ 5,500 ÷ 200,000 = 27.5ms ≈ 28ms; RTT ≈ 56ms theoretical. Measured 70-80ms is ~1.3-1.5x the straight-line bound due to real routing paths.
4. Peak = (50,000×3×5) / 3,600s ≈ 208 writes/sec — about 1-4% of the 5-20K TPS ceiling, so a single node is fine.
5. Throughput ≈ 10,000 / 0.2s = 50,000 req/s.
</details>

---
**Related:** [Back-of-the-Envelope Estimation](07-back-of-envelope-estimation.md) · [Latency, Throughput, Bandwidth](02-latency-throughput-bandwidth.md) · [Object and Blob Storage](../02-core-components/11-object-and-blob-storage.md)

*Last reviewed: 2026-08*
