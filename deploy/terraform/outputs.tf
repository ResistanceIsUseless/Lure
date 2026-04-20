output "public_ip" {
  description = "VM public IP address"
  value       = azurerm_public_ip.lure.ip_address
}

output "ssh_command" {
  description = "SSH into the VM"
  value       = "ssh ${var.admin_username}@${azurerm_public_ip.lure.ip_address}"
}

output "admin_ui_url" {
  description = "Admin dashboard URL"
  value       = "https://${var.content_domain}/admin/ui?token=${var.admin_token}"
  sensitive   = true
}

output "health_url" {
  description = "Health check endpoint"
  value       = "https://${var.content_domain}/health"
}

output "dns_nameservers" {
  description = "Azure DNS zone nameservers — set these as NS records at your registrar"
  value       = azurerm_dns_zone.base.name_servers
}

output "dns_test_command" {
  description = "Test DNS delegation after nameserver propagation"
  value       = "dig test.${var.oob_domain} @${azurerm_public_ip.lure.ip_address}"
}
