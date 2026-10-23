"""Build-time assertions for the custom Omnigent SERVER image.

Runs inside the image after the harness picker patch and the `hvac` install, and
is the only proof that matters — a green Kaniko build is not evidence.

Why a file: Kaniko 1.23.2 does not support Dockerfile heredocs. `RUN python - <<'PY'`
receives an EMPTY stdin, so the interpreter exits 0 having run nothing and the
build stays green over an unverified image. Both checks below used to live in
heredocs and had therefore never executed.

Checks:
  1. `harness_catalog()` — the function the API calls — lists `opencode-native`.
     Patching `harness_labels` without this row does nothing: the catalog is
     built from that dict.
  2. The Vault cipher is wired: `hvac` is importable and
     `build_vault_secret_cipher()` returns a cipher with a live client. The
     stock image fails this LAZILY, on the first credential write (the GitHub
     OAuth callback), which reads as "the user never connected".
"""

from __future__ import annotations

import importlib.metadata as md
import os
import sys

os.environ.setdefault("OMNIGENT_CREDENTIAL_VAULT_KEY", "buildcheck")

# 1. picker catalog
import omnigent.harness_plugins as hp  # noqa: E402

rows = sorted({r["id"] for r in hp.harness_catalog()})
if "opencode-native" not in rows:
    print(f"FATAL: opencode-native missing from harness_catalog: {rows}")
    sys.exit(1)
print("ok: harness_catalog contains opencode-native")

# 2. vault credential cipher
from omnigent.stores.credential_store.vault_cipher import (  # noqa: E402
    build_vault_secret_cipher,
)

cipher = build_vault_secret_cipher()
if cipher is None:
    print("FATAL: OMNIGENT_CREDENTIAL_VAULT_KEY did not select the Vault cipher")
    sys.exit(1)
try:
    cipher._vault  # noqa: SLF001 — raises ImportError when hvac is absent
except ImportError as exc:
    print(f"FATAL: hvac missing, Vault cipher is inert: {exc}")
    sys.exit(1)
print(f"ok: hvac {md.version('hvac')} installed, Vault cipher wired")

# 3. subscription providers may back a managed sandbox. Both halves are needed:
#    `prepare()` must admit the kind, and `catalog()` must reach the allowlist
#    path instead of `_wire()`, which raises for a family-less provider.
import inspect  # noqa: E402

import omnigent.server.inference_catalog as ic  # noqa: E402

ic_src = inspect.getsource(ic)
if '{"gateway", "key", "local", "subscription"}' not in ic_src:
    print("FATAL: prepare() still rejects subscription providers for managed inference")
    sys.exit(1)
if 'if provider.kind == "subscription":' not in ic_src:
    print("FATAL: catalog() has no subscription short-circuit; _wire() would raise")
    sys.exit(1)
print("ok: subscription providers allowed for managed sandboxes")
