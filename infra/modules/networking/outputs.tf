output "vnet_id" {
  description = "Virtual network resource ID"
  value       = azurerm_virtual_network.this.id
}

output "aks_subnet_id" {
  description = "Subnet ID for the AKS node pool"
  value       = azurerm_subnet.aks.id
}

output "services_subnet_id" {
  description = "Subnet ID for internal load balancers"
  value       = azurerm_subnet.services.id
}
