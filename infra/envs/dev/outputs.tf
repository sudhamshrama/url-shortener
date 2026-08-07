# These outputs are the seam between Terraform and everything else. The CI
# pipeline and ArgoCD read them rather than having values hardcoded, so
# rebuilding the infrastructure does not require editing the pipeline.

output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "cluster_name" {
  value = module.aks.cluster_name
}

output "acr_login_server" {
  description = "Set this as the registry in the CI workflow to publish to ACR instead of GHCR"
  value       = module.acr.login_server
}

output "kubeconfig_command" {
  description = "Run this to point kubectl at the new cluster"
  value       = "az aks get-credentials --resource-group ${azurerm_resource_group.this.name} --name ${module.aks.cluster_name}"
}

output "estimated_monthly_cost_usd" {
  description = "Rough, and deliberately visible in every plan output."
  value       = "~$35-70/month: AKS control plane $0 (Free tier) + 1-2x ${var.node_vm_size} nodes + ACR Basic $5 + Log Analytics ~$3. DESTROY WHEN DONE."
}
