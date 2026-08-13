# Reverse Proxy and Forward Proxy

> **TL;DR:** A forward proxy hides the *client* from the server (egress control); a reverse proxy hides the *server* from the client (ingress control, TLS, routing). Same mechanism — intercept and relay HTTP — opposite side of the trust boundary.

## Quick Reference

| Aspect | Forward Proxy | Reverse Proxy |
|---|---|---|
| Sits in front of | Client (or client network) | Server(s) / origin |
| Hides identity of | Client, from the server | Server topology, from the client |
| Client aware of it? | Usually yes (configured) | Usually no (transparent) |
| Classic tools | Squid, corporate proxy, Tor | NGINX, Envoy, HAProxy, Traefik |
| Typical use | Filtering, caching outbound, anonymity | TLS termination, LB, WAF, caching |
| DNS target | Proxy resolves/forwards to real dest | Client resolves to proxy's IP directly |
| HTTPS handling | CONNECT tunnel (opaque relay) | Terminates TLS, re-encrypts (or not) to backend |
| Overlaps with LB? | No | Yes, heavily (not identical) |

## What It Is

- **Proxy** = intermediary that relays requests on behalf of another party, potentially inspecting/modifying them.
- **Forward proxy**: deployed near/by the *client*; the client explicitly (or transparently) sends traffic through it to reach arbitrary external servers. Server sees the proxy's IP, not the client's.
- **Reverse proxy**: deployed near/by the *server*; sits in front of one or more backend services and accepts inbound client traffic on their behalf. Client sees the proxy's IP/domain, not the backend's.
- Directional test: **whose identity is the proxy protecting?** Forward = client's. Reverse = server's.

## Responsibilities

**Reverse proxy buys you:**
- TLS termination — offload crypto from app servers, centralize cert management (Let's Encrypt renewal in one place).
- Compression (gzip/brotli) before sending to client.
- Static asset / response caching (reduces load on origin).
- Request buffering against slow clients — proxy absorbs a slow-drip client so backend threads/connections aren't tied up (protects against Slowloris-style resource exhaustion).
- Header rewriting / normalization (add `X-Forwarded-For`, strip internal headers, rewrite `Host`).
- Single hook point for WAF, rate limiting, auth checks, request logging.
- Canary / blue-green / weighted routing (send 5% of traffic to new version).

**Forward proxy buys you:**
- Egress control — allowlist/denylist which external domains internal hosts may reach.
- Corporate content filtering / DLP (inspect outbound traffic, block categories).
- Caching frequently requested external resources (reduce bandwidth — classic Squid use case).
- Anonymity — mask client identity from destination servers (VPN-adjacent, Tor).

## How It Works

```
Forward proxy:                          Reverse proxy:
Client -> Proxy -> Internet -> Server    Client -> Internet -> Proxy -> [Backend1, Backend2, ...]
(server sees proxy IP)                   (client sees proxy IP; backends hidden)
```

- Client sends normal HTTP request to proxy; proxy relays to origin, returns response to client. Both directions look transparent to the *other* party.
- **CONNECT tunneling (forward proxy + HTTPS):** client issues `CONNECT host:443 HTTP/1.1` to proxy; proxy opens raw TCP to origin and blindly relays bytes — it cannot see/modify the encrypted payload after handshake (unless doing TLS-interception with an installed CA, common in corporate MITM proxies).
- **Reverse proxy + HTTPS:** proxy typically *terminates* TLS (holds the cert/key), decrypts, inspects/routes, then either forwards plaintext internally or re-encrypts to backend (mTLS in service mesh).

## Types / Classifications

- **Transparent proxy**: intercepts traffic without client configuration (network-level redirect, e.g., iptables); client unaware. Common for reverse proxies (client just hits a domain) and for some ISP/corporate forward proxies.
- **Explicit proxy**: client is configured with proxy address/port (browser proxy settings, `HTTP_PROXY` env var); client actively directs traffic there. Typical for forward proxies.
- **Open proxy**: forward proxy with no access control — relays anyone's traffic (abused for anonymization/attacks).
- **API Gateway**: reverse proxy specialized for API concerns (authN/authZ, rate limiting per client, request/response transformation, aggregation).
- **Sidecar proxy**: reverse+forward proxy combined per-service in a mesh (Envoy as Istio sidecar) — handles both inbound (reverse) and outbound (forward) traffic for its pod.

## Where It Fits

```
Internet --[Reverse Proxy / LB / API GW]--> Service A --[Forward Proxy / Egress GW]--> External API
                                                |
                                          [Sidecar mesh proxy: both directions]
```
- Edge tier: reverse proxy is usually the first hop inside your infra (after DNS/CDN).
- Egress tier: forward/egress proxy sits between internal services and the outside world for compliance and control.
- Service mesh: every pod gets a sidecar acting as reverse proxy for inbound and forward proxy for outbound.

## Common Patterns & Real-World Tools

| Tool | Primary role | Notes |
|---|---|---|
| NGINX | Reverse proxy, LB, cache | Config-driven, very common edge/ingress |
| Envoy | Reverse + forward (sidecar), L7 LB | xDS dynamic config, used in Istio, Ambassador |
| HAProxy | Reverse proxy / LB | Strong L4+L7 LB, high perf, health checks |
| Traefik | Reverse proxy | Auto service discovery (Docker/K8s labels), auto TLS |
| Squid | Forward proxy | Caching, ACL-based egress filtering, classic corporate proxy |
| Kong / Apigee | Reverse proxy (API GW) | Adds auth, quotas, transformation plugins |

- **Reverse proxy vs Load Balancer**: overlapping but not identical. A reverse proxy's defining trait is *hiding/fronting servers*; a LB's defining trait is *distributing load across many instances*. NGINX/HAProxy/Envoy do both simultaneously — but you can have a reverse proxy with one backend (no balancing) and a pure L4 LB (e.g., simple TCP/IP load balancer) that doesn't do HTTP-level work a reverse proxy does (header rewrite, caching, TLS termination). Think: LB = a *function*; reverse proxy = a *position in topology* that commonly implements that function plus more.

## Pros & Cons / Trade-offs

| | Pros | Cons |
|---|---|---|
| Reverse proxy | Central TLS/caching/WAF; hides internals; enables canary/versioning | Single point of failure if not HA'd; adds hop latency; config complexity |
| Forward proxy | Central egress policy; caching saves bandwidth; audit trail | Extra latency/hop; SPOF for all outbound traffic; TLS interception breaks e2e encryption trust model |

## Real-World Scenarios

- **Staff design interview**: "design an API gateway" → reverse proxy + rate limiting + auth + routing; discuss TLS termination point and mTLS to backends.
- **Slowloris mitigation**: put NGINX/Envoy in front of app servers so it buffers slow client connections; app server only gets the request once fully received.
- **Canary release**: reverse proxy (Envoy/Traefik) splits traffic by weight or header to new service version before full rollout.
- **Zero-trust egress**: all outbound service traffic forced through an egress forward proxy (e.g., in a VPC) so security can allowlist domains and log SSRF attempts.
- **CDN edge**: Cloudflare/Fastly are reverse proxies at massive scale — terminate TLS, cache static content, shield origin IP (anti-DDoS).

## Nuances & Gotchas

- **X-Forwarded-For spoofing**: any client can set arbitrary `X-Forwarded-For` header; only trust it if you control the immediate proxy and strip/overwrite incoming values at the edge — otherwise apps trusting it for IP-based rate limiting/allowlisting can be trivially bypassed.
- **Trusted-proxy chains**: with multiple proxy hops, `X-Forwarded-For` becomes a comma-separated list; you must know *how many hops* to trust and take the correct index (e.g., NGINX `set_real_ip_from`, Envoy's `xff_num_trusted_hops`) — misconfiguring this either exposes spoofing or loses the real client IP entirely.
- **Losing real client IP**: without `X-Forwarded-For`/`X-Real-IP`/PROXY protocol, backend sees only the proxy's IP — breaks geo-IP, rate limiting, audit logs. PROXY protocol (HAProxy-originated, now widely supported) passes this at L4 for non-HTTP or before TLS termination.
- **Buffering vs streaming**: reverse proxies that fully buffer request/response bodies break large file uploads (memory pressure, timeout) and Server-Sent Events/chunked streaming (client waits for full buffer before seeing anything). Explicitly disable buffering per-route (NGINX `proxy_buffering off`, `proxy_request_buffering off`) for SSE/websockets/large uploads.
- **Header size limits**: proxies cap header size (NGINX default `large_client_header_buffers 4 8k`) — large JWTs/cookies in headers can trigger `400 Request Header Too Large`; must be tuned consistently across every hop.
- **Double-encoding**: a URL-encoded path re-encoded by an intermediate proxy (e.g., `%2F` becoming `%252F`) can break routing rules or, worse, enable path-traversal/WAF-bypass if inconsistent between proxy layers.
- **Timeouts stacked across layers**: CDN -> reverse proxy -> API gateway -> app server each has its own read/write/idle timeout; if an inner timeout is longer than an outer one, client gets a generic 502/504 while the backend keeps working — always set timeouts *decreasing* from outer to inner layer.
- **CONNECT tunnel blindness**: a plain forward proxy cannot inspect/filter HTTPS payloads or even full URL paths (only sees `CONNECT host:443`), only the destination host — true content filtering requires TLS interception (own CA trusted by clients), which has real security/privacy trade-offs.
- **Reverse proxy as SPOF**: must run multiple replicas behind a floating IP/anycast/DNS — the proxy layer itself needs the same HA thinking as the services it fronts.

## Self-Check

1. What precisely distinguishes a reverse proxy from a load balancer, given that tools like NGINX and HAProxy do both?
2. Why can't a backend blindly trust an incoming `X-Forwarded-For` header for rate limiting or IP allowlisting, and what must be configured to make it trustworthy?
3. With a multi-hop proxy chain, what goes wrong if `xff_num_trusted_hops` (or `set_real_ip_from`) is misconfigured in either direction?
4. Why does enabling full request/response buffering on a reverse proxy break both SSE streaming and large file uploads, and how do you fix it per-route?
5. Across CDN -> reverse proxy -> API gateway -> app server, how should timeouts be ordered between layers, and what happens to the client if that ordering is violated?

<details><summary>Answers</summary>

1. A reverse proxy's defining trait is hiding/fronting servers (position in topology); a load balancer's defining trait is distributing load across instances (a function). A reverse proxy can front a single backend with no balancing, and a pure L4 LB can balance without doing HTTP-level work like TLS termination or header rewriting.
2. Any client can set an arbitrary `X-Forwarded-For` value, so it's only trustworthy if the immediate proxy strips/overwrites incoming values at the edge before appending the real client IP.
3. Trusting too many hops exposes you to spoofing (an attacker-supplied IP is accepted as real); trusting too few loses the real client IP and falls back to an intermediate proxy's IP, breaking geo-IP and rate limiting.
4. Buffering forces the proxy to hold the entire body before forwarding, so SSE/chunked clients see nothing until the buffer fills, and large uploads hit memory pressure/timeouts; fix with `proxy_buffering off` and `proxy_request_buffering off` on the affected routes.
5. Timeouts must decrease from outer to inner layer (CDN longest, app server shortest); if an inner layer's timeout is longer than an outer one, the outer layer aborts and returns a generic 502/504 to the client while the backend keeps working unaware the response is discarded.
</details>

---
**Related:** [Load Balancers](01-load-balancers.md) · [API Gateway](03-api-gateway.md) · [Web Servers and Application Servers](10-web-servers-and-application-servers.md)

*Last reviewed: 2026-08*
