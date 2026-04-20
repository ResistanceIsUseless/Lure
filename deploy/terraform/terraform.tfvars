location            = "eastus"
resource_group_name = "rg-lure"
vm_size             = "Standard_B2s"
admin_username      = "lure"

oob_domain     = "oob.campuscloud.io"
content_domain = "content.campuscloud.io"
base_domain    = "campuscloud.io"

ssh_public_key_path = "~/.ssh/id_ed25519.pub"

# Restrict SSH/admin to your IP (update before apply)
# allowed_admin_cidrs = ["203.0.113.50/32"]
