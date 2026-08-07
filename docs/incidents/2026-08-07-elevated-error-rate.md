# Incident: elevated error rate and p95 latency in dev

**Date:** 2026-08-07
**Duration:** ~9 minutes (22:56 – 23:08 UTC)
**Severity:** SEV-3 (dev environment, no users affected)
**Status:** Resolved
**Author:** Sudhamsh

> **This was a deliberate game-day exercise, not a real outage.** Failure was
> injected on purpose to verify the alerting pipeline works. It is written up as
> a real postmortem because the point of the exercise was to find out whether
> the tooling and the process actually work — and it did surface three genuine
> defects, listed under *What we learned*.

---

## Summary

Roughly 12% of requests to the backend returned HTTP 500, and p95 latency rose
from ~10 ms to ~1 s. The `HighErrorRate` alert fired after its 5-minute
threshold and reached Alertmanager. The condition cleared within two minutes of
the injected load stopping.

## Impact

None. Dev environment, synthetic traffic, no real users.

Had this been production: at 4.6 req/s and a 12.5% error rate, roughly **0.6
failed requests per second** — about 210 failed redirects over the nine
minutes. Users would have seen a browser error page instead of reaching their
destination.

## Timeline (UTC)

| Time | Event |
|---|---|
| 22:56 | Load generator starts; error injection begins at ~12% |
| 22:58 | `HighErrorRate` enters **pending** — condition true, 5-min timer running |
| 23:00 | `HighLatencyP95` enters **pending** |
| 23:03 | `HighErrorRate` transitions to **firing**, delivered to Alertmanager, severity `critical` |
| 23:05 | Confirmed in Grafana: error ratio 12.56%, p95 1.0 s, request rate 4.63 rps |
| 23:08 | Load generator stopped |
| 23:08 | `HighLatencyP95` also firing; both begin recovering |

## Detection

Detected automatically by the `HighErrorRate` Prometheus rule. No human noticed
first, which is the desired outcome — mean time to detection was **~7 minutes**
from the start of injection, of which 5 minutes is the deliberate `for:` delay.

That 5-minute delay is a conscious trade. Removing it would cut detection to
under a minute but would page on every transient blip, and an alert people learn
to ignore is worse than no alert.

## Diagnosis path

The path a responder would actually take, and the one that was walked here:

1. **Alert fires** → names the symptom (error rate above 5%), not the cause.
2. **Grafana "Requests by status code"** → shows 500s appearing alongside
   healthy 307s. The service is degraded, not down, which rules out a crash
   loop or a failed deploy.
3. **"Latency percentiles" panel** → p50 stayed near 5 ms while p95 hit 1 s.
   That gap is diagnostic: it means *a subset* of requests are slow, not that
   the service is uniformly overloaded. A dashboard showing only averages would
   have shown nothing at all here.
4. **Loki logs, filtered to the namespace** → the 500s all come from one route.
5. **Click the `trace_id` in the log line** → jumps straight to the Jaeger
   trace for that exact request, showing where the time went.

Steps 4 and 5 are only possible because logs are JSON and carry a trace ID. In
plain-text logs, step 5 does not exist.

## Root cause

Injected. `load/incident.js` directed ~12% of traffic at `/debug/error` and ~8%
at `/debug/slow?seconds=1.5`.

## Resolution

Stopped the load generator. Both alerts cleared on their own.

---

## What we learned

The exercise found three real defects that would each have caused a genuine
problem during a real incident.

### 1. Uvicorn's access logs bypassed the JSON formatter

Configuring the root logger left `uvicorn.access` emitting plain text with no
`trace_id`, because uvicorn installs its own handlers with `propagate=False`.
Logs looked fine in `kubectl logs` and were useless for correlation — step 5 of
the diagnosis path above would simply not have worked.

**Fixed:** clear uvicorn's handlers and re-enable propagation in
`app/observability.py`.

### 2. The Grafana dashboard queried no datasource

Panels were provisioned without an explicit `datasource`, relying on whichever
one Grafana had flagged as default. Every panel rendered "No data" — and Grafana
reports that as an empty panel, not an error, so nothing indicates the query
never ran. During a real incident this looks identical to "the service is
receiving no traffic."

**Fixed:** every panel and target now names its datasource explicitly.

### 3. Readiness probes generate orphan traces

`/ready` is excluded from HTTP tracing, but its `SELECT 1` is still traced by
the SQLAlchemy instrumentation. The result is a parentless span every 5 seconds
per pod — noise that would crowd out real traces at any scale.

**Not yet fixed.** Tracked as a follow-up.

## What went well

- The alert fired, at the right threshold, with the right severity, and reached
  Alertmanager without intervention.
- The `for: 5m` delay behaved exactly as designed — visible as `pending` before
  `firing`.
- p50-vs-p95 divergence made the partial nature of the failure obvious
  immediately.
- Alerts self-resolved once the cause stopped; no manual clearing needed.

## Action items

| # | Action | Owner | Status |
|---|---|---|---|
| 1 | Route uvicorn loggers through the JSON formatter | Sudhamsh | Done |
| 2 | Pin explicit datasources on all dashboard panels | Sudhamsh | Done |
| 3 | Pin Loki datasource UID so trace↔log links resolve | Sudhamsh | Done |
| 4 | Suppress traces for readiness-probe DB queries | Sudhamsh | Open |
| 5 | Wire Alertmanager to a real Slack webhook | Sudhamsh | Open |
| 6 | Add a runbook link to every alert annotation | Sudhamsh | Partial |

---

## Why this document exists

Two reasons.

**Blameless postmortems are how organisations get better.** The question is
never "who broke it" but "what made this failure possible, and what makes the
next one less likely." Every action item above is a systems change, not a person
change.

**An observability stack that has never seen an incident is decoration.** Before
this exercise, the alert rules were a hypothesis: plausible-looking PromQL that
had never evaluated against real conditions. Two of the three defects found here
would have gone unnoticed until a real outage, at exactly the moment they would
hurt most.
