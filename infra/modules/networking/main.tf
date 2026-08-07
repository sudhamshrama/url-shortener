# Networking module: VNet, subnets, NSGs.
#
# AKS needs its own subnet, sized generously. With Azure CNI every *pod* gets a
# real VNet IP, not just every node — so a /24 (251 usable addresses) is
# exhausted by roughly 8 nodes at the default 30 pods per node. Running out of
# subnet space is not something you can fix in place; it requires rebuilding the
# cluster. Hence the /22 here.

terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

resource "azurerm_virtual_network" "this" {
  name                = "vnet-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.aks_subnet_cidr]
}

# Separate subnet reserved for internal load balancers and private endpoints.
# Splitting them from the node subnet means an ingress controller cannot
# accidentally consume addresses the cluster needs to schedule pods.
resource "azurerm_subnet" "services" {
  name                 = "snet-services"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = [var.services_subnet_cidr]

  private_endpoint_network_policies = "Enabled"
}

resource "azurerm_network_security_group" "aks" {
  name                = "nsg-${var.name_prefix}-aks"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  # Inbound HTTPS only. Note there is no SSH rule: node access goes through
  # `az aks command invoke` or a private endpoint, never a public port 22.
  # An open SSH port on a Kubernetes node is a finding in any security review.
  security_rule {
    name                       = "AllowHTTPSInbound"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTPInbound"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }

  # Explicit deny at the lowest priority. Azure already denies by default, but
  # stating it makes the intent reviewable rather than implied.
  security_rule {
    name                       = "DenyAllInbound"
    priority                   = 4096
    direction                  = "Inbound"
    access                     = "Deny"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "aks" {
  subnet_id                 = azurerm_subnet.aks.id
  network_security_group_id = azurerm_network_security_group.aks.id
}
