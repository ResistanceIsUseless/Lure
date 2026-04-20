terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = "13ad1203-e6d5-4076-bf2b-73465865f9f0"
}

# --------------------------------------------------------------------------
# Resource Group
# --------------------------------------------------------------------------
resource "azurerm_resource_group" "lure" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project = "lure"
    purpose = "security-training"
  }
}

# --------------------------------------------------------------------------
# Networking
# --------------------------------------------------------------------------
resource "azurerm_virtual_network" "lure" {
  name                = "vnet-lure"
  location            = azurerm_resource_group.lure.location
  resource_group_name = azurerm_resource_group.lure.name
  address_space       = ["10.0.0.0/24"]
}

resource "azurerm_subnet" "lure" {
  name                 = "snet-lure"
  resource_group_name  = azurerm_resource_group.lure.name
  virtual_network_name = azurerm_virtual_network.lure.name
  address_prefixes     = ["10.0.0.0/24"]
}

resource "azurerm_public_ip" "lure" {
  name                = "pip-lure"
  location            = azurerm_resource_group.lure.location
  resource_group_name = azurerm_resource_group.lure.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    project = "lure"
  }
}

# --------------------------------------------------------------------------
# NSG — open ports for Interactsh + vector server
# --------------------------------------------------------------------------
resource "azurerm_network_security_group" "lure" {
  name                = "nsg-lure"
  location            = azurerm_resource_group.lure.location
  resource_group_name = azurerm_resource_group.lure.name

  # SSH — restricted to admin CIDRs
  security_rule {
    name                       = "AllowSSH"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.allowed_admin_cidrs
    destination_address_prefix = "*"
  }

  # DNS (UDP + TCP)
  security_rule {
    name                       = "AllowDNS-UDP"
    priority                   = 200
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Udp"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowDNS-TCP"
    priority                   = 201
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "53"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # HTTP + HTTPS
  security_rule {
    name                       = "AllowHTTP"
    priority                   = 300
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "AllowHTTPS"
    priority                   = 301
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # SMTP (Interactsh)
  security_rule {
    name                       = "AllowSMTP"
    priority                   = 400
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "25"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # LDAP (Interactsh)
  security_rule {
    name                       = "AllowLDAP"
    priority                   = 401
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "389"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  # FTP (Interactsh)
  security_rule {
    name                       = "AllowFTP"
    priority                   = 402
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "21"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "lure" {
  name                = "nic-lure"
  location            = azurerm_resource_group.lure.location
  resource_group_name = azurerm_resource_group.lure.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.lure.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.lure.id
  }
}

resource "azurerm_network_interface_security_group_association" "lure" {
  network_interface_id      = azurerm_network_interface.lure.id
  network_security_group_id = azurerm_network_security_group.lure.id
}

# --------------------------------------------------------------------------
# DNS Zone
# --------------------------------------------------------------------------
resource "azurerm_dns_zone" "base" {
  name                = var.base_domain
  resource_group_name = azurerm_resource_group.lure.name
}

# NS delegation: oob.campuscloud.io → the VM itself (Interactsh is authoritative)
resource "azurerm_dns_ns_record" "oob" {
  name                = "oob"
  zone_name           = azurerm_dns_zone.base.name
  resource_group_name = azurerm_resource_group.lure.name
  ttl                 = 300

  records = ["ns.${var.base_domain}."]
}

# ns.campuscloud.io → VM public IP
resource "azurerm_dns_a_record" "ns" {
  name                = "ns"
  zone_name           = azurerm_dns_zone.base.name
  resource_group_name = azurerm_resource_group.lure.name
  ttl                 = 300
  records             = [azurerm_public_ip.lure.ip_address]
}

# content.campuscloud.io → VM public IP
resource "azurerm_dns_a_record" "content" {
  name                = "content"
  zone_name           = azurerm_dns_zone.base.name
  resource_group_name = azurerm_resource_group.lure.name
  ttl                 = 300
  records             = [azurerm_public_ip.lure.ip_address]
}

# --------------------------------------------------------------------------
# VM
# --------------------------------------------------------------------------
resource "azurerm_linux_virtual_machine" "lure" {
  name                = "vm-lure"
  location            = azurerm_resource_group.lure.location
  resource_group_name = azurerm_resource_group.lure.name
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [azurerm_network_interface.lure.id]

  admin_ssh_key {
    username   = var.admin_username
    public_key = file(pathexpand(var.ssh_public_key_path))
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    oob_domain        = var.oob_domain
    content_domain    = var.content_domain
    public_ip         = azurerm_public_ip.lure.ip_address
    interactsh_token  = var.interactsh_token
    admin_token       = var.admin_token
    docker_compose    = indent(6, file("${path.module}/../docker-compose.yml"))
    caddyfile         = indent(6, file("${path.module}/../Caddyfile"))
    admin_username    = var.admin_username
  }))

  tags = {
    project = "lure"
    purpose = "security-training"
  }
}
