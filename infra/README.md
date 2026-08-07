# Infrastructure (Terraform)

Azure infrastructure for the URL shortener: AKS, ACR, networking, and Log
Analytics.

> **This code is applied deliberately and briefly, then destroyed.** Everything
> in this project runs for free on a local kind cluster. This module exists to
> demonstrate real infrastructure-as-code, and it is provisioned once — long
> enough to capture evidence — then torn down. Keeping a demo AKS cluster warm
> costs upwards of $70/month, and choosing not to pay that is itself an
> engineering decision.

---

## Layout

```
infra/
├── modules/
│   ├── networking/   VNet, subnets, NSGs
│   ├── aks/          Kubernetes cluster with autoscaling
│   └── acr/          Container registry + AcrPull role assignment
└── envs/
    └── dev/          Composes the modules with dev-sized values
```

The environment directories are deliberately thin — they wire modules together
and pass variables. All logic lives in `modules/`. Prod differs from dev by
*values*, not by duplicated code.

## What it costs

| Resource | Dev config | ~Monthly |
|---|---|---|
| AKS control plane | Free tier | **$0** |
| Worker nodes | 1–2 × Standard_B2s | **$30–60** |
| ACR | Basic | **$5** |
| Log Analytics | 30d, 1GB/day cap | **~$3** |
| **Total** | | **~$38–68** |

The control plane being free is the detail people miss — it's the *nodes* that
cost money, and they bill by the hour whether or not anything runs on them.

A `terraform apply` → screenshot → `terraform destroy` cycle of 2–4 hours costs
roughly **$0.30**.

## Before you apply

**1. Set a budget alert.** Do this before anything else.

Azure Portal → Cost Management → Budgets → Add. Set $5, alert at 50% and 100%.
This is your safety net against the real risk, which is not the hourly rate — it
is forgetting to destroy.

**2. Authenticate.**

```bash
az login
az account set --subscription "<your-subscription-id>"
```

**3. Review the plan.** Never skip this.

```bash
cd envs/dev
terraform init
terraform plan -out=tfplan
```

Read the output. `terraform plan` shows exactly what will be created, changed,
or destroyed. Applying without reading it is how people delete production.

## Applying

```bash
terraform apply tfplan
```

Takes 5–10 minutes; AKS provisioning is genuinely slow.

Then point kubectl at the new cluster:

```bash
az aks get-credentials --resource-group rg-shrt-dev --name aks-shrt-dev
kubectl get nodes
```

## Destroying — do not skip this

```bash
terraform destroy
```

Then **verify in the portal** that the resource group is gone. Terraform
reporting success is not the same as Azure having finished; occasionally a
resource fails to delete and leaves a billable orphan behind.

```bash
az group list --query "[?starts_with(name, 'rg-shrt')].name" -o tsv
```

Empty output means you're clean.

## State

State is not configured yet — the `backend "azurerm"` block in `envs/dev/main.tf`
is commented out, so state is currently local.

**Why this matters:** Terraform state is a JSON file recording every resource it
manages, including resource attributes in plaintext. It is the most sensitive
artifact in an IaC repository and must never be committed — `.gitignore`
excludes `*.tfstate`.

Remote state in Azure Blob Storage adds two things:

1. **Durability.** Losing local state means Terraform forgets your
   infrastructure exists. It will then try to create it all again, and fail on
   name collisions with resources it no longer knows it owns. Recovering means
   importing every resource by hand.
2. **Locking.** The blob is leased during an apply, so a concurrent apply fails
   fast instead of racing. Two simultaneous applies against local state corrupt
   it and orphan resources.

There is a bootstrap problem here: the storage account must exist before
Terraform can store state in it. That's why the backend block is commented out —
you create the storage account once (by hand or via a separate root module),
then uncomment and run `terraform init -migrate-state`.

## Production differences

`envs/prod` is not written yet. When it is, it differs by:

| | dev | prod |
|---|---|---|
| AKS SKU tier | Free (no SLA) | Standard (99.95% SLA, ~$73/mo) |
| Nodes | 1–2 × B2s | 3–6 × D2s_v5, zone-spread |
| `prevent_destroy` | off | **on** — `terraform destroy` fails without an explicit override |
| Entra RBAC | disabled | enabled, admin group required |
| Log retention | 30 days | 90 days |

## Verification status

```
terraform init      OK
terraform validate  Success! The configuration is valid.
terraform fmt       clean
terraform apply     NOT YET RUN — requires an Azure subscription
```

Two genuine errors were found by `validate` and fixed:

1. `retention_policy_in_days` was a nested block in azurerm v3 and became a
   plain attribute in v4. This is why the provider version is pinned `~> 4.0` —
   the pin is load-bearing, not housekeeping.
2. `azure_active_directory_role_based_access_control` requires either a
   `tenant_id` or an admin group. The provider refuses to enable Entra
   integration with neither, which is correct: a cluster with Entra RBAC on and
   no admin group defined would lock you out of your own cluster.
