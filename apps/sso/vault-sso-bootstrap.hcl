# Provision a token carrying this policy and store it in Vaultwarden
# k3s/vault-sso, custom field token. No root token is consumed by the Job.
path "sys/seal-status" { capabilities = ["read"] }
path "sys/auth" { capabilities = ["read"] }
path "sys/auth/oidc" { capabilities = ["create", "update", "sudo"] }
path "auth/oidc/config" { capabilities = ["create", "read", "update"] }
path "auth/oidc/role/lab-users" { capabilities = ["create", "read", "update"] }
path "auth/oidc/role/lab-admins" { capabilities = ["create", "read", "update"] }
path "sys/policies/acl/lab-sso-readonly" { capabilities = ["create", "read", "update"] }
path "sys/policies/acl/lab-sso-admin" { capabilities = ["create", "read", "update"] }
