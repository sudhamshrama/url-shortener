variable "name_prefix" {
  type        = string
  description = "Prefix for resource names"
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "subnet_id" {
  type        = string
  description = "Subnet the node pool is placed in"
}

variable "kubernetes_version" {
  type        = string
  description = "Pinned so an upgrade is a reviewed change, not a surprise. Must still be in standard support -- see note."
  default     = "1.34"

  # Pinning a version is correct; pinning and forgetting is not.
  #
  # 1.31 was the default here and had aged out of standard support by the time
  # this was first applied. AKS rejected it at creation:
  #
  #   K8sVersionNotSupported: Managed cluster is on version 1.31.13, which is
  #   only available for Long-Term Support (LTS)
  #
  # Kubernetes ships roughly three minor versions a year and each leaves
  # standard support after about a year, so a pinned version silently rots.
  # This is exactly why automatic_upgrade_channel is set to "patch" on the
  # cluster -- patches apply themselves, minors stay a deliberate decision.
  #
  # 1.34 is deliberately not the newest. Running N-2 means the release has been
  # through a couple of patch cycles, and there is upgrade headroom before
  # support lapses. Check what is currently offered before changing it:
  #
  #   az aks get-versions --location eastus -o table
}

variable "sku_tier" {
  type    = string
  default = "Free"

  validation {
    condition     = contains(["Free", "Standard", "Premium"], var.sku_tier)
    error_message = "sku_tier must be Free, Standard, or Premium."
  }
}

variable "auto_upgrade_channel" {
  type    = string
  default = "patch"
}

variable "node_vm_size" {
  type        = string
  description = "Must be permitted by the subscription. Student subscriptions restrict this heavily -- see note."
  default     = "Standard_D2ads_v7"

  # Standard_B2s was the original choice: cheapest thing that runs a node.
  # Azure for Students does not permit it. The apply failed with:
  #
  #   The VM size of Standard_B2s is not allowed in your subscription in
  #   location 'eastus'
  #
  # The entire burstable B-series is absent from the allowed list, which
  # consists of D/E/F/M-series and GPU sizes. Standard_D2ads_v7 (2 vCPU, 8 GiB,
  # AMD, with a local temp disk) is among the smallest permitted.
  #
  # Like the region policy, this is enforced at CREATE time, not plan time.
  # Check before choosing:
  #
  #   az vm list-skus --location eastus --size Standard_D --output table
}

variable "os_disk_type" {
  type        = string
  description = "Ephemeral is free but requires a VM size with a local temp disk at least os_disk_size_gb. Managed always works and is billed separately."
  default     = "Managed"

  validation {
    condition     = contains(["Managed", "Ephemeral"], var.os_disk_type)
    error_message = "os_disk_type must be Managed or Ephemeral."
  }
}

variable "node_min_count" {
  type    = number
  default = 1
}

variable "node_max_count" {
  type    = number
  default = 3
}

variable "availability_zones" {
  type        = list(string)
  description = "Empty means no zone spreading. Not all regions or VM sizes support zones."
  default     = []
}

variable "pod_cidr" {
  type    = string
  default = "192.168.0.0/16"
}

variable "service_cidr" {
  type    = string
  default = "172.16.0.0/16"
}

variable "dns_service_ip" {
  type        = string
  description = "Must be inside service_cidr"
  default     = "172.16.0.10"
}

variable "log_analytics_workspace_id" {
  type    = string
  default = null
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "entra_admin_group_object_ids" {
  type        = list(string)
  description = "Entra ID group object IDs granted cluster-admin. Null disables Entra RBAC integration entirely (local accounts only) -- fine for a short-lived demo cluster, wrong for anything shared."
  default     = null
}
