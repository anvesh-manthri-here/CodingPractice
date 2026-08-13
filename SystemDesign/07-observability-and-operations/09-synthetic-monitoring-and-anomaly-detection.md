# Synthetic Monitoring and Anomaly Detection

> **TL;DR:** Synthetic monitoring proactively probes your system from the outside on a schedule, so you find out about an outage before any real user does — real user traffic (RUM/passive monitoring) tells you what's happening, synthetics tell you what's happening *even with zero real traffic hitting that path*. Anomaly detection automates "is this number weird" so humans don't have to eyeball every dashboard.

## Quick Reference

| Concept | What it does | Key trait |
|---|---|---|
| Synthetic monitoring | Scripted probes run on a schedule from external locations | Proactive, works even with zero real traffic |
| Real User Monitoring (RUM) | Passive telemetry from actual user sessions (browser/mobile) | Reactive, only as good as real traffic coverage |
| Uptime/ping check | Simplest synthetic: is the endpoint up, what's the status code | Cheap, low fidelity |
| Scripted/multi-step synthetic | Simulates a full user flow (login → add to cart → checkout) | Catches functional regressions, not just "is it up" |
| Anomaly detection | Statistical/ML flagging of metric values that deviate from expected pattern | Complements static thresholds, catches novel failure shapes |

## What It Is

- **Synthetic monitoring**: scripted, repeatable checks executed from geographically distributed locations (or in-cluster) on a fixed interval — a ping check, an HTTP status check, or a full multi-step browser flow (Selenium/Playwright script) that exercises the exact critical path a real user would.
- **Anomaly detection**: algorithms (statistical — seasonal decomposition, standard-deviation bands; or ML-based) that learn a metric's normal pattern (including daily/weekly seasonality) and flag deviations, instead of relying purely on a human-picked static threshold.
- Both exist to close gaps that passive, request-driven observability (logs/metrics/traces, files 01-04) can't: synthetics catch outages **before any real user hits the broken path** (e.g., 3am, low-traffic region); anomaly detection catches **failure shapes nobody wrote an alert rule for**.

## Responsibilities

- Synthetic checks must run from locations/networks independent of your own infrastructure (third-party probe locations, or at minimum a separate region/AZ) — a probe running from the same failing datacenter doesn't prove external reachability.
- Checks must cover **business-critical user journeys**, not just "does the homepage return 200" — login, checkout, search are usually the highest-value flows to synthetically monitor.
- Anomaly detection must be tuned against real seasonality (day-of-week, time-of-day, holiday patterns) or it produces useless noise — flagging "3am traffic is anomalously low" every single night is a config bug, not a finding.

## How It Works

**Synthetic monitoring pipeline**:
```
Scheduler (every 1-5 min) → dispatches probe from N global locations
   → probe executes script (HTTP GET, or full browser flow)
   → records: success/fail, status code, response time, screenshot (for browser checks)
   → if fails from multiple locations consecutively → alert (single-location
     failure is often just that location's network, not your outage)
```
- Multi-location confirmation avoids false pages from one probe location having a transient network issue unrelated to your service.

**Anomaly detection (statistical)**:
```
Baseline: metric's historical value at this same time-of-day/day-of-week
          (e.g., moving average + seasonal adjustment, or STL decomposition)
Current value compared to baseline ± N standard deviations
  → outside band for M consecutive periods → flag as anomaly
```
- More advanced systems (Datadog, Amazon Lookout for Metrics) use ML models trained per-metric to adapt the "normal" band automatically as patterns shift, rather than a fixed static band.

## Types / Classifications

| Type | Example | Best for |
|---|---|---|
| Uptime/ping check | HTTP GET returns 200 within Xms | Baseline availability, cheapest to run |
| API/endpoint check | Specific API call with expected response body assertion | Functional correctness of a specific endpoint |
| Multi-step browser/transaction check | Full login→checkout flow via headless browser | Catching regressions in critical business flows, including JS/frontend bugs |
| DNS/SSL/certificate check | Domain resolves correctly, cert not expiring soon | Catching a whole class of "silent time-bomb" failures |
| Statistical anomaly detection | Seasonal-adjusted threshold on a metric | Catching drift/degradation static thresholds miss |
| ML-based anomaly detection | Learned model of "normal" per metric | Catching complex/multivariate anomalies humans wouldn't hand-tune for |

## Where It Fits

- Synthetics complement **RUM and passive metrics** (files 01, 03) by covering the case where real traffic volume is too low, too geographically skewed, or entirely absent from a critical path (e.g., a disaster-recovery region that's normally cold).
- Feeds the same **alerting/on-call pipeline** (file 07) — a synthetic check failure is just another alert source, ideally symptom-based (multi-location confirmed failure) rather than noisy single-probe blips.
- Ties into **health checks** (Section 06) conceptually but operates from *outside* the system rather than the LB polling instances internally — synthetics validate the whole path (DNS → CDN → LB → app → DB), not just one instance's liveness.
- Anomaly detection is an enhancement layer on top of **metrics and SLOs** (files 03, 05) — it can flag SLO-relevant metrics drifting abnormally even before a static burn-rate alert threshold is crossed.

## Common Patterns & Real-World Tools

| Tool | Category | Notes |
|---|---|---|
| **Pingdom, UptimeRobot** | Simple uptime/ping checks | Cheap, easy, good baseline coverage |
| **Datadog Synthetics, New Relic Synthetics** | Full synthetic suite | Multi-step browser checks, global probe locations, integrates with APM |
| **Checkly** | Developer-focused synthetics | Playwright-based scripted checks, "monitoring as code" |
| **Grafana Synthetic Monitoring (k6-based)** | Open-source-friendly | Built on k6 load-testing engine |
| **Amazon CloudWatch Synthetics, Lookout for Metrics** | AWS-native | Canary scripts + ML-based anomaly detection |
| **Prometheus + `blackbox_exporter`** | DIY synthetic probing | Simple HTTP/TCP/ICMP probes exposed as Prometheus metrics |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Synthetic monitoring | Catches outages with zero real traffic, proactive, works for low-traffic paths | Only tests what you scripted — doesn't catch issues on paths you didn't think to check |
| RUM (passive) | Reflects actual real-world user experience and device/network diversity | Needs real traffic volume; blind to low-traffic times/regions/flows |
| Static-threshold alerting | Simple, predictable, easy to reason about | Breaks down with seasonality; needs manual retuning as traffic patterns shift |
| Anomaly detection | Adapts to seasonality automatically, catches novel failure shapes | Can be a black box (hard to explain why it fired); needs a training/warm-up period; can still false-positive on genuine but unusual legitimate traffic (e.g., a viral event) |

## Real-World Scenarios

- **3am outage caught before customers notice**: a synthetic checkout-flow probe running every 2 minutes catches a broken payment integration at 3:14am — team fixes it before the 6am traffic ramp in another timezone, avoiding what would have been a customer-facing incident with zero synthetic coverage.
- **SSL certificate expiry synthetic**: a scheduled check specifically validates certificate expiry date weeks in advance — catches an about-to-expire cert that would otherwise cause a hard outage at midnight on expiry day, a failure mode regular uptime pings don't catch until it's too late.
- **Anomaly detection catches slow-burn degradation**: error rate creeps from 0.1% to 0.4% over six hours — below any static alert threshold (set at 1%), but the anomaly detector flags it immediately as a statistically significant deviation from the metric's normal tight band, catching a memory leak days before it would've caused a hard outage.
- **Multi-location synthetic avoids a false page**: a synthetic check fails from the Frankfurt probe location due to a regional ISP issue, but succeeds from US, Singapore, and São Paulo — the alerting rule (requires 2+ locations to fail) correctly suppresses a page, versus a naive single-location check that would've woken someone up for a non-issue.

## Nuances & Gotchas

- **Synthetics only cover what you scripted**: a beautifully monitored login/checkout flow provides zero coverage for, say, the password-reset flow if nobody wrote a script for it — synthetic coverage requires ongoing curation as new critical flows launch, not a one-time setup.
- **Single-location synthetic failures are usually the probe's network, not yours**: always require multi-location confirmation before paging, or you'll page on transient internet weather unrelated to your service.
- **Anomaly detection needs a training/burn-in period**: a newly deployed ML-based detector on a brand-new metric has no seasonal baseline yet and will either stay silent or false-positive constantly for the first few weeks — don't route it to pages until it's proven stable against known-good and known-bad historical windows.
- **Anomaly detection can be gamed by slow drift**: if "normal" itself is redefined continuously by a rolling baseline, a very slow, sustained degradation can be absorbed into the new "normal" without ever triggering — pairing anomaly detection with hard SLO-based floors (file 05) catches what pure relative-anomaly detection misses.
- **Synthetic checks themselves need monitoring**: a probe that silently stops running (misconfigured after a credential rotation, say) gives false confidence — "no alerts" must be distinguishable from "the checker is broken," typically via a heartbeat/dead-man's-switch pattern on the checker itself.
- **Browser-based synthetics are the most fragile to maintain**: UI changes (a button ID, a redesigned checkout flow) break scripted synthetic checks even when the underlying service is perfectly healthy — treat synthetic scripts like test code, with the same maintenance burden and CI integration to keep them from silently going stale/red.
- **Cost and probe frequency trade off directly**: running full multi-step browser checks every 30 seconds from 10 global locations is expensive at scale — tier check frequency/fidelity to business criticality (1-min checks for checkout, 5-min for lower-priority flows).
