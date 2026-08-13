# Serialization Formats — JSON, Protobuf, Avro, Thrift

> **TL;DR:** Pick text (JSON) for public/debuggable APIs, Protobuf for RPC between services you control, Avro for schema-evolving event streams and data lakes, and columnar formats (Parquet/ORC) for analytics storage — the wire format is a contract, and tag/field discipline is what lets you evolve it without downtime.

## Quick Reference

| Use case | Best fit | Why |
|---|---|---|
| Public/partner API | JSON (+ OpenAPI) | Human-readable, curlable, ubiquitous tooling, no codegen required |
| Internal RPC (service-to-service) | Protobuf (gRPC) | Compact, fast, strong typing, streaming, codegen in every lang |
| Event streaming (Kafka) | Avro (+ Schema Registry) | Writer/reader schema resolution, compact, self-describing with registry |
| Analytics / data lake storage | Parquet (or ORC) | Columnar, predicate pushdown, huge compression, not row-oriented |
| Cross-language RPC, legacy/Hadoop shops | Thrift | Similar to protobuf, built-in RPC framework, common at Facebook-lineage stacks |
| Ultra-low-latency, zero-copy reads | FlatBuffers / Cap'n Proto | No decode step; read struct directly off the buffer |

| Format | Type | Schema | Typical size (vs JSON=100%) | Encode/decode CPU |
|---|---|---|---|---|
| JSON | Text | Optional (JSON Schema) | 100% | Slowest (parsing, string alloc) |
| Protobuf | Binary | Required (.proto) | 30-40% | Fast |
| Avro | Binary | Required (schema attached/registry) | 25-35% | Fast, but needs schema to read |
| Thrift (binary/compact) | Binary | Required (.thrift) | 30-45% | Fast |
| Parquet | Binary, columnar | Required | 10-20% (with compression) | Fast for scans, slow for row lookups |
| FlatBuffers/Cap'n Proto | Binary | Required | 30-40% | Near-zero (no decode) |

## What It Is

- Serialization = converting in-memory objects to bytes (wire/disk) and back. Trade-off axis: **human-readability vs size/speed**, and **schema flexibility vs safety**.
- **Text formats** (JSON, XML, YAML): self-describing, diffable, debuggable with curl/cat, larger payloads, slower parse (string→number conversion, quoting overhead).
- **Binary formats** (Protobuf, Avro, Thrift): compact, fast, require schema/IDL to interpret; not human-readable without tooling (`protoc --decode`, `avro-tools`).

## Responsibilities

- Define a **wire contract** independent of language (IDL: `.proto`, `.avsc`, `.thrift`).
- Encode data compactly and decode it deterministically.
- Support **schema evolution** so producers/consumers can deploy independently.
- Provide **codegen** for strongly-typed language bindings.
- (RPC formats) Define service/method framing for request-response or streaming.

## How It Works

### Protobuf wire format essentials
- Every field encodes as `(tag << 3 | wire_type)` varint, then the value.
- **Varint**: 7 bits of data per byte + continuation bit; small numbers (0-127) = 1 byte. Great for small ints/enums, bad for large random numbers (e.g. hashes) — use `fixed64` there instead.
- Wire types: 0=varint, 1=64-bit (fixed64/double), 2=length-delimited (string/bytes/embedded msg/repeated packed), 5=32-bit (fixed32/float).
- **Field tag numbers are the actual identity on the wire** — field *names* never get serialized. Decoding matches purely by tag number, so:
  - Tags 1-15 cost 1 byte (fits in 4-bit tag + 3-bit wire type in one byte) — reserve them for frequently-set/repeated fields.
  - **Never reuse or renumber a tag** once shipped — old binaries will misinterpret new data as the old field's type (silent corruption, not an error).
  - Deleting a field: mark the number `reserved` in the .proto so it can never be reassigned.
- Unknown fields are skipped (length-delimited/varint framing tells the parser how many bytes to jump), which is *why* forward compatibility mostly works for free.

### Avro writer/reader schema resolution
- Avro data files/messages **do not encode field names or tags on the wire at all** — just values in schema-declared order. This makes Avro the most compact of the binary formats but means **the schema is mandatory to read anything**.
- Two schemas exist at read time: the **writer's schema** (what produced the bytes) and the **reader's schema** (what the consumer expects). Avro's resolution algorithm reconciles them field-by-field:
  - Reader schema is matched by field **name**, not position — reordered fields are fine.
  - Field in writer but not reader → dropped.
  - Field in reader but not writer → filled from the reader schema's declared **default**.
  - Type must be compatible per Avro's promotion rules (int→long→float→double, string↔bytes).
- Because the writer schema travels with the data (embedded in Avro Object Container Files, or referenced by ID via Schema Registry in Kafka), a consumer written years later can still read old records — this is exactly why Avro dominates **data lakes and event logs**: files/topics accumulate years of schema drift, and Avro was designed around resolving that drift rather than requiring lockstep deploys.

### Zero-copy formats (one-liner)
**FlatBuffers/Cap'n Proto** skip the encode/decode step entirely — the wire bytes *are* the in-memory layout, so reads are pointer arithmetic into the buffer with no allocation or parsing pass, at the cost of a more rigid/verbose schema and larger payloads than Protobuf.

## Types / Classifications

**Text-based**: JSON, XML, YAML, CSV — self-describing, loose/no schema enforcement by default.

**Binary, schema-on-wire (self-describing enough to skip unknowns)**: Protobuf, Thrift — tag-based, schema needed for full semantics but not for basic skip/forward-compat.

**Binary, schema-required (no tags)**: Avro — smallest payload, but literally undecodable without the schema.

**Binary, zero-copy**: FlatBuffers, Cap'n Proto, SBE — for HFT/game engines/mmap'd IPC.

**Columnar (analytics-at-rest)**: Parquet, ORC — not a wire format, a storage layout; group values by *column* not row.

## Where It Fits

- **RPC layer**: Protobuf via gRPC (HTTP/2 + streaming), Thrift via its own RPC stack (TFramedTransport, multiple protocols: binary/compact/JSON).
- **Event streaming**: Avro (Kafka + Confluent Schema Registry is the canonical pairing); Protobuf and JSON Schema also supported by Schema Registry as of recent Confluent versions.
- **Data lake / warehouse at rest**: Parquet (Spark/Trino/Snowflake/BigQuery native), ORC (Hive/Presto legacy). Row-oriented Avro is common as the *landing* format before compaction jobs convert to Parquet for query layers.
- **Public APIs**: JSON+REST (or GraphQL) — ecosystem expects it, browsers parse it natively, no codegen barrier for third parties.
- **Config files / human-edited**: YAML/JSON, never binary formats.

## Common Patterns & Real-World Tools

- **gRPC**: Protobuf + HTTP/2, code-generates client/server stubs, supports bidi streaming — dominant for internal microservice mesh (Google, Netflix, Square).
- **Kafka + Confluent Schema Registry**: Avro payload + 5-byte magic-byte/schema-ID header on each message; registry enforces compatibility mode on schema `register` calls before allowing publish.
- **Thrift**: Facebook/Meta-originated, still heavy at Meta-lineage and Hadoop-ecosystem shops (HBase, Cassandra historically used it); less momentum than gRPC in new greenfield systems.
- **Parquet + Spark/Athena/BigQuery**: columnar + per-column compression (dictionary, RLE) + min/max stats per row-group enable predicate pushdown — scan only needed columns/row-groups.
- **Protobuf + Buf/Prototool**: linting and breaking-change detection in CI (`buf breaking`) to catch tag reuse or type changes before merge.

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| JSON | Universal, debuggable, no build step, flexible | Verbose, slow parse, weak typing, no native schema enforcement |
| Protobuf | Compact, fast, strict typing, great tooling, streaming (gRPC) | Not human-readable, requires codegen build step, tag management discipline |
| Avro | Most compact, best schema-evolution story, self-describing files | Needs schema to read at all, weaker RPC ecosystem, positional writer/reader coupling if misconfigured |
| Thrift | Similar perf to protobuf, built-in RPC transport options | Smaller community/momentum now, more complex IDL, fragmented protocol/transport combos |
| Parquet/ORC | Massive compression, fast analytical scans | Bad for row-by-row point lookups/updates, not a streaming/RPC format |

## Real-World Scenarios

- **Payments API exposed to external partners**: JSON+REST — partners need to read error bodies without your SDK, and debug with curl/Postman.
- **Internal order service → inventory service, thousands of req/s**: Protobuf/gRPC — sub-millisecond serialization overhead matters at that QPS, and both ends are your own deploys so codegen is fine.
- **Clickstream events into Kafka → S3 data lake → Spark analytics**: Avro on the wire (Schema Registry enforces BACKWARD compatibility so old consumers don't break), compacted to Parquet nightly for the warehouse layer.
- **Mobile app talking to backend over flaky networks**: Protobuf — smaller payloads save mobile data/battery vs JSON; consider Protobuf-over-HTTP (not full gRPC, which needs HTTP/2 support that some mobile proxies/carriers mangle).
- **Game engine networking / trading engine market data**: FlatBuffers or SBE — decode cost must be near-zero, allocation in the hot path is unacceptable.

## Nuances & Gotchas

- **Protobuf `optional` vs proto3 defaults**: proto3 originally removed field presence (no way to distinguish "unset" from "set to 0/empty string") — this silently broke patch/partial-update semantics for teams migrating from proto2. `optional` keyword was reintroduced (proto3.15+) specifically to restore presence tracking; if you need to know "was this field sent," don't rely on the zero-value.
- **Never renumber or reuse protobuf tags** — this is the #1 production incident in protobuf shops: a field gets deleted and a new field takes its old number, and any client still running old code silently deserializes garbage into the wrong type. Always `reserved 7;` deleted tags.
- **Avro requires the writer schema to decode** — if you evolve a schema in a Kafka topic without registering it (or point to the wrong subject), consumers get deserialization exceptions at 3am. Schema Registry's compatibility check exists precisely to make this a *build-time* rejection, not a runtime one.
- **Compatibility modes are not symmetric** — `BACKWARD` (new schema can read old data, i.e. only add optional fields / remove fields with defaults) protects **consumers upgrading after producers**; `FORWARD` (old schema can read new data) protects **consumers upgrading before producers**; `FULL` requires both. Kafka's default is `BACKWARD`, which surprises teams who assumed defaults protect the producer side too.
- **Thrift `required` fields are a trap**: marking a field `required` means any evolution that drops it breaks every existing serialized blob and every client still sending the old shape — most style guides (and later Thrift/proto3 itself) recommend avoiding `required` entirely and validating in application code instead.
- **JSON has no int64 precision**: JS numbers are IEEE-754 doubles, so int64 values above 2^53 (common for Twitter/Snowflake-style IDs) silently truncate when a JS client parses JSON — the standard fix is to serialize large IDs as strings.
- **Field order matters differently per format**: Avro binary encoding is purely positional against the *writer* schema (no tags), so writer-schema field order must exactly match what was written; Protobuf/Thrift don't care about field order at all since tags carry identity.
- **Renaming fields**: safe in Protobuf/Thrift (only the tag number matters, name is cosmetic/codegen-only) — unsafe in Avro/JSON unless you add an alias (Avro supports `"aliases"` in the schema for exactly this) or keep both old and new keys during a migration window.
- **Parquet is not a streaming format** — don't reach for it for Kafka payloads; it's a batch/file format with column-chunk footers that require the whole file (or footer) to plan reads, incompatible with append-as-you-go message semantics.
- **Compact vs Binary Thrift protocol**: TCompactProtocol uses varints and can be 30-40% smaller than TBinaryProtocol, but the two are wire-incompatible — mixing them between client/server versions is a classic silent-failure/connection-reset bug.

## Self-Check

1. You need to delete a deprecated field from a Protobuf message that's still being written by old binaries in production. What's the safe way to do it, and what happens if you just remove the field and let a new field reuse its old tag number?
2. A Kafka consumer written two years after a topic's producer needs to decode old messages. Why does Avro's design make this work without requiring the consumer to have the exact writer schema hardcoded, and what two components (in the Schema Registry setup) make it possible in practice?
3. A large Snowflake-style ID (above 2^53) round-trips through a JSON API to a JavaScript client. What goes wrong, and what's the standard fix?
4. Kafka's default Schema Registry compatibility mode is `BACKWARD`. Explain what guarantee this actually provides, who it protects, and why teams are surprised when it doesn't protect the other side.
5. You need to rename a field for clarity. Why is this safe in Protobuf/Thrift but risky in Avro or JSON, and how can you do it safely in Avro?

<details><summary>Answers</summary>

1. Mark the deleted tag number as `reserved` in the `.proto` file so it can never be reassigned. If you skip this and a new field reuses the old tag, old binaries still running will deserialize the new field's bytes as if they were the old field's type — silent data corruption, not an error.
2. Avro's writer schema travels with the data (embedded in the file, or referenced by a schema ID via Schema Registry), so the reader reconciles it against its own reader schema by field name at read time, filling missing fields from declared defaults — it never needs the writer schema hardcoded in advance.
3. JS numbers are IEEE-754 doubles, so int64 values above 2^53 silently lose precision when parsed. The standard fix is to serialize large IDs as strings in the JSON payload.
4. `BACKWARD` compatibility means a new schema can read data written with the old schema (only adding optional fields or removing fields with defaults), which protects consumers that upgrade after producers. It does not protect the producer side or consumers upgrading before producers — that's what `FORWARD` mode covers.
5. In Protobuf/Thrift only the tag number carries identity on the wire, so the field name is cosmetic and safe to change. In Avro/JSON, field names are structurally load-bearing (Avro matches by name, JSON keys are the data), so renaming breaks readers unless you add an Avro `"aliases"` entry or keep both old and new keys during a migration window.
</details>

---
**Related:** [Network Protocols](10-network-protocols-tcp-udp-http-grpc-websockets.md) · [Publish-Subscribe and Event Streaming](../02-core-components/08-publish-subscribe-and-event-streaming.md) · [Object and Blob Storage](../02-core-components/11-object-and-blob-storage.md)

*Last reviewed: 2026-08*
