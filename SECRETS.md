# Secrets — Vaultwarden

All app secrets live in **Vaultwarden** and are synced into the cluster by
**External Secrets Operator (ESO)** via the bitwarden-cli bridge. Item names
are prefixed **`k3s/`**.

## 1. Provider credentials — create these yourself (NOT vault items)

These are the auth the bridge/operator use; they're the only things in
`SECRETS.md` that don't come from a Vaultwarden item.

### Vaultwarden API (ESO/bitwarden-cli)
1. Vaultwarden vault → **Settings → Security → Keys → New API Key**.
2. Copy the **Client ID** + **Client Secret** (`BW_HOST = https://truenas-scale`).

### Tailscale OAuth (Tailscale operator)
1. Admin Console → **Settings → Keys → Generate… → OAuth clients**.
2. Scope **Read + Write** → copy the **Client ID** + **Client Secret**. Ensure **MagicDNS** is on.

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
