# Secrets — Vaultwarden

All app secrets live in **Vaultwarden** and are synced into the cluster by
**External Secrets Operator (ESO)** via the bitwarden-cli bridge. Item names
are prefixed **`k3s/`**.

## 1. Vaultwarden auth credential — the one thing that is NOT a vault item
Create this yourself; it's what lets ESO's bridge talk to Vaultwarden:

1. Open your Vaultwarden vault → **Settings → Security → Keys → New API Key**.
2. Copy the **Client ID** and **Client Secret**.
3. These (with `BW_HOST`) are the auth used by the `bitwarden-cli`/ESO bridge —
   store them where the bridge expects them.

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
