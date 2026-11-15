# Lab SSO — upstream Keycloak

This k3s deployment uses the community `quay.io/keycloak/keycloak:26.8.2`
image, upstream PostgreSQL 16, and upstream Python. It installs no Red Hat
product images, subscriptions, or operators. Upstream Keycloak is the project
from which the Red Hat product is built; it still shares source and may use
Red Hat base components. This choice means the community distribution, not an
identity provider with no Red Hat project ancestry.

Issuer: `https://sso.tail7f3c08.ts.net/realms/lab`.
Tailscale Ingress supplies HTTPS, consistent with this lab's existing UIs.
Verify the issuer is reachable from pods as well as from tailnet browsers;
node Tailscale connectivity alone does not prove pod egress works.

| Service | Integration |
| --- | --- |
| Argo CD | Native public OIDC clients with PKCE for web and CLI |
| Radar | Native OIDC, persistent cookie key, group-based Kubernetes RBAC |
| Forgejo | Native OIDC source reconciled by Kubernetes Jobs using the native CLI |
| Omnigent | Native OIDC, hex cookie key, Secret-mounted administrator email roster |
| Homepage | Native OIDC with PKCE; v2.8 serves authenticated pages dynamically |
| Hermes dashboard | Bundled `self-hosted` OIDC/PKCE provider; Python init container migrates existing PVC auth settings |
| Hermes API | OAuth2 Proxy validates user JWTs for audience `hermes-api`, then replaces the upstream Authorization header with the private existing API key |
| RustFS Console | Native OIDC with PKCE; browser routing sends admin/callback paths to API port 9000 and pages to Console port 9001 |
| HashiCorp Vault | Native OIDC mount, constrained user/admin roles and policies, independent Kubernetes reconciliation Job |

Caretta/Grafana, VictoriaMetrics, OpenCost, Prometheus, PantryWise, RabbitMQ,
Firecrawl, the registry, RustDesk, and Kubernetes API OIDC configuration are
outside this selection. Vaultwarden remains an external credential source.

## Selected application details

The selected integrations add independent `sso-*-credentials` Secrets. Existing
CreatedOnce credentials are never expanded or regenerated to add an app. Back
up these new Secrets together with the original SSO database/admin credentials.
Omnigent's cookie material is converted to the required 64-character hex format;
OAuth2 Proxy's cookie key is encoded as 32 bytes. The Omnigent administrator
roster is derived from the managed account's email only when `user.admin` is
true. Omnigent's promotion is additive: removing a roster entry does not demote
an existing admin; use the application's administration controls too. Existing
accounts-provider session ownership may require a deliberate user/data migration.

Hermes's init container merges only GitOps-owned dashboard authentication and
plugin settings into the persisted config. Model, Telegram and other user
settings are preserved. It removes the legacy basic-auth block and disables the
`basic` plugin; environment variables alone cannot change an old PVC's plugin
list. Existing API_SERVER_KEY service authentication remains on the private
ClusterIP backend. The public tailnet API Ingress points at OAuth2 Proxy.

API clients must present an OIDC JWT issued for audience `hermes-api` and carrying
`lab-users`. The public PKCE client `hermes-api-cli` registers callback
`http://localhost:8250/oidc/callback` for OIDC-capable native clients. Password
grants remain disabled. Invalid/missing tokens receive JSON 401/403 responses;
API clients are not sent an HTML login page. OAuth2 Proxy uses its pinned 7.15.0
alpha configuration schema, checked locally with that binary's `--config-test`.
Hermes does not implement the cluster's read-only/admin role split: authorized
users can use the dashboard/agent API functionality the application exposes.

RustFS's pinned rc.3 source contains the configured OIDC environment variables.
`readonly` and, for explicit administrators, `consoleAdmin` group memberships
match built-in storage policies. The sidecar only routes the single HTTPS
browser origin; it does not replace RustFS authentication or S3 authorization.
Private-network discovery is allowed only for the configured Keycloak origin.

## Vault bootstrap credential

Create Vaultwarden item **`k3s/vault-sso`**, custom field **`token`**, containing
a Vault token authorized by [vault-sso-bootstrap.hcl](vault-sso-bootstrap.hcl).
An existing Vault administrator must install that policy and issue the token
before the Job can configure SSO. Store/renew or rotate it through Vaultwarden;
its lifetime must cover continued reconciliation. The Job never consumes the
stored Vault root token. This credential controls the named SSO auth/policy
endpoints, including the administrator policy, so treat it as SSO administration
material. It has no direct access to stored secret values or Transit decrypt.

Vault must already be initialized/unsealed. A sealed or uninitialized Vault
causes the independent `sso-vault` Job to fail visibly and retry later, without
blocking Keycloak. The new HTTPS URL is `https://vault.tail7f3c08.ts.net`.
Use OIDC role `lab-users` for inspection without secret reads, or select
`lab-admins` explicitly for administration; the latter requires that Keycloak
group. Both roles validate their group claims, audience, and exact callbacks.

Argo's existing Radar API account is retained. The SSO Application owns the
Argo OIDC/RBAC ConfigMaps so an existing cluster receives the change without
rerunning the full Argo installation; bootstrap literals contain the same values. Radar maps the preferred username
and groups directly to RBAC: `lab-users` can view, while explicit `lab-admins`
can administer. Forgejo retains its existing local accounts and requires login
to link an existing account; automatic account linking by matching email is
disabled. Its `lab-sso` source is reconciled by an Argo PostSync Job and a five-minute
CronJob. The Job copies the matching static CLI and its user/group files from
the existing Forgejo image into an emptyDir, then invokes the CLI directly from
Python without a shell. Pod affinity keeps it on the server node for the RWO
data volume. It mounts the existing app config and generated OIDC credential;
it needs no Kubernetes API token. The existing server has no SSO startup hook. Forgejo's ordinary local
user permissions still determine repository access; the Keycloak group grants
no blanket repository ownership.

Argo CLI login uses `argocd login argocd.tail7f3c08.ts.net --sso`.
Use the current local admin kubeconfig for cluster administration until a
separate Kubernetes API OIDC configuration is explicitly installed.

The Vaultwarden item must be a **Login** named exactly **`sso`**, with a unique
name. Its login username and password become the human SSO account. The
`bitwarden-sso` store filters the bridge response by exact item name and permits
only the `sso` namespace. No human credentials are committed to this repository.
The reconciler reads them from the ESO-managed `sso-user` Secret.

The two labs have independent realms and databases. Using the same vault login
gives the same username/password on both; browser sessions and logout remain
separate. Vaultwarden remains the credential source rather than an OIDC server.

## Account and permissions

`settings.json` configures realm `lab`, the application callbacks, and account
permissions. The login username is taken directly from Vaultwarden. If it is not
an email address, the default email claim is `<username>@danielsson.us.com`.
Set `user.email`, `user.firstName`, and `user.lastName` there when needed.
Only use an email address you control: OIDC applications use it as identity.

The account belongs to `lab-users`; Kubernetes/Radar, Argo, RustFS and Vault have read access by default. Set
`user.admin: true` deliberately to add `lab-admins`, which has cluster-admin and
Argo administration; supported app integrations also map it to their admin role.
Set `user.enabled: false` to disable the identity and expire Keycloak sessions.
Group changes require a fresh application login. Applications can retain their
own local role assignments and sessions; inspect those when revoking access.
An existing unmanaged Keycloak username is never taken over automatically.

ESO reads the vault every minute; `sso-reconcile` runs every five minutes and
also as an Argo PostSync hook. Updating the vault password changes the managed
Keycloak password on the next successful run and invalidates Keycloak sessions.
Unchanged passwords are not reset. Changing the vault username creates the new
account and disables/logs out previously managed accounts. The Bitwarden bridge
must sync its cached vault before ESO can see a newly added/changed item; see
the repository's existing bridge sync procedure. Deleting the item deliberately
retains the last Kubernetes Secret; disable `user.enabled` to revoke access.

## Deployment

Prerequisites: working ESO with Password generators and `CreatedOnce` refresh
policy (ESO 0.19+), the existing unlocked/syncing bitwarden-cli bridge, default
RWO storage, and trusted HTTPS to the issuer from browsers **and application
pods**. Keep certificate verification enabled. The database requests 8Gi,
PostgreSQL requests 256Mi RAM, and Keycloak requests 1Gi RAM.
The application namespaces must already exist before the SSO app publishes
its client Secrets; their normal lab Applications create them.

Publish the reviewed repository changes to the branch Argo tracks (`main` by
default), then sync the root app and `sso`. These changes are only local until
published. The PostSync hook provisions realm/account/clients and populates the
predeclared consumer Secrets. Argo ignores the generated `/data` fields, and
the reconciler can patch only the named consumer Secrets. An incomplete run
fails visibly and is retried by the scheduled job. Inspect logs for errors;
response bodies, tokens, and human credentials are never printed.

```sh
kubectl -n sso get externalsecrets,pods,jobs
kubectl -n sso logs job/sso-configure
# A successful hook is deleted. Run reconciliation explicitly if needed:
kubectl -n sso create job --from=cronjob/sso-reconcile sso-reconcile-manual
kubectl -n sso logs -f job/sso-reconcile-manual
```

Check `https://<issuer-host>/realms/lab/.well-known/openid-configuration`, then
use **Lab SSO** in each integrated UI with the vault login. Recovery/admin
application logins should be retained until a complete browser login succeeds.
Local rendering and unit tests cannot verify ingress, DNS, database startup,
image pull entitlements, or a real browser authorization-code exchange.

## Credential and data lifecycle

Each new integration has a separate CreatedOnce Secret. Independent Password
generators create the Keycloak bootstrap admin password,
database password, and each confidential client/cookie secret. They use
`CreatedOnce` and orphan their target Secrets so routine resyncs/pruning do not
rotate credentials or destroy database access. Back up `sso-admin`, `sso-db`,
`sso-client-credentials`, every new `sso-*-credentials` Secret, and the PostgreSQL volume together using your normal
private backup process. The PVC has `Prune=false,Delete=false`. This is a
single-instance lab deployment; it has no database HA or automatic backups.
Do not delete generated Secrets while retaining the database. Changing the
bootstrap admin environment alone cannot reset an existing Keycloak admin.
Planned technical-secret rotation must update the database/Keycloak and app
consumers together, then restart consumers that read environment at startup.
Do not rotate a generator as a substitute for that procedure.

## Reference review

The [reference repository](https://github.com/aiops-ansible-software-factory-demojam/openshift-gitops/tree/main/cluster/demojam-keycloak)
uses Red Hat build of Keycloak, PostgreSQL, OIDC clients, and an Admin API
bootstrap. Its demo defaults include administrator access and a fallback
password. This lab instead reads the exact Vaultwarden login, generates
independent machine credentials, and makes human administrator access an
explicit setting. It also preserves existing OpenShift login providers and
reconciles credential changes rather than relying on a one-time realm import.

## Local checks

```sh
kustomize build apps/sso >/tmp/sso-render.yaml
python3 -B -m unittest discover -s apps/sso/tests -v
```

Additional local checks:

```sh
python3 -B -m unittest discover -s apps/hermes -p 'test_*.py'
python3 -B -m unittest discover -s apps/forgejo/tests
```
