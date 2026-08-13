# Incident Management and Postmortems

> **TL;DR:** An incident is any event requiring a coordinated human response beyond normal on-call handling — it needs a single Incident Commander, a clear communication channel, and a declared end. The postmortem afterward must be blameless and focused on systemic/contributing factors, not "who broke it," or people start hiding mistakes instead of surfacing them — which guarantees the same failure recurs.

## Quick Reference

| Role/Artifact | Purpose |
|---|---|
| Incident Commander (IC) | Single person coordinating response — decisions, not necessarily the one fixing it |
| Communications Lead | Keeps stakeholders/customers updated, frees IC and responders to focus on the fix |
| Scribe | Timestamps every action/decision in real time — the postmortem's raw material |
| Severity levels (SEV1-4) | Standardized impact classification driving response urgency and process |
| Incident channel | Single source of truth (Slack/Teams channel) — no side-channel decisions |
| Postmortem (retro) | Blameless written analysis: timeline, root/contributing causes, action items |
| Action items | Concrete, owned, tracked follow-up work — the actual mechanism that prevents recurrence |

## What It Is

- **Incident management**: the structured process for detecting, responding to, and resolving an event impacting users, with clear roles so response doesn't devolve into a dozen engineers debugging in isolation with no coordination.
- **Postmortem** (aka retrospective, incident review): a written document produced after resolution that reconstructs the timeline, identifies contributing factors, and produces concrete action items — the primary mechanism an organization has for turning an incident into durable improvement rather than a one-off firefight.
- **Blameless** is not a soft HR nicety — it's a load-bearing engineering practice: postmortems that assign individual blame train people to hide near-misses and unsafe conditions, which removes the organization's ability to see and fix systemic risk before the next incident.

## Responsibilities

- The **Incident Commander** owns the response process (who's doing what, are we escalating, when do we declare resolved) — explicitly *not* required to personally debug or fix the issue; separating "coordinating" from "fixing" prevents the person best positioned to see the whole picture from getting tunnel-visioned into one technical rabbit hole.
- The **Communications Lead** owns keeping affected stakeholders (support team, leadership, sometimes customers via a status page) updated on a cadence, so responders aren't repeatedly interrupted with "any update?" questions mid-fix.
- Everyone involved owns contributing to the postmortem's timeline honestly, including their own mistakes — the org owns making that safe to do (no punishment for good-faith errors surfaced in a postmortem).

## How It Works

**Incident lifecycle**:
```
Detect (alert/page fires or manual report)
   │
Declare (severity assigned, IC named, incident channel opened)
   │
Respond (mitigate first — stop the bleeding — root cause can come later)
   │
Resolve (user impact confirmed ended)
   │
Postmortem (within days, while memory is fresh)
   │
Action items tracked to completion (the step most often skipped)
```
- **Mitigate before you understand**: the fastest path to stopping user impact (rollback, feature flag off, failover to a healthy region) is usually not the same as fully understanding root cause — do the former first, investigate the latter after, unless they happen to be the same action.

**Postmortem structure** (typical template):
```
1. Summary — what happened, user impact, duration
2. Timeline — objective, timestamped sequence of detection/response/resolution
3. Root cause(s) / contributing factors — plural; incidents are rarely one single cause
4. What went well / what went poorly / where we got lucky
5. Action items — specific, owned, tracked (not vague "improve monitoring")
```
- "Where we got lucky" is a Google SRE-book addition worth calling out specifically: incidents that *almost* happened, or would have been much worse under slightly different timing, reveal risk even when the actual outcome wasn't bad — treating a near-miss as a free pass misses the improvement opportunity.

## Types / Classifications

| Severity | Typical definition | Response |
|---|---|---|
| SEV1 | Full outage or major revenue/data-loss impact | All-hands, IC mandatory, exec comms |
| SEV2 | Significant partial degradation | IC mandatory, primary team response |
| SEV3 | Minor impact, workaround exists | Normal on-call handling, no formal IC needed |
| SEV4 | Cosmetic/negligible impact | Ticket, no incident process invoked |

| Postmortem trigger | Example |
|---|---|
| Mandatory | Any SEV1/SEV2, any customer data exposure/loss |
| Optional but encouraged | Near-misses, SEV3s with learning value |
| COE (Correction of Error, Amazon term) | Same concept, Amazon's internal name for the same practice |

## Where It Fits

- The incident channel is where **alerting** (file 07) hands off — a page is the *trigger*, incident management is the *process* that follows once a human is engaged.
- Postmortem action items frequently produce new work across every other file in this section: a new SLO (file 05), a new alert (file 07), a new synthetic check (file 09), a canary/rollback improvement (file 10), or a dashboard fix (file 06) — the postmortem is the feedback loop that closes the observability system.
- Ties into **chaos engineering** (Section 06, file 11) — postmortems reveal untested failure modes that become the next chaos experiment's hypothesis.
- The **PR state notices / merge conflict / CI failure loop** described in this session's own operating instructions is a small-scale, automated instance of the same principle: detect, respond, don't let it go silently unresolved.

## Common Patterns & Real-World Tools

| Tool | Role |
|---|---|
| **PagerDuty / Opsgenie Incident workflows** | Declares incidents, tracks timeline, assigns roles automatically |
| **Slack/Teams + incident bot** (e.g., Blameless, FireHydrant, Rootly) | Auto-creates incident channel, timestamps actions, generates draft timeline |
| **Statuspage / status.io** | External customer-facing communication during an incident |
| **Jeli, incident.io** | Postmortem facilitation and analysis tooling |
| **Google SRE book / "Postmortem Culture" chapter** | The canonical reference for blameless postmortem practice |
| **Etsy's "Debriefing Facilitation Guide"** | Widely cited practical guide for running blameless retros well |

## Pros & Cons / Trade-offs

| Practice | Pros | Cons |
|---|---|---|
| Formal IC role | Clear decision authority, reduces chaos in large incidents | Overhead/ceremony for genuinely small incidents if applied too rigidly |
| Blameless postmortems | Surfaces true contributing factors, builds psychological safety, improves long-term reliability | Requires sustained leadership commitment — one instance of blame undoes months of trust built |
| Mandatory postmortems for all SEV1/2 | Ensures learning isn't optional/skipped under time pressure | Can become box-checking theater if action items aren't actually tracked to completion |
| "Root cause" framing | Simple, intuitive | Real incidents almost always have multiple contributing factors; forcing a single "root cause" narrative oversimplifies and misses systemic fixes |

## Real-World Scenarios

- **Google SRE-style postmortem culture**: an outage caused partly by a config error and partly by an alert that should've caught it sooner but didn't — the postmortem produces two action items (fix the config validation, fix the alert), not a performance review of the engineer who typo'd the config.
- **Separating IC from fixer in a large incident**: during a multi-service cascading failure, the most senior engineer is deliberately kept as IC (coordinating, deciding what to try next, managing comms) rather than being pulled into hands-on debugging — this keeps the response coordinated instead of three separate people trying uncoordinated fixes simultaneously.
- **Action item follow-through gap**: a postmortem identifies "we should have alerted on this" as an action item, but with no owner or deadline it never gets built — six months later the identical incident recurs; the fix wasn't writing the postmortem, it was ticketing and tracking the action item to actual completion.
- **Near-miss postmortem**: a bad deploy would have caused a full outage except an unrelated ongoing rate limit happened to throttle the traffic that would've triggered it — team writes a postmortem anyway ("where we got lucky") and fixes the actual gap (missing canary analysis) before luck runs out next time.

## Nuances & Gotchas

- **Blameless doesn't mean accountability-free**: the org still expects the *system* to be fixed and action items completed — blamelessness protects the individual from punishment for a good-faith mistake, it doesn't mean nobody is responsible for follow-through.
- **The first blame-attribution postmortem poisons the well for years**: once people see a colleague blamed or penalized following a postmortem, future incident timelines get sanitized/incomplete — this is very hard to undo and worth guarding against explicitly, even from well-intentioned "just asking who deployed this" questions.
- **Mitigate-first sometimes conflicts with root-cause instincts**: engineers often want to understand *why* before rolling back, but during an active SEV1 the priority is stopping user impact — a premature "let's just understand this fully first" can needlessly prolong outage duration.
- **Timeline reconstruction is unreliable after the fact**: memory of exact timestamps degrades within hours — the Scribe role capturing real-time timestamps *during* the incident (not reconstructed afterward from memory) is what makes postmortem timelines actually accurate.
- **Severity inflation/deflation both cause problems**: calling everything SEV1 causes alert-fatigue-style desensitization to the incident process itself; calling real outages SEV3 to avoid formal process undercounts organizational risk and skips the mandatory postmortem that would've caught it.
- **Postmortems without tracked action items are just expensive storytelling**: the actual value is in the systemic fixes that follow — an organization should be able to point to concrete changes (new alert, new test, new runbook) traceable to specific past postmortems, not just a folder of unread documents.
- **Cross-team incidents need a single IC even across org boundaries**: a failure at a service boundary between two teams without one agreed-upon IC often produces two uncoordinated responses each assuming the other has it handled — explicit IC handoff/ownership rules for cross-team incidents prevent this gap.
