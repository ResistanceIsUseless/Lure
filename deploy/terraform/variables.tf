variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "resource_group_name" {
  description = "Resource group name"
  type        = string
  default     = "rg-lure"
}

variable "vm_size" {
  description = "VM size"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "VM SSH admin username"
  type        = string
  default     = "lure"
}

variable "oob_domain" {
  description = "OOB callback domain (subdomain delegated to Interactsh)"
  type        = string
  default     = "oob.campuscloud.io"
}

variable "content_domain" {
  description = "Content server domain"
  type        = string
  default     = "content.campuscloud.io"
}

variable "base_domain" {
  description = "Base domain for DNS zone (if managing DNS in Azure)"
  type        = string
  default     = "campuscloud.io"
}

variable "interactsh_token" {
  description = "Token for Interactsh auth"
  type        = string
  sensitive   = true
}

variable "admin_token" {
  description = "Token for Lure admin UI"
  type        = string
  sensitive   = true
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key for VM access"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "allowed_admin_cidrs" {
  description = "CIDRs allowed to SSH and access admin UI"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
