"""Allow a `kind: subscription` provider to back a managed sandbox.

WHY
    Upstream 0.19.0 rejects every provider kind except gateway / key / local for
    managed inference (`prepare()` → "Managed inference requires a gateway, API
    key, or connected Unity provider"), and `catalog()` calls `_wire()` — which
    needs a family table a subscription provider does not have — BEFORE it ever
    consults `model_allowlist`. So a Codex ChatGPT login can never be selected
    in the composer for a Kubernetes-backed sandbox.

    That rule assumes a managed sandbox has no way to hold a CLI login. Ours
    does: the runner mounts a persistent claim at `$CODEX_HOME` (see
    pvc-codex-home.yaml), so the sandbox authenticates with Codex's own OAuth
    and the server only has to publish a curated model list.

WHAT
    1. `prepare()` — accept `subscription` alongside gateway/key/local.
    2. `catalog()` — short-circuit a subscription provider to `_static_catalog`
       (the allowlist path) before `_wire()` can raise.

    Both edits assert their anchors, so an upstream refactor fails the build
    loudly instead of shipping an image that silently reverts to
    "Models unavailable".
"""

from __future__ import annotations

import pathlib
import sys

# The editable install exposes the package itself at /build/omnigent (that is
# where harness_plugins.py lives), not the repo root — so the module path
# repeats "server" only once. Probe both spellings rather than assume one.
_CANDIDATES = (
    pathlib.Path("/build/omnigent/server/inference_catalog.py"),
    pathlib.Path("/build/omnigent/omnigent/server/inference_catalog.py"),
)
TARGET = next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])

PREPARE_OLD = '        if bound is not None and providers[bound.name].kind not in {"gateway", "key", "local"}:'
PREPARE_NEW = '        if bound is not None and providers[bound.name].kind not in {"gateway", "key", "local", "subscription"}:'

CATALOG_OLD = "            _wire(provider, harness)"
CATALOG_NEW = (
    "            # subscription providers carry no family table; the allowlist is the catalog\n"
    "            if provider.kind == \"subscription\":\n"
    "                return self._static_catalog(result, binding, provider)\n"
    "            _wire(provider, harness)"
)


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    original = text

    if PREPARE_NEW in text and CATALOG_NEW in text:
        print("already patched")
        return 0

    if PREPARE_OLD not in text:
        print(f"FATAL: prepare() anchor not found in {TARGET}")
        return 1
    text = text.replace(PREPARE_OLD, PREPARE_NEW, 1)

    if CATALOG_OLD not in text:
        print(f"FATAL: catalog() anchor not found in {TARGET}")
        return 1
    text = text.replace(CATALOG_OLD, CATALOG_NEW, 1)

    if text == original:
        print("FATAL: nothing changed")
        return 1

    TARGET.write_text(text, encoding="utf-8")
    print("patched: subscription providers allowed for managed sandboxes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
