# Screenshots

Proof that the system works. A recruiter will not clone this repo and stand up a
Kubernetes cluster — these images are how they see it running.

Capture on macOS with `Cmd+Shift+4`, then drag a region. Save into this folder
with the exact filenames below so the README embeds resolve.

## The six that matter

| Filename | What to capture | Why it earns its place |
|---|---|---|
| `ci-pipeline-green.png` | The Actions run page, all four jobs with green checks | Shows the whole pipeline in one image — test, build, scan, deploy |
| `trivy-blocked.png` | The Trivy step output from run #6, showing `Total: 11 (HIGH: 11)` and the job failing | **The strongest image in the set.** A real vulnerable image, really blocked. Not a drill |
| `deployment-pr.png` | The merged PR in `url-shortener-config` | The audit trail: which commit, which run, who approved |
| `argocd-sync-tree.png` | ArgoCD → `url-shortener-dev` → the resource tree | The most visually striking. Shows Git reconciling into live infrastructure |
| `grafana-dashboard.png` | The service-health dashboard under load | RED metrics, p50/p95/p99, business metrics |
| `jaeger-trace.png` | A `POST /api/links` trace, expanded | 8 spans showing exactly where the milliseconds went |

## Where they came from

Reproduce the environment:

```bash
kind create cluster --name shrt --config ../../../url-shortener-config/local/kind-config.yaml
```

Then the Helm installs and `kubectl apply -k overlays/dev` — see the config
repo's `local/` directory. Generate traffic so the dashboards are not empty:

```bash
k6 run -e BASE_URL=http://shrt.localhost load/baseline.js
```

For the Trivy image, revert the `apk upgrade` line in `frontend/Dockerfile` and
push — the gate fires again. Or screenshot the historical run, which is
permanent.

## Guidelines

- **Crop to the content.** Nobody needs your dock or menu bar.
- **Light mode for Grafana** if you plan to embed in a light README — dark
  screenshots on a white page look like holes.
- **Do not blur the pod names or commit SHAs.** They are the evidence.
- **Check for anything sensitive** before committing. These go to a public repo.
  Cluster tokens, the ArgoCD password, and any real credential must not appear.
  The ArgoCD admin password in particular is visible in some views — regenerate
  it or crop it out.
