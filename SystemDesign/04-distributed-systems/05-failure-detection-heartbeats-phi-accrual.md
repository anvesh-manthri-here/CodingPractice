# Failure Detection — Heartbeats and Phi-Accrual

> **TL;DR:** Fixed-timeout heartbeats treat failure as binary and either miss failures (timeout too long) or cry wolf under jitter (timeout too short); phi-accrual failure detection instead outputs a continuous suspicion level from a statistical model of past heartbeat intervals, letting each application pick its own risk threshold.

## Quick Reference

| Aspect | Fixed Timeout | Phi-Accrual (φ-accrual) |
|---|---|---|
| Output | Boolean: alive / dead | Continuous suspicion score φ |
| Model | Static threshold (e.g. 5s) | Sliding window of inter-arrival times, fit to distribution |
| Adapts to jitter | No | Yes (recalculates mean/variance continuously) |
| False positives under GC/network blips | High | Low (threshold self-adjusts) |
| Used by | Naive systems, basic health checks | Cassandra, Akka Cluster, Azure Service Fabric |
| Tuning knob | Timeout duration | φ threshold (e.g. 8–12), window size |
| Typical φ formula | N/A | φ = -log10(P(time_since_last_heartbeat)) |
| Detection speed vs accuracy | Fixed trade-off | Tunable per-consumer via threshold |

## What It Is

- **Failure detection**: mechanism by which one node determines that another node/process is unreachable or dead, without a reliable global signal (no shared clock, unbounded message delay per FLP/CAP realities).
- **Heartbeat**: periodic "I'm alive" message (or absence of a NACK) sent by a monitored process to a monitor, over a fixed interval (e.g. every 1s).
- **Phi-accrual detector**: introduced by Hayashibara et al. (2004), used in Cassandra's gossip subsystem — instead of a yes/no verdict, it computes a suspicion level (φ) that increases smoothly as time since last heartbeat grows relative to historical statistics.

## Responsibilities

- Distinguish "node crashed" from "node slow / network partitioned / GC paused" — cannot actually be done with certainty (this is the crux of the problem, per the impossibility of perfect failure detection in async networks).
- Feed cluster membership systems (gossip, SWIM, Raft leader election) with timely-enough signals to trigger failover, re-replication, or leader re-election.
- Balance two competing costs: **missed/slow detection** (stale routing, unavailable service) vs **false positives** (unnecessary failover, split-brain risk, flapping).

## How It Works

### Fixed-timeout heartbeat
1. Node B sends heartbeat to A every `T` interval.
2. A declares B dead if no heartbeat received within `timeout` (commonly `3×T` to `5×T`).
3. Single global constant applied to every node regardless of actual network conditions.

### Phi-accrual
1. Monitor keeps a sliding window (e.g. last 1000 or last N seconds) of inter-arrival times between heartbeats from a given node.
2. Computes mean and variance of these intervals — models arrival time distribution (original paper assumes normal; Cassandra uses a simplified exponential/sampling approach).
3. On each check, compute `φ = -log10(1 - CDF(time_since_last_heartbeat))` — how improbable the current silence is, given history.
4. φ scales logarithmically: φ=1 → ~10% chance of false positive, φ=2 → ~1%, φ=3 → ~0.1%. Consumers pick a threshold (Cassandra default `phi_convict_threshold = 8`).
5. As silence continues, φ climbs continuously — no discrete "timeout moment," just crossing a chosen risk line.

```
heartbeat gaps:  |--1s--|--1s--|--1.1s--|-------?-------
                                          φ rises smoothly
                                          cross threshold -> suspect
```

## Types / Classifications

- **Push-based heartbeat**: monitored node actively sends "I'm alive" (most common; used by Cassandra gossip, Akka).
- **Pull-based / ping**: monitor actively polls (health checks, Kubernetes liveness probes via HTTP/TCP).
- **Binary detectors**: fixed timeout, TCP keepalive, Kubernetes `livenessProbe` failureThreshold — simple, brittle.
- **Adaptive/statistical detectors**: phi-accrual (Cassandra, Akka), Chen's accrual variant, SWIM's adaptive suspicion with indirect probing (used by Consul, Serf/HashiCorp memberlist).
- **Consensus-mediated detection**: failure suspicion escalated through gossip/quorum before action (SWIM, Raft) — reduces single-observer false positives.

## Where It Fits

- Gossip protocols (Cassandra, Akka Cluster, Consul via Serf) use failure detectors as the raw signal feeding membership state machines (alive → suspect → dead → removed).
- Leader election (Raft, ZooKeeper, etcd) relies on session/heartbeat timeouts to trigger re-election — often still fixed-timeout based, which is why election timeouts are randomized (150–300ms range) to avoid split votes, not phi-accrual.
- Load balancers / service mesh (Envoy outlier detection, Kubernetes readiness probes) use simpler windowed-failure-count detectors, a cousin of accrual detection.
- Sits below membership/consensus layers: failure detector answers "is it there?"; consensus layer decides "what do we do about it?"

## Common Patterns & Real-World Tools

| Tool | Detector style | Notes |
|---|---|---|
| Cassandra | Phi-accrual (per-node, `phi_convict_threshold`) | Each node runs its own detector per peer; no global truth. |
| Akka Cluster | Phi-accrual (`akka.cluster.failure-detector`) | Threshold default 8.0, acceptable-heartbeat-pause configurable. |
| SWIM (Consul, Serf) | Suspicion + indirect probing via random peers | Suspicion mechanism dampens false positives without full stats model. |
| Kubernetes | Fixed timeout (liveness/readiness probes) | `failureThreshold × periodSeconds`; simple, tuned per workload. |
| ZooKeeper/etcd | Session timeout (fixed) | Ephemeral node/lease expiry; short timeouts (~ seconds) trade availability for detection speed. |
| Azure Service Fabric | Phi-accrual variant | Adaptive to cross-region latency variance. |

## Pros & Cons / Trade-offs

**Fixed timeout**
- (+) Trivial to implement/reason about; deterministic.
- (-) One constant can't fit all network conditions — LAN vs cross-region WAN vs bursty GC pauses.
- (-) Forces a hard choice: short timeout = fast but false-positive-prone; long timeout = safe but slow failover.

**Phi-accrual**
- (+) Self-tunes to each link's actual latency/jitter profile — a node with historically noisy network naturally gets more slack.
- (+) Decouples "detection mechanism" from "action policy" — different subsystems can use different φ thresholds off the same data.
- (+) Smooth output enables richer decisions (e.g., "mark read-only" at φ=5, "evict" at φ=10) instead of a single cliff.
- (-) More complex; requires enough history/samples to be statistically meaningful (cold start problem for new nodes).
- (-) Assumes some stable underlying distribution — sudden regime shifts (network reconfig, new WAN path) cause temporary misfires until window refills.
- (-) Still fundamentally guessing — can't distinguish "dead" from "partitioned but alive," same as any detector (FLP impossibility applies).

## Real-World Scenarios

- **Cassandra rolling GC pause**: A JVM node hits a 4s stop-the-world GC. Fixed 3s timeout would evict it from the ring, triggering unnecessary hinted handoff/repair traffic. Phi-accrual, having observed prior minor GC blips in the window, tolerates the pause without crossing threshold 8.
- **Cross-region cluster**: Node pair with 150ms RTT and high variance (transatlantic link) vs local pair with 1ms RTT — a single fixed timeout either falsely convicts the WAN pair constantly or is too slow to catch real LAN failures. Phi-accrual maintains separate stats per peer pair.
- **Kubernetes flapping pod**: Fixed liveness probe with `failureThreshold: 1` restarts pods on single missed check during a brief CPU throttle event — classic false-positive/thrashing failure mode from binary detection, mitigated by raising failureThreshold or switching to windowed counting.
- **Split-brain near-miss**: Two DC's lose WAN link; each side's phi-accrual detectors correctly suspect the other, but without a quorum/consensus layer on top, both sides could independently "elect" a new primary — detector alone never solves partition ambiguity, only informs it.

## Nuances & Gotchas

- **Detection is inherently probabilistic, not certain** — the FLP impossibility result means no algorithm can reliably distinguish "crashed" from "arbitrarily slow" in an asynchronous network with unbounded delay. Every detector (including phi-accrual) is really a *timeout with better statistics*, not a proof of death.
- **Cold-start blind spot**: a newly joined node has no interval history — phi-accrual detectors often default to a lenient bootstrap phase, which itself can mask early real failures.
- **Window size trade-off**: too small a sliding window overreacts to a single slow heartbeat (spurious φ spike); too large a window is slow to adapt to a genuine regime change (node moved to a busier host).
- **Correlated failures defeat local detectors**: if the monitor's own process/host is under load (GC, CPU steal in a noisy-neighbor VM), it may misjudge arrival times entirely — detector accuracy assumes the *observer* itself is timely.
- **Threshold tuning is a business decision disguised as a config value**: Cassandra's `phi_convict_threshold=8` (~10^-8 false-positive chance per check) is conservative for a stateful store; a stateless web tier can tolerate a much lower threshold for faster failover.
- **Detectors don't prevent split-brain by themselves** — must be paired with quorum/consensus (Raft term/lease, ZK ephemeral+session, Cassandra hinted handoff + repair) so two "suspicions" don't independently trigger conflicting writes.
- **Randomized timeouts matter even in "fixed" systems**: Raft's randomized election timeout (150–300ms) is a crude but effective decorrelation trick to avoid synchronized false suspicion across replicas — a cheap partial answer to what phi-accrual solves more rigorously.
- **Heartbeat storms at scale**: naive all-to-all heartbeating is O(n²) messages; gossip-based dissemination (SWIM, Cassandra gossip) piggybacks failure info on regular gossip rounds instead of dedicated heartbeat channels, capping overhead as cluster grows.
- **Indirect probing reduces false positives further**: SWIM has suspecting nodes ask k random peers to also ping the suspect before declaring it dead — catches cases where only the direct path, not the node, is broken.
