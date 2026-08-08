# Known issues

Open defects, honestly stated. A repository that claims everything works is
either very small or not telling you the truth.

---

## 1. Perpetual ArgoCD drift on two resources (open)

`StatefulSet/postgres` and `ServiceMonitor/backend` report `OutOfSync`
permanently. The Kubernetes API server populates default fields that are absent
from the Git manifests, so ArgoCD sees a difference on every comparison.

The standard fix is an `ignoreDifferences` block on the Application. Not applied
yet because the specific fields have not been identified — a blanket ignore
would suppress real drift along with the noise, which is worse than the noise.

---

## 2. Readiness probes emit orphan traces (open)

`/ready` is excluded from HTTP tracing, but its `SELECT 1` is still traced by
the SQLAlchemy instrumentation. Each readiness probe therefore produces a
parentless span — one every five seconds, per pod.

Harmless at this scale. At any real scale it would bury genuine traces in noise
and inflate tracing cost. The fix is to suppress instrumentation for that
specific query, or move the readiness check off SQLAlchemy.

---

## 3. Deployment PRs are noisier than they should be (open)

CI uses `kustomize edit set image` to bump the tag, and that command rewrites
the whole file in kustomize's canonical style — re-indenting YAML lists and
dropping no-op keys. The result is a fifteen-line diff for a one-line change.

Functionally correct, but a reviewer should see exactly what changed. Replacing
it with a targeted `yq` edit would keep the diff to a single line.

---

## 4. Sealed Secrets do not survive a cluster rebuild (by design)

Recreating the kind cluster generates a new sealing key, so the committed
SealedSecrets for staging and prod can no longer be decrypted and those
environments come up `Degraded`.

This is Sealed Secrets working exactly as intended — the ciphertext is worthless
without the specific cluster that produced it, which is precisely why it is safe
in a public repository. Regenerating is one `kubeseal` command per environment.

Worth knowing rather than fixing: in a real environment you back up the
controller's private key, and losing it means re-sealing every secret.

---

## Resolved

### Loki appeared to return no logs — my test method was wrong

Recorded because the debugging lesson is more useful than the bug.

Every query returned "zero streams" and the dashboard looked empty, across many
attempts. Ingestion metrics proved the data was there: the distributor had
received 3,454 lines and the ingester had flushed 32 chunks. Hypotheses raised
and discarded along the way: promtail misconfiguration, clock skew, wrong label
selector, query-frontend sharding, result caching, index-gateway routing.

The actual cause was in the test command. `curl --data-urlencode` without `-G`
sends a **POST**, and Grafana's Loki datasource proxy rejects non-allowlisted
POSTs:

```
{"message":"non allow-listed POSTs not allowed on proxied loki datasource"}
HTTP 403
```

`jq '.data.result | length'` then read `null` on that error body and printed
`0` — indistinguishable from an empty result. The one query that had worked
earlier used `-G`; every failing one did not.

**Two lessons.** Check the raw response before theorising about the system:
several hours went into Loki internals when a single un-piped `curl` would have
shown a 403 immediately. And a jq filter that turns an error body into a
plausible-looking `0` is worse than one that crashes — silent coercion hid the
failure.

A related "fix" was also reverted: the dashboard's `{app="backend"}` selector
was correct all along, since promtail derives an `app` label from the pod.
