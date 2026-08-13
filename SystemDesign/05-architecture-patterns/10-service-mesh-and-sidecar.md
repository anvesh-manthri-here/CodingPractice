# Service Mesh and Sidecar Pattern

> **TL;DR:** A service mesh moves cross-cutting network concerns (mTLS, retries, circuit breaking, telemetry, routing) out of app code into a per-pod proxy sidecar (usually Envoy), centrally configured by a control plane (Istio, Linkerd). You trade added latency, resource cost, and operational complexity for language-agnostic, consistent policy enforcement across a polyglot fleet.

## Quick Reference

| Aspect | Detail |
|---|---|
| Data plane proxy | Envoy (Istio), linkerd2-proxy (Rust, Linkerd) |
| Control plane | Istio (istiod), Linkerd control plane, Consul Connect, AWS App Mesh |
| Sidecar injection | Kubernetes mutating webhook (`sidecar.istio.io/inject`) or `linkerd inject` |
| Config propagation protocol | xDS (Envoy discovery protocol: CDS, EDS, LDS, RDS) over gRPC |
| Latency overhead per hop | Istio/Envoy: ~1-5ms p50, higher tail; Linkerd: sub-ms, lighter |
| mTLS | Automatic cert issuance/rotation via SPIFFE identities (Istio Citadel / cert-manager) |
| Traffic capture | iptables redirect (or eBPF w/ Cilium) to route pod traffic through sidecar |
| Ambient mode (newer) | Istio Ambient / Linkerd removes sidecar, uses shared per-node proxy (ztunnel) + waypoint |
| Alternative | Client-side library (gRPC + Finagle, Netflix Hystrix/Ribbon, Spring Cloud) |
| Rule of thumb overkill threshold | < ~10-15 services, single language, single team |

## What It Is

- **Sidecar**: a proxy process co-located with each app container (same pod), intercepting all inbound/outbound traffic transparently.
- **Service mesh**: the sidecars collectively form the *data plane*; a separate *control plane* configures and observes them as a fleet, not one-off.
- Application code just talks to `localhost` or a plain service name — the sidecar handles TLS, retries, LB, routing, without app awareness.

## Responsibilities

- **Sidecar (data plane) per pod**: mTLS origination/termination, retries with backoff, timeouts, circuit breaking, load balancing (round robin, least-request), request routing (canary %, header-based), telemetry emission (metrics, traces, access logs).
- **Control plane**: service discovery aggregation, certificate issuance/rotation, pushing routing/policy config to every sidecar, aggregating telemetry, enforcing authorization policy (RBAC/AuthorizationPolicy CRDs).
- **Not the mesh's job**: app-level business logic, message serialization/schema, database access patterns — mesh operates at L4/L7 network layer only.

## How It Works

```
 Pod A                              Pod B
┌─────────────┬─────────┐   mTLS   ┌─────────┬─────────────┐
│  App        │ Envoy   │ ───────▶ │ Envoy   │  App        │
│  container  │ sidecar │          │ sidecar │  container  │
└─────────────┴─────────┘          └─────────┴─────────────┘
        ▲                                  ▲
        └──────────── xDS config ──────────┘
                     (control plane: istiod)
```

1. Kubelet starts pod; init container sets iptables rules redirecting all TCP traffic through the sidecar's ports.
2. Sidecar registers with control plane, receives CDS (clusters), EDS (endpoints), LDS (listeners), RDS (routes) over a persistent gRPC stream.
3. App makes a plain HTTP/gRPC call to another service name; iptables transparently routes it to the local Envoy.
4. Envoy resolves destination endpoints, applies retry/timeout/circuit-breaker policy, establishes mTLS to the destination's sidecar using SPIFFE SVIDs, forwards.
5. Destination sidecar terminates TLS, applies inbound policy (authz check), forwards to local app container.
6. Both sidecars emit metrics (Prometheus format) and spans (OpenTelemetry/Zipkin) without any app instrumentation.

## Types / Classifications

| Model | Description | Example |
|---|---|---|
| Sidecar-per-pod | One proxy per workload instance | Istio (classic), Linkerd |
| Node-level proxy (ambient) | Shared L4 proxy per node + optional L7 waypoint per namespace | Istio Ambient Mesh |
| Library-embedded | Networking logic linked into app binary, no separate process | gRPC interceptors, Netflix OSS (Hystrix/Ribbon), Finagle |
| Gateway-only mesh | Central proxy at edge/ingress, no per-service sidecar | API Gateway (Kong, NGINX) — not a full mesh, no east-west mTLS |
| eBPF-based dataplane | Kernel-level interception, bypasses iptables/userspace hop | Cilium Service Mesh |

## Where It Fits

- Sits transparently in the **network path between services**, below the app layer, above raw TCP/IP — orthogonal to your app framework.
- Complements, doesn't replace: API gateway (north-south, edge) handles external traffic; mesh handles east-west (service-to-service) internal traffic.
- Integrates with Kubernetes as the primary substrate (CRDs: VirtualService, DestinationRule, PeerAuthentication); also usable on VMs (Consul Connect) but heavier lift.
- Feeds observability stack: Prometheus/Grafana for metrics, Jaeger/Zipkin for traces, Kiali for topology visualization.

## Common Patterns & Real-World Tools

- **Canary/traffic-shifting**: Istio `VirtualService` weight-based routing (90/10 split) without app changes.
- **Circuit breaking**: Envoy `outlier detection` — eject endpoint after N consecutive 5xx.
- **mTLS everywhere ("zero trust")**: Istio `PeerAuthentication: STRICT` mode, SPIFFE identity per workload.
- **Retry budgets**: prevent retry storms — Envoy caps retries as % of active requests, not per-call unlimited retries.
- **Fault injection for chaos testing**: Istio injects delays/aborts at the proxy layer for resilience testing.
- **Multi-cluster mesh**: Istio multi-primary or primary-remote for cross-region service discovery + failover.
- Companies: Lyft (created Envoy), Google/IBM (Istio), Buoyant (Linkerd creator), HashiCorp (Consul Connect), AWS App Mesh (managed, being deprecated in favor of ECS Service Connect).

## Pros & Cons / Trade-offs

| Pros | Cons |
|---|---|
| Language-agnostic — Go, Java, Python services get same mTLS/retries without per-language libs | Extra hop = added p50/p99 latency (2 sidecar hops per call: client-side + server-side) |
| Centralized, consistent policy (authz, rate limit, retry) across hundreds of services | New moving part: control plane outage/misconfig can degrade entire fleet |
| Decouples networking upgrades from app redeploys — patch Envoy CVE without touching app code | Resource overhead: sidecar CPU/memory per pod (Envoy ~50-100MB baseline, adds up at scale) |
| Rich built-in observability (golden signals) with zero app instrumentation | Steep learning curve — CRDs, xDS debugging, cert lifecycle are non-trivial |
| Uniform zero-trust security posture (mTLS by default) | Debugging is harder — traffic path now includes proxy hops, iptables redirects |
| Gradual traffic shifting/canary without app-level feature flags | Version skew risk between control plane and sidecar during upgrades |

## Real-World Scenarios

- **Netflix-scale polyglot org (100s of services, many languages)**: mesh justified — avoids reimplementing Hystrix-equivalent resilience in every language.
- **Fintech requiring auditable zero-trust**: Istio STRICT mTLS + AuthorizationPolicy gives provable service-to-service encryption for compliance (PCI-DSS).
- **Startup with 8 microservices, all Go, one team**: mesh is overkill — a shared Go middleware library (retry/circuit-breaker via `sony/gobreaker` or `grpc` interceptors) achieves 90% of the benefit at near-zero ops cost.
- **Gradual migration**: teams often adopt Linkerd first (lighter, simpler) for mTLS + observability, defer Istio's advanced traffic management until actually needed.
- **Cost-sensitive high-QPS system**: latency-critical services (sub-5ms SLA) sometimes opt out of sidecar injection for that specific service, or move to ambient/eBPF mode to cut the extra hop.

## Nuances & Gotchas

- **Sidecar startup race**: app container can start before Envoy is ready, causing connection refused on pod boot — mitigated by `holdApplicationUntilProxyStarts` in Istio or init-container ordering.
- **Sidecar resource requests multiply cluster cost**: 100 pods × 100MB Envoy sidecar = 10GB just for proxies; budget this into capacity planning, not an afterthought.
- **Retries + timeouts compounding**: default Envoy retry policy at every hop can amplify a slow downstream into a retry storm; must configure retry budgets and consistent deadlines across the call chain, not just per-hop.
- **mTLS breaks non-HTTP/gRPC protocols silently**: raw TCP or protocols not fully understood by Envoy L7 filters may need `PERMISSIVE` mode fallback or explicit port exclusion.
- **Zombie sidecars on Kubernetes Jobs**: sidecar keeps running after main container exits, blocking Job completion — needed native sidecar containers (K8s 1.29+) or `istio-proxy` termination hooks to fix.
- **Control plane becomes SPOF for config, not data**: existing sidecars keep serving cached config if istiod goes down, but new pods/config changes stall — always test control plane HA separately from data plane resilience.
- **Cert rotation edge cases**: clock skew or slow rotation causes intermittent mTLS handshake failures that look like random 503s, hard to correlate without checking cert expiry/SPIFFE logs specifically.
- **Upgrade complexity**: Istio control plane and Envoy sidecar versions must stay within supported skew (usually N, N-1); canary upgrading the mesh itself is a project, not a `helm upgrade`.
- **Ambient mode still maturing (2025-2026)**: removes per-pod sidecar cost but L7 features route through shared waypoint proxies — adds its own hop and is less battle-tested than classic sidecar model.
- **"It's slow" complaints are often misconfiguration, not the mesh itself**: unbounded connection pools, missing keep-alive, or Nagle's algorithm interactions with iptables redirection commonly cause the worst latency spikes, not Envoy processing time itself.
