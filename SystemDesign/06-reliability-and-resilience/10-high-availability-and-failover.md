# High Availability and Failover

> **TL;DR:** HA eliminates single points of failure via redundancy (active-passive or active-active) across AZs/regions; failover only works if failure detection is accurate and old primaries are provably dead (fencing) — otherwise you trade downtime for split-brain corruption.

## Quick Reference

| Concept | Key Fact |
|---|---|
| VRRP | Virtual Router Redundancy Protocol — election via priority, virtual IP moves on failure |
| keepalived | Linux VRRP implementation, ~1-3s failover via multicast heartbeats |
| STONITH | "Shoot The Other Node In The Head" — forcibly kill/power-off suspect primary before promoting new one |
| Fencing | Any mechanism (STONITH, storage fencing, network isolation) preventing a zombie node from acting as primary |
| RTO | Recovery Time Objective — max acceptable downtime |
| RPO | Recovery Point Objective — max acceptable data loss window |
| Typical automatic failover | 10-60s (detection) + 1-30s (decision/quorum) + seconds-minutes (promotion) + 0-300s (DNS TTL) |
| Multi-AZ | Sub-10ms latency, sync replication feasible, single-region blast radius |
| Multi-region | 50-150ms+ latency, usually async replication, survives region-wide outage |
| Split-brain | Two nodes both believe they're primary — usually from network partition, not real failure |

## What It Is
- Architecture designed so a component failure does not cause service outage — measured in "nines" (99.9% = 8.7h/yr downtime, 99.99% = 52min/yr).
- Failover = the mechanism that detects a failure and redirects traffic/promotes a standby to maintain availability.
- HA is not fault-tolerance: HA tolerates brief disruption + recovery; fault-tolerant systems mask failure with zero interruption (much more expensive, e.g. lockstep hardware).

## Responsibilities
- Detect failure quickly without false positives (health checks, heartbeats).
- Decide there's actually a failure and reach consensus (avoid partition-induced bad decisions).
- Promote a standby / reroute traffic to a healthy node.
- Fence/isolate the old primary so it can't accept writes concurrently with the new one.
- Propagate the new topology to clients (DNS, load balancer, service discovery, connection strings).

## How It Works
### Active-Passive (VRRP/keepalived)
- Passive node sits idle (or read-only replica), sends/receives heartbeats to/from active.
- keepalived nodes negotiate a Virtual IP (VIP) via VRRP; master owns VIP, advertises priority every ~1s.
- On missed advertisements (default ~3 intervals), backup promotes itself, gratuitous ARP claims VIP — clients see no config change, just a network-layer switch.
- Simple, but passive capacity is wasted and failover still has a detection window (typically 1-3s for VRRP, longer for app-level checks).

### Active-Active
- All nodes serve traffic simultaneously; load balancer (or client-side routing) spreads load.
- Failure of one node = load balancer stops routing to it (health check fails), remaining nodes absorb load — no promotion step needed, just capacity re-routing.
- Requires state to be shareable or partition-tolerant (shared DB, distributed cache like Redis Cluster, or stateless nodes) — this is the hard part, not the routing.

### Automatic Failover Sequence
```
[Heartbeat miss] -> [Confirm N consecutive failures] -> [Quorum/decision]
   -> [Fence old primary] -> [Promote new primary] -> [Update routing/DNS]
   -> [Clients reconnect]
```
- Each arrow is latency. A "30-second failover" marketing claim usually only covers detection+promotion, not client reconnect or DNS propagation.

### Fencing / STONITH
- Problem: health check failing ≠ node is dead. Could be a network partition where the primary is alive and still accepting writes.
- Promoting a new primary without fencing the old one = two primaries both think they own the data = split-brain = divergent/corrupted state.
- STONITH: standby issues an out-of-band power-off/reboot command (IPMI, cloud API `StopInstance`, PDU power cycle) to the suspect node before promoting itself.
- Storage-level fencing alternative: revoke the old primary's access to shared storage/SAN LUN (used in Pacemaker/DRBD, Oracle RAC).
- Quorum-based fencing: only a node that can see a majority of cluster members (etcd, Consul, Zookeeper) is allowed to promote — minority partition self-demotes instead of assuming it's fine.

## Types / Classifications
| Pattern | Failover Trigger | Data Consistency | Example Tech |
|---|---|---|---|
| Active-Passive (VIP) | Heartbeat loss | Sync or async replication | keepalived, Pacemaker+Corosync, Windows Failover Cluster |
| Active-Active | LB health check | Requires conflict-free state or CRDTs | HAProxy/NGINX + stateless app tier, Cassandra |
| Multi-AZ | AZ health signal | Sync replication (low latency) | RDS Multi-AZ, Aurora, GCP regional persistent disk |
| Multi-region | Region outage / manual or automated DNS failover | Async replication (higher RPO) | Route 53 health checks + failover routing, Cosmos DB multi-region writes |
| Consensus-based | Loss of leader heartbeat in Raft/Paxos | Strong (majority ack before commit) | etcd, Zookeeper, Kafka (KRaft), CockroachDB |

## Where It Fits
- Sits below the load balancer/DNS layer and above raw infrastructure: LB/DNS decide *where* traffic goes, HA cluster logic decides *what's currently healthy*.
- Database tier: primary-replica with automated failover (Patroni for Postgres, MHA/Orchestrator for MySQL, Aurora's built-in failover ~30s).
- Stateless app tier: HA is mostly "just add more instances behind a load balancer" — active-active by default, no promotion logic needed.
- Network edge: VRRP/keepalived commonly front load balancers themselves (HAProxy pair with VIP) so the LB isn't itself a SPOF.

## Common Patterns & Real-World Tools
- **Patroni** (Postgres): uses etcd/Consul/Zookeeper for consensus, handles fencing via `pg_rewind` and connection blocking, typical failover 10-30s.
- **Pacemaker + Corosync**: general-purpose Linux HA cluster manager, native STONITH plugins for IPMI/cloud/vCenter.
- **AWS RDS Multi-AZ**: synchronous standby, DNS CNAME flip on failure, ~60-120s typical RTO.
- **Route 53 health checks + failover routing policy**: DNS-based cross-region failover; real RTO gated by client-side DNS TTL/caching (can be minutes despite low TTL due to resolver caching).
- **Kafka (KRaft/ZooKeeper)**: controller election on broker loss via Raft, in-sync replica (ISR) promotion, avoids split-brain via epoch/leader-fencing tokens.
- **MongoDB replica sets**: automatic primary election via Raft-like protocol, needs odd number of voting members to avoid ties.

## Pros & Cons / Trade-offs
| Approach | Pros | Cons |
|---|---|---|
| Fast auto-failover (short timeouts) | Low RTO | High false-positive rate → flapping, unnecessary failovers under transient GC pause/network blip |
| Slow/conservative failover | Fewer false positives | Longer real outages, higher RTO |
| Active-passive | Simple consistency story | Wastes standby capacity, promotion step adds latency |
| Active-active | No promotion delay, better resource use | Requires solving distributed state/conflict resolution — much harder |
| Automatic failover | No human in the loop, fast | Risk of split-brain, wrong-decision cascades (thundering herd on remaining nodes) |
| Manual failover | Human judgment prevents bad auto-decisions | RTO bounded by on-call response time (minutes to tens of minutes) |

## Real-World Scenarios
- **GitHub Oct 2018 incident**: 43-second network partition caused MySQL orchestrator to promote a new primary in the wrong DC while old primary kept accepting writes briefly — resulted in data reconciliation taking 24+ hours despite the "failover" itself being fast.
- **Postgres/Patroni without fencing**: old primary on a stalled-but-alive node keeps serving reads/writes to clients that haven't yet been rerouted; new primary also accepts writes → diverged WAL, manual `pg_rewind` needed.
- **DNS failover with long-lived resolver caches**: Route 53 TTL set to 60s, but corporate resolvers/browsers cache for 300s+, so effective RTO is 5-10x the configured TTL.
- **VRRP flapping under CPU load**: garbage collection pause on active node delays VRRP advertisement past the dead-interval, backup takes over VIP, active recovers and reclaims it seconds later — repeated flapping causes connection resets and ARP cache thrashing across the LAN.

## Nuances & Gotchas
- **False positives are the real enemy, not slow detection.** Aggressive health-check thresholds (e.g., 2 missed checks = failover) look great in RTO SLAs but cause flapping storms during routine GC pauses, deploys, or transient packet loss — each flap causes a connection storm as clients reconnect.
- **A health check failing is not proof of death.** Network partitions produce identical symptoms to real node failure from the observer's side — this is why fencing/STONITH is non-negotiable for stateful systems, not an optional hardening step.
- **Quorum size matters more than node count.** A 2-node cluster cannot safely auto-fail over (no majority possible) — this is why etcd/Zookeeper require odd numbers (3, 5) and why 2-node keepalived setups often need a third arbitrator or manual tie-break.
- **Real RTO = sum of every hop, not just "failover time."** Detection window (health check interval × failure threshold) + decision/quorum round-trip + fencing command latency (cloud API calls can take 5-30s) + promotion (WAL replay, cache warm-up) + client-side reconnect/DNS TTL — teams that only measure "time to elect new primary" chronically underestimate real user-facing downtime by 2-5x.
- **Cache/connection pool amnesia after failover.** New primary has a cold buffer cache/query plan cache — post-failover latency spikes even after routing is fixed, sometimes worse than the outage itself for read-heavy workloads.
- **Split-brain damage is often silent.** Divergent writes during a split-brain window may not surface until much later (e.g., duplicate order IDs, lost updates) — reconciliation cost frequently exceeds the cost of the original outage.
- **Multi-region failover changes your consistency model, not just your topology.** Async cross-region replication means failover always has nonzero RPO — decide and document acceptable data-loss window before an incident, not during one.
- **Test failover regularly (game days/chaos engineering).** Untested failover automation is a liability — Netflix's Chaos Monkey philosophy exists because failover code paths rot and silently break when nobody exercises them for months.
