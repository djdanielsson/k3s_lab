#!/usr/bin/env python3
"""Unseal the lab Vault using the unseal keys stored in Vaultwarden.

Vault boots sealed and stays sealed until an operator supplies the threshold
number of unseal shares. The shares live in the Vaultwarden item
`k3s/vault-unseal` (see the note in that item for the lab-trade discussion);
this script reads them from the item, drives `POST /v1/sys/unseal` until the
seal lifts, and prints only status transitions.

Run it:
  - after any Vault pod restart (node reboot, rollout, chart upgrade), and
  - before using the Transit cipher, since Omnigent's credential store is
    disabled while Vault is sealed.

Idempotent: an already-unsealed Vault is reported and exits 0.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BRIDGE = "http://bitwarden-cli.external-secrets.svc:8087"
VAULT = "http://vault.vault.svc.cluster.local:8200"
ITEM = "k3s/vault-unseal"
THRESHOLD_HINT = 3


def bw_get(path: str) -> dict:
    with urllib.request.urlopen(BRIDGE + path, timeout=30) as resp:
        return json.loads(resp.read().decode())


def vault(path: str, payload: dict | None = None, token: str | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(VAULT + path, data=data, method="POST" if data else "GET")
    if token:
        r.add_header("X-Vault-Token", token)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def main() -> int:
    status, st = vault("/v1/sys/seal-status")
    if not st.get("initialized"):
        print("Vault is NOT initialised — run init first; unsealing cannot help")
        return 1
    if not st.get("sealed"):
        print("Vault already unsealed (version", st.get("version"), ")")
        return 0
    print(f"sealed: true | progress {st.get('progress')}/{st.get('t')}")

    import urllib.parse as _up
    listing = bw_get(f"/list/object/items?search={_up.quote(ITEM)}")
    items = (listing.get("data") or {}).get("data") or []
    if not items:
        print(f"no vault item {ITEM} — cannot unseal")
        return 1
    fields = {f["name"]: f["value"] for f in (items[0].get("fields") or [])}
    shares = [fields[k] for k in sorted(fields) if k.startswith("UNSEAL_KEY_")]
    threshold = int(fields.get("UNSEAL_THRESHOLD") or THRESHOLD_HINT)
    print(f"read {len(shares)} share(s) from the vault item; threshold {threshold}")

    for i, share in enumerate(shares[:threshold]):
        code, resp = vault("/v1/sys/unseal", {"key": share})
        print(f"  share {i+1}: HTTP {code} sealed={resp.get('sealed')} progress={resp.get('progress')}")
        if resp.get("sealed") is False:
            break

    code, final = vault("/v1/sys/seal-status")
    print("final seal-status: sealed =", final.get("sealed"))
    return 0 if final.get("sealed") is False else 1


if __name__ == "__main__":
    raise SystemExit(main())
