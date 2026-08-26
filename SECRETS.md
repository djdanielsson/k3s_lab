# Secrets — inventory & how to configure

Every secret is stored as a **SealedSecret** (ciphertext in this repo). The
in-cluster **sealed-secrets** controller decrypts each into a normal k8s
`Secret`. To *create or update* any of them you **re-seal** the plaintext into
the `sealed-secret.yaml` and push — ArgoCD applies it and the controller updates
the Secret.

> 🔑 Private key backup (needed to **decrypt** on a cluster rebuild):
> `/opt/data/sealed-secrets-backup/sealed-secrets-key.yaml.key` — keep it safe/off-box.

## Tooling
```bash
export PATH="$HOME/.local/bin:$PATH"     # kubeseal is installed there
# (re)grab the controller's public cert to seal with:
kubectl -n kube-system get secret -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > /tmp/ss-cert.pem
```

## General re-seal command
```bash
kubeseal --cert /tmp/ss-cert.pem --format yaml \
  < /tmp/plain-secret.yaml > <repo>/apps/<app>/sealed-secret.yaml
cd /opt/data/k3s_lab && git add -A && git commit -m "secrets" && git push
```

---

## 1. `bitwarden-cli` — Vaultwarden API creds (ESO)
`external-secrets` ns · file `apps/eso-bitwarden/sealed-secret.yaml`

| Key | Input / where to get it |
|-----|--------------------------|
| `BW_HOST` | `https://truenas-scale` (your Vaultwarden) |
| `BW_CLIENTID` | Vaultwarden → Settings → Security → Keys → **New API Key** → Client ID |
| `BW_CLIENTSECRET` | Vaultwarden → same → Client Secret |
| `BW_PASSWORD` | only set if your Vaultwarden/CLI setup requires it |

After sealing: the `bitwarden-cli` sidecar authenticates and ESO's webhook
stores (`bitwarden-login`/`-fields`/-`notes`) read everything else from Vaultwarden.

---

## Vaultwarden items — what to create, and the object/inputs

ESO reads an item by **searching for its name** (`remoteRef.key`), then extracts
a value from one of three places on that item (choose per secret):

| ESO store             | value comes from the item's…                  | `externalSecret` property |
|-----------------------|------------------------------------------------|---------------------------|
| `bitwarden-login`     | **login** object → `username` or `password`   | `username` / `password`    |
| `bitwarden-fields`    | a **custom field** whose *name* = the property | the field name             |
| `bitwarden-notes`     | the item's **Notes** (whole text = the value)  | (none — one value)         |

### Rule of thumb
- **A single secret value** → a **Secure Note** item, put the value in **Notes**,
  read via `bitwarden-notes`.
- **A set of values** → an item with **custom Fields** (name = key), read each
  via `bitwarden-fields`.
- **A user/pass pair** → use a `login` item, read via `bitwarden-login`.

### Example — PantryWise DB password
Create a Vaultwarden item named **`pantrywise/db`** (a login or a custom field):
- custom field name `password` → value = postgres password

ExternalSecret (in the app's ns):
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata: { name: pantrywise-db, namespace: pantrywise }
spec:
  secretStoreRef: { name: bitwarden-fields, kind: ClusterSecretStore }
  target: { name: pantrywise-secrets }
  data:
    - remoteRef: { key: pantrywise/db, property: password }
      secretKey: postgres-password
```

### Suggested items
| Item name (seek = `remoteRef.key`) | Object        | Field(s)                    | Read via |
|------------------------------------|---------------|-----------------------------|----------|
| `pantrywise/jwt`                   | Secure Note / custom | field `jwt`           | notes / fields |
| `pantrywise/db`                    | custom fields  | `password`, `user`, `url`   | fields    |
| `github/tokens`                    | custom fields  | one field per token         | fields    |
| `radar/auth`                       | custom fields  | `oidcSecret`, `clientId`…   | fields    |
| `registry/htpasswd`                | Secure Note    | Notes = the htpasswd string | notes     |

> The item **name must be uniquely searchable** — ESO's sidecar searches
> `?search=<key>` and takes data[0], so use unique names (e.g. `pantrywise/db`),
> not just `password`.

## 2. `tailscale-oauth` — Tailscale operator creds
`tailscale` ns · file `apps/tailscale-operator/sealed-secret.yaml`

| Key | Input / where to get it |
|-----|--------------------------|
| `client_id` | Admin Console → Settings → Keys → **OAuth clients** (scope: Read + Write) → Client ID |
| `client_secret` | Admin Console → same → Client Secret |

## 3. `pantrywise-secrets` — PantryWise
`pantrywise` ns · file `apps/pantrywise/sealed-secret.yaml`

| Key | Input |
|-----|-------|
| `jwt-secret` | JWT signing secret (any strong random string; rotate and apps re-issue tokens) |
| `postgres-user` | `postgres` |
| `postgres-password` | postgres password (`postgres` by default) |
| `postgres-db` | `pantrywise` |
| `database-url` | `postgresql://<user>:<pass>@postgres:5432/<db>?schema=public` |

## 4. `forgejo-secrets` — Forgejo DB
`forgejo` ns · file `apps/forgejo/sealed-secret.yaml`

| Key | Input |
|-----|-------|
| `db-user` | `forgejo` |
| `db-password` | postgres password (a random one was generated/chosen) |
| `db-name` | `forgejo` |

---

## Default creds still to harden (not sealed, built into images)
- **RustFS console**: `rustfsadmin / rustfsadmin` (set via env once exposed)
- **Radar**: `auth mode: none` — wire Authentik SSO/basic-auth **before** exposing externally
- **dnsmasq web/none** (DNS only)
- **netalertx / netdata**: no auth on their UIs (LAN/tailnet scope)
