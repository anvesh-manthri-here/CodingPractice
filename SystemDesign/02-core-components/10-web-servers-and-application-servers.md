# Web Servers and Application Servers

> **TL;DR:** A web server handles connections, TLS, static files, and buffering; an application server executes business logic behind it via a gateway interface. Sizing worker/thread pools correctly and reusing connections matter more than picking a "faster" server.

## Quick Reference

| Concept | Key Fact |
|---|---|
| Web server job | TCP/TLS termination, static files, buffering, reverse proxy, load balancing |
| App server job | Runs app code, sessions, business logic, DB calls |
| Apache model | Prefork / worker MPM — process or thread per connection |
| NGINX model | Event-driven, single-threaded event loop per worker (epoll/kqueue) |
| CPU-bound pool size | `workers = cores + 1` |
| I/O-bound pool size | `workers = cores * (1 + wait_time/service_time)` |
| Gunicorn default | `(2 * cores) + 1` workers |
| Gateway interfaces | WSGI, ASGI, FastCGI, PHP-FPM, Servlet, Rack |
| Graceful reload | SIGHUP / SIGUSR2 + socket handoff, old workers drain then exit |
| Standard deploy | NGINX/Envoy (reverse proxy) → app server (Gunicorn/Puma/Tomcat) |
| Slowloris fix | Buffering proxy in front absorbs slow clients |

## What It Is

- **Web server**: serves HTTP, terminates TLS, serves static assets, proxies dynamic requests. Optimized for many concurrent connections with minimal per-connection cost.
- **Application server**: hosts and executes application code (Python/Java/Ruby/Node), manages request-scoped state, talks to DBs/caches. Optimized for CPU/memory-heavy execution, not raw connection concurrency.
- They're often deployed together, never merged in production: web server absorbs network chaos, app server stays focused on logic.

## Responsibilities

| Layer | Does | Does NOT do |
|---|---|---|
| Web server | TLS termination, HTTP parsing, static files, gzip/brotli, rate limiting, connection keep-alive, request buffering, load balancing/reverse proxy | Execute business logic, hold DB connections |
| App server | Route dispatch, business logic, ORM/DB calls, session/auth logic, template rendering | Terminate raw TLS at scale, serve millions of static files efficiently |

## How It Works

```
Client --TLS--> [NGINX/Envoy: static + proxy] --HTTP/FastCGI/WSGI--> [App Server: Gunicorn/Puma/Tomcat] --> App Code --> DB
```

- Web server accepts connection, may serve response directly (static file) or proxy upstream.
- Proxying uses a gateway protocol: HTTP/1.1 over a Unix socket or loopback, or a language-native protocol (FastCGI, AJP).
- App server's worker pool picks up the request, runs app code, returns response through the same path.
- Buffering: web server can fully read a slow client's request before handing a complete request to the app server, freeing app workers quickly.

## Types / Classifications

### Process/Concurrency Models
- **Prefork (Apache `mpm_prefork`)**: master forks N worker *processes*, each handles one connection at a time. Memory-safe (no shared state, crash isolation) but expensive per worker (full process + loaded modules replicated).
- **Worker/threaded (Apache `mpm_worker`, `mpm_event`)**: processes each hold a thread pool; more concurrency per unit memory, but shared-memory bugs possible.
- **Event-driven (NGINX, Node, Envoy)**: small fixed number of worker processes (~1 per core), each runs a non-blocking event loop (epoll/kqueue) handling thousands of connections via async I/O. No thread-per-connection cost; blocking calls stall the whole loop.

### Apache vs NGINX
| | Apache (prefork/worker) | NGINX |
|---|---|---|
| Concurrency unit | Process or thread per connection | Event loop, async per worker |
| Memory under load | Scales linearly with connections | Flat, scales with cores |
| Dynamic modules (.htaccess, mod_php) | Rich, per-directory config | Minimal, config-only, no runtime modules |
| C10K behavior | Degrades (context-switch/memory cost) | Designed for it |
| Typical role today | Legacy app server / embedded interpreter | Reverse proxy, static server, LB, TLS termination |

## Where It Fits

```
Internet -> CDN -> Load Balancer -> Reverse Proxy (NGINX/Envoy/Caddy)
                                        |-- static assets (served directly)
                                        `-- /api/* --> App Server pool (Gunicorn/uvicorn/Puma/Tomcat/Node)
                                                          `--> DB / cache / downstream services
```
- Sits between the load balancer and the application code, and between the app process and the OS network stack.
- In containers, the "reverse proxy" role often collapses into a sidecar (Envoy in a service mesh) instead of a standalone server.

## Common Patterns & Real-World Tools

- **Gateway interfaces exist to decouple the web server (fast, general-purpose, any language) from the app runtime (language-specific)** — same server, swap app languages without rewriting the proxy.
  - **WSGI** (Python, sync): Gunicorn workers implement it; one request per worker thread/process at a time.
  - **ASGI** (Python, async): uvicorn/Hypercorn — enables WebSockets, async I/O, used behind Gunicorn as a worker class (`uvicorn.workers.UvicornWorker`).
  - **FastCGI / PHP-FPM**: persistent PHP worker pool, avoids fork-per-request of old CGI.
  - **Servlet container** (Java): Tomcat/Jetty implement the Servlet spec, manage thread pools per request.
  - **Rack** (Ruby): interface between web servers and Puma/Unicorn/Passenger.
- **Reverse-proxy-in-front is the standard**: NGINX/Envoy/Caddy terminate TLS and buffer, then proxy to app servers over localhost/Unix socket — never expose Gunicorn/Puma/Tomcat directly to the internet.
- **Sidecar pattern**: in Kubernetes/service mesh, Envoy runs as a sidecar per pod, handling mTLS, retries, circuit breaking — app server only speaks plain HTTP to localhost.
- Caddy: automatic HTTPS (ACME), simpler config than NGINX, growing in small-to-mid deployments.

## Pros & Cons / Trade-offs

| Choice | Pros | Cons |
|---|---|---|
| Prefork (Apache) | Isolation, simple mental model, tolerates blocking/leaky code | High memory, poor at high concurrency |
| Event-driven (NGINX) | Handles 10k+ connections/worker, low memory | One blocking call stalls all requests on that worker |
| Sync app server (Gunicorn WSGI, Puma) | Simple reasoning, no async pitfalls | Thread/process-bound concurrency ceiling |
| Async app server (uvicorn, Node) | High I/O concurrency per process | Any accidental blocking call kills throughput; harder debugging |
| Reverse proxy in front | Buffers slow clients, TLS offload, easy horizontal scaling | Extra hop latency (~sub-ms to low ms), extra config layer |

## Real-World Scenarios

- **API behind NGINX + Gunicorn**: NGINX buffers uploads/downloads and serves static/media; Gunicorn's sync workers run Django/Flask without worrying about slow clients tying up app processes.
- **High-throughput async API**: FastAPI on uvicorn workers managed by Gunicorn (`gunicorn -k uvicorn.workers.UvicornWorker`), handling many concurrent I/O-bound calls (DB, HTTP) per process.
- **Java monolith**: Tomcat embedded, thread pool sized to DB connection pool size, behind an Envoy/ALB doing TLS termination and health checks.
- **Service mesh microservice**: app container + Envoy sidecar; app only ever talks HTTP to `localhost:PORT`, Envoy handles retries, mTLS, and observability.
- **Static-heavy site**: Caddy or NGINX serves 95% of traffic directly from disk with zero app-server involvement; only `/api` routes proxy through.

## Nuances & Gotchas

- **Container CPU limits vs host cores**: `os.cpu_count()` in a container often returns the *host's* core count, not the cgroup quota — a pod limited to 0.5 CPU can still spawn `2*32+1 = 65` Gunicorn workers, causing massive over-subscription and OOM kills. Read cgroup `cpu.max`/`cpu.cfs_quota_us` or set worker count explicitly via env var.
- **Thread pool starvation in async runtimes**: a single blocking call (sync DB driver, `requests.get`, disk I/O) inside an `async def` handler blocks the entire event loop — one bad endpoint can stall all concurrent requests on that worker. Fix: run blocking calls in a thread-pool executor (`run_in_executor`) or use async drivers.
- **FD and ephemeral port exhaustion**: each proxied connection can consume a client-side ephemeral port to the upstream; under high RPS without keep-alive reuse, you exhaust the ~28k ephemeral port range or the process FD limit (`ulimit -n`, default 1024) well before CPU/memory becomes the bottleneck. Fix: enable upstream keep-alive pools, raise `ulimit`, tune `net.ipv4.ip_local_port_range`.
- **Slowloris**: a client trickles headers/body 1 byte at a time, holding a worker/thread open indefinitely; prefork/threaded servers with limited worker counts are exhausted with few connections. A buffering reverse proxy (NGINX) fully reads the request before forwarding, so the slow client only ties up a cheap event-loop slot, not an app worker.
- **Timeout misalignment across the chain**: LB timeout (e.g., 60s) shorter than proxy timeout (90s) shorter than app timeout (120s) means the LB retries/cuts a connection while the app server is still processing — causes duplicate side effects and wasted work. Rule: each hop's timeout should be strictly shorter than the one behind it.
- **Keep-alive misconfiguration**: disabling keep-alive between proxy and app server forces a new TCP handshake (and TLS handshake if mTLS) per request — can 2-3x tail latency under load; but keep-alive connections held open too long can pin a specific app worker exclusively to one client, causing load imbalance behind a proxy that doesn't round-robin per-request.
- **Memory-per-worker multiplication (prefork)**: each Apache/Unicorn prefork worker duplicates the app's full memory footprint (interpreter + loaded libraries, e.g., 150-300MB for a Rails/Django app); 40 workers can mean 6-12GB RSS. Copy-on-write from `fork()` helps only for memory untouched post-fork — Ruby/Python GC quickly dirties pages, so COW savings shrink over time. Prefer worker recycling (`max_requests`) to bound growth from leaks.
- **Graceful reload mechanics**: SIGHUP (NGINX/Apache) or SIGUSR2 (Unicorn/Gunicorn) triggers spawning new workers against the *same bound socket* (`SO_REUSEPORT` or inherited FD), draining old workers after in-flight requests finish, then killing them — zero dropped connections if timeouts are set correctly; a stuck worker with no request timeout can block reload indefinitely.
- **Sizing formula caveat**: the I/O-bound formula assumes uniform blocking ratio; in practice, profile actual wait/service time ratio (APM traces) rather than guessing — over-provisioning threads against a single-CPU-bound downstream (e.g., a DB with its own connection limit) just shifts the bottleneck and adds context-switch overhead.

## Self-Check

1. A container is limited to 2 CPUs via cgroup quota but sits on a 32-core host. Why can `os.cpu_count()`-based worker sizing (e.g., Gunicorn's `2*cores+1`) cause OOM kills here, and what should you read instead?
2. Your API server proxies to an upstream without connection reuse and is hitting connection failures under high RPS, even though CPU and memory are fine. What two OS-level resources are likely exhausted, and what's the fix?
3. An I/O-bound service profiles at a wait/service time ratio of 4:1 on an 8-core box. Using the formula from this file, how many workers should you provision?
4. How does putting a buffering reverse proxy (e.g., NGINX) in front of an app server defeat a Slowloris attack, given that the attack itself still reaches the proxy?
5. Why must each hop's timeout in a LB -> proxy -> app server chain be strictly shorter than the timeout of the hop behind it?

<details><summary>Answers</summary>

1. `os.cpu_count()` typically reports the host's core count, not the cgroup quota, so a 2-CPU pod computes `2*32+1 = 65` workers and massively over-subscribes its actual allocation, triggering OOM kills; read the cgroup `cpu.max`/`cpu.cfs_quota_us` (or set the worker count explicitly via env var) instead.
2. Client-side ephemeral ports (~28k range) and/or process file descriptors (`ulimit -n`, default 1024) are being exhausted because each proxied connection without keep-alive reuse consumes a fresh port/FD; fix by enabling upstream keep-alive pools, raising `ulimit`, and tuning `net.ipv4.ip_local_port_range`.
3. `workers = cores * (1 + wait/service) = 8 * (1 + 4) = 40` workers.
4. The proxy fully reads a slow client's trickled request before forwarding a complete request upstream, so the slow client only ties up a cheap event-loop slot on the proxy, not a limited app worker/thread — the app server never sees the connection until it's whole.
5. If an upstream hop's timeout is longer than the timeout in front of it, the earlier hop (e.g., the LB) can cut/retry the request while the app server is still processing it, causing duplicate side effects and wasted work on the abandoned request.
</details>

---
**Related:** [Concurrency vs Parallelism](../01-fundamentals/09-concurrency-vs-parallelism.md) · [Reverse Proxy and Forward Proxy](02-reverse-proxy-and-forward-proxy.md) · [Load Balancers](01-load-balancers.md)

*Last reviewed: 2026-08*
