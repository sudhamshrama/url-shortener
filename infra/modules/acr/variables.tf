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
  description = "Granted AcrPull. Null skips the role assignment."
  default     = null
}

variable "tags" {
  type    = map(string)
  default = {}
}
