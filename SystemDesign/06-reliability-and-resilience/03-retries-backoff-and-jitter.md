# Retries, Backoff, and Jitter

> **TL;DR:** Naive retries amplify outages into full-blown collapses; exponential backoff with jitter, capped retry budgets, and strict idempotency are the four load-bearing pillars of a safe retry strategy.

## Quick Reference

| Concept | Formula / Value | Purpose |
|---|---|---|
| Exponential backoff | `delay = base * 2^attempt` | Spread retries over time |
| Cap | `min(delay, max_delay)` (e.g., 20–30s) | Prevent unbounded wait |
| Full jitter | `random(0, min(cap, base*2^attempt))` | Best storm reduction (AWS-recommended) |
| Equal jitter | `delay/2 + random(0, delay/2)` | Bounded floor, less variance |
| Decorrelated jitter | `min(cap, random(base, prev_delay*3))` | Smooths without full randomness |
| Retry budget | e.g., max 10% of traffic as retries | Caps amplification |
| Max attempts | 2–4 typical | Diminishing returns beyond this |
| Circuit breaker trip | 50%+ error rate over rolling window | Stop retrying dead dependency |
| Idempotency key | UUID per logical operation | Dedup on server side |

## What It Is

- **Retry**: reissuing a failed request, betting the failure was transient (network blip, GC pause, leader election).
- **Backoff**: increasing delay between successive retries instead of hammering immediately.
- **Jitter**: randomizing that delay so many clients don't retry in lockstep.
- Together they convert "fail fast and reissue" into a controlled, load-aware recovery strategy rather than a self-inflicted DDoS.

## Responsibilities

- Distinguish retryable errors (timeouts, 503, connection reset) from non-retryable (400, 401, business logic 422).
- Bound total retry attempts and total added latency (deadline propagation).
- Prevent synchronized retry waves across thousands of clients.
- Guarantee at-least-once semantics don't become "at-least-once-but-duplicated-side-effects."
- Give operators a circuit breaker to shed retry load when downstream is truly down, not just slow.

## How It Works

**Why naive immediate retry is dangerous — the retry storm:**
1. Downstream service degrades (e.g., DB connection pool exhausted), latency spikes, some requests time out.
2. Clients immediately retry the same overloaded service.
3. Retries add *more* load exactly when the service has the least spare capacity — classic positive feedback loop.
4. Service that might have self-healed in seconds now stays saturated for minutes; cascades to upstream callers who *also* retry.
5. Result: a transient blip becomes a full outage ("retry amplification" — N clients x M retries = N*M effective load multiplier).

**Exponential backoff mechanics:**
- Attempt 1 fails → wait `base * 2^0`; attempt 2 fails → wait `base * 2^1`; attempt 3 → `base * 2^2`, etc.
- Cap the delay (`max_delay`) so tail latency doesn't run away (e.g., 1s, 2s, 4s, 8s, capped at 20s).
- Combine with a request/deadline budget: if total elapsed time exceeds the caller's SLA, stop retrying and fail fast.

**Why jitter is mandatory — thundering herd without it:**
- If 10,000 clients all fail at the same moment (e.g., a deploy or AZ blip) and use pure exponential backoff, they all wait *exactly* the same delays and retry *in sync* — synchronized waves that repeatedly re-saturate the service.
- Jitter breaks synchronization by randomizing delay, spreading retries across the window instead of spiking at fixed intervals.

**Jitter formulas (AWS Architecture Blog, "Exponential Backoff and Jitter"):**
```
temp = min(cap, base * 2^attempt)

Full Jitter:        sleep = random(0, temp)
Equal Jitter:        sleep = temp/2 + random(0, temp/2)
Decorrelated Jitter:  sleep = min(cap, random(base, prev_sleep * 3))
```
- **Full jitter** empirically gives the lowest total completion time and best spread under load testing — the industry default (used in AWS SDK, gRPC retry policy).
- **Equal jitter** guarantees a nonzero minimum wait (useful when zero-delay retries are unsafe) at the cost of less spread than full jitter.
- **Decorrelated jitter** uses the previous delay to seed the next, avoiding both synchronization and the possibility of many back-to-back zero delays.

**Retry budgets + circuit breakers:**
- A retry budget caps retries as a percentage of *total* request volume (e.g., Google SRE book / gRPC: retries ≤10% of successful request rate), independent of per-request backoff.
- Circuit breaker (closed → open → half-open) trips when error rate crosses a threshold, short-circuiting *new* retries entirely for a cool-down window — this is the system-level brake that per-request backoff alone can't provide.
- Pairing: backoff+jitter smooths *one client's* retry pattern; retry budget+breaker caps *aggregate* retry load across all clients — you need both.

**Idempotency as precondition:**
- Safe to retry only if repeating the operation produces the same effect as executing it once (idempotent) — GET, PUT with full state, DELETE by ID are naturally idempotent; POST (create) is not.
- Client generates an idempotency key (UUID) per logical operation; server stores/dedupes on that key (Stripe API, payment gateways) so a retried POST doesn't double-charge.
- Without idempotency, retrying a non-idempotent write risks duplicate orders, double-sends, double-charges — backoff/jitter only controls *timing*, not *correctness*.

## Types / Classifications

| Strategy | When to use | Notes |
|---|---|---|
| Fixed delay | Low-stakes, low-concurrency internal jobs | Simple but synchronization-prone |
| Exponential backoff (no jitter) | Rarely — only single-client scenarios | Still suffers thundering herd at scale |
| Exponential backoff + full jitter | Default for distributed clients | AWS/gRPC recommended |
| Exponential backoff + equal jitter | When a minimum backoff floor is required | e.g., rate-limited APIs |
| Decorrelated jitter | High-throughput retry loops (queue consumers) | Avoids the "many zero delays" edge case of full jitter |
| Retry-After header driven | HTTP 429/503 with explicit hint | Honor server's stated backoff, don't guess |

## Where It Fits

- **Client SDKs**: AWS SDK, gRPC, Resilience4j, Polly (.NET) all ship built-in exponential-backoff-with-jitter retry policies.
- **Service mesh / API gateway**: Envoy, Istio implement retry budgets and circuit breaking at the infrastructure layer, decoupling retry policy from application code.
- **Message queues**: Kafka consumers, SQS with DLQ + visibility timeout backoff — retry logic lives in the consumer/redrive policy, not per-call.
- **Layered systems**: each hop (client → gateway → service → DB) should NOT independently retry with full attempts — retry amplification multiplies across layers (3 layers x 3 retries = 27x load) unless only the outermost layer retries.

## Common Patterns & Real-World Tools

- **AWS SDK**: full jitter is the default retry mode (`STANDARD` and `ADAPTIVE` modes add client-side rate limiting on top).
- **gRPC**: built-in retry policy config (`maxAttempts`, `initialBackoff`, `maxBackoff`, `backoffMultiplier`) plus **hedging** (send duplicate request after a delay without waiting for failure — different from retry).
- **Resilience4j / Polly**: retry + circuit breaker + bulkhead composable decorators in Java/.NET.
- **Envoy**: `retry_policy` with `num_retries`, `per_try_timeout`, and **retry budget** (`max_retries` as % of active requests) at the proxy layer.
- **Stripe/payment APIs**: mandatory idempotency-key header on all POST/mutating endpoints.
- **Kafka consumer retry**: exponential backoff topic chains (retry-1m, retry-10m, retry-1h) instead of in-process sleep-retry loops.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| No retry | Simple, no amplification risk | Poor UX for transient blips |
| Naive immediate retry | Simple | Retry storms, cascading failure |
| Exponential backoff only | Reduces frequency | Still synchronizes across clients |
| Backoff + jitter | Prevents thundering herd | Slightly higher worst-case single-request latency |
| Retry budget/breaker | Protects downstream at system level | Extra operational complexity, needs tuning per service |
| Aggressive retries everywhere (multi-layer) | N/A | Multiplicative amplification — avoid |

## Real-World Scenarios

- **AWS S3 outage pattern**: clients without jitter retrying in sync after a regional blip extend recovery time by minutes; AWS's own SDK guidance (full jitter) exists precisely because of observed real incidents.
- **Payment double-charge bug**: client times out waiting for a charge API response (charge actually succeeded server-side), naive retry without idempotency key double-charges the customer — root cause is missing idempotency, not bad backoff math.
- **Microservices cascade**: gateway retries 3x, service-A retries 3x calling service-B, service-B retries 3x calling DB — one DB blip becomes 27x load spike; fix is retry only at the edge, or use a shared retry budget across the call chain (deadline propagation via gRPC context / OpenTelemetry baggage).
- **Kubernetes CrashLoopBackOff**: kubelet itself uses capped exponential backoff (10s → 20s → 40s ... capped at 5min) for restarting failing pods, the same pattern applied at the infra level.

## Nuances & Gotchas

- **Multi-layer amplification is the #1 silent killer**: each service in a call chain retrying independently multiplies load exponentially with depth; enforce "retry once, at the edge" or propagate a shared deadline/budget so inner layers know not to retry.
- **Jitter without a cap is still dangerous**: unbounded exponential growth even with randomization can push tail latency past client timeouts, causing *client-side* retries on top — always pair with `max_delay`.
- **Retrying non-idempotent operations is a correctness bug, not a performance one**: no amount of backoff tuning fixes duplicate side effects; fix at the idempotency-key/dedup layer.
- **Circuit breakers can mask real capacity problems**: if breaker keeps flapping open/half-open, that's a signal to fix downstream capacity, not just to tune thresholds.
- **Retry-After header ignored**: many client libraries retry immediately despite the server explicitly saying "wait N seconds" (common in 429 rate-limit responses) — always honor it when present.
- **Hedged requests vs retries are different**: hedging fires a second request *before* failure (to cut tail latency) and can *increase* load if overused — only safe for idempotent, cheap reads with low duplicate-request cost.
- **Timeouts shorter than actual processing time cause false retries**: client times out and retries while the original request is still being processed server-side — can look identical to a retry storm but the root cause is timeout misconfiguration, not backoff.
- **Testing backoff/jitter is often skipped**: load-test retry behavior under actual downstream degradation (chaos engineering, e.g., inject 500ms latency) — synchronized retry bugs only show up under real concurrent failure, not unit tests.
- **DNS/connection-level retries bypass application backoff**: TCP/HTTP client connection pools may retry at a lower layer (e.g., keep-alive reconnect) outside your application's backoff logic — audit the full stack, not just app code.
