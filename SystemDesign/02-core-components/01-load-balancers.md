# Load Balancers

> **TL;DR:** A load balancer distributes traffic across backend instances to maximize throughput, minimize latency, and avoid overload/failure of any single node — the choice of L4 vs L7, algorithm, and health-check strategy determines whether it actually helps under real failure conditions.

## Quick Reference

| Aspect | Options | Default staff-level pick |
|---|---|---|
| Layer | L4 (transport) vs L7 (application) | L7 for HTTP APIs, L4 for raw throughput/non-HTTP |
| Algorithm | RR, weighted RR, least-conn, least-response-time, P2C, consistent hash | Least-conn or P2C for uneven request costs |
| Health checks | Active (probe) vs passive (outlier detection) | Both, layered |
| Affinity | Cookie-based, IP-hash | Avoid; use only if session state can't be externalized |
| TLS | Termination vs passthrough | Termination at LB unless E2E encryption mandated |
| Scope | Local (regional LB) vs Global (GSLB/DNS/anycast) | Both, layered — GSLB routes to region, local LB to instance |
| Tools | NGINX, HAProxy, Envoy, AWS ALB/NLB, Cloudflare | Envoy for service mesh, ALB/NLB for AWS-managed, Cloudflare for edge/global |

## What It Is

- A component (software or hardware) sitting between clients and a pool of backend servers that routes each request/connection to one backend based on a policy.
- Exists at every scale: DNS-level (global), edge/CDN, per-service internal LB (sidecar/mesh), even in-process client-side LB (gRPC, Netflix Ribbon-style).
- Core value: turns a fleet of imperfect, individually-failing machines into a service with higher aggregate availability and capacity than any single node.

## Responsibilities

- Distribute load to avoid hotspotting any backend.
- Detect and route around unhealthy/slow backends (health checking, outlier ejection).
- Absorb traffic spikes via queuing/backpressure and shed load when saturated.
- Terminate/manage TLS, and optionally re-encrypt to backends (mTLS).
- Provide a stable virtual IP/DNS name decoupling clients from backend churn (scale-up/down, deploys).
- Enable zero-downtime deploys via connection draining and slow-start.

## How It Works

```
Client → [DNS/GSLB/Anycast] → [Regional LB (L4/L7)] → [Backend pool]
                                     |
                         health checks + algorithm pick
```

1. Client resolves a name (DNS/GSLB) or hits an anycast IP → routed to nearest/healthy region.
2. Regional LB accepts connection, terminates TLS (if L7), inspects request (if L7).
3. LB consults health state + load algorithm to pick a backend.
4. Forwards request; on backend failure, retries against another backend (if idempotent/safe) or fails fast.
5. Continuously polls (active) or observes live traffic (passive) to update backend health/weight.

## Types / Classifications

### L4 vs L7

| | L4 (Transport) | L7 (Application) |
|---|---|---|
| Sees | IP + TCP/UDP port, packet headers | Full HTTP: path, headers, cookies, body |
| Can't see | URL, headers, cookies | Nothing HTTP — sees everything L4 does too |
| Routing granularity | Per-connection, whole-flow | Per-request (multiplexed over one TCP conn) |
| Use cases | Raw TCP/UDP, gRPC streams, extreme throughput, DDoS-scale | Content-based routing, A/B, canary, header/path rules |
| Throughput | Higher (no parsing) | Lower (parses/buffers requests) |
| Examples | AWS NLB, IPVS, raw HAProxy TCP mode | AWS ALB, NGINX, Envoy, HAProxy HTTP mode |

### Algorithms

| Algorithm | Mechanism | Wins when | Fails when |
|---|---|---|---|
| Round robin | Cycle through backend list | Homogeneous backends, uniform request cost | Uneven backend capacity or request cost → hotspots |
| Weighted RR | RR biased by static capacity weight | Heterogeneous hardware | Weights go stale as load shifts dynamically |
| Least connections | Route to fewest active conns | Long-lived/variable-duration requests | Doesn't account for backend CPU cost per request |
| Least response time | Combines conn count + latency | Latency-sensitive, heterogeneous backend speed | Needs accurate live latency signal; noisy at low volume |
| Power of two choices (P2C) | Sample 2 random backends, pick less-loaded | Large fleets — near-optimal with O(1) cost, avoids herd effect of "always pick global min" | Small pools (little randomness benefit) |
| Consistent hashing | Hash(key) → ring position → backend | Cache affinity, sharding, minimizing remap on scale change | Uneven key distribution → hotspot shard; needs virtual nodes to smooth |

## Where It Fits

- **Edge/global tier:** DNS-based GSLB (Route53, Cloudflare) or anycast IP — routes users to nearest healthy region/PoP. Coarse-grained, slow to react (DNS TTL caching).
- **Regional/L7 tier:** ALB/NGINX/Envoy in front of a service — fine-grained, fast health reaction (seconds).
- **Internal/service mesh tier:** Envoy sidecars or client-side LB (gRPC) route service-to-service calls, often with consistent hashing for cache locality.
- **Database tier:** read-replica LBs, connection poolers (PgBouncer) — different concerns (connection reuse) but same core problem.

## Common Patterns & Real-World Tools

- **NGINX** — reverse proxy, L7, config-reload-based (not fully dynamic), widely used as ingress controller in Kubernetes.
- **HAProxy** — battle-tested L4/L7, very high performance, rich health-check config, common as the LB inside custom infra.
- **Envoy** — L7 proxy built for dynamic service discovery (xDS API), used as Kubernetes Gateway API / Istio data plane, first-class outlier detection and circuit breaking.
- **AWS ALB** — L7, HTTP/HTTPS, path/host-based routing, integrates with target groups + auto scaling.
- **AWS NLB** — L4, static IP, preserves client IP, millions of req/s, used for extreme throughput or non-HTTP (TCP/TLS/UDP).
- **Cloudflare** — global anycast edge LB + DDoS mitigation + WAF, effectively a GSLB + L7 LB combined.
- **Pattern: LB + Circuit Breaker** — Envoy/Istio pairs LB with per-backend circuit breaking to stop cascading failure.
- **Pattern: Blue/Green & Canary** — L7 LB routes % of traffic or header-matched traffic to new version.

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| L4 | Fast, protocol-agnostic, low latency | No content-aware routing, can't do path-based rules |
| L7 | Smart routing, retries, observability, TLS termination | CPU cost to parse, extra hop latency, another SPOF surface |
| Sticky sessions | Simple to bolt onto stateful legacy apps | Defeats even load distribution, complicates scale-down/deploys |
| Consistent hashing | Minimal remap on node change (~1/N keys move) | More complex, needs virtual nodes for even spread |
| Global GSLB | Disaster/region failover, latency-based routing | DNS TTL delay (propagation lag: seconds–hours), client DNS caching abuse |

## Real-World Scenarios

- **E-commerce checkout under Black Friday load:** ALB with least-outstanding-requests + auto-scaling target group; connection draining ensures in-flight checkouts finish before old instances terminate.
- **WebSocket/streaming service:** L4 NLB (needs long-lived connection, no HTTP parsing) since L7 buffering would hurt streaming latency.
- **Multi-region SaaS with regional outage:** Route53 GSLB with health-check-based failover routing shifts traffic to a healthy region within DNS TTL window (mitigated with low TTL, e.g., 30-60s).
- **Sharded cache tier (Redis/Memcached):** Consistent hashing at the client or Envoy layer keeps cache-key locality, minimizing cache-miss storms on backend add/remove.
- **Canary release of a new API version:** Envoy L7 header-match routing sends 5% of traffic (or requests with `x-canary: true`) to new version pool, rest to stable.

## Nuances & Gotchas

- **LB as SPOF:** a single LB instance is a new single point of failure — always deploy LBs in HA pairs (active/active or active/passive with VRRP/keepalived) or use a managed multi-AZ LB (ALB/NLB).
- **Cross-zone load imbalance:** without cross-zone balancing enabled (AWS ALB/NLB), each zone's LB nodes only route to backends in their own zone — uneven backend count per AZ causes hot zones; cross-zone balancing adds inter-AZ data transfer cost.
- **Health-check stampede:** all backends passing/failing health checks in sync (e.g., after a deploy or GC pause) causes synchronized retries/reconnects that overload survivors — mitigate with jittered check intervals and gradual (not instant) ejection.
- **Long-lived connection pinning defeats rebalancing:** with HTTP/2 or gRPC multiplexed over one TCP connection, L4 LB balances once per connection, not per request — a "sticky" heavy client can pin to one backend indefinitely; needs L7 LB or periodic connection recycling (`max_connection_age`).
- **Slow-start for new backends:** a freshly deployed/scaled instance gets full traffic share immediately, causing cold-cache/JIT-warmup overload; ramp traffic gradually (Envoy `slow_start_window`, ALB slow start config).
- **Sticky sessions hide failure and block scale-down:** draining a "sticky" instance strands sessions; prefer externalizing session state (Redis/JWT) over LB-level affinity.
- **Passive health checks (outlier detection) vs active probes:** active checks add load and can lag reality; passive (5xx-rate/latency-based ejection, e.g., Envoy outlier detection) reacts faster to real traffic but needs live traffic to detect — cold/low-traffic backends are blind spots.
- **TLS termination vs passthrough:** termination at LB simplifies backend (plaintext internally, easier L7 routing/observability) but breaks E2E encryption compliance requirements — passthrough (SNI-based routing) avoids that but LB can't inspect/route on HTTP content.
- **DNS-based GSLB propagation lag:** TTL + resolver caching (including misbehaving clients ignoring TTL) means failover isn't instant — anycast IP-based global LB (Cloudflare) avoids this by not depending on DNS propagation at all.
- **Connection draining / deregistration delay:** too short a drain timeout kills in-flight long requests during deploys; too long delays rollout and holds capacity on bad instances — tune per traffic profile (e.g., ALB default 300s).
- **Algorithm choice mismatch:** round robin on backends with wildly different per-request cost (e.g., mixed CPU-bound vs I/O-bound endpoints) causes persistent imbalance — least-connections or P2C adapts, plain RR does not.

## Self-Check

1. You have a gRPC service where each client opens one persistent HTTP/2 connection. After adding new backend pods, they receive almost no traffic. Why, and what fixes it?
2. A batch-processing API has requests ranging from 10ms to 10s (mixed CPU-bound and I/O-bound endpoints). Round robin is causing hotspots. Which algorithm(s) would you switch to, and why does plain RR fail here?
3. Right after a rolling deploy, several backends fail their health check simultaneously and get ejected at once, overloading the survivors. What caused this and how do you prevent it?
4. Give a concrete case where you'd choose L4 over L7 for a load balancer, and explain what capability you're giving up by doing so.
5. Your ALB has cross-zone load balancing disabled and AZ-A has twice as many backend instances as AZ-B. What happens to AZ-B's instances, and what's the trade-off of turning cross-zone balancing on?

<details><summary>Answers</summary>

1. L4 LBs balance per-connection, not per-request; a multiplexed HTTP/2 connection pins to whichever backend it first connected to, so new pods get no share of already-open connections. Fix: use an L7 LB (balances per-request) or force periodic connection recycling (e.g., `max_connection_age`).
2. Least-connections or power-of-two-choices — they route based on actual current load rather than a fixed rotation. Plain RR assumes uniform request cost, so mixing 10ms and 10s requests means some backends accumulate long-running work while RR keeps sending them more.
3. Health-check stampede: checks ran in sync (e.g., all backends paused by the same deploy step or GC pause) so they failed together, and instant ejection removed them all at once. Prevent with jittered health-check intervals and gradual/staggered ejection instead of instant.
4. A WebSocket or streaming service needing long-lived connections and raw throughput (e.g., AWS NLB) — L4 avoids HTTP parsing/buffering latency. You give up content-aware routing: no path/header-based rules, no cookie inspection, no A/B or canary routing at the LB.
5. AZ-B's instances each get a larger share of AZ-B's inbound traffic than AZ-A's instances get of AZ-A's traffic, since each zone's LB nodes only route within their own zone — AZ-B instances run hotter. Turning on cross-zone balancing evens this out but adds inter-AZ data transfer cost.
</details>

---
**Related:** [Reverse Proxy and Forward Proxy](02-reverse-proxy-and-forward-proxy.md) · [API Gateway](03-api-gateway.md) · [DNS and Service Discovery](../01-fundamentals/11-dns-and-service-discovery.md) · [Availability and the Nines](../01-fundamentals/06-availability-and-nines.md)

*Last reviewed: 2026-08*
