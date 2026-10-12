"""usage-notice — add an OpenCode Go plan-usage line to the new-session notice.

The "New session started" / auto-reset notice is built by the gateway in
``gateway/run_turn.py::GatewayTurnMixin._format_session_info()`` and is exactly
three lines (Model / Provider / Context). Hermes exposes no config key, hook
return value, or language-pack slot that appends to it, so this gateway hook
wraps that method once at startup and appends the Go plan's usage windows:

    ◆ Model: `deepseek-v4.1-flash`
    ◆ Provider: opencode-go
    ◆ Context: 1.0M tokens (detected)
    ◆ OpenCode Go: 5h 0% (resets 2h05m) · week 0% · month 0%

Source: ``GET https://opencode.ai/zen/go/v1/usage`` with the same API key the
agent uses (``hermes_cli.auth.resolve_api_key_provider_credentials``). It returns
the three plan meters the workspace dashboard shows — rolling (5h), weekly and
monthly — each as a whole, floored percent of the window's allowance plus the
reset timestamp; the allowance is metered server-side in spend, not tokens, so
"0%" means under 1% consumed, not "no data".

Two things this endpoint is picky about, both handled below: it is behind
Cloudflare, which answers the default Python-urllib User-Agent with
"403 error code: 1010" (a curl/browser UA gets 200 in ~150 ms), and it must never
be polled hard — the meters are a three-table join server-side, so results are
cached in-process for a minute and only fetched when a notice is rendered.

Fail-safe by design: any error (no key, HTTP error, entitlement missing, renamed
method) leaves the notice exactly as upstream renders it — nothing here may break
the notice.

Deployed by gitops (k3s_lab apps/hermes): the `hermes-hooks` ConfigMap is copied
into $HERMES_HOME/hooks/usage-notice/ by the fix-perms init container on every
boot, because Hermes only reads hooks/ once, at gateway startup.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("hooks.usage_notice")

_PATCH_FLAG = "_usage_notice_patched"
_BULLET = "\u25c6"  # ◆ — the marker the built-in lines use
_USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
_PROVIDER = "opencode-go"
_TIMEOUT_S = 6.0
_CACHE_TTL_S = 60.0
# Cloudflare fronts opencode.ai and returns "403 error code: 1010" for the
# default Python-urllib UA; a curl-style UA is accepted.
_USER_AGENT = "curl/8.5.0"

_cache_lock = threading.Lock()
_cache_at = 0.0
_cache_line = ""


def _api_key() -> str:
    """The Go plan API key, resolved the same way the agent resolves it."""
    try:
        from hermes_cli.auth import resolve_api_key_provider_credentials

        creds = resolve_api_key_provider_credentials(_PROVIDER) or {}
        key = str(creds.get("api_key") or "").strip()
        if key:
            return key
    except Exception:
        logger.debug("usage-notice: credential resolution failed", exc_info=True)
    for name in ("OPENCODE_GO_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENCODE_API_KEY"):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _human_delta(seconds: float) -> str:
    """Reset countdown: ``42m`` / ``2h05m`` / ``6d21h``."""
    total = max(0, int(seconds))
    minutes, _ = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def _reset_in(window: dict) -> str:
    raw = window.get("resetsAt")
    if not isinstance(raw, str) or not raw:
        return ""
    try:
        resets_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return _human_delta((resets_at - datetime.now(timezone.utc)).total_seconds())


def _fetch_windows() -> dict:
    key = _api_key()
    if not key:
        return {}
    request = urllib.request.Request(_USAGE_URL)
    request.add_header("Authorization", f"Bearer {key}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", _USER_AGENT)
    with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    usage = payload.get("usage")
    return usage if isinstance(usage, dict) else {}


def _plan_line() -> str:
    """``◆ OpenCode Go: 5h 0% (resets 2h05m) · week 0% · month 0%`` or ""."""
    global _cache_at, _cache_line
    with _cache_lock:
        now = time.monotonic()
        if now - _cache_at < _CACHE_TTL_S:
            return _cache_line

    line = ""
    try:
        windows = _fetch_windows()
        parts = []
        for key, label in (("rolling", "5h"), ("weekly", "week"), ("monthly", "month")):
            window = windows.get(key)
            if not isinstance(window, dict) or window.get("percent") is None:
                continue
            segment = f"{label} {int(window['percent'])}%"
            if key == "rolling":
                reset = _reset_in(window)
                if reset:
                    segment += f" (resets {reset})"
            if window.get("status") not in (None, "ok"):
                segment += " — rate limited"
            parts.append(segment)
        if parts:
            line = f"{_BULLET} OpenCode Go: " + " · ".join(parts)
    except urllib.error.HTTPError as exc:
        # 401/403 mean "no Go subscription for this key" as much as "bad key".
        logger.debug("usage-notice: usage endpoint returned HTTP %s", exc.code)
    except Exception:
        logger.debug("usage-notice: plan usage lookup failed", exc_info=True)

    with _cache_lock:
        _cache_at = time.monotonic()
        _cache_line = line
    return line


def _install_patch() -> bool:
    """Wrap ``GatewayTurnMixin._format_session_info`` once; idempotent."""
    from gateway.run_turn import GatewayTurnMixin  # gateway process only

    original = getattr(GatewayTurnMixin, "_format_session_info", None)
    if original is None or getattr(original, _PATCH_FLAG, False):
        return False  # renamed/absent upstream, or already wrapped

    def _format_session_info(self):
        base = original(self)
        try:
            line = _plan_line()
        except Exception:  # the notice must render even if usage does not
            logger.debug("usage-notice: plan line failed", exc_info=True)
            line = ""
        return f"{base}\n{line}" if line else base

    setattr(_format_session_info, _PATCH_FLAG, True)
    GatewayTurnMixin._format_session_info = _format_session_info
    logger.info("usage-notice: session-info block now carries the Go plan windows")
    return True


def handle(event_type, context):  # declared events are observers; work happens at load
    try:
        _install_patch()
    except Exception:
        logger.debug("usage-notice: patch install failed", exc_info=True)


# Module body runs when the hook loads at gateway startup — before the first
# notice is built.
try:
    _install_patch()
except Exception:
    logger.debug("usage-notice: gateway module not importable yet; deferring", exc_info=True)
