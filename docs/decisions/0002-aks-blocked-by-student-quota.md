# ADR 0002: AKS could not be provisioned — student-subscription quota

**Status:** Accepted (constraint, not a choice)
**Date:** 2026-08-09

## Context

The Terraform in `infra/` describes an AKS cluster, container registry,
networking, and Log Analytics. It passed `terraform validate` and produced a
clean `Plan: 11 to add, 0 to change, 0 to destroy` against a real Azure for
Students subscription.

The apply failed. Five times, for five different reasons, each surfacing only at
create time.

## What happened

### 1. Region disallowed by policy

```
RequestDisallowedByAzure: Resource 'vnet-shrt-dev' was disallowed by Azure:
This policy maintains a set of best available regions where your subscription
can deploy resources.
```

The subscription carries a policy assignment named *Allowed resource deployment
regions*, restricting deployment to:

```
eastus · mexicocentral · norwayeast · northcentralus · westus
```

`southcentralus` — chosen because it is closest to Texas — is not among them.
Nothing in the Terraform is wrong; the plan cannot see the policy.

### 2. Kubernetes version aged out of support

```
K8sVersionNotSupported: Managed cluster is on version 1.31.13, which is only
available for Long-Term Support (LTS)
```

`1.31` was pinned when the module was written. Kubernetes ships roughly three
minor releases a year and each leaves standard support after about a year, so a
pinned version rots on a timer.

### 3. VM size not permitted

```
The VM size of Standard_B2s is not allowed in your subscription in
location 'eastus'
```

The entire burstable B-series is absent from this subscription's allowed list,
which consists of D/E/F/M-series and GPU sizes.

### 4. Quota exhausted for the chosen family

```
ErrCode_InsufficientVCPUQuota: requested 2, remaining 0 for family
StandardDadsv7Family for region eastus
```

### 5. Quota exhausted for *every* permitted family

This is the fatal one. Checking each family AKS would accept:

```
StandardDadsv7Family    0      StandardEadsv7Family   0
StandardDaldsv7Family   0      StandardEasv7Family    0
StandardDalsv7Family    0      StandardEdsv7Family    0
StandardDasv7Family     0      StandardEsv7Family     0
StandardDdsv7Family     0      StandardFadsv7Family   0
StandardDldsv7Family    0      ... every one, zero
StandardDlsv7Family     0
StandardDsv7Family      0
```

And across all five permitted regions — `eastus`, `westus`, `northcentralus`,
`mexicocentral`, `norwayeast` — the total quota across AKS-eligible families is
**0** in every case.

The subscription has 6 total regional vCPUs and 10 vCPUs of `Bsv2` quota, but
AKS will not accept a B-series size here. The one family with quota
(`standardDCSFamily`, 2 vCPUs) is DCsv2, which is not on the allowed list. The
intersection of *permitted by AKS* and *has quota* is empty.

## Decision

**Do not pursue AKS on this subscription.** The Terraform stays as written and
validated. It is correct; the subscription cannot execute it.

The rest of the configuration — networking, ACR, Log Analytics — was applied
successfully, verified in the portal, and destroyed cleanly. That part is real.

## Consequences

**What can honestly be claimed:** Terraform modules for AKS, ACR, and
networking, written, validated, and applied against a real Azure subscription.
VNet, subnets, NSG with rules, a container registry with RBAC, and a Log
Analytics workspace were genuinely created and destroyed. The AKS module has
never run.

**What cannot:** that a Kubernetes cluster was provisioned in Azure. It was not.
Kubernetes work in this project ran on kind, locally.

**Options not taken:**

- *Request a quota increase.* Free and worth doing, but student subscriptions
  are frequently denied and the turnaround is around 24 hours. Not worth
  blocking on.
- *Switch to a pay-as-you-go subscription.* Would work. Costs real money and
  contradicts the project's $0 constraint.
- *Use a different provider.* AWS and GCP free tiers have their own limits;
  swapping would mean rewriting the modules to prove the same point.

## The lesson worth keeping

**`terraform plan` validates configuration, not authorization.**

A clean plan means your HCL is syntactically valid, internally consistent, and
that the provider can compute a diff. It says nothing about whether your
subscription is permitted to create those resources — policy assignments, SKU
allowlists, and quota are all evaluated by the resource provider at create time.

Every one of the five failures above produced a *successful plan* first.

This has a practical consequence for CI: a pipeline that runs `terraform plan`
on pull requests and reports green gives a false sense of safety. The plan
passing does not mean the apply will. Catching these earlier means either
running against a real environment, or adding explicit pre-flight checks:

```bash
az policy assignment list \
  --query "[?displayName=='Allowed resource deployment regions'].parameters"
az vm list-usage --location <region> -o table
az aks get-versions --location <region> -o table
```

The `location` and `os_disk_type` variables now carry `validation` blocks so at
least the region mistake fails fast, locally, with a message that names the
allowed values. Quota cannot be validated that way — it is runtime state — but
the check is documented in `infra/README.md`.
