variable "name_prefix" {
  type = string
}

variable "unique_suffix" {
  type        = string
  description = "ACR names are globally unique across all Azure tenants; a suffix avoids collisions"
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "sku" {
  type        = string
  description = "Basic ~$5/mo, Standard ~$20/mo, Premium ~$500/mo"
  default     = "Basic"

  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.sku)
    error_message = "sku must be Basic, Standard, or Premium."
  }
}

variable "aks_kubelet_identity_object_id" {
  type        = string
  description = "Kubelet identity granted AcrPull. May be unknown at plan time."
  default     = null
}

variable "enable_aks_pull_role" {
  type        = bool
  description = "Whether to create the AcrPull role assignment. Must be statically known at plan time -- see the note in main.tf."
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
