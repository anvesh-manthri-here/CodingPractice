# Consistent Hashing

> **TL;DR:** Map both nodes and keys onto a fixed hash ring (0..2^32-1); a key belongs to the first node clockwise from its hash. Adding/removing a node only remaps ~K/N keys instead of nearly all of them, which is what makes distributed stores elastically scalable.

## Quick Reference

| Aspect | Plain Modulo (`hash(key) % N`) | Consistent Hashing |
|---|---|---|
| Keys remapped on node add/remove | ~100% (all keys, since N changes) | ~1/N (only keys owned by adjacent node) |
| Distribution evenness (1 token/node) | N/A | Poor — hot ranges, needs virtual nodes |
| Distribution evenness (100-256 vnodes/node) | N/A | Good, stddev ~1/sqrt(vnodes) |
| Lookup cost | O(1) | O(log N) via sorted ring (binary search) |
| Used by | Naive sharding, memcached (old) | Cassandra, DynamoDB, Riak, memcached (ketama), Akamai CDN |
| Replica placement | Separate logic needed | Walk ring clockwise, pick next N-1 distinct physical nodes |
| Ring size (typical) | — | 2^32 (32-bit hash, e.g., MurmurHash3) or 2^63 (Cassandra tokens) |

## What It Is

- A technique to distribute keys across a changing set of nodes while minimizing reshuffling when nodes join/leave.
- Both **nodes** and **keys** are hashed into the *same* circular space (a "ring"). A key is owned by the first node encountered walking clockwise from the key's hash position.
- Originally from the 1997 Karger et al. paper (MIT) for web cache load balancing (Akamai); later foundational to Dynamo (2007) and everything downstream of it (Cassandra, Riak, DynamoDB internals).

## Responsibilities

- **Partitioning/sharding**: deterministically decide which node(s) own a given key without a central lookup table for every key.
- **Minimizing churn**: bound the blast radius of topology changes (node failure, scale-out, rebalancing) to a small fraction of data.
- **Enabling replication**: provide a natural, deterministic way to pick N-1 additional replica nodes (the next distinct nodes clockwise).
- **Load balancing**: spread keys roughly evenly across heterogeneous or growing node sets.

## How It Works

1. Choose a hash function (MurmurHash3, MD5, SHA-1) producing a fixed-size output space, e.g., 0 to 2^32-1, arranged as a circle.
2. Hash each physical node's identifier (IP:port, node ID) → position on the ring.
3. Hash each key → position on the ring.
4. Key's owner = first node found walking clockwise from the key's position (`ring.ceilingEntry(hash(key))`, wrapping to the first node if none found).
5. **Node join**: new node N_new takes ownership of the arc between itself and its counter-clockwise neighbor. Only keys in that arc move (from the neighbor to N_new) — everything else is untouched.
6. **Node leave/failure**: its arc merges into the next clockwise node; only that node's data needs redistribution/re-replication.
7. Implementation: sorted map/skip-list of ring positions → node; lookup is a binary search (`O(log N)`), not a linear scan.

```
        node C
      .-------.
   key3        node D
    |            |
  (ring)        key4
    |            |
   node B      key5
      '-------'
        node A ← key1 lands here, key2 lands at B
```

### Why ~1/N keys move, not all

- Plain modulo: `hash(key) % N` — changing N from 4 to 5 changes the modulus for *nearly every key*, causing a full cache stampede / full data reshuffle.
- Ring approach: only the arc adjacent to the changed node is affected; all other arcs (and their key ownership) are structurally unchanged. Expected fraction moved ≈ 1/N for adding the (N+1)th node.

## Types / Classifications

- **Single-token ring** (1 position per node): simple but causes uneven load — one node can get a disproportionately large/small arc, especially with few nodes.
- **Virtual nodes (vnodes)**: each physical node is hashed to many positions (e.g., 100–256 tokens in Cassandra, configurable via `num_tokens`). Benefits:
  - Smooths distribution (law of large numbers over many small arcs instead of one big arc).
  - Faster, more even rebalancing — a joining node's vnodes steal small slices from *many* peers instead of one big slice from one peer, parallelizing data streaming.
  - Handles heterogeneous hardware: give beefier nodes more vnodes (weighted consistent hashing).
- **Bounded-load consistent hashing** (Google, 2016): adds a load cap per node during lookup to avoid hotspotting even with skewed key popularity.
- **Rendezvous hashing (HRW)**: alternative to ring-based CH — compute `hash(key, node)` for every node, pick max; O(N) per lookup but no ring data structure, sometimes simpler, used in some CDN/sharding designs.
- **Jump Consistent Hash** (Google, 2014): O(1) memory, no ring, but only supports adding/removing the *last* node (ordered bucket list) — great for stateless sharding, not for arbitrary node removal.

## Where It Fits

- **Client or coordinator layer** in a distributed KV/wide-column store: determines which node(s) to route a read/write to (Cassandra's partitioner, DynamoDB's internal partition map).
- **Load balancers / CDNs**: consistent hashing at L7 (e.g., NGINX `hash $uri consistent`, Envoy's ring-hash load balancer) to keep cache-key affinity stable as backend pool resizes.
- **Distributed caches**: memcached client libraries (ketama) hash cache keys to server list so restarting one server doesn't invalidate the whole cache.
- Sits below the replication/consistency layer (quorum reads/writes, vector clocks/LWW) but above raw storage engines (SSTables, B-trees).

## Common Patterns & Real-World Tools

| System | Ring detail | Replica placement |
|---|---|---|
| **Cassandra** | Each node gets `num_tokens` (default 16, historically 256) random tokens on a 2^63 ring; `Murmur3Partitioner` default | Walk ring clockwise from key's primary token, pick next N-1 *distinct physical nodes* (skipping vnodes on same node/rack for `NetworkTopologyStrategy`) |
| **DynamoDB** (and Riak, based on Dynamo paper) | Conceptually a ring internally; partitions map to storage nodes | "Preference list" = N nodes clockwise from key; used for sipload W/R quorum ops |
| **Riak** | 160-bit ring, default 64 vnodes (partitions) regardless of node count | N-value replicas placed at next N vnodes clockwise, preferably on distinct physical nodes |
| **memcached (ketama)** | Client-side library hashes server list + keys onto a ring | No replication — pure sharding for cache lookup |
| **Envoy / Maglev (Google)** | Ring-hash or Maglev consistent hashing LB policy | Used for session affinity to backend pods |

## Pros & Cons / Trade-offs

**Pros**
- Minimal data movement on scale-out/scale-in — critical for online rebalancing without downtime.
- Decentralized: any client/coordinator can compute ownership without a central registry (given a shared ring/token view, e.g., via gossip).
- Naturally extends to replica placement (N-1 next distinct nodes) — one mechanism for both sharding and replication.

**Cons**
- Single-token ring gives uneven load (can be 100%+ variance with few nodes) — mandates vnodes, which adds bookkeeping overhead.
- Lookup is O(log N) vs O(1) for modulo — negligible in practice but non-zero.
- Vnodes increase rebalancing *fan-out*: a node join/leave touches data on many peers simultaneously, which can spike I/O/network during large topology changes (mitigated by streaming throttles in Cassandra).
- Doesn't account for real-time load/heat by default — a "popular key" can still overload its owning node (needs bounded-load variant or read replicas/caching in front).
- Hash function choice matters: weak hash → clustering/collisions on the ring, defeating evenness.

## Real-World Scenarios

- **Cassandra cluster scale-out**: add a node to a 10-node ring; with vnodes it streams roughly 1/11th of the ring's data from many peers in parallel rather than a single massive bootstrap from one neighbor.
- **Memcached fleet resize**: losing 1 of 20 cache servers with modulo hashing invalidates ~100% of cache (mass cache stampede to DB); with ketama consistent hashing only ~5% of keys remap.
- **Multi-region DynamoDB-style store**: replica list per key spans nodes in different racks/AZs (topology-aware placement layered on top of the ring) so a rack failure doesn't lose all N replicas of any key.
- **Envoy ring-hash LB for stateful gRPC streams**: keeps the same backend for a client's session even as pods autoscale, avoiding session-store lookups.

## Nuances & Gotchas

- **Vnode count tuning is a real production lever**: Cassandra 3.x lowered default `num_tokens` from 256 to 16 after finding 256 caused excessive streaming fan-out and slow repairs on large clusters — more vnodes = smoother balance but worse operational blast radius per topology change.
- **Rack/AZ awareness is not automatic**: naive "next N clockwise nodes" can place all replicas in the same rack if node placement isn't randomized — Cassandra's `NetworkTopologyStrategy` and Riak's replica placement explicitly skip nodes to enforce diversity.
- **Hot keys/hot partitions still happen**: consistent hashing balances *key count*, not *request rate*. A celebrity key (viral post ID) can saturate one partition regardless of ring math — needs application-level sharding suffixes or caching.
- **Token/vnode metadata drift**: if nodes disagree on ring state (stale gossip), reads/writes can go to wrong replicas — quorum reads (R+W>N) mask this but repair (`nodetool repair`) is still needed to fix entropy.
- **Bootstrapping storms**: joining node with vnodes pulls data from many sources at once; without `streaming_socket_timeout`/throttling this can saturate cluster network bandwidth and cause latency spikes on unrelated traffic.
- **Hash collisions and skew**: MD5/SHA are fine, but a poor or non-uniform hash (e.g., raw key prefixes without hashing) reintroduces exactly the skew consistent hashing was meant to solve.
- **Adding many nodes at once vs one at a time**: doubling cluster size in one shot with vnodes is efficient (theoretical ~50% data movement, unavoidable), but doing it incrementally still triggers full streaming per node — batch/parallel bootstrap tooling matters at scale.
- **Client-side vs server-side ring**: memcached's consistent hashing lives in the *client library* — if different app instances use different library versions/configs, they compute different rings and silently miss each other's cache entries.
- **Virtual node ID collisions**: extremely rare but hashing two different node identifiers to the same ring position needs explicit tie-breaking (e.g., secondary hash or lexicographic ID compare) or one node silently loses its slot.
