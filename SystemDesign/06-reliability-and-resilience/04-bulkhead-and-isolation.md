# Bulkhead and Isolation

> **TL;DR:** Partition finite resources (threads, connections, memory) per dependency so one slow/failing downstream can't starve callers of unrelated downstreams — like a ship's watertight compartments containing a hull breach.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Origin | Naval architecture — compartmentalized hull, one flooded section doesn't sink ship |
| Software analog | Netflix Hystrix (2012, now maintenance mode) popularized thread-pool bulkheads |
| Two main strategies | Thread-pool-per-dependency vs semaphore (counter) isolation |
| Modern successor | Resilience4j `Bulkhead` (semaphore) + `ThreadPoolBulkhead`; Envoy circuit breaker `max_connections`/`max_pending_requests` per cluster |
| Typical thread pool size | 5–20 threads per dependency, sized via Little's Law: `threads = throughput(req/s) × latency(s) + buffer` |
| Semaphore limit | Max concurrent calls (no thread switch), e.g. 10–50 concurrent permits |
| Pairs with | Circuit breaker (stops calls), timeout (bounds hold time), rate limiter (bounds inbound) |
| DB analog | Separate connection pools per service/tenant, e.g. HikariCP pool-per-datasource |
| K8s analog | CPU/memory `limits` per pod/namespace; `LimitRange`, `ResourceQuota` |

## What It Is

- A resource-isolation pattern: cap and separate the concurrency/capacity each downstream dependency can consume from a shared pool (threads, DB connections, sockets, memory).
- Goal: contain failure blast radius — a hung dependency exhausts *its own* allocation, not the whole app's.
- Not a failure-detection pattern (that's circuit breakers) — it's a resource-fencing pattern that limits *how much damage* a failure can do while it's happening.

## Responsibilities

- Cap concurrent requests/threads per dependency (or per tenant, per API, per priority class).
- Provide fast-fail (rejection) when a bulkhead's capacity is full, instead of unbounded queuing.
- Preserve capacity for healthy dependencies when one dependency degrades.
- Expose per-bulkhead metrics (queue depth, rejections, active count) for alerting and capacity planning.

## How It Works

```
Shared thread pool (BAD)              Bulkheaded pools (GOOD)
┌─────────────────────┐               ┌───────┐ ┌───────┐ ┌───────┐
│ 200 threads, all     │               │ Pool A│ │ Pool B│ │ Pool C│
│ requests share one   │               │ 20 thr│ │ 20 thr│ │ 20 thr│
│ pool → Service C     │               │ →Svc A│ │ →Svc B│ │ →Svc C│
│ hangs, all 200       │               │  fine │ │  fine │ │ HUNG, │
│ threads eventually   │               │       │ │       │ │ but   │
│ blocked on C         │               │       │ │       │ │ isolated
└─────────────────────┘               └───────┘ └───────┘ └───────┘
```

1. Request arrives, routed to call downstream D.
2. Isolation layer checks D's bulkhead: thread pool has a free thread, or semaphore has a free permit.
3. If capacity available → execute call (own thread, or borrow caller's thread under a permit).
4. If capacity exhausted → reject immediately (fail fast) or queue briefly with a small bounded queue + timeout.
5. Rejection triggers fallback (cached data, default value, error response) — never blocks caller indefinitely.
6. Bulkhead state feeds circuit breaker: high rejection/timeout rate trips the breaker to open.

## Types / Classifications

**Thread-pool isolation**
- Each dependency gets a dedicated, bounded `ExecutorService` (e.g., `Executors.newFixedThreadPool(10)`).
- Caller thread submits work and returns; execution happens on the dependency's own thread.
- True isolation — a stuck call ties up only that pool's threads, caller thread is freed to time out independently.
- Cost: context-switch/scheduling overhead, extra memory per pool (thread stacks ~1MB each on JVM), added latency (~1-3ms per hop).

**Semaphore isolation**
- A counter (permits) limits concurrent calls; execution stays on the *caller's own thread* — no thread handoff.
- Much cheaper (no extra threads, no context switch) — Netflix Hystrix default recommendation for high-volume, low-latency calls.
- Weaker isolation: if the downstream call itself doesn't respect timeouts, the caller thread can still block, only capped in *count*, not in *time*.
- Best combined with a strict client-side timeout on the call itself.

**Process/container-level bulkheads**
- Separate deployments (canary pools, dedicated node pools) or separate connection pools per tenant/dependency at the infra layer (Kubernetes ResourceQuota, per-tenant DB pools).
- Coarser grain, higher isolation guarantee (separate OS processes/pods can't share a leaked FD table).

## Where It Fits

- Sits in the client-side resilience layer, alongside timeouts, retries, and circuit breakers — typically implemented via a library (Resilience4j, Hystrix, Polly for .NET) or a sidecar/proxy (Envoy, Istio).
- Applied at the call site to each external dependency: DB, cache, downstream microservice, third-party API.
- In service mesh: Envoy's per-upstream-cluster `circuit_breakers.thresholds` (`max_connections`, `max_pending_requests`, `max_requests`, `max_retries`) implement bulkheads at the proxy without app code changes.
- API gateways (Kong, AWS API Gateway) apply per-route/per-backend concurrency limits as a bulkhead for the whole gateway process.

## Common Patterns & Real-World Tools

| Tool | Bulkhead Mechanism |
|---|---|
| Netflix Hystrix | `HystrixThreadPoolProperties` (thread pool) or semaphore isolation strategy per command |
| Resilience4j | `Bulkhead` (semaphore, `maxConcurrentCalls`) and `ThreadPoolBulkhead` (queue + pool) |
| Envoy / Istio | `max_connections`, `max_pending_requests`, `max_requests` per upstream cluster |
| HikariCP | Separate `HikariDataSource` instances per downstream DB/service |
| Kubernetes | `ResourceQuota`, `LimitRange`, pod CPU/mem `limits`, `PriorityClass` |
| gRPC | Per-channel connection limits, separate channels per service |
| AWS | Separate Lambda concurrency reservations per function; SQS per-queue visibility limits |
| Java `ExecutorService` | `newFixedThreadPool` per dependency with `ArrayBlockingQueue` cap + `RejectedExecutionHandler` |

## Pros & Cons / Trade-offs

| Aspect | Thread-Pool Isolation | Semaphore Isolation |
|---|---|---|
| Isolation strength | Strong — caller thread never blocks on downstream | Weaker — caller thread can still block if call has no timeout |
| Overhead | Higher (extra threads, context switches, memory) | Low (just a counter) |
| Timeout enforcement | Easy — kill/abandon the pool thread | Must rely on client's own call timeout |
| Best for | High-latency, unreliable, or high-volume external calls; want async | Low-latency, high-QPS internal calls where overhead matters |
| Failure containment | Excellent | Good, but only bounds concurrency, not duration |

- General trade-off: more/smaller bulkheads = better isolation but more ops complexity (sizing N pools) and worse resource utilization (idle capacity in one pool while another is starved).
- Static sizing is brittle — traffic mix shifts, requiring re-tuning; adaptive/dynamic bulkheads (e.g., adjust based on latency percentiles) are harder to build but avoid manual retuning.

## Real-World Scenarios

- **Netflix**: birthed Hystrix after cascading failures where a slow personalization service exhausted the shared Tomcat thread pool, taking down the entire API layer — thread-pool-per-dependency became the fix.
- **E-commerce checkout**: payment-gateway calls isolated in their own 10-thread pool; if the payment provider degrades, product search and cart APIs (different pools) stay fully responsive.
- **Multi-tenant SaaS**: per-tenant connection pool caps prevent one noisy tenant's batch job from starving other tenants' interactive queries on a shared Postgres instance.
- **Envoy sidecar**: `max_pending_requests: 100` on an upstream cluster means the 101st queued request is rejected with 503 instead of piling up and OOM-ing the proxy.
- **Kubernetes noisy neighbor**: without per-namespace `ResourceQuota`, one team's memory-leaking pod can pressure the node and evict pods from unrelated namespaces — a cluster-level bulkhead failure.

## Nuances & Gotchas

- **Shared connection pool masks the bulkhead**: app-level thread pools are isolated, but if all pools ultimately draw from one shared DB connection pool, the "bulkhead" is fake — the DB pool becomes the real bottleneck. Isolate at *every* shared-resource layer, not just threads.
- **Undersized bulkheads cause false rejections** under normal bursty load; oversized ones defeat the purpose (still enough threads to exhaust host memory/CPU). Size via Little's Law and revisit after traffic growth.
- **Thread-pool isolation adds tail latency** even on the happy path (queueing + context switch) — can violate tight SLAs for latency-sensitive hot paths; semaphore isolation avoids this cost.
- **Semaphore isolation without a call timeout is a leak in disguise**: caller thread blocks on the downstream call itself; permits free up only when the call returns, so a hung call still ties up caller threads indefinitely — always pair with a hard timeout.
- **Bulkhead + retry interaction**: retries on a nearly-full bulkhead accelerate exhaustion — cap retries and use jittered backoff, or skip retry entirely when the breaker for that dependency is open.
- **Bulkhead + circuit breaker ordering matters**: check the circuit breaker *before* acquiring a bulkhead permit — otherwise doomed calls still consume scarce slots while the breaker is open.
- **Metrics blind spot**: rejections at the bulkhead often don't surface as "errors" in default dashboards (they're fast-fails, not exceptions from the downstream) — must explicitly monitor rejection counts/rates per bulkhead.
- **Queueing inside the bulkhead is a hidden bulkhead-buster**: a large bounded queue in front of a thread pool just delays the exhaustion and adds latency; keep queues small (or zero) and prefer immediate rejection with fallback.
- **Fallback logic itself needs isolation**: if the fallback path calls another dependency (e.g., cache miss falls back to a secondary service), that fallback needs its own bulkhead too, or the "safety net" becomes a second point of cascading failure.
- **Cross-AZ/region bulkheads**: isolating by thread pool alone doesn't help if the underlying network path or DNS resolver is shared and saturated — infra-level isolation (separate NAT gateways, separate DNS caches) is sometimes needed too.
