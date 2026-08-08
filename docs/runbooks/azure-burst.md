# Runbook: the Azure burst

Provision the real infrastructure, capture evidence, destroy it. One session,
roughly 90 minutes, about **15 cents**.

The point is not that AKS is hard to create. The point is being able to say you
provisioned it, saw it work, and chose not to pay $70/month to keep a demo warm.

---

## Before you start

| Check | How |
|---|---|
| Budget alert exists | Portal → Cost Management → Budgets. **$8, alerts at 50% and 100%.** Already done. |
| Logged in | `az account show` → should say *Azure for Students*, state *Enabled* |
| Providers registered | `az provider show -n Microsoft.Network --query registrationState -o tsv` → **Registered** |
| Credit available | Portal → Cost Management + Billing → Credits |

The provider check matters. On a new subscription `Microsoft.Network` takes 30+
minutes to register, and an apply started before it finishes fails partway —
leaving a resource group and Log Analytics workspace behind that you then have
to clean up manually.

---

## 1. Plan

```bash
cd ~/projects/url-shortener/infra/envs/dev
terraform plan -out=tfplan
```

Expect **`Plan: 11 to add, 0 to change, 0 to destroy.`**

Read it. Specifically confirm:

- `location = "southcentralus"` — not a region you did not intend
- `sku_tier = "Free"` on the AKS cluster — `Standard` adds ~$73/month
- `vm_size = "Standard_B2s"` — the cheapest size that runs a real node
- `min_count = 1` — not 3

A plan that says *destroy* anything on a first run means something is wrong with
your state. Stop and work out why.

## 2. Apply

```bash
terraform apply tfplan
```

5–10 minutes. AKS provisioning is genuinely slow; this is normal.

**Note the wall-clock time you started.** Billing runs from here.

## 3. Verify it is real

```bash
az aks get-credentials --resource-group rg-shrt-dev --name aks-shrt-dev
kubectl get nodes -o wide
kubectl config current-context
```

You should see real Azure VMs, not kind containers — Ubuntu nodes with private
IPs in `10.0.x.x`.

## 4. Capture evidence

The whole reason for the exercise. Take these before destroying:

| Screenshot | Where | Why |
|---|---|---|
| `terraform apply` completion | Terminal — the `Apply complete! Resources: 11 added` line plus outputs | Proof it ran |
| `kubectl get nodes` against AKS | Terminal — include `kubectl config current-context` showing the AKS name | Proof the cluster is real |
| Resource group in the portal | Portal → Resource groups → `rg-shrt-dev` → Overview | The visual a non-engineer understands |
| AKS cluster overview | Portal → the cluster → Overview, showing node pool and Kubernetes version | Detail |

Optionally deploy the app to it — but the manifests reference GHCR, and the
sealed secrets were sealed for a *different* cluster's key, so staging and prod
will not decrypt. Dev works, since it generates its own credentials.

## 5. Destroy

**Do not skip this.**

```bash
terraform destroy
```

Type `yes` when prompted. Takes 5–10 minutes.

## 6. Verify the destroy

Terraform reporting success is not the same as Azure having finished.
Occasionally a resource fails to delete and leaves a billable orphan.

```bash
az group list --query "[?starts_with(name, 'rg-shrt')].name" -o tsv
```

**Empty output means you are clean.** Screenshot this too — "I destroyed it"
is a stronger claim with evidence than without.

Also check the portal: Resource groups should not list `rg-shrt-dev`. Note that
AKS creates a *second*, auto-managed resource group named
`MC_rg-shrt-dev_aks-shrt-dev_southcentralus` which holds the actual VMs. It is
deleted along with the cluster, but confirm it is gone — that is where the
compute charges live.

---

## If something goes wrong

**Apply fails partway.** Terraform records what it created. Re-running `apply`
continues from there; `destroy` removes what exists. State is intact either way
— that is the whole point of state.

**"context deadline exceeded" on a provider.** A resource provider is still
registering. Wait for `az provider show -n <name>` to report `Registered`, then
re-run.

**You lose the terminal mid-apply.** Resources keep billing. Recovery is
`terraform destroy` from this directory — state is on local disk, so it must be
the same machine. This is precisely the argument for remote state, which is
commented out in `main.tf` and would be the first thing to add for real use.

**Quota errors.** Student subscriptions have low vCPU quotas per region. Either
request an increase or switch region in `terraform.tfvars`.

---

## What this earns you

Before: *"I wrote Terraform modules for AKS."*

After: *"I provisioned a multi-environment AKS cluster with Terraform, verified
it, captured the evidence, and destroyed it — because keeping a demo cluster
warm costs $70 a month and that is a bad trade."*

The second answer demonstrates cost awareness, which is the part most portfolios
skip entirely.
