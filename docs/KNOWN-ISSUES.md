# Known issues

Open defects, honestly stated. A repository that claims everything works is
either very small or not telling you the truth.

---

## 1. Loki queries return no results (open)

**Status:** unresolved. Centralised logging does not work.

Metrics (Prometheus) and tracing (Jaeger) both work. Logging does not, so the
README does not claim it.

### Symptom

Promtail runs on every node with the correct push URL and reports no errors.
Loki accepts the writes. But `query_range` returns zero streams for any
selector, while Loki's own request log shows the data is present:

```
component=querier   length=9m48s   returned_lines=2   ← data IS there
component=frontend  length=1h0m0s  returned_lines=0   ← same query, longer range
```

Accompanied by:

```
msg="failed mapping AST" err="context canceled"
```

The query returns **HTTP 200 with an empty result**, which is the worst possible
failure mode: indistinguishable from "no logs exist." During an incident that
reads as "the service is receiving no traffic."

### What has been ruled out

- **Promtail not running** — three pods, all Running, no errors in their logs.
- **Wrong push URL** — verified `http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`.
- **Clock skew** — a query window extended two hours into the future still
  returned nothing.
- **Wrong label selector** — even `{namespace="url-shortener-dev"}` with no
  further filtering returns zero.
- **Query splitting/sharding** — `split_queries_by_interval: 0`,
  `max_query_parallelism: 1`, and `tsdb_max_query_parallelism: 1` were applied.
  Did not resolve it.

### Leading hypothesis

`index_total_chunks=0` and `store_chunks_download_time=0s` in Loki's query log
suggest the TSDB index is not resolving chunks from the filesystem store. Data
appears queryable only while it is still in the ingester's head chunk, and
becomes invisible once flushed.

That points at the schema or filesystem-storage configuration in single-binary
mode rather than at ingestion.

### Next steps

- Inspect the contents of Loki's PVC to confirm whether chunks and index files
  are actually being written.
- Compare against the chart's default `schemaConfig` — the pinned `v13`/`tsdb`
  values may not match what this chart version expects.
- Try `boltdb-shipper` instead of `tsdb` as a control.

---

## 2. Dashboard log panel used a label that does not exist (fixed)

The Grafana log panel queried `{app="backend"}`, but pods are labelled
`app.kubernetes.io/name=backend`. The panel would have shown nothing even with
Loki working. Now queries `{namespace="url-shortener-dev"}`.

---

## 3. Perpetual ArgoCD drift on two resources (open)

`StatefulSet/postgres` and `ServiceMonitor/backend` report `OutOfSync`
permanently. The Kubernetes API server populates default fields that are absent
from the Git manifests, so ArgoCD sees a difference on every comparison.

Standard fix is an `ignoreDifferences` block on the Application. Not applied yet
because the specific fields have not been identified — adding a blanket ignore
would suppress real drift along with the noise.

---

## 4. Readiness probes emit orphan traces (open)

`/ready` is excluded from HTTP tracing, but its `SELECT 1` is still traced by
the SQLAlchemy instrumentation. Each readiness probe therefore produces a
parentless span — one every five seconds, per pod.

Harmless at this scale. At any real scale it would bury genuine traces in noise
and inflate tracing cost. Fix is to suppress instrumentation for that specific
query, or to move the readiness check off SQLAlchemy.

---

## 5. Deployment PRs are noisier than they should be (open)

CI uses `kustomize edit set image` to bump the tag, and that command rewrites
the whole file in kustomize's canonical style — re-indenting YAML lists and
dropping no-op keys. The result is a fifteen-line diff for a one-line change.

Functionally correct, but a reviewer should see exactly what changed. Replacing
it with a targeted `yq` edit would keep the diff to a single line.
