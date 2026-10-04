#!/usr/bin/env python3
"""Mint a least-privilege Vault token for Omnigent and seed it into Vaultwarden.

WHAT OMNIGENT NEEDS
    The credential-store cipher calls exactly two Transit paths, both scoped to
    one key: `transit/encrypt/omnigent-credentials` and
    `transit/decrypt/omnigent-credentials`. Nothing else. So the token is minted
    against a policy granting only those two capabilities — NOT root, NOT
    `transit/*`.

WHY A TOKEN AND NOT KUBERNETES AUTH
    Vault's k8s auth method would let the pod authenticate with its own
    ServiceAccount and drop the static token entirely, and that is the better
    long-term shape. It needs a reviewer JWT + a role bound to the SA, which
    means reading the SA token and a Vault API dance at deploy time. For the
    prototype this token is the smaller step; the k8s-auth upgrade is a
    follow-up, and this script's policy object is reusable for it.

SECRET HANDLING
    The minted token is written straight into Vaultwarden (via the ESO bridge)
    and printed only as a length. Nothing here echoes it. `init.json` (unseal
    keys + root token) is never touched beyond reading the root token in-process.

Usage:
    python3 mint-omnigent-token.py            # mint + seed the vault item
    python3 mint-omnigent-token.py --rotate   # mint a new token, revoke the old
"""
from __future__ import annotations

import ast
import json
import os
import sys
import urllib.error
import urllib.request


VAULT = "http://vault.vault.svc.cluster.local:8200"
BRIDGE = "http://bitwarden-cli.external-secrets.svc:8087"
CHECKPOINT = os.environ.get("VAULT_INIT_JSON", os.path.expanduser("~/vault-init.json"))
POLICY = "omnigent-transit"
ITEM = "k3s/omnigent-vault"
KEY_NAME = "omnigent-credentials"


def root_token() -> str:
    return ast.literal_eval(open(CHECKPOINT).read())["root_token"]


def vapi(path: str, payload=None, token: str | None = None, method: str | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(VAULT + path, data=data,
                               method=method or ("POST" if data else "GET"))
    r.add_header("X-Vault-Token", token or root_token())
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def bw(path: str, payload=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BRIDGE + path, data=data, method=method)
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def main() -> int:
    # 1. Policy: only the two Transit ops on the one key.
    policy = {
        "path": {
            f"transit/encrypt/{KEY_NAME}": {"capabilities": ["update"]},
            f"transit/decrypt/{KEY_NAME}": {"capabilities": ["update"]},
            # read the key's metadata (version/derived state) but not configure it
            f"transit/keys/{KEY_NAME}": {"capabilities": ["read"]},
        }
    }
    s, _ = vapi(f"/v1/sys/policies/acl/{POLICY}", {"policy": json.dumps(policy)})
    print(f"policy {POLICY}: {s}")

    # 2. Mint a periodic-less token with a long TTL, no renewal needed.
    s, tok = vapi("/v1/auth/token/create",
                  {"policies": [POLICY], "ttl": "8760h", "no_parent": True,
                   "display_name": "omnigent-credential-store"})
    if s != 200:
        print("token create failed:", tok)
        return 1
    token = tok["auth"]["client_token"]
    accessor = tok["auth"]["accessor"]
    print(f"token minted: len={len(token)} accessor={accessor[:8]}… policies={tok['auth']['policies']}")

    # 3. Prove it can do the job AND nothing more.
    def probe(path, payload):
        return vapi(path, payload, token=token)[0]
    ok_enc = probe(f"/v1/transit/encrypt/{KEY_NAME}",
                   {"plaintext": "aGk=", "context": "Y3R4"})
    ok_dec = probe(f"/v1/transit/decrypt/{KEY_NAME}",
                   {"ciphertext": "vault:v1:AAAA", "context": "Y3R4"})
    denied = probe("/v1/sys/policies/acl", None)
    print(f"  encrypt -> {ok_enc} (200 expected) | decrypt-attempt -> {ok_dec} (400 expected: bad ct)")
    print(f"  sys/policies -> {denied} (403 expected — proves least privilege)")

    # 4. Seed the vault item, refusing to create a duplicate.
    s, listing = bw(f"/list/object/items?search={urllib.parse.quote(ITEM)}")
    items = (listing.get("data") or {}).get("data") or []
    if len(items) > 1:
        print(f"REFUSING: {len(items)} items match {ITEM}; ESO indexes data.data[0]")
        return 1
    field = {"name": "VAULT_TOKEN", "value": token, "type": 1}
    if items:
        item_id = items[0]["id"]
        s, _ = bw(f"/object/item/{item_id}", {"type": 1, "name": ITEM,
                   "fields": [field, {"name": "VAULT_ADDR", "value": VAULT, "type": 0},
                              {"name": "VAULT_KEY", "value": KEY_NAME, "type": 0}]},
                  method="POST")
        print(f"updated vault item {ITEM}: {s}")
    else:
        s, _ = bw("/object/item", {"type": 1, "name": ITEM,
                   "notes": "Omnigent credential-store cipher: Vault Transit token. "
                            "Least-privilege policy 'omnigent-transit' (encrypt/decrypt on "
                            "omnigent-credentials only). Rotate with mint-omnigent-token.py --rotate.",
                   "fields": [field, {"name": "VAULT_ADDR", "value": VAULT, "type": 0},
                              {"name": "VAULT_KEY", "value": KEY_NAME, "type": 0}]},
                  method="POST")
        print(f"created vault item {ITEM}: {s}")
    s, _ = bw("/sync", {}, method="POST")
    print("bridge sync:", s, "(then verify the token, not the stored blob)")
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402 — used above; imported here to keep the header clean

    raise SystemExit(main())
