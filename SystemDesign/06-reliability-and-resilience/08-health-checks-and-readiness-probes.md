# Health Checks and Readiness Probes

> **TL;DR:** Liveness answers "should this process be killed?", readiness answers "should this instance receive traffic?" — conflating the two turns transient slowness into cascading restarts and outages. Shallow checks (TCP/200 OK) miss gray failures where the process is up but broken.

## Quick Reference

| Probe | Question | Failure Action | Should Check | Typical Interval |
|---|---|---|---|---|
| **Liveness** | Is the process deadlocked/crashed? | Restart container | Process responsiveness only, NOT dependencies | 10-30s, 3 failures to trigger |
| **Readiness** | Can this instance serve traffic now? | Remove from LB/Service endpoints | Dependencies it actually needs (DB pool, cache, downstream) | 5-10s, 1-3 failures |
| **Startup** | Has slow-start finished? | Suppress liveness checks until done | Same as liveness target, but with long grace period | `failureThreshold * periodSeconds` >> boot time |

## What It Is

- Health checks: automated signals an orchestrator/LB polls to decide whether to route traffic to or restart an instance.
- Three distinct probes in Kubernetes; most non-k8s LBs (ELB, NGINX upstream checks) only have the readiness-equivalent concept.
- Not a monitoring/alerting system — health checks drive **automated control-plane actions** (restart, evict), so false signals directly cause outages, not just noisy dashboards.

## Responsibilities

- **Liveness**: detect unrecoverable internal states (deadlock, hung thread pool, OOM-adjacent stall) that only a restart fixes.
- **Readiness**: gate traffic admission — protects both the instance (avoid overload during warmup/GC) and the caller (avoid errors from a not-yet-ready backend).
- **Startup**: protect slow-booting apps (JVM warmup, cache preload, Spring context init) from being killed by liveness before they've had a chance to become healthy.

## How It Works

```
        ┌─────────────┐   fail   ┌──────────────┐
        │ Startup     │─────────▶│ kill/restart │
        │ probe       │          └──────────────┘
        └──────┬──────┘
         success (probe disabled from now on)
               ▼
   ┌────────────────────────┐      ┌────────────────────┐
   │ Liveness probe (loop)  │─fail▶│ restart container   │
   └────────────────────────┘      └────────────────────┘
               │ (independent, parallel loop)
               ▼
   ┌────────────────────────┐      ┌────────────────────┐
   │ Readiness probe (loop) │─fail▶│ remove from Endpoints│
   └────────────────────────┘      └────────────────────┘
```

- kubelet runs each probe independently via its own goroutine per container; results are decoupled — a pod can be "alive" but "not ready" simultaneously (normal during GC pause or DB failover).
- `startupProbe` present ⇒ liveness/readiness are **disabled** until startup succeeds — prevents the classic crash loop on slow boot.
- Readiness failure removes pod IP from the Service's `Endpoints`/`EndpointSlice`; kube-proxy stops routing to it within one sync cycle (typically sub-second to a few seconds).
- Liveness failure sends SIGTERM (then SIGKILL after `terminationGracePeriodSeconds`), restarting the container — the pod's readiness also flips false during that window.

## Types / Classifications

| Check Depth | Example | Detects | Misses |
|---|---|---|---|
| **Shallow / TCP** | `nc -z host port` | Process listening | App deadlocked but socket accepting |
| **Shallow / HTTP 200** | `GET /healthz` returns static 200 | Process serving HTTP at all | DB down, cache unreachable, thread pool exhausted |
| **Deep / dependency-aware** | `/readyz` pings DB with timeout, checks connection pool saturation, checks required downstream | Real serving capability | Can cause **cascading failure** if it checks a dependency shared by the whole fleet (see gotchas) |
| **Deep / synthetic transaction** | Execute a lightweight representative query/read | End-to-end correctness | Cost — adds load, needs its own timeout/circuit breaking |

- **Gray failure blind spot**: shallow checks report healthy while the app returns 500s, hangs on 10% of requests, or has a full connection pool — because the check never exercises the failing path. This is the #1 reason "all pods green, app still down" incidents happen.
- Rule of thumb: liveness = shallow (cheap, cannot depend on anything external — a DB outage should never trigger mass restarts). Readiness = medium-deep (checks *this instance's* ability to do its job, not global infra health).

## Where It Fits

- Sits between the orchestrator (k8s kubelet, ECS agent, Consul health checks) and the load balancer's routing table (kube-proxy/iptables/IPVS, Envoy EDS, ELB target group).
- Upstream of client-facing traffic but downstream of deployment rollout logic — readiness gates `maxUnavailable`/`maxSurge` progression during rolling updates.
- Complements circuit breakers (client-side, per-call) and outlier detection (Envoy/Istio, statistical ejection) — probes are periodic and orchestrator-driven, breakers are per-request and client-driven.

## Common Patterns & Real-World Tools

- **Kubernetes**: `livenessProbe`, `readinessProbe`, `startupProbe` on each container; `exec`, `httpGet`, `tcpSocket`, `grpc` (native since k8s 1.24+) probe types.
- **Spring Boot Actuator**: `/actuator/health/liveness` and `/actuator/health/readiness` groups map directly to k8s probes; enable via `management.endpoint.health.probes.enabled=true`.
- **Envoy**: active health checking (`health_checks` on cluster) + passive outlier detection; distinct from k8s readiness but same philosophy.
- **AWS ELB/ALB target groups**: single health check type (closer to readiness) — no liveness concept; EC2 auto-recovery/ASG health checks are the liveness analog.
- **Consul**: script/HTTP/TCP/TTL checks feed service catalog; TTL checks (app must actively ping-heartbeat) catch hung-but-not-crashed processes well.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Shallow liveness | Safe, no cascading restarts, cheap | Won't catch deadlocks that don't affect the probed endpoint |
| Deep readiness | Catches real gray failures, protects callers | If it checks a shared dependency (e.g., central DB), one DB blip fails **every** pod's readiness simultaneously → total outage instead of graceful degradation |
| Deep liveness (anti-pattern) | Seems thorough | Turns a transient dependency outage into a mass-restart storm — worst possible amplification |
| No startup probe on slow app | Simpler config | liveness kills app mid-boot → CrashLoopBackOff, app never gets a chance to start |

## Real-World Scenarios

- **JVM app, no startup probe**: 45s boot time, liveness `initialDelaySeconds: 10, periodSeconds: 10, failureThreshold: 3` (fails at 40s) — pod restarts right before it's ready, loops forever. Fix: add `startupProbe` with `failureThreshold: 30, periodSeconds: 2` (60s budget).
- **Readiness checks central Postgres, liveness doesn't**: Postgres primary fails over, 30s unavailability. Every pod goes unready simultaneously → 503s at the LB, but no restarts, pods self-heal the moment DB returns. Correct behavior — contrast with deep liveness which would restart the entire fleet and prolong the outage via boot storms.
- **Rolling deploy without readiness gating**: new pods marked "ready" via TCP-only check before app finishes loading a 2GB in-memory cache → first requests to new pods 5xx for ~20s during every deploy. Fix: HTTP readiness endpoint that returns 200 only after cache load completes.
- **Shallow `/healthz` returns 200 always**: connection pool to downstream payment service exhausted, 40% of real requests timing out, but health check hits a route that doesn't touch that pool — k8s and LB both report healthy while customers see errors. Root-caused only via error-rate alerting, not probes.

## Nuances & Gotchas

- **Never call a shared/global dependency from liveness** — a flaky external service (Redis, S3) will cause kubelet to restart every replica simultaneously; use readiness for that, and even there, prefer local circuit-breaker state over a live network call every probe tick.
- **Readiness checking a shared dependency causes thundering-herd outages, not graceful degradation** — if the DB blips for 2s, all pods drop from Endpoints at once, traffic has nowhere to go; better: fail readiness only if *this instance's* local health is bad (e.g., its own pool exhausted), and let per-request circuit breakers handle shared dependency failures.
- **`initialDelaySeconds` is not a startup guarantee** — it's a flat delay before the *first* probe, not "wait until ready." Combine with `failureThreshold` math or use `startupProbe` instead (k8s 1.16+).
- **Probe timeout too short under load**: `timeoutSeconds: 1` on an app under GC pressure causes false-negative restarts exactly when the app is under load and least able to absorb a restart — set timeout based on p99 probe-endpoint latency under load, not idle latency.
- **Health check endpoint itself becomes a bottleneck**: deep checks that open a new DB connection per probe (instead of reusing a pool/cached result) add load and can be the thing that tips an already-struggling DB over — cache readiness result for 1-2s instead of checking synchronously every call.
- **Liveness flapping during GC pauses**: long stop-the-world GC (old CMS/G1 with large heaps) exceeds probe timeout → restart → cache cold → more GC pressure on the replacement → repeat. Fix: tune GC (G1/ZGC/Shenandoah), raise `failureThreshold`/`timeoutSeconds`, or move that check off liveness entirely.
- **Sidecar/mesh probes race the app container**: in Istio/Linkerd, kubelet may probe the pod IP before the sidecar proxy is ready to route, causing false failures right after pod start — mitigated by `holdApplicationUntilProxyStarts` (Istio) or native sidecar containers (k8s 1.29+ `restartPolicy: Always` init containers).
- **Graceful shutdown vs readiness lag**: on SIGTERM, app should fail readiness *immediately* but keep serving in-flight requests during `terminationGracePeriodSeconds`, because iptables/EndpointSlice propagation isn't instant — race causes a small window of connection-refused errors if the app stops serving the instant it gets SIGTERM.
- **One endpoint reused for both liveness and readiness** is the most common real-world mistake — guarantees that any dependency blip becomes a restart storm instead of a controlled traffic drain.
