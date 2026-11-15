# Available only to the OIDC role bound to the explicit lab-admins group.
path "*" { capabilities = ["create", "read", "update", "delete", "list", "sudo", "patch"] }
