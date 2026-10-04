#!/usr/bin/env python3
"""Verify the lab Vault's Transit key is DERIVED and binds a per-row context.

The contract Omnigent's credential store depends on: each stored secret is
encrypted with the row's identity passed as Transit's per-operation `context`,
and ONLY a key created with `derived=true` honours it. A non-derived key ignores
the context, so every row would share one key — encryption still "works" and the
per-user binding is silently gone. So this asserts `derived` is true and then
proves it by round-tripping: the same ciphertext must decrypt under its own
context and be REJECTED under a different one.

Uses the vault CLI inside the pod for reads (the CLI renders Vault's JSON with
single quotes, so parse with ast.literal_eval) and the HTTP API for
encrypt/decrypt (the CLI has no context flag for those).

Prints booleans and shapes only — never the root token or any plaintext.
"""
from __future__ import annotations

import ast
import base64
import json
import os
import sys

import kubernetes
from kubernetes import stream

NS, POD, KEY = "vault", "vault-0", "omnigent-credentials"
CHECKPOINT = os.environ.get("VAULT_INIT_JSON", os.path.expanduser("~/vault-init.json"))


def vexec(script: str, timeout: int = 90) -> str:
    kubernetes.config.load_incluster_config()
    v1 = kubernetes.client.CoreV1Api()
    return stream.stream(
        v1.connect_get_namespaced_pod_exec, POD, NS,
        command=["sh", "-c", script], stderr=True, stdin=False,
        stdout=True, tty=False, _request_timeout=timeout,
    )


def main() -> int:
    token = ast.literal_eval(open(CHECKPOINT).read())["root_token"]
    pre = "VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN='" + token + "' "

    meta = ast.literal_eval(vexec(pre + "vault read -format=json transit/keys/" + KEY))["data"]
    print("transit key:", KEY)
    print("  type:", meta.get("type"), "| kdf:", meta.get("kdf"), "| derived:", meta.get("derived"),
          "| latest_version:", meta.get("latest_version"))
    if meta.get("derived") is not True:
        print("FAIL: not derived — per-row context binding would be ignored")
        return 1

    def ctx_b64(d: dict) -> str:
        # Sorted-key JSON, matching the crate's unambiguous serialization.
        return base64.b64encode(
            json.dumps(d, sort_keys=True, separators=(",", ":")).encode()
        ).decode()

    c1 = ctx_b64({"account_id": "acct-1", "provider": "github", "user_id": "u1", "workspace_id": "0"})
    c2 = ctx_b64({"account_id": "acct-2", "provider": "github", "user_id": "u1", "workspace_id": "0"})
    plain = base64.b64encode(b"round-trip").decode()

    def api(path: str, payload: dict) -> str:
        body = json.dumps(payload)
        return vexec(pre + "wget -q -O- --header='Content-Type: application/json' "
                     "--post-data='" + body + "' http://127.0.0.1:8200" + path)

    enc_raw = api(f"/v1/transit/encrypt/{KEY}", {"plaintext": plain, "context": c1})
    enc = json.loads(enc_raw)
    ct = enc["data"]["ciphertext"]
    print("  encrypt with context 1: ok | ciphertext len:", len(ct))

    dec = json.loads(api(f"/v1/transit/decrypt/{KEY}", {"ciphertext": ct, "context": c1}))
    same = dec["data"]["plaintext"] == plain
    print("  decrypt with SAME context:", same)

    other = api(f"/v1/transit/decrypt/{KEY}", {"ciphertext": ct, "context": c2})
    rejected = "message authentication failed" in other or "error" in other.lower() and "plaintext" not in other
    print("  decrypt with DIFFERENT context rejected:", rejected, "|", other.strip()[:90])

    ok = same and rejected
    print("\nVERDICT:", "derived key + per-row context binding VERIFIED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
