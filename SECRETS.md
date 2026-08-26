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
