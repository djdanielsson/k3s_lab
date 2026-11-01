"""Build-time source patch: opencode-native sessions never ask for permission.

Why a file and not a Dockerfile heredoc: Kaniko 1.23.2 hands `RUN python - <<'PY'`
an empty stdin, so Python exits 0 having done nothing and the build still goes
green over an unpatched image. Every patch in this directory is a real context
file for that reason.

What it changes — `omnigent/runner/native/orchestration.py`:

    config["permission"] = "ask"          ->   "allow" (env-overridable)

Upstream sets "ask" deliberately: opencode's enforcement is reactive (there is
no pre-tool hook), so forcing every tool call to prompt is what routes the call
through Omnigent's policy engine via the forwarder's permission gate. That is
also why a managed session cannot run unattended: every bash/edit/external
directory read becomes a TUI modal, and because each subagent runs as its own
opencode session, "Allow always" does not carry over — a nine-subagent review
stalls on dozens of prompts while nobody is looking at the terminal.

This cluster wants unattended sessions, so the default becomes "allow". The
trade-off, stated plainly: native opencode tool calls no longer round-trip
through the policy engine's reactive gate. The policy-bridge plugin still loads
and still fires its REQUEST / TOOL_RESULT hooks.

Set OMNIGENT_OPENCODE_PERMISSION=ask to get the upstream behaviour back without
rebuilding.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

ANCHOR = '        config["permission"] = "ask"\n'
PATCHED = (
    "        # Cluster patch: an unattended session must not block on TUI\n"
    "        # permission modals. Upstream forces \"ask\" so the reactive gate\n"
    "        # routes tool calls through the policy engine; see\n"
    "        # patches/opencode-no-ask.py for the trade-off.\n"
    '        config["permission"] = os.environ.get('
    '"OMNIGENT_OPENCODE_PERMISSION", "allow")\n'
)


def main() -> int:
    root = next(pathlib.Path("/opt/venv/lib").glob("python3.*/site-packages/omnigent"))
    target = root / "runner" / "native" / "orchestration.py"
    if not target.is_file():
        print(f"FAIL: {target} not found", file=sys.stderr)
        return 1

    source = target.read_text(encoding="utf-8")
    count = source.count(ANCHOR)
    if count != 1:
        print(
            f"FAIL: expected exactly one {ANCHOR.strip()!r} anchor, found {count}. "
            "Upstream moved the permission assignment; re-derive the patch.",
            file=sys.stderr,
        )
        return 1

    if PATCHED in source:
        print("already patched")
        return 0

    target.write_text(source.replace(ANCHOR, PATCHED), encoding="utf-8")

    # Drop bytecode so Python cannot load the pre-patch module.
    for cache in target.parent.glob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)

    patched = target.read_text(encoding="utf-8")
    if 'OMNIGENT_OPENCODE_PERMISSION' not in patched or ANCHOR in patched:
        print("FAIL: patch did not apply cleanly", file=sys.stderr)
        return 1

    print(f"patched {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
