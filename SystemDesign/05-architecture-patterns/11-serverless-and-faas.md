# Serverless and FaaS

> **TL;DR:** Serverless abstracts away servers, capacity planning, and idle cost — you ship a function or container, the platform triggers it on events, scales it 0→N→0, and bills per invocation/duration. The trade-off is cold-start latency and mandatory state externalization.

## Quick Reference

| Aspect | AWS Lambda | Cloud Run | Cloudflare Workers |
|---|---|---|---|
| Unit of deploy | Function (zip/image) | Container image | JS/Wasm bundle |
| Isolation | microVM (Firecracker) | gVisor/container | V8 isolate |
| Cold start | 100ms–2s+ (runtime dep.) | 1–4s (container boot) | ~0–5ms |
| Max duration | 15 min | 60 min (req), unlimited (jobs) | CPU time capped (~30s–50ms/req tiers) |
| Scale-to-zero | Yes | Yes | Yes (always warm-ish at edge) |
| Pricing basis | GB-sec + requests | vCPU-sec + memory-sec + requests | CPU-ms + requests |
| State | External only | External only | KV/Durable Objects/R2 |
| Language flexibility | Runtimes + custom (Docker) | Any (Docker) | JS/TS/Wasm/Rust-via-Wasm |

## What It Is

- "Serverless" = no server management, not "no servers." Provider owns provisioning, patching, scaling, and idle capacity.
- FaaS (Function-as-a-Service) is the compute flavor of serverless: short-lived, event-triggered functions billed per execution — Lambda, Azure Functions, Google Cloud Functions.
- Adjacent serverless compute: Cloud Run (serverless containers), Cloudflare Workers (serverless V8 isolates at edge) — broader "serverless" umbrella than pure FaaS.
- What it abstracts: OS patching, capacity planning, load balancer config, auto-scaling logic, and idle-server cost.
- What it does NOT abstract: cold starts, concurrency limits, execution timeouts, vendor-specific IAM/networking, cost predictability at scale.

## Responsibilities

- **You own:** business logic, dependency packaging, memory/timeout config, IDs/permissions per function, idempotency, and externalizing all state.
- **Platform owns:** scheduling invocations, scaling instances (0 to burst limits, e.g., Lambda default 1000 concurrent/region), host patching, network isolation between tenants.
- **Shared:** cold-start mitigation (you: package size, provisioned concurrency; platform: snapshotting, pre-warming).

## How It Works

1. Event source (API Gateway, S3 put, SQS message, cron, HTTP request) triggers invocation.
2. Platform checks for a warm instance; if none, spins up new execution environment (**cold start**).
3. Runtime loads code/dependencies, initializes global scope (DB connections, SDK clients) — this init cost is amortized across warm invocations only.
4. Handler executes with the event payload, returns response or writes to downstream (queue, DB).
5. Instance stays warm briefly (Lambda: minutes, idle-dependent) to serve next invocation without re-init; frozen/thawed between invocations to save CPU while idle.
6. Environment eventually recycled — any local disk (`/tmp`) or in-memory cache is **not guaranteed** to survive to the next invocation.

```
Event → [Router/Trigger] → warm? --yes--> Handler(payload) → Response
                              |no
                              v
                        Cold Start: alloc VM/isolate → load code → init → Handler(payload)
```

## Types / Classifications

- **Container-based FaaS** (Lambda, Cloud Run, Azure Functions): microVM or container per instance, strong isolation, higher cold-start floor (100ms–seconds), supports arbitrary runtimes via container images.
- **Isolate-based edge compute** (Cloudflare Workers, Fastly Compute@Edge): V8 isolates share a process, near-zero cold start (single-digit ms), but restricted to JS/Wasm and limited CPU/memory (128MB, no native binaries beyond Wasm).
- **Event-driven vs HTTP-driven**: async (SQS/S3/EventBridge triggers, retried on failure, no caller waiting) vs sync (API Gateway/ALB, caller blocks for response).
- **Request-based vs job-based** (Cloud Run specifically): Cloud Run Services (HTTP, scale on concurrent requests) vs Cloud Run Jobs (run-to-completion batch, no HTTP).
- **Provisioned/reserved concurrency**: pre-warmed instances kept hot to eliminate cold starts, paid for even when idle — a deliberate opt-out of pure pay-per-use.

## Where It Fits

- Glue code between managed services: S3 → Lambda → DynamoDB, image thumbnailing, webhook handlers.
- API backends with spiky/unpredictable traffic where always-on EC2/K8s would sit idle most of the time.
- Cron/batch jobs, ETL steps, event processing (Kafka/Kinesis consumers via Lambda triggers).
- Edge logic: auth checks, A/B routing, header rewriting at CDN edge (Workers) before hitting origin.
- NOT a fit as the sole compute for long-lived stateful services (WebSocket servers holding connection state, in-memory session stores) or steady high-throughput workloads (>~30-40% sustained utilization — EC2/Fargate gets cheaper).

## Common Patterns & Real-World Tools

- **API Gateway + Lambda + DynamoDB**: classic serverless REST API, single-table design to avoid N+1 cold DB calls.
- **Step Functions / Durable Functions**: orchestrate multi-step workflows across stateless functions since functions can't hold state between steps themselves.
- **SQS/EventBridge fan-out**: decouple producer from Lambda consumer, gives retry/DLQ semantics FaaS lacks natively.
- **Cloud Run for "lift-and-shift serverless"**: existing Docker containers get scale-to-zero without rewriting as functions — good migration path from k8s.
- **Cloudflare Workers + KV/Durable Objects**: stateful coordination at edge (rate limiting, WebSocket hibernation) despite stateless isolate model.
- **Serverless Framework / SAM / Terraform**: IaC to manage function sprawl, versioning, and permissions at scale.

## Pros & Cons / Trade-offs

| Dimension | Serverless wins | Always-on wins |
|---|---|---|
| Traffic pattern | Spiky, bursty, idle periods | Steady, high, predictable |
| Cost at low/med volume | Pay only for actual usage | Idle capacity wasted |
| Cost at high sustained volume | Per-invocation pricing compounds expensive | Reserved/spot instances amortize cheaper |
| Ops burden | Near-zero (no patching/scaling code) | Significant (capacity planning, autoscaling tuning) |
| Latency sensitivity | Cold starts hurt p99 | Consistent latency, warm always |
| Long-running/stateful | Poor fit (timeouts, no local state) | Natural fit |
| Vendor lock-in | High (triggers, IAM, proprietary APIs) | Lower (portable containers) |

**Break-even rule of thumb:** Lambda vs equivalent Fargate/EC2 typically crosses over around 30-40% sustained CPU utilization — below that serverless is cheaper, above it dedicated compute wins.

## Real-World Scenarios

- **Netflix**: uses Lambda for encoding pipeline triggers and operational automation, not for core streaming compute (too costly/latency-sensitive at that volume).
- **iRobot**: rebuilt IoT backend on Lambda + DynamoDB, cut infra cost significantly by matching pay-per-use to bursty device check-in traffic.
- **Cloudflare Workers for edge auth**: JWT validation and geo-routing done in <5ms at 300+ PoPs before request reaches origin, impossible with container cold starts at that scale.
- **Coca-Cola vending machines**: event-driven Lambda for machine telemetry — infrequent, unpredictable events across thousands of devices, classic FaaS sweet spot.
- **Anti-pattern seen in practice**: teams put a high-QPS steady internal API on Lambda, get surprised by a bill 3-5x an equivalent ECS service — sustained load defeats the pay-per-use advantage.

## Nuances & Gotchas

- **Cold start tax compounds with VPC attachment**: Lambda functions inside a VPC historically added seconds for ENI attachment; Hyperplane ENIs (2019+) fixed most of this but cross-account/complex VPC setups still see spikes.
- **Language runtime matters a lot**: Node/Python/Go cold starts ~100-300ms; JVM-based (Java, Kotlin, C#) can be 1-2s+ due to classloading/JIT — SnapStart (Lambda Java) or GraalVM native-image mitigates this.
- **Connection pool exhaustion**: each concurrent Lambda instance can open its own DB connection; at 1000 concurrency you can blow out Postgres `max_connections` — use RDS Proxy, PgBouncer, or Aurora Data API.
- **"Frozen" execution environments**: background threads/timers started in one invocation may resume mid-execution in the next invocation on the same warm instance — causes subtle bugs (stale async work firing unexpectedly).
- **Idempotency is mandatory, not optional**: at-least-once delivery (SQS, S3 events, EventBridge retries) means duplicate invocations WILL happen — design handlers idempotent (dedupe keys, conditional writes).
- **No local state means no in-memory cache reliability**: `/tmp` (512MB-10GB on Lambda) persists only within a warm instance's lifetime, not across cold starts or between concurrent instances — never treat it as durable.
- **Concurrency limits throttle silently**: default account/region concurrency caps (Lambda: 1000) can cause 429s under burst; needs reserved concurrency or limit increase requests planned ahead.
- **Provisioned concurrency isn't free**: paying to keep instances warm reintroduces the "always-on cost" you were trying to avoid — defeats part of the value prop if overused.
- **Observability is harder**: no persistent host to SSH into; distributed tracing (X-Ray, OpenTelemetry) across dozens of short-lived functions becomes essential, not optional.
- **Workers' isolate model has hard CPU limits**: no long CPU-bound loops (crypto, image processing) without hitting the ~10-50ms CPU-time wall — must offload to Durable Objects or external service.
- **Testing/local dev friction**: emulating cold starts, IAM permissions, and event payloads locally (SAM local, LocalStack) never perfectly matches production trigger behavior — integration bugs slip through.
- **Egress and API Gateway costs often dwarf compute costs**: teams optimize function duration and ignore that API Gateway request pricing or NAT Gateway egress is the actual bill driver.
