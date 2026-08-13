# Backpressure

> **TL;DR:** Backpressure is a feedback mechanism that lets a slow consumer tell a fast producer to slow down, preventing unbounded memory growth and cascading failure; without it, buffers just delay the crash instead of preventing it.

## Quick Reference

| Concept | Mechanism | Layer | Effect |
|---|---|---|---|
| Explicit backpressure | `request(n)` (Reactive Streams), TCP window | Transport/app protocol | Producer literally cannot send more until told |
| Implicit backpressure | Queue depth, 503/429 responses, latency spikes | App/infra | Producer *infers* it should slow down |
| Load shedding | Drop requests at threshold (LB, `httpd` `MaxConnections`) | Edge/ingress | Protects consumer, sacrifices some work |
| Bounded queue | Fixed-capacity buffer (`ArrayBlockingQueue`, Kafka partition) | App/broker | Converts unbounded growth into blocking or rejection |
| Circuit breaker | Trip on error rate (Hystrix, resilience4j) | Client-side | Stops calling a failing/overloaded dependency |
| Rate limiting | Token bucket, leaky bucket (Envoy, Guava `RateLimiter`) | Ingress/client | Caps producer rate independent of consumer signal |

## What It Is

- Backpressure = a **signal flowing backward** from consumer to producer indicating "slow down," as opposed to data flowing forward.
- Core problem: producer produces at rate P, consumer processes at rate C. If P > C sustained, *something* must give — memory, latency, or dropped work.
- Without backpressure, the gap between P and C is absorbed by a buffer (queue, socket buffer, in-memory list) that grows until OOM or the process dies — the crash is delayed, not prevented.
- Analogy: a dam holding back a river doesn't stop the river's flow rate upstream; it just relocates where the flood happens.

## Responsibilities

- **Signal the mismatch**: expose queue depth, in-flight count, or explicit demand back to the producer.
- **Bound resource usage**: cap queues/buffers so failure is a controlled rejection, not an OOM kill.
- **Propagate the signal upstream**: a slowdown at hop N is useless if hop N-1 keeps blasting data — the signal must reach the *original* source (client, event producer) to actually reduce system-wide load.
- **Preserve stability under sustained overload**: convert "unbounded queueing → crash" into "bounded queueing → controlled degradation."

## How It Works

1. **Unbounded buffering (the failure mode)**: producer writes to an ever-growing queue/list; consumer lags; heap grows; GC pressure rises; eventually OOM or the process is killed by the OS/orchestrator (k8s OOMKilled). The crash happens *later* and with *more* accumulated undelivered work — often worse than immediate failure.
2. **Explicit signaling — Reactive Streams**: consumer calls `subscription.request(n)`, telling producer exactly how many items it can handle; producer *must not* emit more than requested. Implemented in RxJava, Project Reactor, Akka Streams, JDK `Flow` API. This is a pull-based contract — producer is contractually blocked, not just advised.
3. **Explicit signaling — TCP flow control**: receiver advertises a window size in every ACK; sender cannot have more than `window` bytes unacknowledged in flight. Purely transport-layer, automatic, applies to any TCP-based protocol (HTTP/1.1, gRPC over HTTP/2 has its own additional flow control per stream).
4. **Implicit signaling — queue depth / latency**: producer (or a load balancer) polls or observes consumer queue length, p99 latency, or error rate, and throttles itself heuristically. No formal contract — producer *chooses* to slow down based on inference, can be wrong or slow to react.
5. **Implicit signaling — HTTP 503/429**: consumer (server) rejects request when overloaded; producer (client) must interpret this and back off, typically with `Retry-After` header + exponential backoff + jitter. Requires the client to cooperate; a client that ignores 503 and retries immediately makes things worse (retry storm).
6. **Kafka model**: consumer pulls at its own pace (`poll()`); broker retains messages up to retention window regardless of consumer speed — this decouples producer/consumer rates via a durable, bounded-by-time buffer, effectively backpressure absorbed by disk instead of RAM.

## Types / Classifications

| Type | Producer awareness | Example | Failure mode if ignored |
|---|---|---|---|
| Pull-based (demand-driven) | Producer *cannot* violate demand | Reactive Streams `request(n)`, Kafka consumer `poll()` | Not possible by contract |
| Push with feedback | Producer *should* honor signal | TCP window, gRPC flow control | Sender-side buffer overflow |
| Push with inference | Producer *guesses* from side signals | Client watching 503 rate, latency | Retry storms, thundering herd |
| No backpressure | None | Fire-and-forget UDP, unbounded in-memory queue | OOM, delayed crash |

## Where It Fits

```
Client → API Gateway → Service A → Queue → Service B → DB
   ^________________________________________|
        backpressure must propagate ALL the way back here,
        not just stop at Service B's queue
```

- Backpressure must be **end-to-end**, not just hop-local. If Service B slows and only the B↔Queue link backs off, the queue between A and B just grows unbounded — you've moved the problem, not solved it.
- True effectiveness requires propagation through **every hop** back to the original producer (often an external client or upstream event source) so the *actual* rate of new work entering the system drops.
- Common mistake: adding a bounded queue at one internal hop "fixes" that hop's OOM but the caller of that hop (which now blocks or gets rejected) has no idea what to do — if it just retries in a loop, you've converted an OOM into a retry storm.

## Common Patterns & Real-World Tools

- **Reactive Streams / Project Reactor / RxJava**: JVM ecosystem standard for explicit `request(n)` demand signaling; Spring WebFlux built on this.
- **gRPC**: HTTP/2 stream-level flow control windows, independent per stream, tunable via `flow_control_window`.
- **Kafka**: consumer-driven pull model + bounded partition/broker storage = natural backpressure; producers can be throttled via `max.in.flight.requests` and quota configs.
- **TCP**: window-based flow control at the transport layer, invisible to app code but foundational — this is why a slow HTTP client can stall a server thread pool.
- **Akka Streams**: actor mailboxes + demand-based stream processing, same `request(n)` idea.
- **Envoy/NGINX**: connection/request queueing with `max_pending_requests`, circuit breaking thresholds (Envoy `circuit_breakers`) — implicit backpressure via rejection.
- **Kubernetes**: readiness probes remove overloaded pods from the LB rotation — a coarse, implicit backpressure signal at the infra layer.
- **RabbitMQ**: `prefetch count` limits unacked messages delivered to a consumer — explicit, broker-enforced.

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Explicit (request(n), TCP window) | Precise, contractual, no guessing | Requires protocol support end-to-end; not all systems support it |
| Implicit (queue depth, 503) | Works with any protocol, simple to bolt on | Lag in reaction, risk of retry storms, tuning thresholds is guesswork |
| Bounded queues | Predictable memory ceiling | Requires deciding: block, drop, or reject when full — no free lunch |
| Load shedding | Protects system, fast, simple | Actively discards work — data loss or client-visible errors |
| Unbounded buffering | Simple, "just works" until it doesn't | Delays and often worsens the eventual failure (OOM with huge backlog) |

## Real-World Scenarios

- **Log aggregation pipeline**: app writes logs faster than Logstash/Fluentd can ship them; without backpressure, in-memory log buffer grows until the app itself OOMs — mitigated by bounded queue + drop-oldest policy or disk-backed buffer (Filebeat).
- **Mobile push notification fan-out**: notification service outpaces APNs/FCM rate limits; without backpressure the internal queue balloons — fix is rate-limiting the *producer* based on provider's 429 responses, not just queueing more.
- **Streaming video upload**: client (producer) uploads faster than transcoding service consumes; TCP window naturally throttles the socket, but if service reads into an unbounded app-level buffer before transcoding, TCP-level backpressure is defeated by app-level buffering.
- **Retry storm cascading outage**: Service B returns 503 under load; Service A doesn't implement backoff and retries immediately in a tight loop — this is backpressure signal present but not honored, functionally equivalent to no backpressure.
- **Load shedding at ingress**: Envoy configured to reject (503) new requests once concurrent connections exceed a threshold, protecting downstream DB — this is *not* backpressure, it's shedding: dropped requests are gone, not delayed.

## Nuances & Gotchas

- **Backpressure that stops at one hop is theater.** A bounded queue between A and B just moves the OOM risk to whatever sits in front of A, unless A also propagates the "slow down" signal to *its* caller.
- **Backpressure vs. load shedding are often confused but are opposite strategies**: backpressure preserves all work but slows the rate of new work (lossless, but can increase latency unboundedly if producer can't actually slow down — e.g., a hardware sensor emitting fixed-rate telemetry). Load shedding actively discards work to protect the system (lossy, but bounds latency).
- **Mixing them without deciding is a common bug**: a bounded queue with no explicit policy on "what happens when full" silently becomes either backpressure (blocking put) or shedding (drop) depending on implementation default — know which one your `BlockingQueue.offer()` vs `.put()` choice gives you.
- **Async fire-and-forget defeats backpressure entirely**: e.g., using `@Async` methods, message queues without ack, or UDP — the producer has no way to even receive the "slow down" signal, so buffering is the only option, and it's unbounded by default in many frameworks.
- **Buffering "just delays the crash" is literally true with numbers**: e.g., 10K req/s in, 8K req/s out, 2K/s net growth, 4GB heap, 1KB/request → OOM in ~2000 seconds instead of immediately. The system *looks* healthy for 33 minutes then falls over harder (larger backlog to recover, cold caches, GC death spiral).
- **Retry-After and backoff must be honored by the actual producer**, not just logged — many outages are caused by a service correctly returning 503 while every caller silently retries at full speed (thundering herd amplification).
- **Reactive Streams' `request(n)` only works if *every* operator in the chain respects it** — a single `buffer()` or `flatMap()` with unbounded concurrency in the middle of a reactive pipeline silently reintroduces unbounded buffering, defeating the whole point.
- **TCP backpressure can be invisible and misleading**: a stalled TCP receiver (slow client) causes the sender's socket buffer to fill, then `write()` blocks — this can silently stall an entire thread-per-connection server (thread pool exhaustion) with no application-level signal at all until threads run out.
- **Kubernetes HPA is not backpressure**: scaling up consumers reduces the P/C gap but does nothing to control abusive/bursty producers; still need rate limiting or queue-based leveling (e.g., SQS + Lambda concurrency limits) alongside autoscaling.
- **Backpressure adds latency by design** — that's the trade you're accepting. If your SLA can't tolerate producer-side stalling, you actually want load shedding or a bigger (but still bounded and monitored) buffer, not backpressure.
