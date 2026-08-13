# Saga Pattern

> **TL;DR:** A saga replaces one distributed ACID transaction with a sequence of local transactions, each service committing its own DB and publishing an event/command to trigger the next step; if any step fails, previously completed steps are undone via explicit compensating transactions.

## Quick Reference

| Aspect | Choreography | Orchestration |
|---|---|---|
| Control | Distributed — services react to events | Centralized — orchestrator issues commands |
| Coupling | Low (pub/sub), but implicit workflow | Higher (orchestrator knows all services) |
| Visibility | Hard to trace end-to-end | Single place to see/monitor state |
| Failure handling | Each service listens for failure events, compensates itself | Orchestrator explicitly calls compensations in reverse order |
| Best for | 2-4 steps, simple flows | Long, complex, branching workflows |
| Real tools | Kafka, EventBridge, SNS/SQS | Temporal, AWS Step Functions, Camunda, Netflix Conductor |
| Consistency model | Eventual consistency only | Eventual consistency only |
| Isolation | None (no ACID "I") — needs semantic locks | None — same problem |

## What It Is

- A pattern for managing data consistency across microservices without 2-phase commit (2PC), which doesn't scale and creates tight coupling via a transaction coordinator holding locks across services.
- Saga = sequence of local transactions `T1, T2, ... Tn`. Each `Ti` commits to its own service's database and publishes an event or triggers the next step.
- If `Tn` fails, the saga runs compensating transactions `Cn-1, Cn-2, ... C1` to semantically undo prior steps — not a rollback in the DB sense, but a business-logic "undo."

## Responsibilities

- Define the forward path: ordered/parallel local transactions across services (e.g., Order → Payment → Inventory → Shipping).
- Define a compensating action for every step that has a side effect worth undoing.
- Track saga state (which steps completed) so retries/compensation resume correctly after a crash.
- Guarantee eventual consistency, not atomicity — accept that intermediate states are visible to other transactions.
- Enforce idempotency on every step and compensation (network retries WILL re-deliver messages).

## How It Works

```
Order Service --T1--> Payment Service --T2--> Inventory Service --T3--> Shipping
     |                     |                       |
   (fails)                 |                       |
     |<---- C1 none ----   |                       |
                       (T2 fails)
     |<---------------- C1: refund payment ---------
```

- **Choreography:** each service publishes a domain event after its local commit; other services subscribe and act. `OrderCreated` → Payment service charges card → publishes `PaymentCompleted` → Inventory reserves stock → publishes `StockReserved` → etc. On failure, service publishes `PaymentFailed`; Order service subscribes and cancels the order (its own compensation).
- **Orchestration:** a central orchestrator (state machine) sends commands (`ChargeCard`, `ReserveStock`) and waits for replies. On failure it explicitly invokes compensations in reverse order it drove. The orchestrator itself must be durable (persist state after each step) or a crash mid-saga loses track.
- Both models rely on **at-least-once delivery + idempotency keys** (dedupe by `sagaId+stepId`) since messages/commands can be redelivered.
- Orchestrator state persistence is usually event-sourced: replay the event log to know exactly which step you're on after a restart.

## Types / Classifications

- **Choreography saga** — event-driven, decentralized, no single owner of the workflow.
- **Orchestration saga** — a coordinator service/workflow engine owns the sequence, retries, and compensation logic.
- **Additive/pivot-based compensation** — steps before the "pivot transaction" (the point of no return, e.g., payment capture) are compensatable; steps after are retriable-only (must be guaranteed to eventually succeed, e.g., shipping label print retried forever, never compensated).
- **Semantic lock / TCC (Try-Confirm-Cancel)** — variant where each participant reserves resources in a "Try" phase, confirms or cancels explicitly, giving stronger isolation-like guarantees than plain saga.

## Where It Fits

- Microservices architectures where each service owns its own database (database-per-service) and cross-service 2PC is off the table.
- E-commerce checkout: order, payment, inventory, shipping, notification — classic saga textbook example.
- Booking systems (flights + hotel + car): reserve each independently, compensate (cancel reservation) if any leg fails.
- Not needed inside a single service/single DB — just use a local ACID transaction there.

## Common Patterns & Real-World Tools

- **Temporal** (successor to Cadence) — code-based durable workflow orchestration; write the saga as normal code with `try/catch`, Temporal persists execution history and replays on failure. Compensation = explicit catch-block logic, often via a `defer`-style compensation stack.
- **AWS Step Functions** — JSON/ASL state machine, `Catch`/`Retry` fields per state, integrates natively with Lambda/SQS/SNS for orchestrated sagas; visual execution history in console.
- **Camunda / Zeebe** — BPMN-based orchestration engine, popular in enterprise Java shops; models compensation boundary events directly in the BPMN diagram.
- **Netflix Conductor** — JSON workflow definitions, Netflix's own orchestration engine, similar niche to Step Functions.
- **Kafka + outbox pattern** — common choreography backbone: write DB change + event to an outbox table in one local transaction, a CDC connector (Debezium) publishes reliably, avoiding dual-write inconsistency.
- **Axon Framework** — Java/CQRS+event-sourcing framework with built-in saga support (`@Saga`, `@SagaEventHandler`).

## Pros & Cons / Trade-offs

- **Pros:** no distributed locks, each service scales/deploys independently, works across heterogeneous datastores, resilient to long-running steps (hours/days).
- **Cons:** no isolation — dirty reads possible (another request sees a half-completed saga's intermediate state); debugging is harder (need distributed tracing, correlation IDs); compensations add code complexity (business logic doubled: forward + reverse).
- **Choreography cons at scale:** event chains become a "distributed monolith" — hard to trace, cyclic dependencies risk, adding a step means touching multiple services' event subscriptions.
- **Orchestration cons:** orchestrator becomes a critical single point of workflow logic (though not necessarily availability if stateless/replayable); risk of it becoming a mini-monolith owning too much business logic.

## Real-World Scenarios

- **E-commerce order:** Reserve inventory → Charge payment → Create shipment. If shipment creation fails, compensate by refunding payment (`RefundPayment`) and releasing inventory (`ReleaseStock`) — both idempotent, keyed by order ID.
- **Travel booking:** Reserve flight, reserve hotel, reserve car in parallel; if hotel reservation fails, cancel flight + car reservations concurrently via orchestrator fan-out compensation.
- **Bank transfer across microservices:** Debit account A (local tx) → Credit account B (local tx). If credit fails, compensate with a credit-back to A, not a "rollback" — the debit already externally visible (e.g., appeared in A's statement) and must be reversed as a new transaction, not erased.
- **Saga + outbox at a payments company:** Order service writes `OrderCreated` to outbox table in same DB tx as order row; Debezium tails the DB WAL and publishes to Kafka — guarantees the event is never lost even if the process crashes right after commit.

## Nuances & Gotchas

- **Not everything is compensatable.** Sending a confirmation email or SMS can't be "un-sent" — compensate semantically instead: send a follow-up "Order Cancelled" email, not a rollback. Physical-world actions (shipped package) may require a totally different compensation (return/refund process, not an undo).
- **Pivot transaction discipline:** once you cross the pivot step (e.g., payment captured, non-refundable ticket issued), the saga must switch from "compensate on failure" to "retry until success" — mixing these up causes half-compensated, half-retried limbo states.
- **Idempotency is mandatory, not optional.** At-least-once messaging means every step and every compensation handler must dedupe (`sagaId + stepNumber` as idempotency key) or you'll double-charge/double-cancel.
- **Lost updates / dirty reads:** because there's no isolation, a concurrent read can observe "stock reserved" before "payment confirmed" and make a bad decision downstream — mitigate with semantic locks (mark record `PENDING`) so other flows treat it specially.
- **Compensation can itself fail.** A compensating transaction needs its own retry policy and, ultimately, a dead-letter queue + manual/ops intervention path for cases like "refund API is down for an hour."
- **Ordering guarantees in choreography** depend entirely on the broker: Kafka guarantees order per-partition only, so keying events by `orderId`/aggregate ID is essential or steps can race.
- **Timeout-based sagas need a saga log/state store** (durable, queryable) — without one, a crashed orchestrator has no way to resume or know it needs to compensate; this is exactly what Temporal's event history and Step Functions' execution state solve for you.
- **Testing is the hidden cost:** every forward path needs a matching compensation path tested under partial-failure scenarios (step 3 of 5 fails) — teams routinely under-invest here and discover broken compensation logic in production during an actual outage.
- **Sagas != distributed transactions.** They give eventual consistency and business-level rollback, not atomicity/isolation — don't sell them to stakeholders as "the same as a DB transaction," set expectations that intermediate inconsistent states are visible.
