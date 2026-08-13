# Fault Tolerance and Redundancy

> **TL;DR:** Faults are inevitable; failures are optional. Redundancy converts independent component faults into masked errors, but the masking math collapses the moment failures correlate — so design for graceful degradation, not just duplication.

## Quick Reference

| Concept | Definition | Key number/mechanism |
|---|---|---|
| Fault | Root cause defect (disk sector dies, bit flips) | Latent, may never trigger |
| Error | Internal state deviates from correct (wrong checksum) | Detectable via checks/CRC |
| Failure | System stops delivering correct service externally | Visible to user/SLA |
| Active-active | All nodes serve traffic concurrently | RTO ~0s, 2x+ cost, needs idempotency |
| Active-passive | Standby node(s) idle until failover | RTO seconds–minutes, 2x cost, simpler |
| N+1 | One spare beyond capacity needed | Survives 1 failure, ~1/(N+1) extra cost |
| N+2 | Two spares beyond capacity | Survives 2 simultaneous failures |
| 2N | Full duplicate capacity | 100% overhead, active-active or hot standby |
| Independence assumption | P(all fail) = P(fail)^n | Breaks under correlated failures |

## What It Is

- **Fault**: a defect or anomaly in a component (bad RAM cell, buggy code path, expired cert). Exists whether or not it's ever exercised.
- **Error**: the fault is triggered and produces an incorrect internal state (a corrupted in-memory value, a miscalculated checksum). Not yet visible outside the system.
- **Failure**: the error propagates to the system boundary and the service deviates from its spec (500s returned, wrong balance shown, timeout). This is what SLAs measure.
- Chain: **Fault → Error → Failure**. Fault tolerance means the chain is broken at "Error" — the system detects/masks the error before it becomes a failure.
- Redundancy is the primary mechanism for breaking that chain: duplicate a component so one instance's fault doesn't propagate to a system-level failure.

## Responsibilities

- Detect faults early (health checks, CRCs, heartbeats) before they become failures.
- Contain blast radius (bulkheads, cell-based architecture, circuit breakers) so one faulty component doesn't cascade.
- Mask errors via redundancy (retry on replica, quorum reads, error-correcting codes).
- Degrade gracefully when full masking isn't possible — shed low-priority work, serve stale/cached data, return partial results.
- Recover state and rejoin redundant pool automatically (self-healing, auto-scaling replacement).

## How It Works

1. **Detection**: heartbeats (etcd/Consul), TCP health checks (ELB/ALB), application-level probes (Kubernetes liveness/readiness).
2. **Isolation**: circuit breaker (Hystrix/resilience4j) trips to stop calling a failing dependency; bulkhead pools (separate thread pools per dependency) prevent thread starvation from spreading.
3. **Redirection**: load balancer removes unhealthy node from rotation; DNS failover (Route 53) or VRRP/keepalived moves virtual IP to standby.
4. **Masking**: quorum protocols (Raft, Paxos) tolerate f failures out of 2f+1 nodes; erasure coding (Reed-Solomon in S3, HDFS) reconstructs data from partial shards.
5. **Recovery**: replace failed instance (ASG), replay from WAL/log (Kafka, Postgres), resync replica (streaming replication).

```
Fault (disk bit rot)
   -> Error (checksum mismatch, in-memory corrupt page)
      -> [redundancy/detection breaks chain here]
         -> Failure (client sees error/wrong data)  <-- goal: never reach this
```

## Types / Classifications

**Redundancy topology:**
- **Active-active**: every replica handles live traffic (multi-region API behind global LB, Cassandra multi-DC). Zero failover time, but requires idempotent writes, conflict resolution (CRDTs, last-write-wins), and doubles/triples steady-state cost.
- **Active-passive (hot/warm/cold standby)**: primary serves, standby replicates but doesn't serve. Postgres streaming replication with pg_auto_failover; RTO ranges from seconds (hot standby, replicated state) to hours (cold standby, restore from backup).
- **N+1**: capacity for N units of load plus exactly 1 spare unit. Standard for stateless app tiers, power supplies, web server fleets. Tolerates exactly one concurrent failure.
- **N+2**: two spares — used when failure + planned maintenance can overlap, or MTTR is long enough that a second failure is plausible before the first is fixed. Common in power/cooling (data center UPS design) and critical quorum systems.
- **2N / 2N+1**: fully duplicated redundant systems (data center dual power feeds), highest cost, used for tier-4 infra.

**By what's duplicated:** hardware (RAID, dual PSUs), data (replicas, backups), compute (multi-AZ instances), network paths (multi-homed BGP), geography (multi-region).

## Where It Fits

- **Load balancer layer**: health-checked pool of N+1 backends (NGINX upstream, AWS ALB target groups).
- **Data layer**: leader-follower replication (MySQL, Postgres) or leaderless quorum (Cassandra, DynamoDB) with replication factor 3 as the de facto standard (tolerates 1 node loss with quorum reads/writes).
- **Consensus layer**: Raft/Paxos clusters (etcd, ZooKeeper, Kafka controller) sized as 2f+1 to tolerate f faults — 3 nodes tolerate 1, 5 tolerate 2.
- **Infra layer**: multi-AZ deployment (AWS), multi-region DR (active-passive with Route 53 failover or active-active with Global Accelerator).
- **Power/network**: redundant PSUs, dual ToR switches, diverse fiber paths — the physical N+1/2N layer everything above sits on.

## Common Patterns & Real-World Tools

| Pattern | Tool/Example |
|---|---|
| Leader election + failover | ZooKeeper, etcd Raft, Patroni for Postgres HA |
| Quorum replication | Cassandra RF=3 with QUORUM reads/writes, DynamoDB |
| Circuit breaker | resilience4j, Netflix Hystrix (legacy), Envoy outlier detection |
| Bulkhead isolation | Separate thread pools / connection pools per downstream |
| Erasure coding | S3 (11 nines via Reed-Solomon-like schemes), HDFS EC |
| Multi-AZ hot standby | RDS Multi-AZ, Aurora with 6-way replication across 3 AZs |
| Graceful degradation | Netflix serving cached recommendations when personalization service is down |
| Load shedding | Rate limiting + priority queues (drop low-priority requests first) |

## Pros & Cons / Trade-offs

| Approach | Recovery Time | Cost | Complexity | Notes |
|---|---|---|---|---|
| Active-active | ~0 (no failover) | Highest (full extra capacity always running) | High (conflict resolution, idempotency) | Best RTO/RPO, hardest to build correctly |
| Active-passive hot standby | Seconds | High (standby fully provisioned, idle) | Medium | Common default for RDBMS HA |
| Active-passive warm/cold | Minutes–hours | Lower | Lower | Acceptable for DR tier, not primary HA |
| N+1 | Depends on detection+reroute speed | Low overhead (~1/N extra) | Low | Fine when failures are rare & independent |
| N+2 | Same as N+1 but survives double fault | Higher overhead | Low-Medium | Needed when MTTR is long relative to MTBF |

- General trade-off: **lower RTO/RPO costs more money and more engineering complexity** (conflict resolution, data consistency, testing failover paths regularly — e.g., Netflix Chaos Monkey / GameDay).
- Redundancy protects against *component* failure, not against *correlated* failure or bad deploys (a bug pushed to all active-active nodes fails everywhere simultaneously).

## Real-World Scenarios

- **Postgres HA**: primary + 2 synchronous replicas (N+1 within a quorum), Patroni handles leader election on primary failure — RTO ~10-30s.
- **S3 durability**: data erasure-coded across multiple AZs/facilities; tolerates concurrent loss of multiple devices without data loss (not just "1 copy fails").
- **AWS region-level DR**: active-passive across regions using Route 53 health-check failover; RPO/RTO measured in minutes because cross-region replication lags.
- **Netflix graceful degradation**: if the recommendation microservice fails, homepage falls back to a generic/cached "trending now" list instead of a blank page or 500 — availability preserved, quality reduced.
- **Kubernetes**: Pod Disruption Budgets + multiple replicas ensure N+1 during voluntary disruptions (node drains, rolling upgrades), separate from failure-driven redundancy.

## Nuances & Gotchas

- **Independence assumption is usually false.** Redundancy math (`P(system down) = P(node down)^n`) assumes failures are statistically independent. In reality: shared power circuit, shared rack, shared AZ, shared cloud region, shared config/deploy pipeline, shared software bug — any of these correlate failures and silently erase your "five nines" calculation. A 3-replica DB all in one AZ is not N+2 protection, it's N+0 against an AZ outage.
- **Correlated failure classes to check for**: simultaneous deploy of buggy config to all replicas (config-as-code pushed everywhere at once), a shared certificate expiring, a shared upstream dependency (DNS, auth service) that all "independent" nodes call, a cascading retry storm where failover load itself takes down the survivors (thundering herd on failover).
- **Failover mechanism itself is a single point of failure**: DNS TTL caching delays failover; VIP/keepalived split-brain can cause two nodes to think they're primary simultaneously and corrupt data.
- **Standby drift**: passive replicas that are never tested (no regular failover drills / chaos testing) often fail to actually take over when needed — untested redundancy is not redundancy.
- **Graceful degradation requires upfront design**, not an afterthought: define priority tiers of functionality (must-serve vs nice-to-have), build fallback paths (cached/stale data, feature flags to disable non-critical features under load) — bolting this on during an incident rarely works.
- **All-or-nothing anti-pattern**: a monolithic health check that marks the whole service "down" because one non-critical dependency (e.g., analytics) is unhealthy wastes redundancy — decouple critical-path failures from cosmetic ones.
- **Cost of masking too well**: perfect error masking can hide a slowly worsening fault (e.g., a degraded disk in RAID silently rebuilding again and again) until multiple faults coincide and cause an unmasked failure — monitor redundancy consumption (spares used), not just current uptime.
- **N+1 vs N+2 decision hinges on MTTR, not just MTBF**: if mean time to repair a failed unit is long (days, e.g., hardware RMA), the probability of a second concurrent failure rises — N+2 or faster automated replacement becomes necessary even with low individual failure rates.
