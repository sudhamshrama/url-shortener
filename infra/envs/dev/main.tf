# Dev environment.
#
# This file is deliberately thin: it wires modules together and supplies
# environment-specific sizing. All the logic lives in ../../modules. That is the
# entire point of modules — dev, staging, and prod differ by variable values,
# not by duplicated code.

terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state.
  #
  # Terraform state is a JSON file recording every resource it manages, and it
  # is the single most sensitive artifact in an IaC repo — it contains resource
  # attributes in plaintext, including generated passwords and connection
  # strings. It must never be committed.
  #
  # Storing it in Azure Blob Storage also provides *locking*: the blob is leased
  # during an apply, so a second apply fails fast instead of racing. Two
  # concurrent applies against local state produce corrupted state and orphaned
  # resources, which is far worse than a failed command.
  #
  # Commented out until the storage account exists — see bootstrap/README.md.
  # Chicken-and-egg: the backend must exist before Terraform can use it, so it
  # is created once by hand or by a separate root module.
  #
  # backend "azurerm" {
  #   resource_group_name  = "rg-shrt-tfstate"
  #   storage_account_name = "stshrttfstate"
  #   container_name       = "tfstate"
  #   key                  = "dev.terraform.tfstate"
  #   use_azuread_auth     = true
  # }
}

provider "azurerm" {
  # Do not let the provider register Azure resource providers.
  #
  # By default azurerm registers *every* Azure resource provider (~80 of them)
  # the first time it touches a subscription. On an existing subscription that
  # is a no-op you never notice. On a brand-new one it is a 20+ minute wait,
  # and it does not always finish inside the provider's own timeout:
  #
  #   waiting for Subscription Provider (Microsoft.Network) to be registered:
  #   context deadline exceeded
  #
  # That is a failed plan, on a subscription where nothing is wrong. The
  # registrations are also permanent and subscription-wide, so paying that cost
  # on every CI run buys nothing.
  #
  # Instead the six providers this configuration actually needs are registered
  # once, explicitly, via `az provider register` — see infra/README.md. The
  # trade-off is that forgetting one produces a confusing error at apply time
  # rather than a slow but self-healing plan, which is why the list is
  # documented rather than tribal knowledge.
  resource_provider_registrations = "none"

  features {
    resource_group {
      # Refuse to delete a resource group that still contains resources. This
      # is a guardrail against the classic accident: deleting an RG in the
      # portal is one click and takes everything with it.
      prevent_deletion_if_contains_resources = true
    }
  }
}

locals {
  name_prefix = "shrt-${var.environment}"

  # Tags are not decoration. `cost-center` and `owner` are what let you answer
  # "what is this $80 line item" three months later, and `managed-by` tells the
  # next person not to edit these resources in the portal.
  tags = {
    project     = "url-shortener"
    environment = var.environment
    managed-by  = "terraform"
    owner       = "sudhamshrama"
    repo        = "github.com/sudhamshrama/url-shortener"
    # Marks this environment as safe to delete — the prod equivalent says
    # "never".
    lifecycle = "ephemeral"
  }
}

# ACR names must be globally unique across every Azure tenant, so a random
# suffix avoids a name collision with a stranger's registry.
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

# Control-plane and container logs. Kept small: 30 days of retention in the
# cheapest tier, because Log Analytics is billed per GB ingested and it is
# genuinely easy to run up a surprising bill here.
resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.name_prefix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  daily_quota_gb      = 1
  tags                = local.tags
}

module "networking" {
  source = "../../modules/networking"

  name_prefix         = local.name_prefix
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

module "aks" {
  source = "../../modules/aks"

  name_prefix         = local.name_prefix
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  subnet_id           = module.networking.aks_subnet_id

  # Dev sizing: the smallest thing that actually works. One node most of the
  # time, scaling to two under load, on the cheapest burstable VM size.
  sku_tier       = "Free"
  node_vm_size   = var.node_vm_size
  node_min_count = 1
  node_max_count = 2

  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = local.tags
}

module "acr" {
  source = "../../modules/acr"

  name_prefix         = local.name_prefix
  unique_suffix       = random_string.suffix.result
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Basic"

  # Wiring this output into this input is what creates the AcrPull role
  # assignment — and it is also what makes Terraform apply AKS before ACR's role
  # binding, without any explicit depends_on. Implicit dependencies through
  # references are how Terraform builds its graph.
  aks_kubelet_identity_object_id = module.aks.kubelet_identity_object_id

  tags = local.tags
}
