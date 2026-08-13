# Search Engines and the Inverted Index

> **TL;DR:** Search engines flip document→terms into term→documents (the inverted index) so full-text queries hit posting lists instead of scanning rows; segment-based storage, BM25 scoring, and shard scatter-gather turn this into a distributed, near-real-time system.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Inverted index | term → posting list of {docID, freq, positions[]} |
| Analyzer stages | tokenize → lowercase → stopword removal → stemming/lemmatization → synonyms |
| Segment | immutable Lucene file set; writes create new segments, never mutate old ones |
| Refresh interval | ES/OpenSearch default 1s (near-real-time, not real-time) |
| Merge | background compaction of small segments into larger ones; reclaims deletes |
| Scoring | BM25 (default since ES 5/Solr 6/Lucene), replaced TF-IDF |
| Sharding | index split into N primary shards, fixed at creation (ES) |
| Query path | scatter-gather: query all shards → merge/re-rank top-K → fetch docs |
| Deep pagination | `from+size` degrades badly; use `search_after` / scroll / PIT |
| Vector search | HNSW ANN index for embeddings; hybrid = BM25 + vector, fused (e.g. RRF) |
| Popular engines | Elasticsearch, OpenSearch, Solr (all on Lucene), Typesense, Meilisearch, pgvector, Postgres `tsvector` |

## What It Is

- A search engine answers "which documents contain X" in O(matching docs) instead of O(all docs) via an **inverted index**: term → sorted posting list of doc IDs (+ term frequency, + positions for phrase queries).
- Contrast with a **forward index** (doc → terms), used for highlighting/rebuilding source, not lookup.
- Core primitive underneath: Lucene (Java). Elasticsearch/OpenSearch/Solr are distributed orchestration + REST layers on top of Lucene segments.

## Responsibilities

- Tokenize and normalize text at index time (the **analysis pipeline**).
- Store posting lists compactly (delta + varint encoding, skip lists for fast intersection).
- Rank matching documents by relevance (TF-IDF/BM25) or vector similarity.
- Support boolean, phrase, fuzzy, range, geo, and aggregation queries.
- Stay near-real-time searchable while ingesting continuous writes.
- Scale horizontally via sharding + replicate for availability/read throughput.

## How It Works

**Analysis pipeline (index time AND query time — must match):**
1. Tokenize: split "Running shoes!" → [Running, shoes]
2. Lowercase: → [running, shoes]
3. Stopword removal: drop "the", "is", "a" (optional, language-specific)
4. Stemming/lemmatization: running → run (Porter/Snowball stemmer)
5. Synonym expansion: run ↔ jog (index-time expands stored terms; query-time expands search terms)

If index-time and query-time analyzers diverge (e.g. one stems, the other doesn't), queries silently miss matches — no error, just wrong recall. This is the #1 real-world bug class.

**Segment lifecycle:**
```
Write → in-memory buffer → refresh (default 1s) → new immutable segment (searchable)
                                                  → flush → fsync to disk (translog trimmed)
Many small segments → background merge → fewer, larger segments (deletes purged)
```
- Segments are immutable: updates = mark-old-doc-deleted + index-new-doc. Deletes are tombstones until merge.
- **Refresh** makes writes searchable (cheap, in-memory → new segment); **flush** persists to disk (expensive, fsync).
- Trade-off: shorter refresh interval = fresher search, more small segments, more merge pressure, lower indexing throughput.

**Scoring:**
- TF-IDF: `score = termFreq * log(N/docFreq)` — raw TF grows unbounded, doesn't saturate, ignores doc length normalization well.
- **BM25** (Okapi): adds TF saturation (diminishing returns past a few occurrences via `k1`, default ~1.2) and document-length normalization (`b`, default 0.75, penalizes long docs less naively than TF-IDF). Won because it correlates better with human relevance judgments and has two tunable, well-understood knobs.

## Types / Classifications

| Type | Mechanism | Example |
|---|---|---|
| Lexical / full-text | inverted index, term matching | Lucene, Elasticsearch, Postgres FTS |
| Vector / semantic | embeddings + ANN (HNSW, IVF) | pgvector, Pinecone, Elasticsearch dense_vector |
| Hybrid | lexical + vector fused (RRF, weighted sum) | Elasticsearch, Vespa, Weaviate |
| Embedded / lightweight | single-binary, low-ops | Typesense, Meilisearch, SQLite FTS5 |
| Structured-first w/ search bolt-on | relational + tsvector/GIN index | Postgres full-text search |

## Where It Fits

```
Client → App/API → [Write path: CDC/dual-write] → Search Cluster (coordinator node)
                                                          |  scatter query to shards
                                              shard1  shard2  shard3 ... (+ replicas)
                                                          |  gather + merge top-K
                                                       ranked results → App → Client
Source of truth: primary DB (Postgres/MySQL) --sync/CDC--> Search index (derived, rebuildable)
```
- Sits beside, never instead of, the system-of-record DB. Populated via dual-write, outbox pattern, or CDC (Debezium → Kafka → indexer).
- Typical layer for: product search, log/observability search (ELK stack), autocomplete, log analytics.

## Common Patterns & Real-World Tools

- **ELK/OpenSearch stack**: Elasticsearch/OpenSearch + Logstash/Beats/Fluentd (ingest) + Kibana/OpenSearch Dashboards (viz) — dominant for logs and product search.
- **Solr**: older Lucene-based engine, SolrCloud for distribution, strong in enterprise/legacy search.
- **Typesense / Meilisearch**: typo-tolerant, instant-search UX, simple ops, smaller scale than ES.
- **pgvector**: adds vector columns + HNSW/IVFFlat index to Postgres; good when you don't want a second system.
- **Postgres `tsvector`/GIN**: "good enough" full-text for moderate scale, avoids running a search cluster.
- **Reciprocal Rank Fusion (RRF)**: standard way to combine BM25 rank and vector-similarity rank into one hybrid score without needing comparable score scales.
- **Autocomplete**: edge n-grams or dedicated prefix structures (FST in Lucene), not full inverted-index queries.

## Pros & Cons / Trade-offs

| Choice | Pro | Con |
|---|---|---|
| Dedicated search cluster (ES/OS) | Fast full-text, faceting, relevance tuning, scales horizontally | Extra infra, eventual consistency with source DB, ops burden (JVM, heap, shards) |
| Postgres FTS/pgvector | One system, transactional consistency, simple ops | Weaker relevance tuning, scales worse past tens of millions of docs |
| Short refresh interval | Fresh results | Merge pressure, lower write throughput, more segments to search |
| Long refresh interval | High write throughput | Stale search results (search lag) |
| More primary shards | More parallelism, higher ceiling | More overhead per query (fan-out), harder to resize later |
| BM25 over TF-IDF | Length-normalized, saturates, tunable | Still needs `k1`/`b` tuning per corpus; not semantic |

## Real-World Scenarios

- **E-commerce search**: Elasticsearch index of products, BM25 + boosted fields (title > description), filters (facets) via aggregations, synonym list for brand/category matching.
- **Log analytics (ELK)**: Filebeat ships logs → Elasticsearch indexes with daily/rolling indices → ILM policies delete/rollover old indices → Kibana dashboards query recent hot data.
- **RAG for an LLM app**: pgvector or dedicated vector DB stores embedding chunks; hybrid BM25+vector retrieval feeds top-K chunks into the prompt context.
- **Autocomplete-as-you-type**: separate lightweight index (Typesense/edge n-grams) tuned for prefix latency, distinct from the main relevance-ranked search index.

## Nuances & Gotchas

- **Deep pagination blows up**: `from+size` requires each shard to sort `from+size` docs and ship them to the coordinator — `from=10000` is O(10000) per shard, causing memory/CPU spikes. Use `search_after` (cursor-based) or Point-in-Time (PIT) + `search_after` for stable deep scroll; `scroll` API for full exports only, not live pagination.
- **Distributed scoring skew**: BM25's IDF is computed **per shard** by default, not globally. With uneven term distribution across shards (e.g. routing by customer), the same document can score differently depending on shard placement. Fix: `dfs_query_then_fetch` (global term stats, slower) or accept the skew at small shard counts.
- **Mapping changes require reindex**: field type changes (e.g. `text`→`keyword`, analyzer swap) aren't in-place; Lucene segments are immutable, so you create a new index with the new mapping and reindex all docs (alias swap for zero-downtime cutover).
- **Refresh interval is a latency/throughput dial**: setting `refresh_interval: -1` during bulk imports then re-enabling after is a standard trick to avoid segment/merge storms during large loads.
- **Merge storms**: too many small segments (from aggressive refresh or high delete rate) trigger heavy background merges that compete with query/index I/O — visible as latency spikes; tune `merge.policy` segment count/size thresholds or throttle write rate.
- **Write amplification**: every update = delete + reindex, not a mutation; frequent updates to the same doc (e.g. view counters) multiply I/O — batch or move hot-mutable fields out of the search doc.
- **Never treat the index as source of truth**: it's derived and rebuildable; losing it should mean "reindex from DB," not "restore from backup or lose data." Don't write business-critical state only to Elasticsearch.
- **Index/source drift**: if the CDC pipeline (Debezium/Kafka connector) lags or drops events, search results silently diverge from the DB — monitor consumer lag and run periodic reconciliation/checksums, not just "trust the pipeline."
- **Stemming is language- and domain-specific**: over-aggressive stemming merges unrelated words (e.g. "organization"→"organ" in bad configs); under-stemming misses plurals/tenses — test with real query logs, not intuition.
- **Stopword removal can break exact-phrase or short-code search**: e.g. "to be or not to be" or product codes like "A" or "OR" — use a separate non-stopword-filtered field for exact-match use cases.

## Self-Check

1. Why must index-time and query-time analyzers match, and what does the failure look like when they don't?
2. Why does `from+size` deep pagination degrade badly, and what should replace it for stable deep scroll versus full export?
3. Why can the same document score differently depending on which shard it lands on, and what fixes this (at what cost)?
4. You changed a field from `text` to `keyword` in the mapping. Why can't this be applied in place, and what's the safe way to roll it out?
5. Concretely, what two mechanisms does BM25 add over TF-IDF, and why did that make it the better default?

<details><summary>Answers</summary>

1. The analysis pipeline (tokenize/lowercase/stem/synonyms) must produce the same terms at index and query time, or terms won't match in the posting list. Failure is silent: no error, just missing results (wrong recall), e.g. one side stems "running"→"run" and the other doesn't.
2. Each shard must sort and ship `from+size` docs to the coordinator, so cost grows with `from` (O(10000) per shard at `from=10000`), spiking memory/CPU. Use `search_after`/PIT for live deep pagination; use `scroll` only for full exports, not user-facing pagination.
3. BM25's IDF is computed per shard by default, so uneven term distribution across shards (e.g. customer-based routing) makes the same doc score differently by placement. Fix is `dfs_query_then_fetch` for global term stats, at the cost of extra query latency.
4. Lucene segments are immutable, so mapping/analyzer changes can't mutate existing postings in place. Create a new index with the new mapping, reindex all docs into it, then cut over via alias swap for zero downtime.
5. BM25 adds TF saturation (diminishing returns past a few term occurrences via `k1`) and document-length normalization (via `b`), unlike TF-IDF's unbounded raw TF. It won because it correlates better with human relevance judgments and exposes two tunable, well-understood knobs.
</details>

---
**Related:** [Object and Blob Storage](11-object-and-blob-storage.md) · [Publish-Subscribe and Event Streaming](08-publish-subscribe-and-event-streaming.md) · [Caching Fundamentals](04-caching-fundamentals.md)

*Last reviewed: 2026-08*
