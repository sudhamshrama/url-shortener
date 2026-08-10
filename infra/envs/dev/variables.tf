variable "environment" {
  type    = string
  default = "dev"
}

variable "location" {
  type        = string
  description = "Must be permitted by the subscription's 'Allowed resource deployment regions' policy -- see the note below."
  default     = "eastus"

  # Azure for Students subscriptions carry a policy assignment named
  # "Allowed resource deployment regions" that restricts deployment to a short
  # list. On this subscription that list is:
  #
  #   eastus, mexicocentral, norwayeast, northcentralus, westus
  #
  # southcentralus -- the obvious pick for Texas -- is NOT on it. Deploying
  # there fails at APPLY time, not plan time, with:
  #
  #   RequestDisallowedByAzure: Resource 'x' was disallowed by Azure: This
  #   policy maintains a set of best available regions...
  #
  # Plan cannot catch this because Azure Policy is evaluated by the resource
  # provider at creation. That is worth internalising: `terraform plan`
  # validates your configuration, not your authorisation.
  #
  # Check before choosing a region:
  #   az policy assignment list \
  #     --query "[?displayName=='Allowed resource deployment regions'].parameters"
  validation {
    condition = contains(
      ["eastus", "mexicocentral", "norwayeast", "northcentralus", "westus"],
      var.location
    )
    error_message = "Region not permitted by this subscription's policy. Allowed: eastus, mexicocentral, norwayeast, northcentralus, westus."
  }
}

variable "node_vm_size" {
  type        = string
  description = "Standard_B2s: 2 vCPU, 4GB, ~$30/mo. The floor for a working AKS node."
  default     = "Standard_B2s"
}
