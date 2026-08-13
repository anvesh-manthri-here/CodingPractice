# Concurrency vs Parallelism

> **TL;DR:** Concurrency is *structuring* a program to deal with many things at once (interleaving); parallelism is *executing* many things at the exact same instant (needs multiple cores). Concurrency is about correctness/design; parallelism is about throughput/hardware.

## Quick Reference

| Concept | Cores needed | Unit | Switch cost | Typical scale | Example |
|---|---|---|---|---|---|
| Concurrency | 1+ | any | — | thousands+ | event loop handling requests |
| Parallelism | 2+ | any | — | = core count | matrix multiply on 8 cores |
| Process | N/A | OS scheduled | ~1-10 µs | 10s-100s | separate services |
| OS Thread | N/A | OS scheduled | ~1-5 µs | 1k-10k | thread pool |
| Green thread/coroutine | N/A | user scheduled | ~20-200 ns | 100k-1M+ | goroutine, `async fn` |
| Context switch (thread, same core) | — | — | ~1-2 µs | — | cache/TLB reload dominates |
| Context switch (process) | — | — | ~5-10 µs | — | + page table swap |
| Function call | — | — | ~1-5 ns | — | baseline reference |

## What It Is

- **Concurrency**: multiple tasks make progress over overlapping time windows; on 1 core this is interleaving (time-slicing), not simultaneity.
- **Parallelism**: multiple tasks execute at literally the same instant, requiring ≥2 execution units (cores, CPUs, GPU lanes).
- Rob Pike's framing: "Concurrency is about dealing with lots of things at once. Parallelism is about doing lots of things at once." You can have concurrency without parallelism (single-core async I/O) and parallelism without much concurrency (SIMD loop).

## Responsibilities

- **Concurrency model** must provide: task scheduling, isolation/communication (shared memory vs message passing), and a way to yield on blocking operations.
- **Parallelism** must provide: work partitioning, synchronization (locks/atomics/barriers), and load balancing across cores.
- Both must handle failure isolation — one task/thread failing shouldn't corrupt others' state.

## How It Works

**Blocking vs non-blocking vs async I/O**
- Blocking: thread parks in the OS until I/O completes (`read()` blocks the calling thread) — simple, wastes a thread per in-flight request.
- Non-blocking: call returns immediately with EWOULDBLOCK if not ready; caller must poll (`select`/`poll`/`epoll`/`kqueue`/IOCP).
- Async I/O: OS/runtime notifies completion via callback/future/event (Linux `io_uring`, Windows IOCP) — no thread sits idle waiting.

**Event loop / reactor**
- Single thread registers fds/handles with the OS multiplexer (epoll/kqueue/IOCP), blocks on that multiplexer, then dispatches ready events to callbacks/handlers one at a time.
- Never call a blocking syscall or do heavy CPU work inside the loop — it stalls every other connection (the classic Node.js "blocking the event loop" bug).
- CPU-bound work must be offloaded to a worker thread/pool (`worker_threads`, `libuv` threadpool) to keep the loop free.

```
epoll_wait() -> [fd3 readable, fd7 writable] -> dispatch callbacks -> back to epoll_wait()
```

**Thread-per-request vs event-driven**
- Apache (prefork/worker MPM): 1 OS thread (or process) per connection; ~8 KB-8 MB stack each; caps concurrency at a few thousand due to memory + context-switch overhead.
- NGINX: event-driven, few worker processes (≈ 1 per core), each running an epoll loop handling 10k+ connections (the C10K solution).
- Node.js: single-threaded JS event loop + libuv threadpool (default 4 threads) for fs/DNS/crypto; great for I/O-bound, bad for CPU-bound (blocks everyone).
- Go goroutines: M:N scheduler — GOMAXPROCS OS threads (M) multiplex millions of goroutines (G) via P (processor) contexts; goroutine stacks start at 2 KB and grow; blocking syscalls detach the M so others aren't starved.
- Java virtual threads (Project Loom, JDK 21+): M:N green threads on `ForkJoinPool` carrier threads; blocking code (`Thread.sleep`, blocking I/O) auto-unmounts the virtual thread from its carrier instead of parking an OS thread — lets you write blocking-style code at goroutine-like scale (millions of VTs).

## Types / Classifications

| Model | Preemptive? | Memory/unit | Scheduler | Notes |
|---|---|---|---|---|
| OS process | yes | MBs (own address space) | kernel | strong isolation, IPC needed to share |
| OS thread | yes | KBs-MBs stack | kernel | shared address space, real parallelism |
| Green thread/coroutine | usually cooperative | KBs, grows dynamically | language runtime | yields at await/blocking points |
| Fiber/callback (Node) | cooperative | closures on heap | single-thread event loop | no preemption, must yield voluntarily |
| SIMD/data parallelism | n/a | n/a | hardware lanes | true parallelism, no concurrency control needed |

## Where It Fits

- I/O-bound services (web/API gateways, proxies) → concurrency-first design (event loop or M:N green threads); parallelism secondary.
- CPU-bound workloads (image processing, ML training, compression) → parallelism-first (multi-process, SIMD, GPU); concurrency model matters less.
- The concurrency model **constrains the architecture**: pick thread-per-request and you get natural backpressure via thread pool exhaustion but hit memory/switch limits early; pick event-driven and you get huge fan-out but must avoid ever blocking the loop, which pushes CPU work to separate workers/processes and forces async-everywhere APIs (coloring problem).
- Load balancers and connection pools must be sized against whichever model backs the service (thread-pool depth vs event-loop concurrency limit).

## Common Patterns & Real-World Tools

- **Reactor pattern**: NGINX, Redis (single-threaded event loop for command execution, I/O threads added in 6.0+ for reads/writes only), Node.js, `epoll`-based proxies (Envoy uses a thread-per-core event loop model).
- **Proactor pattern**: Windows IOCP, `io_uring`-based async runtimes (Tokio on Linux can use it).
- **M:N scheduling**: Go runtime, Erlang/BEAM VM (millions of lightweight processes), Java virtual threads.
- **Thread pool + queue**: Java `ExecutorService`, Python `ThreadPoolExecutor`/`ProcessPoolExecutor`, database connection pools (HikariCP).
- **Actor model**: Akka, Erlang/Elixir — concurrency via message passing, avoids shared-memory hazards entirely.
- **CSP (channels)**: Go channels, Kotlin coroutines + channels — communicate by sharing, don't share by communicating.
- **Data parallelism**: OpenMP, CUDA/GPU kernels, Spark/Hadoop (parallelism across a cluster, concurrency within each executor).

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Thread-per-request | simple mental model, real parallelism, OS-enforced isolation | memory (MBs × threads), context-switch overhead, caps at ~1k-10k concurrent |
| Event loop (single thread) | no locking needed for shared state, huge connection scale, cache-friendly | one blocking call stalls everything, no CPU parallelism, "function coloring" (async spreads through codebase) |
| M:N green threads (Go/Loom) | blocking-style code + massive concurrency, no manual callback chains | scheduler complexity hidden from dev, GC/stack-growth pauses possible, still needs care around blocking native calls (Loom "pinning") |
| Multi-process | full isolation, true parallelism, crash containment | IPC/serialization cost, higher memory, no shared-memory speed |
| Shared-memory threads | fast communication (no copy) | races, deadlock, needs locks/atomics — hard to get right |

## Real-World Scenarios

- **API gateway under 50k concurrent connections**: event-driven (NGINX/Envoy) wins — thread-per-request would need 50k threads (~50-400 GB stack memory alone).
- **Video transcoding service**: CPU-bound → parallelism via multiple processes/workers pinned to cores; async I/O doesn't help since the bottleneck is compute, not waiting.
- **Migrating a Spring MVC (thread-per-request) app to virtual threads**: swapping `Thread` for `Thread.ofVirtual()` removes the thread-pool ceiling for I/O-bound endpoints with minimal code change — but CPU-bound endpoints see no benefit and pinned `synchronized` blocks can starve carrier threads.
- **Node.js CPU spike**: a single `JSON.parse` on a 200 MB payload or an unbounded regex blocks the entire event loop — every other request's latency spikes together (a canonical prod incident pattern, cause of ReDoS-style outages).

## Nuances & Gotchas

- **False sharing**: two threads writing to different variables that land on the same 64-byte cache line cause cache-coherency ping-pong (MESI invalidations), silently degrading throughput 10-100x with no logical bug — fix with padding/alignment.
- **Deadlock via lock ordering**: thread A locks X then Y, thread B locks Y then X — classic; fix by imposing a global lock acquisition order or using `tryLock` with backoff.
- **Priority inversion**: low-priority thread holds a lock a high-priority thread needs, and a medium-priority thread preempts the low one — famously bit the Mars Pathfinder; fix via priority inheritance.
- **Thread pool sizing formula (Little's Law-derived)**: CPU-bound → `threads ≈ cores` (more just adds context-switch overhead); I/O-bound → `threads ≈ cores × (1 + wait_time/compute_time)` — e.g., 8 cores, 90% time waiting on I/O → ~80 threads is reasonable, not 8.
- **Async "function coloring"**: once a function is `async`, every caller up the stack must become async too (or block on it) — this is a real API design cost, not just syntax, and mixing sync/async code is a frequent source of deadlocks (e.g., blocking on a `Task` inside an async context in .NET/older C#).
- **Green-thread pinning**: Java virtual threads pin their carrier thread during `synchronized` blocks or native/JNI calls — under load this can silently degrade to thread-per-request behavior; use `ReentrantLock` instead of `synchronized` in hot paths.
- **GIL (Python)**: CPython threads give concurrency but not CPU parallelism for pure-Python code (GIL) — use `multiprocessing` or C-extension release-the-GIL libraries (NumPy) for CPU parallelism; Python 3.13's free-threaded build removes this but ecosystem support is still maturing.
- **False assumption "more threads = more throughput"**: past the point where cores are saturated, adding threads increases context-switch and cache-thrashing overhead and can *reduce* throughput — always benchmark, don't guess.
- **Context switch cost is understated by the raw number**: the ~1-2 µs kernel-reported switch cost ignores cache/TLB warm-up afterward, which can be 10-100x larger depending on working-set size — this is why thread-per-core (shard by CPU, pin threads) designs (Seastar, Envoy) outperform naive thread pools at high core counts.
- **Starvation vs deadlock**: starvation (a task never gets scheduled, e.g., low-priority goroutine behind a tight loop of high-priority ones) is often mistaken for deadlock in incident reports — different root cause, different fix (fairness/preemption vs breaking a cycle).
- **Distributed parallelism ≠ local parallelism**: partitioning work across machines (Spark/MapReduce) adds network latency and partial-failure modes that local thread parallelism never has — don't reuse local concurrency intuition for cluster design.

## Self-Check

1. You have 12 cores and a service where requests spend 75% of their time waiting on a downstream DB call and 25% doing local compute. Using the thread-pool sizing formula in this doc, roughly how many threads should the pool hold?
2. Two threads each write to their own independent variable, no shared state, yet throughput drops 10-100x under contention with no logical bug. What's happening at the hardware level, and how is it fixed?
3. A team migrates a Spring MVC app's blocking `Thread` calls to Java virtual threads to raise I/O concurrency, but a hot path wrapped in a `synchronized` block shows no improvement under load. Why, and what's the fix?
4. Why does CPython threading give you concurrency but not CPU parallelism for pure-Python code, and what are two ways around it?
5. The raw kernel-reported cost of a same-core thread context switch is ~1-2 µs. Why can naive thread-pool designs still underperform thread-per-core designs (like Seastar/Envoy) at high core counts despite that low number?

<details><summary>Answers</summary>

1. `threads ≈ cores × (1 + wait/compute)` = 12 × (1 + 0.75/0.25) = 12 × 4 = ~48 threads.
2. False sharing — the two variables land on the same 64-byte cache line, so writes trigger MESI cache-coherency invalidation ping-pong between cores even though there's no logical data race; fix with padding/alignment so each variable owns its own cache line.
3. `synchronized` blocks pin the virtual thread to its carrier OS thread instead of letting it unmount on blocking, so under load the hot path degrades back to thread-per-request behavior; replace `synchronized` with `ReentrantLock` in hot paths.
4. The GIL lets only one thread execute Python bytecode at a time, so threads interleave (concurrency) but never run Python code simultaneously on multiple cores (no parallelism); work around it with `multiprocessing` (separate processes, separate GILs) or C-extension libraries like NumPy that release the GIL during native computation.
5. The reported switch cost ignores the cache/TLB warm-up afterward, which can be 10-100x larger depending on working-set size — naive pools bounce threads across cores and thrash caches, while thread-per-core designs pin threads to cores and shard work to keep caches warm.
</details>

---
**Related:** [Latency, Throughput, Bandwidth](02-latency-throughput-bandwidth.md) · [Web Servers and Application Servers](../02-core-components/10-web-servers-and-application-servers.md) · [WebSockets, SSE, Long Polling](../02-core-components/14-websockets-sse-long-polling.md)

*Last reviewed: 2026-08*
