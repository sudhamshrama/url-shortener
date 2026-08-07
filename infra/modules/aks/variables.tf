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
  description = "Pinned so an upgrade is a reviewed change, not a surprise"
  default     = "1.31"
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
  description = "Standard_B2s is the cheapest size that can actually run a cluster (~$30/mo each)"
  default     = "Standard_B2s"
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
