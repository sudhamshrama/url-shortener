# url-shortener

A small URL shortener that exists to be *deployed properly*. The application is
deliberately modest; the delivery pipeline around it is the point.

Companion repository: [`url-shortener-config`](https://github.com/sudhamshrama/url-shortener-config)
holds the Kubernetes manifests and ArgoCD definitions. Two repos, because CI
writing to the repo that triggers CI is a loop worth avoiding.

---

## What this demonstrates

| | |
|---|---|
| **CI/CD** | GitHub Actions — lint, strict types, tests against real Postgres, multi-arch build, vulnerability gate, publish |
| **Security** | Trivy blocks HIGH/CRITICAL, non-root containers, read-only root filesystems, dropped capabilities, SBOM + signed provenance |
| **Kubernetes** | Kustomize base + three overlays, StatefulSet with persistent storage, probes, PDBs, resource governance |
| **GitOps** | ArgoCD — auto-sync in dev, approval-gated in prod, drift detection, one-commit rollback |
| **Secrets** | Sealed Secrets — encrypted values committed safely to a public repo |
| **Observability** | Prometheus metrics, Loki logs, Jaeger traces, with deliberate failure injection to prove the alerts work |
| **IaC** | Terraform modules for AKS, ACR, and networking, with remote state and locking |

---

## Architecture

```mermaid
flowchart TB
    dev["Developer"] -->|git push| gh["GitHub"]

    subgraph ci["CI — this repo"]
        direction TB
        lint["ruff · mypy · pytest<br/>(real Postgres)"] --> build["docker buildx<br/>amd64 + arm64"]
        build --> scan{"Trivy<br/>HIGH/CRITICAL?"}
        scan -->|found| stop["Build fails<br/>nothing published"]
        scan -->|clean| push["Push to GHCR"]
    end

    gh --> lint
    push -->|opens PR with new tag| cfg["config repo"]

    subgraph gitops["GitOps — ArgoCD"]
        cfg --> argo["ArgoCD reconciles"]
        argo -->|auto-sync| devns["dev namespace"]
        argo -->|manual approval| prodns["prod namespace"]
    end

    subgraph obs["Observability"]
        devns --> prom["Prometheus"]
        devns --> loki["Loki"]
        devns --> jaeger["Jaeger"]
        prom --> graf["Grafana"]
        loki --> graf
    end
```

### The request path

```mermaid
flowchart LR
    browser["Browser"] --> ing["Ingress<br/>nginx"]
    ing --> fe["frontend<br/>nginx + static"]
    fe -->|"/api/*, unknown paths"| be["backend<br/>FastAPI"]
    be --> cache{"in-process<br/>LRU cache"}
    cache -->|hit| resp["307 redirect"]
    cache -->|miss| pg[("Postgres<br/>StatefulSet + PVC")]
    pg --> resp
```

The frontend proxies to the backend rather than the browser calling it directly.
One origin means no CORS, and no backend address baked into the frontend image.

---

## Running it locally

Requires Docker. Nothing else.

```bash
docker compose up --build
```

Then open <http://localhost:8080>.

Compose starts Postgres, waits for it to pass a health check, runs the Alembic
migration as a one-shot job, and only then starts the API and frontend.

### Running the tests without Docker

The suite defaults to in-memory SQLite, so it needs no services at all:

```bash
cd backend && uv sync --group dev && uv run pytest
```

Point it at Postgres to run the same suite the way CI does:

```bash
TEST_DATABASE_URL=postgresql+psycopg://shortener:shortener@localhost:5432/shortener_test uv run pytest
```

Running both is not redundant. SQLite tolerates things Postgres rejects — the
first bug this project ever had was a `BigInteger` primary key that autoincrements
on Postgres and silently does not on SQLite. See
[`docs/decisions/`](docs/decisions/) for the write-up.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/links` | Create a short link |
| `GET` | `/api/links/{code}` | Stats for a link |
| `GET` | `/{code}` | Redirect (307) and increment the hit counter |
| `GET` | `/health` | Liveness — checks nothing external, by design |
| `GET` | `/ready` | Readiness — verifies the database is reachable |
| `GET` | `/version` | Build version, git SHA, and the pod that answered |
| `GET` | `/docs` | Swagger UI |

Interactive docs are at `/docs`.

### Liveness vs readiness

These are different questions and conflating them causes outages:

- **`/health`** answers *"is this process wedged?"* Kubernetes **restarts** the
  pod when it fails, so it must not check the database. If it did, a brief
  Postgres blip would fail the probe on every replica simultaneously and
  Kubernetes would restart the entire fleet — converting a recoverable
  dependency wobble into a self-inflicted outage.
- **`/ready`** answers *"should this pod receive traffic right now?"* Kubernetes
  removes it from the Service but does not restart it. Checking the database
  here is correct: it will recover on its own.

There is a regression test asserting `/health` stays green while the database
dependency raises.

### Failure injection

Gated behind `ENABLE_DEBUG_ENDPOINTS`, off by default, and enabled only in the
dev overlay:

| Path | Effect |
|---|---|
| `/debug/slow?seconds=2` | Inflates p95/p99 latency without burning CPU |
| `/debug/error?rate=0.05` | Returns 500s at a set rate, to test alert thresholds |
| `/debug/leak?megabytes=50` | Allocates and holds memory until the container OOMKills |

These exist so the observability work in Stage 6 can be *proven* rather than
assumed. An alerting stack that has never fired is decoration.

---

## Layout

```
backend/          FastAPI service
  app/            application code
  alembic/        schema migrations
  tests/          pytest suite (SQLite by default, Postgres in CI)
  Dockerfile      multi-stage, non-root, multi-arch
frontend/         vanilla HTML/JS on nginx
  nginx.conf      static serving + reverse proxy
infra/            Terraform modules (AKS, ACR, networking)
.github/workflows CI pipeline
docs/decisions/   architecture decision records
```

---

## Notable decisions

Fuller write-ups in [`docs/decisions/`](docs/decisions/).

**Sync SQLAlchemy with `def` handlers, not `async def`.** FastAPI runs plain
`def` handlers in a threadpool, so a blocking database call cannot stall the
event loop. The failure this avoids is the common one — `async def` handlers
calling a blocking driver, serialising every request in the process and
producing latency nobody can explain.

**Random short codes, not a sequential counter.** Sequential base62 is denser,
but it makes every link on the service enumerable. Generated with `secrets`
rather than `random`, because `random` is a Mersenne Twister whose future output
is predictable from a handful of observed values.

**307 redirects, not 301.** A permanent redirect is cached by the browser
indefinitely, so repeat visits never reach the service and the hit counter
silently stops counting. Metric correctness beats the marginal latency win.

**Unique constraint for collisions, not check-then-insert.** Checking
availability before inserting has a race window; under concurrency two requests
both see "available" and one insert fails anyway. Letting the database's
constraint reject the duplicate and retrying is the only correct version.

**Vanilla JS, no build step.** No `node_modules`, no transitive npm advisories
in the vulnerability scan, and a frontend image that is nginx plus three files.

**GHCR, not ACR.** Free and unlimited for public images. The pipeline pushes to
an OCI registry; swapping in Azure Container Registry is a two-line change.

---

## Cost

Built to run at **$0**. Everything except one deliberate exercise runs on a
laptop with kind and GitHub's free tier.

The Terraform in `infra/` is applied against real Azure exactly once — with a
budget alert set — long enough to capture evidence, then destroyed. Keeping a
demo AKS cluster warm costs upwards of $75/month, and choosing not to pay it is
itself an engineering decision worth defending.

---

## Status

| Stage | State |
|---|---|
| Application + tests | Done — 19 tests, 86% coverage, mypy strict clean |
| Container images | Done — backend 349 MB, frontend 98.8 MB, both non-root |
| Local stack | Done — `docker compose up` works end to end |
| Kubernetes manifests | Done — running on kind, PVC persistence verified |
| CI pipeline | Written, actionlint clean |
| GitOps / ArgoCD | Manifests written, ArgoCD not yet installed |
| Observability | Done — metrics, logs, traces, alerts, and a [postmortem](docs/incidents/2026-08-07-elevated-error-rate.md) from a real game-day |
| Terraform | Not started |
