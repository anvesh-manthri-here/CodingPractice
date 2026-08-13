# DNS and Service Discovery

> **TL;DR:** DNS is the internet's original service discovery — hierarchical, cached, eventually-consistent name resolution; modern service discovery (Consul, etcd, Kubernetes DNS) reuses the same ideas at sub-second freshness for ephemeral, autoscaling backends.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Resolution path | stub resolver → recursive resolver → root → TLD → authoritative NS |
| Common record types | A, AAAA, CNAME, SRV, TXT, NS, PTR, SOA |
| Default TTLs | 60s–86400s; low (30-60s) for failover-critical records |
| Caching layers that ignore TTL | browser DNS cache, OS resolver cache, JVM `networkaddress.cache.ttl` (**-1 = forever** when a SecurityManager is set; 30s otherwise), glibc `nscd` |
| DNS load balancing | round-robin A records, GeoDNS, weighted records, anycast (same IP, many PoPs via BGP) |
| Service discovery styles | client-side (Eureka + Ribbon) vs server-side (ELB, k8s kube-proxy/Service) |
| Popular registries | Consul, etcd (+Raft), ZooKeeper (+ZAB), Eureka, Kubernetes API/CoreDNS |
| K8s DNS | `<svc>.<ns>.svc.cluster.local` → ClusterIP; headless Service → all pod IPs |
| Health-check cadence | Consul ~10-30s TTL/HTTP checks; k8s liveness/readiness probes drive Endpoints updates |

## What It Is

- **DNS**: distributed, hierarchical, cached database mapping names → IPs (and other records), built for internet-scale, slow-changing infrastructure.
- **Service discovery**: the general problem of "how does caller find a healthy instance of callee right now," in environments where instances scale up/down and reschedule in seconds — DNS is one implementation, often too slow/coarse alone.

## Responsibilities

- Name → address translation (A/AAAA), plus service metadata (SRV, TXT).
- Load distribution across replicas (round-robin, weighted, latency-based via GeoDNS).
- Failure/topology abstraction — clients target a stable name, not volatile IPs.
- In service discovery: registration, health verification, deregistration, and propagating membership changes to consumers.

## How It Works

### Classic DNS resolution path
```
stub resolver (OS) → recursive resolver (ISP/8.8.8.8/1.1.1.1, caches)
   → root server (.) → TLD server (.com) → authoritative NS (example.com)
   → answer bubbles back, cached at every hop per record TTL
```
- Stub resolver: minimal, just forwards queries, keeps tiny/no cache.
- Recursive resolver: does the walking, caches per-TTL, this is where most hits are served after first lookup.
- Authoritative server: source of truth for the zone, returns the actual record + TTL.
- Iterative vs recursive queries: recursive resolver issues iterative queries to root/TLD/authoritative on the client's behalf.

### Record types that matter
| Type | Purpose |
|---|---|
| A / AAAA | hostname → IPv4/IPv6 |
| CNAME | alias to another name (cannot coexist with other records at same node) |
| SRV | service+port+priority+weight (`_service._proto.name`), used by SIP, k8s headless, some SD systems |
| TXT | arbitrary text — SPF/DKIM, ACME challenges, service metadata |
| NS | delegates a zone to authoritative servers |
| SOA | zone admin metadata, refresh/retry/expire/minimum-TTL |
| PTR | reverse lookup, IP → name |

### TTL and caching layers
- TTL set by authoritative zone owner; every resolver/cache in the path is *supposed* to honor it and evict on expiry.
- Real caching stack, top to bottom: browser cache → OS stub cache → recursive resolver cache → **application/runtime cache** (JVM, some HTTP clients) → connection pools that hold sockets long past DNS TTL anyway.

### DNS-based load balancing
- **Round-robin A records**: multiple A records for one name, resolver/client rotates or picks first — no health awareness, coarse.
- **Weighted/latency records**: Route53/NS1 weighted or latency-based routing, splits traffic by percentage or by measured RTT.
- **GeoDNS**: answer varies by resolver's geographic location — routes users to nearest region (Route53 geolocation, NS1, Akamai).
- **Anycast**: same IP announced from many PoPs via BGP; network routes to topologically nearest instance (Cloudflare, Google 8.8.8.8, root DNS servers themselves). Not really "DNS-based" — works at IP routing layer, often *used for* DNS resolvers.

### Service discovery mechanics
- **Client-side discovery**: client queries a registry directly, gets full instance list, load-balances locally (Netflix Eureka + Ribbon). Registry is on hot path only for the lookup; extra library complexity per language.
- **Server-side discovery**: client hits a fixed endpoint (LB/proxy), the LB queries the registry and forwards (AWS ELB, Kubernetes Service via kube-proxy/iptables/IPVS, Envoy+xDS). Simpler clients, LB is another hop and potential bottleneck.
- **Registration**: self-registration (app pings registry on startup — Eureka client) vs third-party registration (sidecar/registrar or orchestrator does it — Kubernetes kubelet updates Endpoints, Consul via Registrator).

## Types / Classifications

| Axis | Options |
|---|---|
| Discovery pattern | client-side vs server-side |
| Registration | self-registration vs third-party registrar |
| Consistency model | CP (etcd/ZooKeeper, Raft/ZAB — strict consistency, unavailable on partition) vs AP (Eureka — stays available, may serve stale list) |
| Data plane | pure DNS (SRV/A records) vs API-based registry (HTTP/gRPC to Consul/etcd) vs control-plane push (xDS to Envoy) |

## Where It Fits

```
Client → [DNS: name→VIP/LB IP] → LB/Proxy/Mesh sidecar → [Service Discovery: VIP→instance IPs] → Instance
```
- DNS typically resolves a *stable* endpoint (LB, ClusterIP, VIP); service discovery resolves *behind* that endpoint to actual, changing instances — two layers, different freshness requirements.
- Service meshes (Istio/Envoy, Linkerd) push registry state via xDS instead of DNS, bypassing TTL/cache staleness entirely.

## Common Patterns & Real-World Tools

| Tool | Consensus | Notes |
|---|---|---|
| Consul (HashiCorp) | Raft | health checks (TTL/HTTP/TCP/gRPC), DNS interface + HTTP API, multi-DC |
| etcd | Raft | k8s's backing store; watch API for near-real-time change notification |
| ZooKeeper | ZAB | ephemeral znodes = auto-deregistration on session timeout; used by Kafka (legacy), older Hadoop stack |
| Eureka (Netflix) | AP, self-preservation mode | designed to favor availability over consistency during partitions |
| Kubernetes DNS (CoreDNS) | backed by etcd | Service → ClusterIP (stable, load-balanced); headless Service (`clusterIP: None`) → DNS returns all pod IPs directly, used for stateful sets / client-side LB |
| Route53 / NS1 | — | managed authoritative DNS with weighted, latency, geo, failover routing policies |
| Envoy xDS / Istio | — | pull/push service topology outside DNS entirely, sub-second propagation |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Plain DNS LB | universal, no client library, works everywhere | coarse, TTL-bound staleness, no real health-awareness, connection pooling defeats rotation |
| Client-side discovery (Eureka) | fewer hops, client controls LB policy | registry client needed per language, more complex clients |
| Server-side discovery (k8s Service, ELB) | thin/dumb clients, centralized policy | LB is extra hop + potential bottleneck/SPOF |
| CP registry (etcd/ZK) | strongly consistent membership | unavailable during partition — can block discovery entirely |
| AP registry (Eureka) | discovery keeps working during partition | may hand out dead instances temporarily |
| Anycast | fast failover at network layer, low latency | needs BGP control, wrong for stateful/session-sticky services |

## Real-World Scenarios

- **Blue/green or region failover**: flip a Route53 weighted/failover record from 100/0 to 0/100 — clients honoring TTL pick up new target within TTL window; clients ignoring TTL (JVM) stay stuck on dead endpoint.
- **Kubernetes rolling deploy**: new pod passes readiness probe → added to Endpoints/EndpointSlice → CoreDNS/kube-proxy update within ~1-2s; old pod gets SIGTERM, removed from Endpoints *before* terminating (not after) to avoid routing to a dying pod.
- **Multi-region active-active**: GeoDNS routes each user to nearest region; combined with health-check-based failover records so a region outage removes it from the answer set within its TTL.
- **Kafka/Cassandra bootstrap**: seed nodes discovered via SRV or headless Service DNS at startup, then peers gossip full membership — DNS is only used for initial bootstrap, not steady-state discovery.

## Nuances & Gotchas

- **JVM DNS caching can be forever — check before you assume**: with a SecurityManager installed, `networkaddress.cache.ttl` defaults to `-1`, so the JVM resolves a hostname once and never re-resolves until restart — the classic cause of "EC2 IP changed under an ELB, app kept hammering the old dead IP." Without a SecurityManager, modern JDKs default to 30s, which is usually fine. Either way, set it explicitly (`networkaddress.cache.ttl=60`, or `-Dsun.net.inetaddr.ttl`) rather than inheriting whichever default applies.
- **Stale TTLs during failover**: even with a correct low TTL, resolvers/ISPs/corporate DNS often ignore or clamp it — real-world failover can take minutes, not seconds, regardless of what you set. Never rely on DNS TTL alone for sub-minute failover; pair with a real LB/health-check layer or anycast.
- **Thundering herd on synchronized TTL expiry**: if many clients cached the same record at the same time (e.g., cold start, mass deploy), TTL expiry causes a synchronized re-resolution burst against the recursive resolver / authoritative NS — mitigate with jittered TTLs or negative-cache-aware resolvers.
- **DNS as a hidden SPOF**: an internal DNS/registry outage (e.g., a company's internal Consul/CoreDNS) silently breaks *every* service simultaneously, even though "nothing changed" in the failing service — always monitor DNS resolution latency/errors as a first-class SLO, not an afterthought.
- **Negative caching**: NXDOMAIN responses are cached too (per SOA minimum-TTL) — a service that isn't registered yet can stay "not found" for that period even after it comes up.
- **CNAME chains**: CNAME at zone apex is illegal (RFC), and long CNAME chains add resolution hops/latency and break at any dangling link (dangling CNAME = subdomain takeover risk).
- **Headless Service pitfalls**: clients must re-resolve DNS themselves for load balancing (no ClusterIP LB) — HTTP clients with connection keep-alive/pooling will stick to one pod's IP indefinitely unless they re-resolve per request.
- **Connection pooling defeats DNS rotation everywhere**, not just JVM: any client holding persistent connections (HTTP keep-alive, DB drivers, gRPC channels) won't see a DNS change until the connection breaks/recycles — combine with app-level connection TTL/max-lifetime settings.
- **Split-horizon/private DNS mismatches**: internal service names resolving differently inside VPC vs public internet cause "works from my laptop, fails from prod" bugs — verify resolution context, not just the record.
- **ZooKeeper ephemeral node flakiness**: brief GC pause or network blip drops the session → node deregistered → thundering reconnect/re-registration storm; tune session timeout vs GC pause headroom carefully.

## Self-Check

1. You flipped a Route53 failover record to point away from a dead host, but some clients kept hitting it for minutes afterward. Name three distinct causes.
2. Why can `networkaddress.cache.ttl` alone make a JVM service permanently stuck on a dead IP, and what's the fix?
3. A registry outage takes down every service at once even though none of them changed. Why does this happen, and how do you guard against it operationally?
4. You need service membership during a network partition. Contrast what happens with a CP registry (etcd/ZooKeeper) versus an AP registry (Eureka).
5. Why does a headless Kubernetes Service (`clusterIP: None`) combined with HTTP keep-alive connections defeat load balancing across pods?

<details><summary>Answers</summary>

1. Persistent connections/connection pooling holding sockets past TTL; resolvers/ISPs ignoring or clamping the TTL; and application/runtime-level caches (e.g., JVM DNS cache) that don't honor TTL at all.
2. With a SecurityManager installed, the default is `-1` (cache forever), so the JVM resolves the hostname once at startup and never re-resolves — fix by setting `networkaddress.cache.ttl` explicitly (e.g., 60s) rather than relying on the default.
3. Every service depends on DNS/registry to find its dependencies, so a shared internal DNS/Consul/CoreDNS outage breaks lookups everywhere simultaneously; guard by monitoring DNS resolution latency/errors as a first-class SLO, not an afterthought.
4. CP (etcd/ZK) goes unavailable during a partition, blocking discovery entirely until quorum is restored; AP (Eureka) stays available via self-preservation mode but may hand out stale/dead instances.
5. Headless Services return all pod IPs with no ClusterIP-based load balancing, so clients must re-resolve DNS per request; a client holding a keep-alive connection sticks to one pod's IP indefinitely since it never re-resolves.
</details>

---
**Related:** [Network Protocols](10-network-protocols-tcp-udp-http-grpc-websockets.md) · [Load Balancers](../02-core-components/01-load-balancers.md) · [CDN](../02-core-components/06-cdn.md)

*Last reviewed: 2026-08*
