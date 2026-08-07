variable "name_prefix" {
  description = "Prefix for all resource names, e.g. shrt-dev"
  type        = string
}

variable "location" {
  description = "Azure region"
  type        = string
}

variable "resource_group_name" {
  description = "Existing resource group to create resources in"
  type        = string
}

variable "vnet_cidr" {
  description = "Address space for the virtual network"
  type        = string
  default     = "10.0.0.0/16"
}

variable "aks_subnet_cidr" {
  description = "Subnet for AKS nodes and pods. A /22 gives ~1000 addresses; with Azure CNI every pod consumes one."
  type        = string
  default     = "10.0.0.0/22"

  validation {
    # A /24 or smaller is exhausted by ~8 nodes and cannot be resized in place.
    condition     = tonumber(split("/", var.aks_subnet_cidr)[1]) <= 23
    error_message = "AKS subnet must be /23 or larger; smaller ranges run out of pod IPs and require rebuilding the cluster."
  }
}

variable "services_subnet_cidr" {
  description = "Subnet for internal load balancers and private endpoints"
  type        = string
  default     = "10.0.4.0/24"
}

variable "tags" {
  description = "Tags applied to every resource"
  type        = map(string)
  default     = {}
}
