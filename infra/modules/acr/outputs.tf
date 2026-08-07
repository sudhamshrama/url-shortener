output "login_server" {
  description = "Registry hostname, consumed by the CI pipeline"
  value       = azurerm_container_registry.this.login_server
}

output "registry_id" {
  value = azurerm_container_registry.this.id
}
