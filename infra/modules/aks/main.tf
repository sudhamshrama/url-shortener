# AKS module.
#
# Cost note, because this is the expensive resource in the whole portfolio:
# the AKS *control plane* is free on the Free tier, but the worker nodes are
# ordinary VMs and are billed by the hour whether or not anything is running on
# them. Two Standard_B2s nodes are roughly $60-75/month. That is the entire
# reason this project runs on kind locally and applies this module only in a
# short, supervised burst.

terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = "aks-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  dns_prefix          = var.name_prefix
  kubernetes_version  = var.kubernetes_version
  tags                = var.tags

  # "Free" has no uptime SLA and is right for dev. Production uses "Standard",
  # which adds a financially-backed 99.95% SLA and costs about $73/month for the
  # control plane alone.
  sku_tier = var.sku_tier

  # Node auto-upgrade. Kubernetes minor versions leave support after about a
  # year, and a cluster stuck on an unsupported version cannot be upgraded in
  # one hop — you have to walk it forward one minor at a time, which is a
  # multi-day operation nobody enjoys.
  automatic_upgrade_channel = var.auto_upgrade_channel

  default_node_pool {
    name           = "system"
    vm_size        = var.node_vm_size
    vnet_subnet_id = var.subnet_id

    # Autoscaling rather than a fixed count, so the cluster shrinks when idle.
    # On a metered subscription this is the difference between paying for peak
    # and paying for actual use.
    auto_scaling_enabled = true
    min_count            = var.node_min_count
    max_count            = var.node_max_count

    # Spreads nodes across availability zones. Without this, a single zone
    # outage takes the whole cluster down. Only set where the region supports
    # zones — hence the variable rather than a hardcoded list.
    zones = var.availability_zones

    os_disk_size_gb = 64
    # Ephemeral OS disks live on the VM's local storage: faster, and free,
    # versus a managed disk that is billed separately. The trade is that node
    # state does not survive a reimage, which for a Kubernetes node is fine —
    # nodes are meant to be disposable.
    os_disk_type = "Ephemeral"

    upgrade_settings {
      max_surge = "33%"
    }
  }

  # Managed identity rather than a service principal with a password. There is
  # no secret to rotate, leak, or commit — Azure handles the credential
  # lifecycle. "How do you avoid long-lived cloud credentials?" is a standard
  # interview question and this is the answer.
  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin = "azure"
    # Azure CNI Overlay: pods get IPs from a separate overlay CIDR rather than
    # consuming VNet addresses. This removes the subnet-exhaustion problem the
    # networking module warns about, at the cost of pods not being directly
    # routable from outside the cluster.
    network_plugin_mode = "overlay"
    pod_cidr            = var.pod_cidr
    service_cidr        = var.service_cidr
    dns_service_ip      = var.dns_service_ip
    load_balancer_sku   = "standard"
    outbound_type       = "loadBalancer"
  }

  # Send control-plane logs to Log Analytics. Without this, "why did the
  # scheduler refuse to place my pod three hours ago" is unanswerable.
  dynamic "oms_agent" {
    for_each = var.log_analytics_workspace_id == null ? [] : [1]
    content {
      log_analytics_workspace_id = var.log_analytics_workspace_id
    }
  }

  # Kubernetes RBAC backed by Entra ID, so cluster access follows the same
  # identity system as everything else and can be revoked centrally.
  #
  # Gated behind a variable because the provider requires either a tenant_id or
  # an admin group to be named -- enabling it with neither is a validation error,
  # not a silent default. That strictness is correct: an "Entra-integrated"
  # cluster with no admin group defined would lock you out of your own cluster.
  dynamic "azure_active_directory_role_based_access_control" {
    for_each = var.entra_admin_group_object_ids == null ? [] : [1]
    content {
      azure_rbac_enabled     = true
      admin_group_object_ids = var.entra_admin_group_object_ids
    }
  }

  lifecycle {
    ignore_changes = [
      # The autoscaler owns node_count at runtime. Without this, every
      # `terraform apply` would try to reset it to the value in state and fight
      # the autoscaler — a genuinely confusing failure where infrastructure
      # oscillates for no visible reason.
      default_node_pool[0].node_count,
    ]
  }
}
