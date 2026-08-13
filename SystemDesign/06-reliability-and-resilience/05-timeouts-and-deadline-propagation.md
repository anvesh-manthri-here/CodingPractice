# Timeouts and Deadline Propagation

> **TL;DR:** Every network call needs an explicit timeout shorter than the caller's remaining budget, and that budget must propagate downstream so cancelled requests actually stop cancelled work instead of becoming zombies.

## Quick Reference

| Concept | Rule of Thumb |
|---|---|
| Default timeout | NEVER "wait forever" — pick p99.9 latency + margin |
| Hop ordering | Inner timeout < outer timeout (strictly, with margin) |
| gRPC | `context.WithTimeout` / deadline auto-propagates via metadata (`grpc-timeout` header) |
| HTTP | No built-in propagation — must pass `X-Request-Deadline` / budget header manually |
| Connect timeout | Separate, shorter (e.g., 1-3s) from request/read timeout |
| Retry + timeout | Total retry budget must fit inside caller's deadline, not reset it |
| Client library defaults | Often `0` / infinite (e.g., old `net/http.Client{}`, JDBC) — must override |
| Cancellation propagation | `context.Context` (Go), `CancellationToken` (.NET), gRPC deadline exceeded → cancels ctx |
| Zombie work | Work continues after client gave up — DB query, downstream call still running |

## What It Is

- **Timeout**: max time a caller waits for a response before giving up and freeing local resources (thread, connection, memory).
- **Deadline**: an absolute point in time ("done by 14:32:05.100") that travels with a request across every hop, as opposed to a timeout which is a relative duration reset at each hop.
- **Deadline propagation**: passing the remaining time budget downstream so every service in the call chain knows when to stop working — not just when to stop waiting.

## Responsibilities

- Bound resource consumption per request: threads, sockets, connection-pool slots, memory buffers.
- Prevent cascading resource exhaustion when a downstream dependency slows down or hangs.
- Enable fast failure/fallback instead of client-side infinite hangs.
- Stop wasted compute: cancel DB queries, RPCs, and CPU work once no one is waiting for the result.
- Feed circuit breakers and retry budgets accurate signal (timeout = failure, distinct from success).

## How It Works

1. Client sets a timeout (or absolute deadline) before issuing a call — e.g., 500ms.
2. As the request crosses each hop, the **remaining** budget shrinks (network latency + processing already consumed).
3. Each service must set its own outbound timeouts to fit inside what's left, not reissue a fresh full timeout.
4. If the deadline is exceeded, an error propagates back (`DEADLINE_EXCEEDED` in gRPC, `504` in HTTP) and — critically — a **cancellation signal propagates forward** so in-flight downstream work stops.

```
Client (2s deadline)
  -> API Gateway (budget: 2s - elapsed ~50ms = 1.95s, sets own timeout 1.8s)
     -> Service A (budget ~1.7s, timeout 1.5s)
        -> Service B (budget ~1.3s, timeout 1.0s)
           -> DB query (must respect ctx cancel, abort if client gone)
```

- **gRPC**: deadline is absolute wall-clock time, encoded in the `grpc-timeout` header, converted to remaining duration at each hop. The Go/Java/C++ context automatically cancels when deadline passes — server handlers checking `ctx.Err()` stop early.
- **HTTP**: no native deadline propagation. Must implement manually — pass a header like `X-Deadline: 2026-08-13T14:32:05.100Z` and have each service compute its own timeout from it, or truncate remaining budget and forward it.
- Client disconnect (TCP RST) is a separate, weaker cancellation signal — many servers ignore it unless explicitly wired to `context`/`CancellationToken`.

## Types / Classifications

| Timeout Type | Scope | Example |
|---|---|---|
| Connect timeout | TCP/TLS handshake | 1-3s |
| Request/read timeout | Time to first byte / full response | 500ms-5s |
| Idle timeout | Keep-alive connection inactivity | 60-120s |
| Overall/deadline timeout | End-to-end budget across retries | Set once at edge, shrinks per hop |
| Per-attempt timeout | Single retry attempt (subset of overall) | overall/attempts |

## Where It Fits

- Sits alongside **retries, circuit breakers, and backpressure** as core resilience primitives (see related files in `06-reliability-and-resilience`).
- Directly tied to the web-server gotcha of unbounded thread/worker pools: a hung upstream call with no timeout holds a worker forever, exhausting the pool under load (see `04-web-servers-and-request-handling` notes).
- Sits under load balancers and API gateways, which often enforce their own timeout as a safety net independent of app-level timeouts (e.g., NGINX `proxy_read_timeout`, ALB idle timeout 60s default).
- Feeds observability: timeout rate is a first-class SLO signal, distinct from error rate.

## Common Patterns & Real-World Tools

- **gRPC context deadlines**: `ctx, cancel := context.WithTimeout(parent, 500*time.Millisecond)` — propagates automatically over the wire; server-side `ctx.Done()` triggers cleanup.
- **Envoy/Istio**: `timeout:` field per route in VirtualService; separate `idleTimeout` for streaming. Enforces hop-level ceiling regardless of app code.
- **Hystrix/resilience4j**: explicit `TimeLimiter` decorator wrapping calls, paired with circuit breaker state.
- **AWS SDKs**: `apiCallTimeout` (total incl. retries) vs `apiCallAttemptTimeout` (per attempt) — explicit two-tier budget.
- **Postgres**: `statement_timeout`, `idle_in_transaction_session_timeout` — DB-side enforcement independent of app.
- **HTTP budget header pattern**: services like Google's internal RPC and some HTTP meshes forward `X-Deadline` or `grpc-timeout`-style header manually.
- **Kubernetes**: `terminationGracePeriodSeconds` is a related but distinct deadline — for pod shutdown, not request handling.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Fixed generous timeout (e.g., 30s everywhere) | Simple | Masks hangs, exhausts resources slowly, bad UX |
| Aggressive uniform timeout | Fast failure | False positives under GC pause / network jitter |
| Per-hop shrinking budget (deadline propagation) | Prevents zombie work, matches real SLA | More complex, requires framework support (easy in gRPC, manual in HTTP) |
| No propagation (each hop resets full timeout) | Easy to implement | Downstream can burn 3x the client's patience combined (30s client wait but 90s of actual work in flight) |

## Real-World Scenarios

- **Retry storm cascade**: Service A times out at 5s and retries 3x = 15s of load on Service B, while Service A's own caller gave up at 3s — classic non-propagated timeout bug amplifying load during an incident.
- **Payment double-charge**: Client gives up after 10s timeout, but payment service (no deadline awareness) completes the charge at 12s — client retries, charges twice. Deadline propagation + idempotency keys fix this.
- **Thread pool exhaustion**: Tomcat/Jetty worker threads pinned on an HTTP client call with no read timeout to a slow downstream — pool fills, health checks start failing, cascades to full outage (the exact gotcha referenced in the web-servers file).
- **gRPC deadline exceeded on fan-out**: An aggregator service calls 5 backends in parallel with an 800ms deadline; 4 respond in 200ms but 1 hangs — deadline propagation cancels that RPC at the backend, freeing its resources rather than leaving it running for the full backend-side default timeout.

## Nuances & Gotchas

- **Cancellation isn't automatic just because you have a timeout.** A gRPC/HTTP client returning "timeout" to the caller does NOT stop the server from finishing the work unless the server explicitly checks `ctx.Done()` / respects cancellation — many handlers, especially ones doing blocking I/O (JDBC, sync file writes), ignore it entirely, so the "zombie work" keeps consuming CPU/DB connections.
- **Retries silently multiply effective timeout.** 3 retries × 5s timeout = worst case 15s, but if the parent's deadline is only 3s, retries after the deadline has passed are pure waste — always check remaining budget before each retry attempt, don't just check attempt count.
- **Clock skew breaks absolute deadlines.** gRPC's `grpc-timeout` is relative (recomputed per hop) specifically to avoid clock-skew issues with absolute timestamps across machines; if you build a custom header with wall-clock deadlines, NTP drift of even 50-100ms can cause premature cancellation or missed ones.
- **"Shorter than upstream" must include margin for serialization/queueing, not just processing.** If A calls B with timeout 1s and B calls C with timeout 950ms, B has only 50ms left for its own logic — under load (GC pause, queueing) that's gone instantly, causing spurious timeouts even when C is healthy.
- **Load balancer/proxy timeouts often override app timeouts silently.** An ALB idle timeout of 60s or NGINX `proxy_read_timeout` of 60s can kill a connection before your app-level 90s timeout fires, producing a confusing `502`/`504` instead of your app's graceful timeout error — always audit every layer in the path.
- **Connection pool checkout has its own timeout, separate from request timeout.** A "connect timeout" is not the same as "pool wait timeout" — HikariCP `connectionTimeout`, for instance, governs waiting for an available pooled connection, and misconfiguring it as infinite causes request threads to pile up waiting for a connection that never frees.
- **Streaming/long-poll endpoints need idle timeouts, not fixed request timeouts.** A chat/SSE endpoint legitimately runs for minutes — apply a fixed 30s request timeout and you'll kill healthy long-lived connections; use idle/inactivity timeouts instead.
- **Default client library timeouts are traps.** Old Go `http.Client{}`, Python `requests` without `timeout=`, and default JDBC drivers all default to infinite — this is the single most common production incident root cause in this category; lint/enforce timeout presence in code review or via a wrapped client factory.
- **Deadline propagation must be idempotency-aware.** If a downstream cancels mid-write because the deadline expired, partial writes can leave inconsistent state — cancellation must be paired with either transactional rollback or idempotent retry keys, not just "stop working."
