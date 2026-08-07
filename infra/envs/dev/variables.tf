variable "environment" {
  type    = string
  default = "dev"
}

variable "location" {
  type        = string
  description = "southcentralus is closest to Texas and reliably has capacity for small burstable VM sizes"
  default     = "southcentralus"
}

variable "node_vm_size" {
  type        = string
  description = "Standard_B2s: 2 vCPU, 4GB, ~$30/mo. The floor for a working AKS node."
  default     = "Standard_B2s"
}
