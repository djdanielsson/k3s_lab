# Human UI inspection; this grants no secret values or Transit decrypt access.
path "sys/mounts" { capabilities = ["read"] }
path "sys/auth" { capabilities = ["read"] }
path "sys/policies/acl" { capabilities = ["list"] }
path "sys/policies/acl/*" { capabilities = ["read"] }
