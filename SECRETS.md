# Secrets — Vaultwarden

All app secrets live in **Vaultwarden** and are synced into the cluster by
**External Secrets Operator (ESO)** via the bitwarden-cli bridge. Item names
are prefixed **`k3s/`**.

## 1. Provider credentials — create these yourself (NOT vault items)

These are the auth the bridge/operator use; they're the only things in
`SECRETS.md` that don't come from a Vaultwarden item.

> **Redeploy backup (do this once, store offline):** SealedSecrets can only
> be decrypted by THIS cluster's key. Back it up or a fresh cluster cannot
> unseal `apps/*/sealed-secret.yaml` (radar-argocd-token…):
> ```bash
> kubectl -n kube-system get secret sealed-secrets-key -o yaml > sealed-secrets-key.backup.yaml
> # restore on the new cluster BEFORE ArgoCD syncs sealed apps:
> kubectl apply -f sealed-secrets-key.backup.yaml -n kube-system
> ```
> Also re-mint the Radar→ArgoCD token on a fresh install (account `radar`
> is declarative in `infra/argocd`, but tokens don't transfer):
> ```bash
> # login as admin, then:
> curl -sk -X POST https://<argocd-ts-host>/api/v1/account/radar/token \
>   -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
>   -d '{"id":"radar-ui"}'
> # reseal into apps/radar-auth/sealed-secret.yaml with kubeseal
> ```

### Vaultwarden API (ESO/bitwarden-cli)
1. Vaultwarden vault → **Settings → Security → Keys → New API Key**.
2. Copy the **Client ID** + **Client Secret** (`BW_HOST = https://truenas-scale`).

```bash
kubectl -n external-secrets create secret generic bitwarden-cli \
  --from-literal=BW_HOST=https://truenas-scale \
  --from-literal=BW_CLIENTID=<YOUR_CLIENT_ID> \
  --from-literal=BW_CLIENTSECRET=<YOUR_CLIENT_SECRET> \
  --from-literal=BW_PASSWORD=<if_used> \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Tailscale OAuth (Tailscale operator)
1. Admin Console → **Settings → Keys → Generate… → OAuth clients**.
2. Scope **Read + Write** → copy the **Client ID** + **Client Secret**. Ensure **MagicDNS** is on.
3. Store them on the `k3s/tailscale` Vaultwarden item as fields `CLIENT_ID` and
   `CLIENT_SECRET`. That item is the source of truth: the `tailscale-oauth`
   Application (see §2) syncs it into the operator's `operator-oauth` Secret,
   which the operator mounts at `/oauth/`.

Do **not** apply this by hand any more. The credential previously existed only as
a hand-applied Secret, so there was nothing to rotate from when it leaked:

```bash
# historical, replaced by the ExternalSecret — do not run
kubectl -n tailscale create secret generic tailscale-oauth \
  --from-literal=CLIENT_ID=... --from-literal=CLIENT_SECRET=...
```

To rotate: create the replacement client in the console, edit the two fields on
`k3s/tailscale`, delete the old client, then restart the operator pod
(`kubectl -n tailscale delete pod -l app=tailscale-operator`) — the operator
reads the credential files once at startup, so the new value is not picked up on
its own.

## 2. Vaultwarden items to create
Create items with `k3s/` names. A secret value is stored on an item in one of
three places (pick what fits):

| Storage | Put the value in…            | ESO store          |
|---------|------------------------------|--------------------|
| Single value | the item's **Notes**     | `bitwarden-notes`  |
| Multiple values | a **Custom Field** (name=key) | `bitwarden-fields` |
| User/pass | the item's **login** object | `bitwarden-login`  |

Item names must be unique (the bridge searches by exact name).

| Item name             | Type         | Inputs (fields / notes)        |
|-----------------------|--------------|--------------------------------|
| `k3s/pantrywise-jwt`  | Custom field | field `jwt`                    |
| `k3s/pantrywise-db`   | Custom fields| `user`, `password`, `url`      |
| `k3s/forgejo-db`      | Custom fields| `user`, `password`, `name`     |
| `k3s/github-tokens`   | Custom fields| one field per token            |
| `k3s/radar-auth`      | Custom fields| `oidcSecret`, `clientId`       |
| `k3s/registry-htpasswd` | Secure Note | Notes = the htpasswd string  |
| `k3s/hermes-env`       | Custom fields| `OPENCODE_GO_API_KEY`, `GITHUB_TOKEN`, `API_SERVER_KEY`, `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`, `HERMES_DASHBOARD_BASIC_AUTH_SECRET`, and (if running Telegram in-cluster) `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `TELEGRAM_HOME_CHANNEL` |
| `k3s/radar-argocd-token` | Custom field | field `token` — ArgoCD API token for account `radar` (mint after install, see §1 note) |
| `k3s/forgejo-secrets` | Custom fields| `db-name`, `db-user`, `db-password` — **must match the live `forgejo-secrets` Secret** or Forgejo loses its database on redeploy |
| `k3s/pantrywise-secrets` | Custom fields | `database-url`, `jwt-secret`, `postgres-db`, `postgres-user`, `postgres-password` — **must match the live `pantrywise-secrets` Secret** |
| `k3s/litellm` | Custom fields | `LITELLM_MASTER_KEY` — the gateway's only credential (every agent talks to it, and it authenticates to nothing else); `OPENCODE_GO_API_KEY` — the OpenCode Go subscription key behind the `fast` / `smart` aliases; `POSTGRES_PASSWORD` — the `litellm-postgres` superuser password, from which `DATABASE_URL` is composed for spend logging; `UI_PASSWORD` — the admin UI's login password (username `admin`; the UI rejects the master key). Fields `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and `LAN_LLM_API_KEY` on this item are empty leftovers from the AgentForge era and are read by nothing. |
| `k3s/omnigent`        | Custom fields | `POSTGRES_PASSWORD` — postgres superuser password, and the value the server's `DATABASE_URL` is composed from; `OMNIGENT_ACCOUNTS_COOKIE_SECRET` — **must be a hex string** (the server refuses to start on anything else). Omnigent's *model* credential is not here: it comes from `k3s/litellm` field `LITELLM_MASTER_KEY`, because every model call goes to the in-cluster LiteLLM, whose master key is its only valid credential. |
| `k3s/tailscale` | Custom fields | `CLIENT_ID`, `CLIENT_SECRET` — the Tailscale operator's OAuth client (`tag:k3s`, scope `all`), which mints an auth key for every tailnet Ingress proxy. Source of truth for the `operator-oauth` Secret; see §1 note on rotating it. |
| `k3s/admin-kubeconfig` | Secure Note | **Notes** = a complete kubeconfig for the operator's own kubectl access over Tailscale; also fields `token` and `server`. Subject: ServiceAccount `david` in ns `admin-access` (cluster-admin). Tokens expire — re-mint and update the note when it stops working (see below). |

### Rotating the admin kubeconfig (`k3s/admin-kubeconfig`)

```bash
# mint a fresh token (any workload with cluster access, e.g. the hermes pod)
kubectl -n admin-access create token david --duration=8760h
# build a kubeconfig with server https://100.93.49.21:6443 and the cluster CA,
# paste into the vault item's Notes; client certs are NOT used (token auth).
```

The token is a bearer credential with no separate Secret object — nothing to
delete on rotation; the old one simply expires.
