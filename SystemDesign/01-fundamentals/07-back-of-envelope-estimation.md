# Back-of-the-Envelope Estimation

> **TL;DR:** Convert a vague product ask into QPS, storage, and server-count numbers in under 10 minutes, using round powers-of-two/ten, explicit assumptions, and a peak multiplier — precision to one significant figure is the goal, not accuracy.

## Quick Reference

| Quantity | Rule of thumb |
|---|---|
| 1 day in seconds | ~86,400 ≈ **10^5 s** (use this rounding, always) |
| 1 month | ~2.6M seconds; 1 year ≈ **3.15 × 10^7 s** |
| Average QPS | DAU × actions/user/day ÷ 86,400 |
| Peak QPS | avg QPS × peak factor (**2–3x** typical, up to 10x for flash events) |
| 1 server capacity | ~1,000–10,000 QPS (simple reads, cached) — validate per case |
| Read:Write ratio | state it (e.g. 100:1 for Twitter feed, 10:1 typical social) |
| Replication factor | **3x** (common default: 1 primary + 2 replicas) |
| Storage growth | multiply 1-yr storage × 5 for 5-yr planning, then × replication |
| KB / MB / GB / TB / PB | 10^3 / 10^6 / 10^9 / 10^12 / 10^15 bytes (use decimal, not 1024, for estimates) |
| Bandwidth | storage-per-day ÷ 86,400 → bytes/sec, then × 8 → bits/sec |
| Latency (memory vs disk vs network) | L1 ~1ns, RAM ~100ns, SSD ~100µs, cross-continent RTT ~150ms |

## What It Is

- A structured Fermi-estimation technique to size a system (traffic, storage, bandwidth, servers) from a handful of top-line business numbers (DAU, avg actions/user).
- Purpose: sanity-check design decisions ("do we need sharding on day 1?"), not to produce a spec — being off by 2-3x is fine, being off by 100x means you misread the problem.
- Core interview/design signal: shows you can reason quantitatively about scale before committing to an architecture.

## Responsibilities

- Convert business metrics → engineering load metrics (QPS, IOPS, storage/day).
- Surface which subsystem is the bottleneck (compute vs storage vs bandwidth vs metadata).
- Justify architectural choices numerically: "150K QPS peak read → need caching + read replicas, not a single Postgres box."
- Give a growth trajectory (1yr / 5yr) so you don't design for today only to redesign in 8 months.

## How It Works

1. **Clarify scope & gather inputs**: DAU/MAU, actions per user per day, avg payload size, read:write ratio, retention period. State each as an assumption out loud.
2. **DAU → total daily actions**: `DAU × actions/user/day`.
3. **Total actions → average QPS**: `total daily actions / 86,400`.
4. **Average → peak QPS**: multiply by peak factor (2-3x normal diurnal swing; 5-10x for sales/launches/viral events).
5. **Storage per action**: `avg object size × writes/day` → daily storage; extrapolate to 1yr, 5yr.
6. **Apply replication/redundancy factor** (typically 3x) and index/metadata overhead (add ~10-30%).
7. **Bandwidth**: `daily storage bytes / 86,400 sec × 8` = bits/sec ingress; do the same for egress (often egress >> ingress, e.g. reads >> writes).
8. **Server count**: `peak QPS / QPS-per-server`, then round up and add headroom (~1.5x for failover/maintenance).
9. **Sanity check** against known reference points (e.g. "Twitter is ~6,000 tweets/sec avg" ) and round every result to 1-2 significant figures.

```
DAU → daily actions → avg QPS → peak QPS ─┐
                                            ├─→ server count
avg object size → daily/annual storage ─┐  │
                        × replication   ├──┴─→ bandwidth (storage/day ÷ 86400 × 8)
                        × 5yr growth    ┘
```

## Types / Classifications

- **Traffic estimation**: QPS, RPS, peak/avg, read vs write split.
- **Storage estimation**: raw data size, index overhead, replication, retention/TTL, cold vs hot tiers.
- **Bandwidth estimation**: ingress (uploads) vs egress (downloads/reads), CDN offload impact.
- **Compute/server estimation**: server count from QPS, memory footprint (working set for caching), cache hit-ratio impact on DB load.
- **Memory estimation**: cache sizing = hot dataset size (often 20% of data serves 80% of traffic — Pareto within Pareto).

## Where It Fits

- **First 5-10 minutes of a system design interview**, right after requirements gathering, before high-level architecture.
- Drives concrete decisions later in the same design: "peak QPS = 50K read → need a cache layer + CDN" or "5PB over 5 years → need a distributed object store like S3/HDFS, not local disks."
- Revisited at capacity-planning time in real systems (SRE/infra teams do this quarterly with actual metrics instead of guesses).

## Common Patterns & Real-World Tools

| Pattern | Real system reference |
|---|---|
| CDN offload for read-heavy egress | Cloudflare/CloudFront cut origin bandwidth 80-95% for static media |
| Cache-aside for hot reads | Redis/Memcached sized to top ~20% of objects by access frequency |
| Horizontal sharding once single-node write QPS is exceeded | MySQL/Postgres shard at ~5-10K writes/sec/node ceiling |
| Object storage for blobs, DB for metadata | S3 + DynamoDB/Postgres (Instagram, Dropbox pattern) |
| Message queue to absorb write spikes | Kafka/SQS buffering when peak >> provisioned DB capacity |
| Read replicas for read:write skew | Postgres/MySQL replicas when read:write > 10:1 |

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Fast — catches order-of-magnitude design errors in minutes | Not a substitute for load testing / real profiling |
| Forces explicit, debatable assumptions (good communication signal) | Garbage in, garbage out — wrong DAU assumption cascades everywhere |
| Cheap to redo when requirements change | Ignores tail latency, hot-key skew, non-uniform access patterns |
| Universally applicable across domains | Overprecision (calculator-level answers) signals *lack* of seniority, not rigor |

## Real-World Scenarios

**Assumptions (state these out loud):**
- 500M DAU, each user views 30 photos/day and uploads 1 photo every 10 days (0.1 uploads/user/day).
- Avg photo size after compression: 200 KB. Each upload also generates 3 thumbnail sizes (~50 KB total extra) → **250 KB/upload** total storage.
- Read:write ratio ≈ 300:1 (views vs uploads) — validate: 30 views vs 0.1 uploads per user/day = 300:1. ✓
- Peak factor: 3x average (diurnal pattern, no major campaign).
- Replication factor: 3x. Retention: keep everything (no deletion policy assumed).

**Step 1 — Writes (uploads):**
- Daily uploads = 500M × 0.1 = **50M uploads/day**.
- Avg write QPS = 50M / 10^5 s = **500 writes/sec**.
- Peak write QPS = 500 × 3 = **~1,500 writes/sec**.

**Step 2 — Reads (views):**
- Daily views = 500M × 30 = **15B views/day**.
- Avg read QPS = 15 × 10^9 / 10^5 = **150,000 reads/sec**.
- Peak read QPS = 150K × 3 = **~450,000 reads/sec**.
- Confirms read:write ≈ 450K:1.5K ≈ 300:1, consistent with assumption. ✓

**Step 3 — Storage:**
- Daily raw storage = 50M uploads × 250 KB = 12.5 × 10^12 bytes = **12.5 TB/day**.
- Annual = 12.5 TB × 365 ≈ **4.6 PB/year**.
- 5-year (linear, ignoring DAU growth) ≈ **23 PB**; apply 3x replication → **~70 PB** provisioned.
- (If DAU grows 20%/yr, compound it — but for BOTE, linear + a stated caveat is acceptable.)

**Step 4 — Bandwidth:**
- Ingress (uploads): 12.5 TB/day / 86,400s = ~145 MB/s ≈ **1.2 Gbps** sustained; peak (×3) ≈ **3.6 Gbps**.
- Egress (reads): most views are feed/thumbnail-sized rather than full 200 KB originals, so assume **100 KB served per view**: 15B × 100 KB = 1.5 PB/day / 86,400s ≈ 17.4 GB/s ≈ **140 Gbps** sustained — this is why CDN offload is mandatory, not optional.

**Step 5 — Servers:**
- Assume 1 app server handles 5,000 QPS (cached reads, light logic) → peak read servers = 450,000 / 5,000 = **90 servers**, round to **~100 with headroom**.
- Write path (uploads involve encoding/thumbnailing, heavier) assume 500 QPS/server → 1,500/500 = **3 servers minimum**, round to **~10** for redundancy + processing headroom.

**Conclusion this estimation drives:** egress bandwidth (140 Gbps) is the dominant cost/design driver → CDN in front of a blob store (S3-like) is non-negotiable; 70 PB over 5 years rules out single-datacenter block storage → need a distributed object store with erasure coding or 3x replication; read:write of 300:1 justifies aggressive caching (Redis/CDN) over optimizing the write path.

## Nuances & Gotchas

- **86,400 ≈ 10^5 rounding** introduces ~15.7% error by itself — acceptable for BOTE, but say it explicitly so the interviewer knows you know.
- **Peak factor is the #1 place people guess wrong.** Diurnal traffic (2-3x) is very different from flash-sale/viral/breaking-news traffic (10-100x) — Black Friday, World Cup goals, celebrity deaths have caused 20-50x spikes; always ask "is there a known spike pattern?"
- **Hot-key skew breaks uniform-QPS-per-server math.** A celebrity's photo can single-handedly blow past any per-node QPS budget your average-based sizing assumed — average QPS hides this entirely; design caching/CDN for the tail, not the mean.
- **Read:write ratio changes the entire architecture**, not just cache sizing — high read:write (100:1+) favors read replicas/CDN/denormalization; near 1:1 (chat, IoT ingestion) favors write-optimized stores (LSM-trees, append logs) over B-trees.
- **Don't forget metadata/index overhead** — a naive storage estimate for objects ignores DB rows for ownership, permissions, search indices; this can add 10-30% and sometimes becomes the real bottleneck (e.g., a metadata DB hitting IOPS limits while blob storage is fine).
- **Egress vs ingress asymmetry is usually the real cost driver** in media-heavy systems (as shown above: 140 Gbps egress vs 3.6 Gbps ingress) — teams that only estimate write path get blindsided by CDN/bandwidth bills.
- **5-year linear growth undercounts** if DAU is growing — always caveat "this assumes flat DAU; compound at growth rate X% if provided," rather than silently presenting a linear number as the real forecast.
- **Rounding discipline**: round early and often to 1 significant figure (500K not 487,326); never carry a precise-looking number through five steps of multiplication — the false precision misleads more than it informs.
- **State assumptions as questions, not facts**: "I'll assume 500M DAU and 30 views/user/day — does that match your expectations?" invites correction and is the actual skill being evaluated, more than the arithmetic itself.
- **Server QPS capacity varies 100x by workload** (a static-file server vs a JOIN-heavy transactional query) — never use a single "QPS per server" constant without stating what kind of request it represents.
- **Cache hit ratio changes server count by an order of magnitude** — a 95% cache hit rate means only 5% of 450K QPS (22.5K) hits the DB tier; forgetting to model this leads to wildly over-provisioning the database layer.

## Self-Check

1. A messaging app has 200M DAU, each sending 20 messages/day. Using the 10^5 s/day rounding and a 3x peak factor, what's the peak write QPS?
2. Peak read QPS is 200,000 and the cache hit ratio is 90%. How much QPS actually reaches the database tier?
3. Why does using 86,400 ≈ 10^5 for seconds/day matter enough to state out loud, given it introduces error?
4. A single celebrity post can blow past a per-node QPS budget even though your average-based sizing looked fine. Why does average QPS hide this, and what should you design for instead?
5. A system moves from a 10:1 to a 1:1 read:write ratio (e.g., chat/IoT ingestion). How should the storage/DB architecture choice change?

<details><summary>Answers</summary>

1. Daily messages = 200M × 20 = 4B; avg QPS = 4B / 10^5 = 40,000; peak = 40,000 × 3 = **120,000 QPS**.
2. Only the 10% miss rate hits the DB: 200,000 × 0.10 = **20,000 QPS** to the database tier.
3. It's a ~15.7% built-in error (86,400 vs 100,000); acceptable for order-of-magnitude estimates, but staying silent about it looks like false precision rather than a deliberate simplification.
4. Average QPS is a per-node mean across all keys, so it hides skew toward one hot object; design caching/CDN capacity for the tail (hottest key), not the mean, or the hot node falls over while aggregate load looks fine.
5. Near 1:1 read:write favors write-optimized stores (LSM-trees, append logs) over B-trees, since heavy random writes/updates are now as significant as reads rather than being dwarfed by a read-heavy skew that favored replicas/CDN/denormalization.
</details>

---
**Related:** [Napkin Math](08-napkin-math-numbers-every-engineer-should-know.md) · [Latency, Throughput, Bandwidth](02-latency-throughput-bandwidth.md) · [Caching Fundamentals](../02-core-components/04-caching-fundamentals.md)

*Last reviewed: 2026-08*
