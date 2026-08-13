# Circuit Breaker

> **TL;DR:** A stateful guard around a remote call that stops sending requests to a dependency once it's failing too often, so callers fail fast instead of piling up threads/latency waiting on a dying service — then periodically probes to see if it recovered.

## Quick Reference

| Aspect | Detail |
|---|---|
| States | CLOSED (normal) → OPEN (blocking) → HALF_OPEN (probing) → back to CLOSED or OPEN |
| Trip trigger | Failure rate ≥ threshold (e.g. 50%) over a sliding window (count- or time-based) |
| Open duration | Fixed wait (e.g. 30–60s) or exponential backoff before trying HALF_OPEN |
| Half-open trigger | Timer expiry; allows N trial calls (e.g. 10) |
| Close trigger | Trial calls succeed above threshold |
| Re-open trigger | Any/enough trial call fails in HALF_OPEN |
| Key libs | resilience4j (Java), Polly (.NET), Envoy outlier detection, Hystrix (legacy/EOL) |
| Sits relative to | Inside retry loop, outside/around timeout; per-dependency, not per-request |
| Failure signal | Exceptions, timeouts, 5xx, slow-call rate (not 4xx business errors) |

## What It Is

- A finite-state machine wrapping a call to a dependency (HTTP client, DB pool, RPC stub) that tracks recent success/failure and decides whether to allow, block, or probe.
- Named after the electrical circuit breaker: trips (opens) to stop current (traffic) flowing into a faulty circuit, protecting the rest of the system.
- Local to a process/instance by default (resilience4j) or can be centralized at the proxy/mesh layer (Envoy, per-upstream-host ejection).

## Responsibilities

- Detect degraded dependency health from real call outcomes (no separate health-check polling needed, though can complement one).
- Fail fast (throw/return error in microseconds) instead of letting calls block until timeout.
- Shed load off a struggling downstream so it has a chance to recover instead of being kept saturated by retries.
- Provide a recovery probe mechanism (HALF_OPEN) to detect restoration without a manual restart/flag flip.
- Expose metrics/state transitions for alerting (state changes are a strong incident signal).

## How It Works

```
        failure rate >= threshold
   CLOSED ───────────────────────────► OPEN
     ▲                                   │
     │ success rate ok in trial          │ wait duration elapses
     │ (HALF_OPEN passes)                ▼
     └────────────────────────────── HALF_OPEN
                    ▲   any/enough trial calls fail → back to OPEN
```

- **CLOSED**: all calls pass through; breaker records outcomes in a sliding window (last N calls, or last T seconds).
- Trip condition: `failure_rate >= threshold` AND `calls >= minimum_number_of_calls` (avoids tripping on 2/2 failures at startup).
- **OPEN**: calls short-circuit immediately (throw `CallNotPermittedException` or similar) — zero network I/O, zero thread blocking.
- After `wait_duration_in_open_state`, breaker transitions automatically to **HALF_OPEN**.
- **HALF_OPEN**: allows a limited number of permitted calls through as live probes; blocks the rest.
- If probe success rate ≥ threshold → CLOSED (reset counters); if not → OPEN again (restart wait timer, optionally with backoff).
- Also commonly trips on **slow-call rate** (e.g. >80% of calls exceed 2s) even if they technically "succeed" — protects against degraded-but-not-erroring dependencies.

## Types / Classifications

| Window type | Mechanism | Notes |
|---|---|---|
| Count-based | Ring buffer of last N call outcomes | Simple, resilience4j default (e.g. last 100 calls) |
| Time-based | Bucketed outcomes per second over last T seconds | Better for bursty/low-traffic services |
| Ratio-based (Envoy outlier detection) | % of hosts/requests ejected from load-balancing pool | Operates on upstream *hosts*, not one logical dependency |

By scope:
- **Per-instance/in-process**: resilience4j, Polly — state lives in the calling app, not shared across instances (each pod trips independently).
- **Sidecar/mesh-level**: Envoy outlier detection, Istio — ejects individual unhealthy upstream endpoints from the LB pool; state shared at proxy layer across all callers routed through it.
- **Bulkhead-combined**: some implementations pair circuit breaking with a bounded thread pool/semaphore per dependency (classic Hystrix pattern) so one slow dependency can't starve threads for others even before the breaker trips.

## Where It Fits

Call chain ordering (outer → inner) for a single downstream call:

```
Bulkhead (limit concurrency) → Circuit Breaker → Retry → Timeout → actual network call
```

- **Timeout is innermost**: bounds a single attempt's duration; without it, calls hang and the breaker never even sees a "failure" in reasonable time.
- **Retry wraps timeout**: retries a single timed-out/failed attempt N times — but retries against an already-struggling dependency amplify load.
- **Circuit breaker wraps retry**: once retries collectively push failure rate over threshold, breaker opens so *the whole retry block* is skipped on subsequent calls — this is the key ordering: breaker sees outcome of the retry-wrapped call, not each raw attempt, to avoid tripping on transient single-attempt blips.
- **Bulkhead outermost**: caps how many concurrent calls (threads/connections) can even attempt this dependency, independent of breaker state.
- resilience4j lets you compose this explicitly via `Decorators.ofSupplier(...).withCircuitBreaker(...).withRetry(...).withBulkhead(...)`.

## Common Patterns & Real-World Tools

| Tool | Style | Notes |
|---|---|---|
| **resilience4j** | In-process Java library | Modular decorators (CircuitBreaker, Retry, Bulkhead, RateLimiter, TimeLimiter); functional composition; replaced Hystrix as the de facto standard since ~2019 |
| **Hystrix (Netflix)** | In-process, legacy | First mainstream implementation; thread-pool-per-dependency isolation; in maintenance mode/EOL since 2018, still seen in older Spring Cloud stacks |
| **Envoy outlier detection** | Sidecar/proxy | Ejects unhealthy hosts from LB pool based on consecutive 5xx / gateway errors / success-rate outliers; no app code changes |
| **Istio** | Service mesh (built on Envoy) | Exposes outlier detection via `DestinationRule`; cluster-wide, works across polyglot services |
| **Polly** | .NET library | Same decorator pattern as resilience4j (`CircuitBreakerPolicy`, `WrapAsync`) |
| **AWS App Mesh / SMs generally** | Proxy-level | Similar ejection semantics to Envoy |
| **Spring Cloud Circuit Breaker** | Abstraction | Pluggable backend (resilience4j, Sentinel) |

## Pros & Cons / Trade-offs

**Pros**
- Fails in microseconds instead of consuming a thread/connection for the full timeout duration — directly prevents thread-pool/connection-pool exhaustion cascading to unrelated endpoints.
- Gives a struggling dependency breathing room to recover instead of being hammered by retries from every caller.
- Converts silent slow degradation into an observable state transition (alerting hook).

**Cons / Trade-offs**
- Adds a stateful component per dependency per instance — more config surface, another thing to tune and misconfigure.
- Purely local (non-mesh) breakers don't share state across instances: one pod can be OPEN while others hammer the same dying dependency (thundering herd redistributed, not eliminated).
- During OPEN, legitimate requests fail even if the dependency would have handled them fine (false positives, esp. right after trip).
- Adds latency/complexity to debug: "which layer failed — breaker, retry, or timeout?" requires good structured logging of decorator outcomes.

## Real-World Scenarios

- **Payment service calling a flaky fraud-check API**: breaker set to trip at 50% failure over last 50 calls, opens for 30s, half-open allows 5 probes — prevents payment threads from blocking on a dead fraud API and backing up checkout entirely.
- **Envoy outlier detection in a K8s mesh**: ejects a single pod returning 5xx consecutively from the Service's endpoint list for 30s while healthy pods keep serving — no app code involvement, works uniformly for Java/Go/Python services behind the mesh.
- **Cascading failure prevention**: service A calls B calls C; C degrades — without breakers, A's and B's thread pools both saturate waiting on C, taking down A and B even though only C is unhealthy ("death by a thousand blocked threads"). Breaker at B→C stops it there.
- **Netflix Hystrix origin story**: built specifically after a mid-tier service outage cascaded to the API gateway and then to the whole site because no call had circuit-breaking/bulkheading — canonical case study for why this pattern exists.

## Nuances & Gotchas

- **Tripping on business errors (4xx)**: naive configs count all exceptions as failures — a spike of legitimate 400s (bad user input) trips the breaker and blocks *valid* traffic too. Explicitly exclude 4xx/validation exceptions from the failure predicate (resilience4j `recordExceptions`/`ignoreExceptions`).
- **Flapping**: OPEN → HALF_OPEN → OPEN → HALF_OPEN cycling rapidly when wait_duration is too short relative to dependency recovery time. Fix: exponential backoff on repeated re-opens, or require a longer sustained success window before fully closing.
- **Minimum call volume**: at low traffic, 2 failures out of 3 calls looks like 66% failure rate and trips instantly — always set `minimumNumberOfCalls` (e.g. 20) so the window has statistical significance before evaluating.
- **Half-open thundering herd**: if HALF_OPEN allows too many concurrent probes at once (misconfigured `permittedNumberOfCallsInHalfOpenState`), it re-floods a barely-recovering dependency and immediately re-trips — keep this small (5–10) relative to normal traffic.
- **Breaker + retry ordering mistake**: if retry wraps the breaker (breaker innermost) instead of the reverse, each retry attempt is independently short-circuited, which can mask real backoff behavior and makes tuning confusing — canonical ordering is breaker outside retry per call-chain diagram above, though some teams intentionally invert this; be consistent and document it.
- **Per-instance blindness**: with N=100 pods each running local resilience4j breakers, a dependency degrading enough to hurt but not enough to trip any single pod's window can still cause aggregate SLO breach — sidecar-level (Envoy) or centrally-aggregated breaker state closes this gap.
- **Silent misconfiguration**: an OPEN breaker returning fallback data (e.g. cached/stale response) can mask an outage from monitoring if the fallback path doesn't emit its own error metric — always instrument fallback invocation separately from success.
- **Timeout must exist for breaker to work**: a circuit breaker without an inner timeout still lets individual calls hang indefinitely; the breaker only sees "failure" after that hang completes, so it reacts far slower than expected. Always pair with an aggressive timeout (e.g. p99 latency + margin, not some arbitrary 30s default).
- **State reset on deploy**: in-process breakers reset to CLOSED on every pod restart/deploy — a rolling deploy during an ongoing dependency outage can cause a burst of retried failures per new pod before it re-trips.
