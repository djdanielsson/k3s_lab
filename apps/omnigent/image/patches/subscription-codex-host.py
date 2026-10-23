"""Let a bound `kind: subscription` provider launch the native Codex terminal.

WHY
    `resolve_native_codex_launch` treats an explicitly bound provider as
    authoritative and asks `_codex_provider_launch` to turn it into CLI
    overrides. For a `subscription` entry that helper returns ``None`` by
    design ("defers to Codex's own stored login"), and the caller turns ``None``
    into a hard error:

        ValueError: Configured provider 'codex-sub' cannot route Codex.

    The function already knows what a subscription means — its spec-level branch
    returns a launch with `model_provider="openai"`, the session model, and
    `login_required = not _codex_login_usable()`. Only the *bound* branch was
    missing that case, so a Codex ChatGPT login could never back a managed
    sandbox whose harness binding names it.

WHAT
    In the bound branch, when `_codex_provider_launch` returns ``None`` and the
    provider is a subscription, emit the same own-login launch instead of
    raising. Endpoint kinds still fail loudly: they reach this point only when
    their credential or base_url is unusable.

VERIFY
    The script also compiles the patched file and asserts both markers, so a
    green Kaniko build means the edit is really in the image.
"""

from __future__ import annotations

import pathlib
import py_compile
import sys

TARGET = pathlib.Path(
    "/opt/venv/lib/python3.12/site-packages/omnigent/harnesses/codex_native/app_server.py"
)

OLD = '''    if bound is not None:
        selected = resolve_bound_model(explicit, "codex-native", model)
        bound_launch = _codex_provider_launch(bound, selected)
        if bound_launch is None:
            raise ValueError(
                f"Configured provider {bound.name!r} cannot route Codex. "
                "Check its OpenAI endpoint and credential reference."
            )
        return bound_launch
'''

NEW = '''    if bound is not None:
        selected = resolve_bound_model(explicit, "codex-native", model)
        bound_launch = _codex_provider_launch(bound, selected)
        if bound_launch is None:
            # A bound `kind: subscription` provider has no endpoint to route
            # through: it means "use Codex's own stored login", exactly like the
            # spec-level subscription branch below. Our managed sandboxes hold
            # that login in a persistent CODEX_HOME, so this is a supported
            # route, not a misconfiguration.
            if bound.kind == SUBSCRIPTION_KIND:
                bound_codex_logged_in = _codex_login_usable()
                return NativeCodexLaunch(
                    config_overrides=['model_provider="openai"'],
                    model=selected,
                    profile=None,
                    summary=(
                        f"Codex CLI login (bound provider {bound.name!r}; "
                        + (
                            "Codex is logged in"
                            if bound_codex_logged_in
                            else "Codex is not logged in"
                        )
                        + ")"
                    ),
                    login_required=not bound_codex_logged_in,
                )
            raise ValueError(
                f"Configured provider {bound.name!r} cannot route Codex. "
                "Check its OpenAI endpoint and credential reference."
            )
        return bound_launch
'''

MARKER = "bound provider {bound.name!r}"


def main() -> int:
    if not TARGET.is_file():
        print(f"FATAL: {TARGET} not found — host image layout changed")
        return 1
    text = TARGET.read_text(encoding="utf-8")

    if MARKER in text:
        print("already patched")
    else:
        if OLD not in text:
            print("FATAL: bound-provider anchor not found; upstream changed")
            return 1
        text = text.replace(OLD, NEW, 1)
        TARGET.write_text(text, encoding="utf-8")
        print("patched: bound subscription providers launch Codex's own login")

    # Never leave stale bytecode that could shadow the edited source.
    cache = TARGET.parent / "__pycache__"
    if cache.is_dir():
        for pyc in cache.glob("app_server*.pyc"):
            pyc.unlink()

    py_compile.compile(str(TARGET), doraise=True)
    patched = TARGET.read_text(encoding="utf-8")
    for needle in ('if bound.kind == SUBSCRIPTION_KIND:', MARKER):
        if needle not in patched:
            print(f"FATAL: verification failed, missing {needle!r}")
            return 1
    print("ok: subscription launch path present and compiles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
