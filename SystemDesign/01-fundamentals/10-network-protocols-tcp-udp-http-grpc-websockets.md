# Network Protocols — TCP, UDP, HTTP, gRPC, WebSockets

> **TL;DR:** TCP trades latency for reliability via handshake + slow start; UDP skips both for speed. HTTP evolved from serial (1.1) → multiplexed-over-one-TCP-conn (2) → multiplexed-over-UDP/QUIC (3) to kill head-of-line blocking at each layer. gRPC = HTTP/2 + protobuf for typed RPC; WebSockets/SSE = long-lived channels for push.

## Quick Reference

| Need | Pick | Why |
|---|---|---|
| Reliable request/response, browser compat | HTTP/1.1 or 2 | Universal support |
| High fan-out API, many small requests, poor/lossy networks | HTTP/3 (QUIC) | No cross-stream HOL blocking, faster reconnect |
| Internal service-to-service RPC, strict schemas | gRPC | Binary protobuf, codegen, streaming, low overhead |
| Server → client live updates, text-only, simple | SSE | HTTP-based, auto-reconnect, one-directional |
| Bidirectional low-latency (chat, games, collab) | WebSockets | Full-duplex, single persistent TCP conn |
| Real-time media/telemetry, loss-tolerant | UDP (or QUIC/WebRTC) | No retransmit stalls, lower latency |
| File transfer, DB replication, anything needing ordering | TCP | Guaranteed, ordered delivery |
| Latency-critical repeat connections to same host | TLS 1.3 + 0-RTT / HTTP QUIC | Skip handshake RTTs |

## What It Is

- **TCP**: connection-oriented, reliable, ordered, byte-stream transport over IP. Congestion + flow control built in.
- **UDP**: connectionless, unreliable, unordered datagram transport. No handshake, no retransmission, no congestion control (app must implement if needed).
- **HTTP**: application-layer request/response protocol; versions 1.1/2 run over TCP, HTTP/3 runs over UDP via QUIC.
- **gRPC**: RPC framework built on HTTP/2 + Protocol Buffers; generates client/server stubs from `.proto` schemas.
- **WebSockets**: full-duplex, message-framed protocol that upgrades from an HTTP connection, then holds a persistent TCP socket open.

## Responsibilities

| Layer | Guarantees | Does NOT guarantee |
|---|---|---|
| TCP | Ordering, reliability (ACK+retransmit), congestion avoidance, flow control | Message boundaries, latency |
| UDP | Checksummed delivery attempt | Ordering, delivery, congestion control |
| HTTP | Semantics (methods, status, headers), caching, content negotiation | Transport reliability (delegates to TCP/QUIC) |
| gRPC | Typed contracts, streaming semantics, deadlines/cancellation, codegen | Nothing beyond HTTP/2's transport guarantees |
| WebSockets | Full-duplex framed messaging over one TCP conn | Built-in reconnect, ordering across reconnects |

## How It Works

### TCP handshake + slow start
- 3-way handshake: SYN → SYN-ACK → ACK = **1 RTT** before any app data flows (1.5 RTT counting the request itself).
- **Slow start**: congestion window (cwnd) begins at ~10 segments (~14KB), doubles each RTT until loss or ssthresh. A short-lived connection (small API call, one HTTP/1.1 request) never leaves slow start — it pays handshake RTT + ramp-up RTTs before hitting steady throughput. This is why connection reuse (keep-alive, HTTP/2 multiplexing, connection pooling) matters far more than raw bandwidth for typical web latency.
- **Congestion control**: CUBIC (Linux default pre-BBR) grows cwnd as a cubic function of time since last loss — loss-based, fills buffers until packet drop (bufferbloat-prone). **BBR** (Google) models bottleneck bandwidth + RTT directly and paces sends to match, avoiding queue buildup — better throughput on lossy/high-BDP links, used by YouTube, Spotify.

### HTTP evolution (the actual fixes)
1. **HTTP/1.1**: one request in flight per TCP connection (pipelining exists but unusable due to HOL blocking at the app layer) → browsers open 6 parallel TCP connections per origin as a workaround.
2. **HTTP/2**: multiplexes many streams over **one TCP connection** using binary framing — fixes app-level HOL blocking and the 6-connection hack. Adds header compression (HPACK), server push. **But**: still one TCP stream underneath — a single lost packet blocks *all* multiplexed streams until retransmit (transport-level HOL blocking reappears).
3. **HTTP/3 / QUIC**: runs over UDP, implements reliability + streams itself. Each stream has independent loss recovery — one lost packet only stalls its own stream. Handshake merges TCP+TLS into ~1 RTT (0-RTT possible on resumption). Connection IDs survive network/IP changes (mobile Wi-Fi↔LTE handoff without reconnect).

### gRPC
- Protobuf: binary, schema-defined, smaller + faster to (de)serialize than JSON; strong typing catches contract drift at compile time.
- Runs over HTTP/2 → gets multiplexing, flow control, header compression for free.
- 4 streaming modes: **unary** (1 req/1 resp), **server-streaming** (1 req/N resp — e.g. price feed), **client-streaming** (N req/1 resp — e.g. file upload), **bidi-streaming** (N/N — e.g. chat, live translation).
- Deadlines/cancellation propagate across service hops natively — critical for cutting cascading latency.

### WebSockets vs SSE
- WebSocket handshake: normal HTTP request with `Upgrade: websocket` + `Connection: Upgrade` headers → server responds `101 Switching Protocols` → connection becomes raw bidirectional frame channel (1 HTTP round trip to establish, then persistent).
- SSE (Server-Sent Events): plain HTTP response with `Content-Type: text/event-stream`, kept open; browser `EventSource` API auto-reconnects with `Last-Event-ID`. One-directional (server→client) only, text-only, but far simpler ops (works through standard HTTP infra, proxies, load balancers) than WebSockets.

### TLS handshake cost
- TLS 1.2 full handshake: **2 RTT** on top of TCP's 1 RTT = 3 RTT before first app byte.
- TLS 1.3: full handshake down to **1 RTT**; **0-RTT resumption** (session tickets/PSK) lets returning clients send encrypted app data in the *first* flight — 0 extra RTT, but replayable (only safe for idempotent requests).
- QUIC (HTTP/3) folds transport + TLS 1.3 handshake together — new connection ≈1 RTT, resumed connection can be 0-RTT total.

```
HTTP/1.1:  [TCP 1RTT][TLS 1-2RTT][HTTP req/resp] x6 conns, serial per conn
HTTP/2:    [TCP 1RTT][TLS 1RTT][multiplexed streams, 1 conn] -- HOL at TCP layer
HTTP/3:    [QUIC+TLS1.3 ~1RTT, 0-RTT on resume][independent streams, no cross-stream HOL]
```

## Types / Classifications

- **Transport**: TCP (stream), UDP (datagram), QUIC (stream-multiplexed datagram-based).
- **HTTP semantics vs framing**: semantics (methods/status/headers) unchanged since 1.1; only framing/transport changed across 1.1→2→3.
- **gRPC streaming**: unary, server-streaming, client-streaming, bidirectional.
- **Push mechanisms**: WebSockets (bidi), SSE (server→client), long-polling (legacy fallback), HTTP/2 server push (largely deprecated/removed from browsers).

## Where It Fits

- East-west (service-to-service): gRPC over HTTP/2, often behind a service mesh (Envoy/Linkerd) that terminates and re-establishes connections, handles retries/mTLS.
- North-south (client-facing API): HTTP/1.1 or 2 via REST/JSON for broad compatibility; HTTP/3 increasingly at the CDN/edge layer (Cloudflare, Google, Meta default to QUIC).
- Real-time layer: WebSockets/SSE sit alongside the request/response API, often via a dedicated gateway (e.g., separate WS fleet) since they need sticky, long-lived connections — different scaling model than stateless HTTP.
- Media/telemetry: UDP or WebRTC (UDP-based) for voice/video; QUIC increasingly replacing raw UDP+custom protocol.

## Common Patterns & Real-World Tools

| Pattern/Tool | Protocol basis |
|---|---|
| gRPC-Web | gRPC semantics tunneled over HTTP/1.1/2 for browsers (no raw HTTP/2 trailers support in browser fetch) |
| Envoy/Linkerd/Istio | HTTP/2 + gRPC-aware L7 proxying, mTLS, retries |
| Kafka, custom binary RPC | Raw TCP for max control over framing/backpressure |
| WebRTC | UDP + ICE/STUN/TURN for P2P media, SRTP encryption |
| DNS, NTP, QUIC, gaming | UDP (loss-tolerant or self-managed reliability) |
| GraphQL subscriptions | Often WebSockets under the hood |
| Load balancer health checks | Usually TCP or HTTP/1.1 for simplicity |

## Pros & Cons / Trade-offs

| Protocol | Pros | Cons |
|---|---|---|
| TCP | Reliable, ordered, ubiquitous | Handshake + slow-start latency tax, HOL blocking, connection state cost at scale (millions of sockets) |
| UDP | Minimal latency, no setup, app controls reliability | No ordering/delivery guarantee, no congestion control (risk of flooding network) unless app adds it |
| HTTP/1.1 | Simple, cacheable, debuggable (text) | HOL blocking, 6-conn-per-origin overhead |
| HTTP/2 | Multiplexing, header compression | Transport-level HOL blocking on packet loss, harder to debug (binary) |
| HTTP/3 | No cross-stream HOL, fast/0-RTT reconnects, connection migration | Newer — some middleboxes/firewalls block UDP 443, more CPU (userspace transport) |
| gRPC | Fast, typed, streaming built-in | Not browser-native (needs gRPC-Web/proxy), harder to hand-debug than REST/JSON |
| WebSockets | True bidi, low per-message overhead after handshake | Stateful — complicates load balancing/scaling, no built-in reconnect/backoff, harder to cache/proxy |
| SSE | Simple, auto-reconnect, plain HTTP | One-directional, text-only, browser connection-per-origin limits (6) can starve other requests |

## Real-World Scenarios

- **Mobile app on flaky LTE**: HTTP/2 API calls stall repeatedly on packet loss (HOL at TCP layer); migrating to HTTP/3 removes cross-request stalls and survives Wi-Fi↔cellular handoff via QUIC connection IDs.
- **Microservices calling a pricing service 50x per request**: REST/JSON over HTTP/1.1 adds serialization + connection overhead; switching to gRPC unary calls with protobuf and HTTP/2 connection reuse cuts p99 latency significantly.
- **Live stock ticker**: SSE is enough (server→client only) and is simpler ops than WebSockets; if client also needs to send frequent orders, WebSockets is justified.
- **Video conferencing**: UDP/WebRTC — a dropped frame is preferable to TCP stalling the whole stream waiting for retransmit.
- **Payment API, chatty short-lived connections from many small clients**: never leaves TCP slow start — keep-alive pooling or moving to HTTP/2 multiplexing gives large latency wins with zero backend changes.

## Nuances & Gotchas

- **Load balancers and WebSockets**: L4 LB must use sticky sessions or consistent hashing — a WS connection can't be transparently rerouted mid-life like stateless HTTP; scaling WS fleets requires connection draining logic on deploy, not just rolling restart.
- **HTTP/2 "one bad stream ruins them all"**: a single retransmit on the shared TCP connection stalls every multiplexed stream — ironically this can make HTTP/2 *slower* than HTTP/1.1's parallel connections on lossy mobile networks. Root cause behind HTTP/3's existence.
- **QUIC over UDP gets firewalled**: many corporate/enterprise networks block/throttle UDP 443; browsers transparently fall back to HTTP/2, so "HTTP/3 support" doesn't guarantee it's actually used — always verify via `alt-svc` negotiation logs, don't assume.
- **TCP connection exhaustion**: high-throughput services opening a new TCP connection per request exhaust ephemeral ports (TIME_WAIT pileup) — always pool/reuse connections; this bites teams migrating off HTTP/1.1 keep-alive misconfigured to close per request.
- **BBR vs CUBIC coexistence**: BBR can out-compete CUBIC flows sharing the same bottleneck buffer, starving CUBIC-based neighbors — mixed-stack multi-tenant networks need care before flipping the default.
- **gRPC deadlines don't auto-propagate through everything**: if an intermediate proxy or thread pool doesn't forward context, a canceled parent RPC can leave orphaned child RPCs still running — audit deadline propagation across every hop, not just direct calls.
- **0-RTT TLS replay risk**: 0-RTT data can be replayed by an attacker (no forward-secrecy handshake yet) — never put non-idempotent operations (e.g., "charge card") in the 0-RTT early-data flight.
- **UDP amplification**: services accepting unauthenticated UDP (DNS, NTP, QUIC handshakes) are classic DDoS reflection/amplification vectors — QUIC mandates the server not send >3x the client's initial packet size until address is validated, specifically to blunt this.
- **Slow start resets on idle**: TCP congestion window can reset after an idle period (implementation-dependent) — a connection pool that's been idle for seconds may reopen at slow-start speed, not where it left off; don't assume "warm" connections stay warm forever.
- **HTTP/2 server push is effectively dead**: Chrome removed it (2022) — don't design new systems around it; prefer preload hints or HTTP/3 prioritization instead.

## Self-Check

1. On a lossy mobile network, why can HTTP/2 actually perform worse than HTTP/1.1 despite multiplexing?
2. A client resumes a TLS 1.3 session using 0-RTT to a new HTTP/3 endpoint. Counting from the first packet sent to the first application-layer response byte received, how many RTTs are involved, and what's the catch with sending a non-idempotent request in that first flight?
3. Your org's firewall blocks outbound UDP/443. A client reports "HTTP/3 support" in its stack — will requests actually use QUIC? What silently happens instead?
4. A connection pool has been idle for 30 seconds and then bursts traffic. Why might throughput be worse than expected even though the TCP connection was already established?
5. Why does gRPC's deadline propagation sometimes fail to cancel downstream work even though the client canceled the parent RPC?

<details><summary>Answers</summary>

1. HTTP/2 multiplexes all streams over one TCP connection, so a single lost packet triggers a retransmit that stalls every multiplexed stream (transport-level HOL blocking) — HTTP/1.1's 6 parallel connections isolate the loss to just one of them.
2. 0-RTT resumption sends encrypted app data in the first flight, so the response can arrive in ~1 RTT total; the catch is 0-RTT data has no forward-secrecy/replay protection yet, so it must never carry non-idempotent operations (e.g., a charge) since an attacker could replay the flight.
3. No — browsers detect the blocked UDP and transparently fall back to HTTP/2 over TCP; "HTTP/3 support" in the stack doesn't mean QUIC is actually negotiated, which must be confirmed via `alt-svc` logs, not assumed.
4. TCP's congestion window can reset after an idle period (implementation-dependent), so the "warm" connection reopens at slow-start cwnd (~10 segments) rather than the steady-state throughput it had before going idle.
5. If an intermediate proxy or thread pool along the call chain doesn't forward the deadline/cancellation context, the child RPC keeps running as an orphan even after the parent is canceled — propagation must be audited at every hop, not just the direct caller.
</details>

---
**Related:** [DNS and Service Discovery](11-dns-and-service-discovery.md) · [Serialization Formats](12-serialization-formats-json-protobuf-avro-thrift.md) · [WebSockets, SSE, Long Polling](../02-core-components/14-websockets-sse-long-polling.md)

*Last reviewed: 2026-08*
