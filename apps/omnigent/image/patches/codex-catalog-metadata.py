"""Enrich the curated (allowlist) catalog with display names and effort ladders.

WHY
    A `kind: subscription` provider has no server-side discovery, so the server
    answers the model picker from `model_allowlist` via `_static_catalog`. Those
    rows carry only `id`/`model`/`displayName`(id)/`isDefault`, which the
    composer renders as bare slugs with no reasoning-effort choices — even
    though Codex itself advertises per-model effort levels and the session API
    accepts `reasoning_effort`.

WHAT
    Merge an operator-supplied JSON catalog (ConfigMap `omnigent-codex-catalog`,
    mounted at /etc/omnigent/codex-models.json from `codex debug models`) into
    those rows: real display names plus `supportedReasoningEfforts`. Consumers
    that already understand discovered catalogs read the same field, so nothing
    downstream needs to learn a new shape. A missing file degrades to the old
    behaviour instead of failing.
"""

from __future__ import annotations

import pathlib
import py_compile
import sys

_CANDIDATES = (
    pathlib.Path("/build/omnigent/server/inference_catalog.py"),
    pathlib.Path("/build/omnigent/omnigent/server/inference_catalog.py"),
)
TARGET = next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])

OLD = '''        source = {"kind": provider.kind, "label": result["provider_label"], "name": provider.name}
        result.update(
            status="ready",
            default_model=default,
            models=[
                {
                    "id": model,
                    "model": model,
                    "displayName": model,
                    "isDefault": model == default,
                    "source": source,
                }
                for model in ids
            ],
        )
        return result
'''

NEW = '''        source = {"kind": provider.kind, "label": result["provider_label"], "name": provider.name}
        # Operator catalog (ConfigMap omnigent-codex-catalog): real display names
        # and the per-model reasoning ladders Codex advertises, so the composer
        # can show efforts for a provider that has no server-side discovery.
        import json as _json
        import os as _os

        meta: dict[str, dict[str, Any]] = {}
        try:
            with open(
                _os.environ.get("OMNIGENT_CODEX_CATALOG", "/etc/omnigent/codex-models.json"),
                encoding="utf-8",
            ) as _fh:
                for _row in _json.load(_fh):
                    if isinstance(_row, dict) and isinstance(_row.get("id"), str):
                        meta[_row["id"]] = _row
        except (OSError, ValueError, TypeError):
            meta = {}
        rows: list[dict[str, Any]] = []
        for model in ids:
            info = meta.get(model) or {}
            row: dict[str, Any] = {
                "id": model,
                "model": model,
                "displayName": info.get("displayName") or model,
                "isDefault": model == default,
                "source": source,
            }
            efforts = info.get("efforts")
            if isinstance(efforts, list) and efforts:
                row["supportedReasoningEfforts"] = [
                    {"reasoningEffort": effort}
                    for effort in efforts
                    if isinstance(effort, str)
                ]
            rows.append(row)
        result.update(status="ready", default_model=default, models=rows)
        return result
'''

MARKER = "OMNIGENT_CODEX_CATALOG"


def main() -> int:
    if not TARGET.is_file():
        print(f"FATAL: {TARGET} not found — server image layout changed")
        return 1
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        print("already patched")
    else:
        if OLD not in text:
            print("FATAL: _static_catalog anchor not found; upstream changed")
            return 1
        TARGET.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
        print("patched: static catalog enriched from the operator catalog")

    cache = TARGET.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob("inference_catalog*.pyc"):
            pyc.unlink()

    py_compile.compile(str(TARGET), doraise=True)
    patched = TARGET.read_text(encoding="utf-8")
    for needle in (MARKER, "supportedReasoningEfforts"):
        if needle not in patched:
            print(f"FATAL: verification failed, missing {needle!r}")
            return 1
    print("ok: catalog enrichment present and compiles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
