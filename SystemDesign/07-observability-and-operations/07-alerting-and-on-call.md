# Alerting and On-Call

> **TL;DR:** Every page should be actionable, urgent, and real — anything else is alert fatigue that trains on-call to ignore pages, which is how the real incident gets missed. Alert on symptoms (user-facing impact, SLO burn rate) that require a human *right now*, route everything else to tickets/dashboards, and route by service ownership so the right person gets woken up.

## Quick Reference

| Principle | Meaning |
|---|---|
| Page on symptoms, not causes | "Checkout error rate > 5%" (symptom) not "CPU > 80%" (cause — may not even matter) |
| Every page must be actionable | If there's nothing a human can do right now, it shouldn't page |
| Multi-window burn-rate alerts | Combine a fast + slow window to catch severe incidents quickly without paging on noise |
| Ticket vs page vs dashboard | Page = wake someone now; ticket = fix this week; dashboard = FYI, no action needed |
| Escalation policy | Primary on-call → secondary → team lead, each with a timeout before escalating |
| Runbook link | Every alert should link to what to do next, not require the recipient to reverse-engineer intent |

## What It Is

- **Alerting**: automated detection of a condition requiring human attention, delivered via a paging system (PagerDuty, Opsgenie, VictorOps) that can call/SMS/push to wake someone up, distinct from a dashboard that just displays state passively.
- **On-call**: the rotation of engineers responsible for responding to pages for a given service/team, typically on a weekly rotation with defined escalation if the primary doesn't acknowledge in time.
- The core design tension: **too sensitive** → alert fatigue, on-call learns to ignore/silence pages, real incidents get missed; **too lax** → real incidents go undetected until a customer complains, which is strictly worse.

## Responsibilities

- Alert rules must fire on conditions that are both **urgent** (needs action within minutes, not next business day) and **actionable** (the on-call engineer can actually do something — restart, rollback, failover — not just watch helplessly).
- The paging system must route to the correct owning team (service ownership mapping) and escalate automatically if unacknowledged within a timeout.
- Every alert should carry enough context (which service, what's the symptom, link to dashboard/runbook) that on-call doesn't start from zero at 3am.

## How It Works

**Symptom-based vs cause-based alerting**:
```
Cause-based (avoid as primary):  "CPU > 80% for 5 min" → pages even if latency/errors are fine
                                  (autoscaling might handle it; no user impact yet)

Symptom-based (prefer):          "p99 latency > SLO threshold for 5 min AND error rate > 1%"
                                  → pages only when users are actually affected
```
- Cause-level metrics (CPU, memory, queue depth) are still valuable — but as **dashboards for investigation after a symptom-based page fires**, or as tickets for capacity planning, not as the primary page trigger.

**Multi-window, multi-burn-rate alerting** (Google SRE pattern, ties to file 05's error budgets):
```
Alert if: burn_rate(1h window) > 14.4  AND  burn_rate(5m window) > 14.4   → page immediately
       OR burn_rate(6h window) > 6     AND  burn_rate(30m window) > 6     → page, less urgent
       OR burn_rate(3d window) > 1                                        → ticket, not page
```
- Short window alone is noisy (a 2-minute blip trips it); long window alone is slow to detect severe incidents. Requiring both a short and long window to agree filters noise while still catching fast severe burns quickly — this specific pattern is the standard reference implementation from the Google SRE workbook.

**Escalation**:
```
Alert fires → pages Primary on-call
   │ no ack within 5 min
   ▼
pages Secondary on-call
   │ no ack within 5 min
   ▼
pages Team Lead / manager
```

## Types / Classifications

| Alert severity | Response | Channel |
|---|---|---|
| P1/SEV1 — full outage, revenue-impacting | Immediate page, all hands | Phone call + SMS + push |
| P2/SEV2 — degraded, partial impact | Page primary on-call | Push/SMS |
| P3 — minor issue, no immediate user impact | Ticket, business-hours | Slack/email/ticket system |
| Informational | No page, dashboard/log only | None (or low-priority Slack channel) |

## Where It Fits

- Sits directly on **SLOs and error budgets** (file 05) — the best alerting practice is deriving alert thresholds from burn rate against the SLO, not arbitrary static thresholds picked without reference to what "bad" actually means for users.
- Consumes **metrics** (file 03) almost exclusively for the trigger condition, and links out to **traces/logs** (files 02, 04) for the investigation that follows a page.
- Feeds directly into **incident management** (file 11) — a page is the entry point into the incident response process.
- Interacts with **circuit breakers / health checks** (Section 06) — state transitions in those components are themselves common, well-understood alert sources (e.g., "circuit breaker opened" is a strong, specific signal).

## Common Patterns & Real-World Tools

| Tool | Role |
|---|---|
| **PagerDuty / Opsgenie / VictorOps** | Paging, escalation policies, on-call scheduling |
| **Prometheus Alertmanager** | Alert routing, grouping, deduplication, silencing on top of Prometheus rules |
| **Grafana Alerting** | Unified alerting across multiple data sources with routing |
| **Slack/Teams integration** | Lower-severity alert delivery, incident channel auto-creation |
| **Google SRE "multi-window, multi-burn-rate"** | The reference alerting design pattern for SLO-based paging |

## Pros & Cons / Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| Symptom-based alerting | Directly tied to user impact, fewer false pages | Requires good SLIs already defined (upfront investment) |
| Cause-based alerting | Simple to set up (threshold on any raw metric) | Pages for things that may not matter (autoscaler handles it, no impact yet) — root cause of alert fatigue |
| Static thresholds | Easy to understand and set up | Doesn't adapt to traffic patterns (weekday vs weekend baseline); brittle |
| Burn-rate/SLO-based thresholds | Adapts automatically to what "bad enough to matter" means | More setup complexity, requires SLO infrastructure already in place |
| Aggressive escalation policies | Ensures someone eventually responds | Poorly tuned timeouts wake up too many people for minor issues, causing org-wide fatigue |

## Real-World Scenarios

- **Classic alert fatigue death spiral**: a team pages on CPU > 80%, gets paged 15 times a week for auto-scaling events that resolve themselves, starts silencing the alert reflexively — three months later a real CPU-driven outage happens and nobody notices for 40 minutes because the alert channel is muted by habit.
- **Google SRE reference burn-rate config**: a 99.9% SLO service alerts at burn rate 14.4x (would exhaust a 30-day budget in ~2 days) checked over both 1h and 5m windows for a fast page, and burn rate 6x over 6h/30m for a slower ticket-level alert — tuned specifically to catch a severe incident within ~5 minutes of detection while ignoring single-minute blips.
- **Runbook-linked alert cuts MTTR**: an alert for "circuit breaker opened on payment-service" links directly to a runbook with the three most common causes and their fixes — on-call resolves in 10 minutes instead of 45 spent rediscovering context from scratch.
- **Ownership-routing failure**: an alert for a shared database pages the wrong team (the team that happens to own the alerting rule, not the team that owns the DB) — on-call has no context or access to fix it, has to manually escalate, adding 20 minutes to an otherwise 5-minute fix; fixed by tying alert routing to a service ownership catalog.

## Nuances & Gotchas

- **A page with no action is a bug in the alert, not a fact of life** — if the standard response to an alert is "acknowledge and go back to sleep, it'll resolve itself," that alert should not page; downgrade it to a ticket or dashboard.
- **Alert fatigue is a slow, invisible failure mode**: nobody decides "let's start ignoring alerts" — it happens gradually, alert by alert, until the whole channel is background noise; the only fix is aggressively pruning non-actionable alerts, not asking on-call to "just be more careful."
- **Static thresholds break across traffic patterns**: a fixed "errors > 100/min" threshold makes sense at peak traffic and is far too sensitive at 3am low-traffic hours (or the reverse) — percentage-based/ratio-based thresholds (error *rate*, not raw count) or SLO burn rate avoid this.
- **Escalation timeouts need real tuning**: too short (2 min) pages secondary/manager for issues primary was already actively working; too long (30 min) leaves a real outage unattended if primary is unreachable — tune based on actual historical ack-time data, not a guess.
- **Silencing/snoozing during known maintenance is essential but dangerous**: a forgotten silence left on after a maintenance window ends can mask a real subsequent incident — silences should have mandatory expiry times, never indefinite.
- **On-call burnout is a system design problem, not a toughness problem**: rotations without adequate secondary coverage, alert volume left unaddressed, and lack of post-incident time off compound into attrition — treating alert-volume reduction as an ongoing engineering priority (not a one-time cleanup) is what sustains a healthy rotation.
- **Business-hours-only issues shouldn't page overnight**: an alert for "batch job report is 2 hours late" at 3am when the report isn't needed until 9am business hours should be a morning ticket, not a page — matching alert urgency to actual deadline, not just "something is technically wrong," matters as much as the technical threshold.
