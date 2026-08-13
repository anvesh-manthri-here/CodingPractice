# WebSockets, SSE, and Long Polling

> **TL;DR:** Pick the cheapest mechanism that satisfies your directionality need — short polling for rare/simple updates, long polling for compatibility, SSE for server-to-client streams, WebSockets for true bidirectional low-latency; the real engineering problem is not the protocol, it's holding millions of stateful connections open in a fan-out architecture.

## Quick Reference

| Option | Direction | Transport | Reconnect | Proxy-friendly | Relative cost |
|---|---|---|---|---|---|
| Short polling | Client→Server (pull) | HTTP req/res | N/A (new req each time) | Yes | Low value, high request volume |
| Long polling | Client→Server (pull, held) | HTTP req/res | Manual, client re-issues | Yes | Medium (holds a thread/conn per client) |
| SSE | Server→Client only | HTTP/1.1 chunked, single stream | **Automatic**, built into `EventSource` | Yes (plain HTTP) | Medium (1 conn/client, text only) |
| WebSockets | Full duplex | TCP upgrade from HTTP | Manual (app-level) | Sometimes blocked/buffered by old proxies | Higher (persistent conn + framing state) |
| WebTransport | Full duplex, multi-stream | HTTP/3 / QUIC | Built-in (QUIC handles loss) | New; needs UDP/QUIC support | Emerging, lower head-of-line blocking |

## What It Is

- Four (+1) mechanisms to push near-real-time data over HTTP-based infra without a separate custom protocol.
- Core tension: HTTP is request/response; real-time needs the server to speak first — each option is a different trick to allow that.
- WebTransport: newer QUIC-based API giving multiple independent streams + unreliable datagrams, avoiding TCP head-of-line blocking; not yet ubiquitous (2026), used by some gaming/media apps.

## Responsibilities

- Deliver server-originated events to clients with acceptable latency and ordering guarantees.
- Manage connection lifecycle: establish, keep alive, detect death, reconnect, resume state.
- Scale horizontally across many server nodes despite each connection being stateful/sticky.
- Decouple "who is connected where" from "who produces the business event."

## How It Works

**Long polling:** client sends request; server holds it open (no response) until data is available or a timeout (~20-30s) hits; client immediately re-requests. Each cycle is a full HTTP request (headers, TLS if not reused, auth).

**SSE:** client opens `GET` with `Accept: text/event-stream`; server responds `Content-Type: text/event-stream` and keeps the response open, writing `data: ...\n\n` framed events indefinitely (chunked transfer encoding). Browser `EventSource` API handles parsing.

**SSE auto-reconnect + replay:** if the connection drops, `EventSource` automatically reconnects after a server-specified `retry:` interval (ms). Each event can carry `id: <n>`; on reconnect the browser sends header `Last-Event-ID: <n>` so the server can replay everything missed — this is the built-in resume mechanic, no app code needed.

**WebSocket handshake:** client sends HTTP `GET` with `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key` (random base64 nonce); server replies `101 Switching Protocols` with `Sec-WebSocket-Accept` (SHA-1 hash of key + magic GUID). After that, the TCP socket carries the WebSocket **framing protocol** — small binary frames with opcode (text/binary/ping/pong/close), a mask bit (client→server frames MUST be masked), and payload length (7/16/64-bit encoding).

**Keepalive:** WebSocket protocol defines control frames `ping`/`pong` — server (or client) sends ping, peer must reply pong; missed pongs → treat as dead, close. This is separate from any app-level heartbeat JSON message and is what most intermediaries don't understand (they only see opaque binary frames), so idle-timeout at the proxy layer still applies regardless.

```
Client                     LB/Proxy                Gateway Node          Pub/Sub          Business Service
  |--GET Upgrade:ws----------->|------------------------>|                   |                    |
  |<--101 Switching Protocols--|<-------------------------|                   |                    |
  |==== persistent socket, framed messages, ping/pong ====|                   |                    |
  |                             |                          |--subscribe(topic)->|                   |
  |                             |                          |<---publish---------|<---publish---------|
  |<---- pushed frame ----------|<-------------------------|                   |                    |
```

## Types / Classifications

- **By direction:** unidirectional-server (SSE), unidirectional-client-pull (polling/long polling), bidirectional (WebSocket, WebTransport).
- **By transport layer:** HTTP request cycles (polling), single long-lived HTTP response (SSE), upgraded raw TCP (WebSocket), QUIC/UDP streams (WebTransport).
- **By delivery guarantee:** none of these give exactly-once by default — all are at-most-once on the wire; app layer (sequence IDs, ACKs) must add at-least-once/exactly-once semantics.

## Where It Fits

- Sits at the edge, between client and a **connection/gateway tier** — never wire clients directly to stateful business services.
- Gateway tier terminates WebSocket/SSE connections, authenticates once at handshake (cookie/token in URL or first message — no per-frame auth), and subscribes to relevant pub/sub topics per connection.
- **Fan-out pattern:** business services publish domain events to a message bus (Redis Pub/Sub, NATS, Kafka) instead of tracking sockets; any gateway node holding a relevant connection receives the event and pushes to its local sockets. This decouples "which pod holds this user's socket" from "who produced the event."
- Presence (who's online) is tracked as ephemeral state in the pub/sub layer or a shared store (Redis with TTL/heartbeat refresh) keyed by connection, not by service — gateway nodes publish connect/disconnect events other services subscribe to.

## Common Patterns & Real-World Tools

| Tool | Role |
|---|---|
| Socket.IO | WebSocket + long-polling fallback, rooms, auto-reconnect, ack callbacks (Node) |
| Centrifugo | Standalone real-time server/gateway; channels, presence, history/replay via Redis or Postgres |
| Phoenix Channels (Elixir) | BEAM-native, millions of lightweight connections per node (leverages OTP process model) |
| AWS API Gateway WebSocket | Managed connection tier; `connectionId` stored in DynamoDB, Lambda for business logic (fully decoupled gateway/compute) |
| Pusher / Ably | Hosted pub/sub-over-WebSocket-and-SSE as a service; handles presence, history, scaling |
| Envoy | L7 proxy with WebSocket upgrade support; used as the sticky/aware edge in service mesh setups |

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| Short polling | Trivial, stateless, cacheable, works everywhere | Wasteful at low latency targets, high request overhead |
| Long polling | Works through any HTTP proxy/firewall, no special client | Holds server threads/connections, higher latency than push, request churn on every cycle |
| SSE | Simple text protocol, auto-reconnect + replay built in, plain HTTP (cacheable infra, standard auth headers work) | One-way only, browser connection-per-origin limits (6 for HTTP/1.1, mitigated by HTTP/2 multiplexing), no binary framing |
| WebSocket | True bidirectional, low overhead per message after handshake, binary support | No built-in reconnect/replay (must hand-roll), harder to scale/LB, opaque to HTTP-aware middleware (no caching, custom auth) |
| WebTransport | Multiple streams, no head-of-line blocking, unreliable datagram option | Immature ecosystem, needs UDP passthrough (blocked on some corporate networks) |

## Real-World Scenarios

- **Chat / multiplayer / collab editing:** WebSocket — needs low-latency bidirectional messages (typing indicators, cursor positions).
- **Stock ticker, live dashboards, notifications feed:** SSE — server-only push, want HTTP infra (CDNs, standard load balancers) to just work.
- **Legacy enterprise behind strict corporate proxies:** long polling — sometimes the only thing that survives deep packet inspection / old proxy chains.
- **CI build status polling from a CLI tool run occasionally:** short polling — simplicity beats efficiency at this scale.
- **Massive live-event fan-out (sports score to 5M viewers):** SSE or WebSocket behind a gateway tier + pub/sub, often with a CDN-edge relay (e.g., Fastly/Cloudflare) to avoid a single origin fan-out bottleneck.

## Nuances & Gotchas

- **Idle-timeout kills:** AWS ALB defaults to 60s idle timeout; many corporate proxies and mobile carrier NATs silently drop idle connections around 30-60s too — send app-level heartbeats well under that (e.g., every 20-30s) even though WebSocket ping/pong exists, because many intermediaries don't forward control frames as "activity."
- **Sticky sessions vs rolling deploys:** WebSocket/SSE connections are pinned to one gateway node (LB sticky session, e.g. cookie-based affinity). A rolling deploy drains/kills that node — every connection on it disconnects simultaneously. Mitigate with graceful drain (stop routing new conns, send a "reconnect" signal, wait N seconds) not hard kill.
- **Thundering herd on reconnect:** a deploy or brief outage disconnects thousands of clients at once; if they all retry immediately, the reconnect spike can itself take down the gateway tier. Fix: exponential backoff **with jitter** (e.g., `base * 2^attempt + random(0, base)`), capped, on the client.
- **Connection state is the scaling problem, not CPU:** each open connection costs memory (socket buffers, TLS session state, app-level metadata) — a naive server might hold ~10-50KB/connection; C10K (10K conns) is trivial today, C1M (1M conns/node) requires event-loop architectures (epoll/kqueue, not thread-per-connection) as in Phoenix/Erlang or nginx/Envoy-style event loops.
- **LB connection limits:** classic ELB/ALB and even NAT devices have a max concurrent connection ceiling per node/target — capacity planning must budget connections, not just requests/sec, and often means horizontally sharding the gateway tier with consistent hashing on user/session ID.
- **No ordering/delivery guarantee across a reconnect gap:** messages published while a client is disconnected are lost unless you implement sequence numbers + a replay buffer (SSE's `Last-Event-ID` gives this for free; WebSocket needs a custom "resume with cursor" protocol, e.g. resending an offset/sequence on reconnect).
- **No HTTP caching, no standard auth on the socket:** after upgrade, it's just TCP frames — CDNs/reverse-proxy caching layers, cookie-based auth middleware, and API gateways built for REST don't apply; auth typically happens once at handshake (query param/subprotocol token) and must be re-validated periodically for long-lived sessions since a stolen initial token stays valid until the socket closes.
- **Presence is eventually consistent:** a hard-crashed client (phone loses signal) doesn't send a close frame — servers only detect it via missed heartbeats/pings, so "online" status always lags real state by roughly the heartbeat interval.

## Self-Check

1. WebSocket ping/pong is defined in the protocol, yet connections still get killed for being idle. Why does app-level heartbeating remain necessary?
2. A rolling deploy takes down a gateway node holding thousands of WebSocket connections. What goes wrong with a hard kill, and what's the mitigation?
3. After a brief gateway outage, thousands of clients reconnect at once and the spike takes the gateway tier down again. What's the fix, and what's the exact backoff formula?
4. You need server-to-client push for a live dashboard and want to lean on standard HTTP infrastructure (CDNs, caching, auth headers). Why is SSE preferable to WebSockets here, and what's the trade-off you accept?
5. What does SSE's `Last-Event-ID` mechanism give you for free on reconnect, and what would you have to build by hand to get the same behavior over WebSockets?

<details><summary>Answers</summary>

1. Many intermediaries (corporate proxies, mobile NATs, some ALBs) don't recognize WebSocket control frames as "activity" and silently drop idle sockets around 30-60s regardless of ping/pong; app-level heartbeat messages sent well under that threshold (e.g., every 20-30s) are what actually resets those idle timers.
2. A hard kill disconnects every pinned connection on that node simultaneously, causing a reconnect spike; mitigate with graceful drain — stop routing new connections to the node, signal clients to reconnect, then wait N seconds before terminating.
3. Exponential backoff with jitter on the client, capped: `base * 2^attempt + random(0, base)` — this spreads reconnect attempts out instead of letting them all retry immediately and re-overwhelm the gateway tier.
4. SSE runs over plain HTTP/1.1 chunked responses, so caching-aware infra and standard cookie/header-based auth just work, and it has automatic reconnect plus replay built into `EventSource` with no app code. The trade-off is giving up bidirectionality — SSE is server-to-client only.
5. Each SSE event can carry an `id:`, and on disconnect `EventSource` automatically resends the last one as the `Last-Event-ID` header so the server can replay everything missed — no app code required. WebSockets have no such built-in resume; you must hand-roll a sequence/offset cursor and a replay buffer, then implement the resend logic yourself on reconnect.

</details>

---
**Related:** [Network Protocols](../01-fundamentals/10-network-protocols-tcp-udp-http-grpc-websockets.md) · [Load Balancers](01-load-balancers.md) · [Publish-Subscribe and Event Streaming](08-publish-subscribe-and-event-streaming.md)

*Last reviewed: 2026-08*
