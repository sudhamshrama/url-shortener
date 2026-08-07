# Runbook: HighErrorRate

**Alert:** `HighErrorRate`
**Severity:** critical
**Fires when:** 5xx responses exceed 5% of all requests for 5 continuous minutes

> A runbook exists so the person woken at 3 AM does not have to reconstruct your
> reasoning from scratch. Assume the reader is competent, half-asleep, and has
> never seen this service before.

---

## What this means

More than one in twenty requests is failing. The service is degraded but not
necessarily down — a total outage would trigger `BackendDown` instead.

## First: is it actually broken?

```bash
kubectl get pods -n url-shortener-dev
curl -s -H "Host: shrt.localhost" http://localhost/ready
```

If pods are `CrashLoopBackOff` or `/ready` returns 503, skip to
[Database unreachable](#database-unreachable).

## Triage, in order

### 1. Did something just deploy?

By far the most common cause. Check what is running versus what you expect:

```bash
curl -s -H "Host: shrt.localhost" http://localhost/version
kubectl rollout history deployment/backend -n url-shortener-dev
```

If the version changed within ~15 minutes of the alert firing, **roll back
first and investigate after**. Restoring service is the priority; the cause can
wait.

```bash
kubectl rollout undo deployment/backend -n url-shortener-dev
```

Under GitOps the durable fix is `git revert` on the config repo, so ArgoCD does
not re-apply the bad version on its next sync. The `kubectl` command above is
the fast path, not the final one.

### 2. Which endpoint is failing?

Grafana → **url-shortener — service health** → *Requests by status code*.

If the 500s are concentrated on one route, that narrows it immediately.

### 3. Read the logs

Grafana → Explore → Loki:

```logql
{namespace="url-shortener-dev", app="backend"} |= "ERROR"
```

Every log line carries a `trace_id`. Click it to jump to that exact request in
Jaeger.

### 4. Follow the trace

Jaeger shows the span breakdown for the failing request. Look for:

- A long `SELECT` or `INSERT` span → database problem
- A short trace ending abruptly → the app raised early
- `connect` spans dominating → connection pool exhaustion

---

## Database unreachable

`/ready` returning 503 with `"database": "down"` means the app cannot reach
Postgres.

```bash
kubectl get pods -n url-shortener-dev -l app.kubernetes.io/name=postgres
kubectl logs -n url-shortener-dev postgres-0 --tail=50
kubectl get pvc -n url-shortener-dev
```

Common causes:

| Symptom | Cause | Action |
|---|---|---|
| `postgres-0` Pending | PVC unbound, no storage available | Check the StorageClass |
| `postgres-0` CrashLoopBackOff | Corrupt data dir, or wrong `PGDATA` | Check logs; a permissions error means `fsGroup` is wrong |
| Postgres healthy, app still 503 | Wrong credentials in the Secret | Confirm the SealedSecret decrypted |
| Intermittent failures | Connection pool exhausted | Check `connect` span volume in Jaeger |

Note that liveness deliberately does **not** check the database. A Postgres blip
must not restart every backend pod — that turns a recoverable dependency wobble
into a self-inflicted outage.

---

## Connection pool exhaustion

Symptom: the app hangs after serving roughly `pool_size + max_overflow`
requests (15 by default), then recovers, then hangs again.

Cause: a handler returning or raising without releasing its session. `get_db()`
uses try/finally specifically to prevent this, so this points at code that
bypassed the dependency.

Immediate mitigation:

```bash
kubectl rollout restart deployment/backend -n url-shortener-dev
```

That clears the leaked connections but does not fix the leak.

---

## If none of the above

1. Check whether `/debug/error` is reachable — it should be **disabled outside
   dev**. If `ENABLE_DEBUG_ENDPOINTS` is true in staging or prod, that is both
   the cause and a separate incident.
2. Check node pressure: `kubectl describe nodes | grep -A5 Conditions`
3. Check for OOMKills: `kubectl get events -n url-shortener-dev --sort-by=.lastTimestamp | tail -20`

## Escalation

Single-maintainer project. If you are reading this and are not Sudhamsh, the
safe action is to roll back to the last known-good image tag and stop there.
