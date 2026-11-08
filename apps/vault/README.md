# Vault recovery helpers — reproducible from git, not just from a laptop.

These live here because the unseal procedure is operational knowledge: if Vault
is sealed and the only copy of the script is on someone's machine, the recovery
path is lost with it. Auto-unseal now runs as the `vault-unseal` CronJob in
`apps/vault/`, so these are for the cases the CronJob cannot cover — a fresh
Vault, a rotation, or debugging a failed unseal.

## What is where

- **`k3s/vault-unseal`** (Vaultwarden, read through the ESO bridge) — the five
  unseal shards plus `UNSEAL_THRESHOLD`. This is the single source of truth for
  unsealing, and `renew-token-cronjob.yaml` / `unseal-cronjob.yaml` both read
  their material through the bridge rather than embedding it.
- **`k3s/vault-root`** — the root token from `vault operator init`, kept here for
  one purpose: minting or rotating the least-privilege token below. It is
  deliberately reachable from nothing (no ExternalSecret references it), but it
  IS in the vault, which reverses this app's earlier stance. The reason is
  mechanical, not a change of taste: Vault 2.0.4 refuses
  `sys/generate-root/attempt` on an **unsealed** Vault without a sudo token, so
  the unseal shards alone can no longer recover root. Losing the root token
  therefore means wiping and re-initialising Vault — which invalidates every
  stored integration secret. If you would rather keep root off Vaultwarden, move
  it somewhere offline and delete this item.
- **`k3s/vault-omnigent-cipher`** — the least-privilege Transit token Omnigent's
  credential store consumes (`VAULT_TOKEN`, plus `VAULT_ADDR` and `VAULT_KEY`).
  Policy `omnigent-transit` grants encrypt/decrypt/read on the single key
  `omnigent-credentials` and nothing else. It is a **periodic** token (90-day
  period), renewed by `renew-token-cronjob.yaml` once its remaining TTL drops
  below 60 days, so it does not lapse.
- **`init.json`** — the one-time `vault operator init` output (root token). It is
  written mode 600 wherever you keep it and must never be printed or committed.
  Losing it means losing the root token; the shards in Vaultwarden can still
  unseal, and a new root token can be minted with them.

## Recovery runbook

Unseal after a restart is automatic (the CronJob polls every minute). If you
need to do it by hand:

```
python3 unseal.py            # reads shards from the vault item, unseals, prints status only
```

It is idempotent — an unsealed Vault is reported and exits 0 — so it is safe to
run when unsure.

Verify the cipher contract (a derived key that honours per-row context):

```
python3 verify-transit.py
```

Expected: `derived: True`, same-context decrypt succeeds, and a **different**
context is rejected with `message authentication failed`. That rejection is the
proof the per-user binding works; a non-derived key would decrypt happily.

Rotate the token Omnigent uses:

```
python3 mint-omnigent-token.py --rotate
```

## Things that will bite

- **The Vault pod must be reachable at `vault.vault.svc.cluster.local:8200`**
  over plain HTTP. TLS is deliberately off (`global.tlsDisable` + the listener's
  `tls_disable = 1`); there is no Ingress and the Service is ClusterIP-only, so
  the exposure is the cluster network.
- **`seal-status` answers on a sealed Vault; `/v1/sys/health` returns 501.**
  Probe the former. `/v1/sys/seal` is a `PUT`, not a POST (a POST is a 405).
- **The CLI prints its `-format=json` output with single quotes**, so plain
  `json.loads` fails on valid output — parse with `ast.literal_eval`. This cost
  three debugging rounds; do not "fix" it by switching to a different parser.
- **Vaultwarden item names must not be prefixes of one another.** ESO searches
  by substring and indexes `data.data[0]`, so an item named `k3s/omnigent-x`
  makes a search for `k3s/omnigent` return multiple rows and can resolve a field
  from the wrong item. That is why these are `k3s/vault-unseal` /
  `k3s/vault-omnigent-cipher` and not `k3s/omnigent-*`.
