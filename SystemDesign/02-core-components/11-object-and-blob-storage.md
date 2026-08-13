# Object and Blob Storage

> **TL;DR:** Object storage trades POSIX semantics and low-latency mutation for near-infinite scale, extreme durability, and low cost, by storing immutable blobs + metadata under flat keys accessed over HTTP.

## Quick Reference

| Aspect | Value |
|---|---|
| Durability (S3 Standard) | 11 nines (99.999999999%)/yr |
| Availability (S3 Standard) | 99.99% SLA |
| Max object size | 5 TB (S3/GCS); multipart required above 5 GB |
| Multipart part size | 5 MB – 5 GB per part, up to 10,000 parts |
| Presigned URL max TTL | 7 days (S3 SigV4) |
| Cost driver #1 | Egress (~$0.05–0.09/GB), not storage |
| S3 Standard storage | ~$0.023/GB-mo |
| S3 Infrequent Access | ~$0.0125/GB-mo + retrieval fee |
| S3 Glacier Flexible | ~$0.004/GB-mo, retrieval mins–hrs |
| S3 Glacier Deep Archive | ~$0.00099/GB-mo, retrieval ~12 hrs |
| Read-after-write consistency | Strong since Dec 2020 (S3) |
| LIST cost | Slow at scale; O(prefix scan), eventually consistent historically on other providers |

## What It Is

- A key-value store for immutable binary blobs (images, video, backups, logs) plus arbitrary metadata, accessed via HTTP REST API (PUT/GET/DELETE), not a filesystem API.
- Each object = key (string) + value (bytes, up to TB scale) + metadata (content-type, custom headers, ACLs, tags).
- No in-place edits — updating an object means rewriting the whole object (or using multipart to replace parts, still producing a new full object).

## Responsibilities

- Durable persistence of unstructured/semi-structured data at massive scale (exabytes).
- Serve as the "source of truth" tier below databases: media, backups, data lake files, ML artifacts, logs.
- Decouple storage lifecycle (retention, tiering, deletion) from compute.
- Provide access control (bucket policies, IAM, ACLs) and audit trail per object/bucket.

## How It Works

```
Client --PUT/GET(key)--> API/LB --> Metadata layer (key->location)
                                  --> Chunk/shard placement (erasure coded)
                                  --> Distributed disks across failure domains (AZs)
```

- **Flat namespace:** bucket + key string (e.g., `photos/2024/img1.jpg`). "Folders" are a UI/SDK illusion — `/` is just a character in the key; LIST with `delimiter=/` groups keys to fake a tree.
- **Durability via erasure coding:** data split into k data shards + m parity shards (e.g., 6+3), spread across disks/racks/AZs; can lose m shards and reconstruct. Achieves 11 nines with ~1.5x overhead vs 3x for straight replication.
- **Replication** (simpler, used by MinIO/Ceph in smaller clusters): N full copies across nodes/zones; higher storage overhead (2–3x) but simpler and faster to reconstruct.
- **Availability vs durability are separate dials:** durability = probability bytes are never lost; availability = probability a request succeeds *right now*. You can have 11-nines durable data that's temporarily unavailable during a zone outage.

## Types / Classifications

| Type | Unit | Access pattern | Latency | Example |
|---|---|---|---|---|
| Block storage | Fixed-size blocks | Raw disk, OS/filesystem on top | Sub-ms | EBS, SAN, Persistent Disk |
| File storage | Files in a directory tree | POSIX (open/read/write/seek), shared mounts | Low ms | NFS, EFS, Azure Files |
| Object storage | Whole objects via HTTP API | GET/PUT/DELETE, no partial in-place writes | Tens–hundreds ms | S3, GCS, Azure Blob |

**When each wins:**
- Block: databases, boot volumes — need low-latency random I/O and a filesystem.
- File: shared config, legacy apps, HPC scratch — need POSIX semantics, multiple concurrent writers with locking.
- Object: static assets, backups, data lakes, media, logs — need massive scale, HTTP access, cheap durability, don't need in-place mutation.

## Where It Fits

- Sits below/beside databases in the stack: DB stores pointers (URLs/keys) to blobs in object storage rather than storing large binaries inline (reduces DB size/cost).
- Backing store for data lakes (S3 + Athena/Redshift Spectrum, GCS + BigQuery), CDN origins (S3 + CloudFront), static site hosting, backup/archive targets, ML training data and model artifact stores.
- Event notifications (S3 Event Notifications, GCS Pub/Sub notifications) make it a pipeline trigger: upload → Lambda/Cloud Function → thumbnail generation, virus scan, ETL kickoff, search indexing.

## Common Patterns & Real-World Tools

- **Multipart upload:** split large file into parts, upload in parallel, retry failed parts individually, then complete-multipart-upload to stitch. Essential for >100MB files and resumable uploads.
- **Presigned URLs:** server generates a signed, time-limited URL; client uploads/downloads directly to/from the bucket — keeps large transfers off app servers, saves bandwidth/compute.
- **Versioning:** bucket-level flag keeps every write as a new version under the same key; enables restore-on-overwrite/delete (soft delete via delete markers).
- **Object Lock (WORM):** compliance-mode or governance-mode retention that blocks deletion/overwrite until a retention date — used for audit logs, financial records (SEC 17a-4).
- **Lifecycle policies:** automated rules to transition objects between storage classes (Standard → IA → Glacier) or expire them, based on age/tags/prefix.
- **Tools:** AWS S3 (reference implementation), Google Cloud Storage (strong consistency, unified classes), Azure Blob Storage (Hot/Cool/Archive tiers, hierarchical namespace option via ADLS Gen2), MinIO (self-hosted, S3-API-compatible, good for on-prem/K8s), Ceph RGW (S3/Swift-compatible gateway over a Ceph cluster, common in private cloud).

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Virtually unlimited scale, no capacity planning | No partial in-place writes — full object rewrite |
| Very high durability at low cost | Higher latency than block storage (network + API overhead) |
| HTTP API — easy multi-region, multi-client access | No native transactions/joins/indexes — not a DB |
| Pay-per-use, tiered pricing | Egress fees can dwarf storage cost |
| Built-in replication/erasure coding, no ops burden | LIST/prefix operations don't scale like a real filesystem |
| Native versioning, lifecycle, event hooks | Small objects have high relative overhead (metadata, request cost) |

## Real-World Scenarios

- **Media platform:** user uploads video via presigned URL → S3 event triggers transcoding Lambda → outputs written to a different prefix → CDN serves via CloudFront in front of S3.
- **Data lake:** raw JSON logs land in `s3://lake/raw/dt=2026-08-13/`, lifecycle rule moves them to IA after 30 days, Glacier after 180 days; Athena queries raw+curated via external tables.
- **Compliance archive:** financial records written once with Object Lock (compliance mode, 7-year retention) — even root/admin cannot delete before expiry.
- **Backup target:** nightly DB dumps multipart-uploaded to S3 Standard-IA, cross-region replicated, lifecycle-expired after 90 days.

## Nuances & Gotchas

- **LIST is slow and expensive at scale:** it's a paginated scan of a sorted key index, not an O(1) directory read; listing millions of keys under one prefix can take minutes and rack up request costs — maintain your own index (DynamoDB/Postgres) for lookups instead of LISTing.
- **Request-rate limits are per-prefix:** S3 auto-scales partitions but sequential/lexicographic keys (e.g., timestamps, incrementing IDs) can hotspot a single prefix; hash/reverse the key prefix (`a1b2/2026/08/13/file`) to spread load across partitions.
- **Egress dominates cost at scale**, not storage — serving TBs/day out of a bucket without a CDN can cost far more in egress than the data costs to store; put a CDN in front for read-heavy workloads.
- **Bucket-level ops can lag:** bucket creation/deletion, tagging, and some cross-region replication metadata are eventually consistent even on providers with strong object-level consistency — don't assume instant global visibility.
- **Strong read-after-write (S3, 2020) fixed object PUT/DELETE visibility only** — a GET after a PUT now always sees the latest version. It did **not** fix: LIST consistency guarantees across concurrent writes in some edge cases, cross-region replication lag, or give you transactions/atomic multi-object updates.
- **Small-object overhead:** each object carries fixed per-request cost and metadata overhead (~few hundred bytes to KB); millions of tiny objects (e.g., one file per IoT reading) are far more expensive/slow than batching into fewer larger objects (Parquet/Avro rollups).
- **Lifecycle transitions can cost more than they save:** each transition is a billable request, and early deletion from IA/Glacier before the minimum storage duration (30/90/180 days depending on class) incurs an early-deletion penalty — don't transition objects that will be deleted or re-read soon.
- **Don't use object storage as a database:** no secondary indexes, no ACID multi-key transactions, no efficient partial updates or range queries beyond key-prefix — pair it with a real DB/index for anything needing query patterns beyond get-by-key.
- **Erasure coding vs replication trade-off:** erasure coding is more storage-efficient but reconstruction after a disk loss is CPU/network-intensive and slower than replica promotion — matters for recovery time objectives at very large scale.
- **Versioning without lifecycle rules silently inflates cost:** every overwrite keeps the old version billed forever unless you add a noncurrent-version expiration rule.

## Self-Check

1. Why is LISTing millions of keys under one prefix slow and costly, and what should you use instead for lookups?
2. A bucket has 11-nines durability but a client just got a failed GET. Explain how both facts can be true using the S3 numbers.
3. S3 added strong read-after-write consistency in Dec 2020. What specifically did this fix, and what did it explicitly NOT fix?
4. You're writing one object per IoT sensor reading, sequentially timestamped. Name two distinct cost/performance problems this creates and their fixes.
5. A bucket has versioning enabled but no lifecycle rule. What happens to storage cost over time, and why?

<details><summary>Answers</summary>

1. LIST is a paginated scan of a sorted key index, not an O(1) directory read, so it takes minutes and racks up request costs at scale; maintain your own index (e.g., DynamoDB/Postgres) for lookups instead.
2. Durability (99.999999999%) is the probability the bytes are never lost; availability (99.99% SLA) is the probability a request succeeds right now — data can be perfectly intact but temporarily unreachable during a zone outage.
3. It fixed GET-after-PUT/DELETE visibility, so a GET always sees the latest version immediately. It did not fix LIST consistency in some concurrent-write edge cases, cross-region replication lag, or provide transactions/atomic multi-object updates.
4. Sequential/lexicographic keys hotspot a single prefix's request-rate partition (fix: hash/reverse the key prefix); and one-object-per-reading creates massive small-object overhead in per-request cost and metadata (fix: batch into fewer larger objects like Parquet/Avro rollups).
5. Every overwrite keeps the old version billed forever, silently inflating storage cost, because there's no noncurrent-version expiration rule to purge old versions.
</details>

---
**Related:** [CDN](06-cdn.md) · [Search Engines and the Inverted Index](12-search-engines-inverted-index.md) · [Napkin Math](../01-fundamentals/08-napkin-math-numbers-every-engineer-should-know.md)

*Last reviewed: 2026-08*
