# Azure Container Registry.
#
# NOTE: this project publishes to GHCR, not ACR, because GHCR is free for public
# images and ACR's cheapest tier is about $5/month. This module exists because
# ACR is what an Azure shop would use, and swapping registries is a two-line
# change in the pipeline. It is applied only during the supervised burst.

terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

resource "azurerm_container_registry" "this" {
  # ACR names are globally unique across all of Azure and allow only
  # alphanumerics -- no hyphens. That is why this strips them rather than using
  # name_prefix directly, and why a random suffix is appended.
  name                = replace("acr${var.name_prefix}${var.unique_suffix}", "-", "")
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = var.sku
  tags                = var.tags

  # Admin user disabled. It is a shared username/password with push rights --
  # exactly the kind of long-lived credential that ends up in a CI variable and
  # then in a leak. Access goes through managed identity instead.
  admin_enabled = false

  # NOTE: untagged-manifest retention was a nested block in azurerm v3 and became
  # a plain optional attribute in v4 -- and it is Premium-only either way. On
  # Basic it is simply unavailable, so it is omitted rather than guarded. This is
  # the kind of breaking change that makes pinning the provider version
  # (`~> 4.0` above) load-bearing rather than housekeeping.
}

# Let AKS nodes pull images using their own managed identity. No imagePullSecret,
# no registry password stored in a Kubernetes Secret, nothing to rotate.
resource "azurerm_role_assignment" "aks_pull" {
  count = var.aks_kubelet_identity_object_id == null ? 0 : 1

  scope                            = azurerm_container_registry.this.id
  role_definition_name             = "AcrPull"
  principal_id                     = var.aks_kubelet_identity_object_id
  skip_service_principal_aad_check = true
}
