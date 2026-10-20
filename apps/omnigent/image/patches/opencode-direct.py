"""Build-time source patch for the direct OpenCode Go lane (host image only).

Why this is a file and not a Dockerfile heredoc: Kaniko 1.23.2 does not support
Dockerfile heredocs. A `RUN python - <<'PY'` instruction is handed to the shell
with EMPTY stdin, so Python exits 0 having executed nothing and the build goes
green over an unpatched image. That is not theoretical — it is how the first
build of this patch "succeeded" with both edits missing.

Two upstream gaps, both established by reading this image's code:

  1. ``runner/transports/ws_tunnel/serve.py`` advertises the harness kinds the
     runner can spawn in its tunnel hello frame, and ``opencode-native`` is
     absent — so the server never offers the harness on a managed sandbox even
     though the CLI and the executor are installed. ``configured_harness_map()``
     in the same image already reports ``opencode-native: True`` (it is gated on
     the binary), so this row is the only missing piece.

  2. ``build_opencode_provider_config`` writes an ``@ai-sdk/openai-compatible``
     provider with baseURL/apiKey only. OpenCode Go rejects requests without a
     stable per-conversation ``x-opencode-session`` (400 MissingSessionID) and
     asks for a real client identity. LiteLLM papers over this today with a
     constant header; the Omnigent session id is a better key and gives Go
     prompt-cache affinity per conversation.

Both anchors are asserted, so a moved anchor fails the build loudly instead of
shipping an image that merely looks patched. Bytecode from the base image is
deleted for the two edited modules so Python cannot load a stale .pyc.
"""

from __future__ import annotations

import pathlib
import sys

HELLO_ANCHOR = '                    "pi",\n                ],\n'
HELLO_PATCHED = '                    "pi",\n                    "opencode-native",\n                ],\n'

PROVIDER_ANCHOR = (
    "        config = dict(build_opencode_provider_config(gateway))\n"
    '        config["model"] = model_override\n'
)
PROVIDER_PATCHED = (
    "        config = dict(build_opencode_provider_config(gateway))\n"
    "        # Cluster patch: OpenCode Go requires a stable per-conversation\n"
    "        # session id and a real client identity; the synthesized\n"
    "        # @ai-sdk/openai-compatible provider carries neither.\n"
    '        for _og_binding in (config.get("provider") or {}).values():\n'
    '            _og_options = _og_binding.setdefault("options", {})\n'
    '            _og_options.setdefault("headers", {}).update(\n'
    "                {\n"
    '                    "x-opencode-session": f"omnigent-{session_id}",\n'
    '                    "x-opencode-client": "omnigent",\n'
    "                }\n"
    "            )\n"
    '        config["model"] = model_override\n'
)


def main() -> int:
    root = next(pathlib.Path("/opt/venv/lib").glob("python3.*/site-packages/omnigent"))

    serve = root / "runner/transports/ws_tunnel/serve.py"
    text = serve.read_text()
    if '"opencode-native",' not in text:
        if text.count(HELLO_ANCHOR) != 1:
            print(f"FATAL: serve.py hello-frame anchor count {text.count(HELLO_ANCHOR)}")
            return 1
        serve.write_text(text.replace(HELLO_ANCHOR, HELLO_PATCHED))
    if '"opencode-native",' not in serve.read_text():
        print("FATAL: serve.py opencode-native row not present after patch")
        return 1

    orch = root / "runner/native/orchestration.py"
    text = orch.read_text()
    if "x-opencode-session" not in text:
        if text.count(PROVIDER_ANCHOR) != 1:
            print(f"FATAL: orchestration.py provider anchor count {text.count(PROVIDER_ANCHOR)}")
            return 1
        orch.write_text(text.replace(PROVIDER_ANCHOR, PROVIDER_PATCHED))
    if "x-opencode-session" not in orch.read_text():
        print("FATAL: orchestration.py Go headers not present after patch")
        return 1

    for sub, name in (
        ("runner/transports/ws_tunnel", "serve"),
        ("runner/native", "orchestration"),
    ):
        for cache in (root / sub).glob("__pycache__"):
            for pyc in cache.glob(f"{name}.*.pyc"):
                pyc.unlink(missing_ok=True)

    print("patched: opencode-native advertised; OpenCode Go session headers injected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
