"""usage-notice — add a month-to-date usage line to the new-session notice.

The "New session started" / auto-reset notice is built by the gateway in
``gateway/run_turn.py::GatewayTurnMixin._format_session_info()`` and is exactly
three lines (Model / Provider / Context). Hermes exposes no config key, hook
return value, or language-pack slot that appends to it, so this gateway hook
wraps that method once at startup and appends one line rendered from the
gateway's own SQLite session store.

    ✨ New session started!

    ◆ Model: `deepseek-v4.1-flash`
    ◆ Provider: opencode-go
    ◆ Context: 200K tokens (detected)
    ◆ Usage (Oct): 12.4M in · 1.1M out · 3,412 calls

Fail-safe by design: a missing DB, a renamed method, or schema drift leaves the
notice exactly as upstream renders it — nothing here may break the notice.

Deployed by gitops (k3s_lab apps/hermes): the `hermes-hooks` ConfigMap is copied
into $HERMES_HOME/hooks/usage-notice/ by the fix-perms init container on every
boot, because Hermes only reads hooks/ once, at gateway startup.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("hooks.usage_notice")

_PATCH_FLAG = "_usage_notice_patched"
_BULLET = "\u25c6"  # ◆ — the marker the built-in lines use


def _hermes_home() -> Path:
    home = os.environ.get("HERMES_HOME")
    return Path(home) if home else Path.home() / ".hermes"


def _human(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _usage_line() -> str:
    """Month-to-date totals across the whole store, or "" when unavailable.

    Every session row (telegram / tui / cron / subagent alike) carries only its
    own counters, so they sum without double counting — and the parent filter
    SessionDB.usage_totals() applies would be wrong here: this deployment's /new
    chains each session to its predecessor as parent_session_id, so filtering on
    "top-level only" hides nearly all usage.

    Window is sessions *started* in the current calendar month (UTC), so a
    session that spans a month boundary lands in exactly one month.
    """
    db = _hermes_home() / "state.db"
    if not db.exists():
        return ""
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).timestamp()
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except sqlite3.Error as exc:
        logger.debug("usage-notice: cannot open %s: %s", db, exc)
        return ""
    try:
        row = con.execute(
            """
            SELECT COALESCE(SUM(COALESCE(input_tokens, 0)), 0),
                   COALESCE(SUM(COALESCE(output_tokens, 0)), 0),
                   COALESCE(SUM(COALESCE(api_call_count, 0)), 0),
                   COALESCE(SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)), 0)
              FROM sessions
             WHERE COALESCE(message_count, 0) >= 1
               AND COALESCE(archived, 0) = 0
               AND COALESCE(started_at, last_activity_at, 0) >= ?
            """,
            (month_start,),
        ).fetchone()
    except sqlite3.Error as exc:
        logger.debug("usage-notice: usage query failed: %s", exc)
        return ""
    finally:
        con.close()

    if not row:
        return ""
    tokens_in, tokens_out, calls = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    cost = float(row[3] or 0.0)
    if not (tokens_in or tokens_out or calls):
        return ""
    parts = [f"{_human(tokens_in)} in", f"{_human(tokens_out)} out", f"{calls:,} calls"]
    if cost > 0:  # opencode-go has no price catalog entry, so this stays hidden today
        parts.append(f"${cost:,.2f}")
    return f"{_BULLET} Usage ({now.strftime('%b')}): " + " · ".join(parts)


def _install_patch() -> bool:
    """Wrap ``GatewayTurnMixin._format_session_info`` once; idempotent."""
    from gateway.run_turn import GatewayTurnMixin  # gateway process only

    original = getattr(GatewayTurnMixin, "_format_session_info", None)
    if original is None or getattr(original, _PATCH_FLAG, False):
        return False  # renamed/absent upstream, or already wrapped

    def _format_session_info(self):
        base = original(self)
        try:
            line = _usage_line()
        except Exception:  # the notice must render even if usage does not
            logger.debug("usage-notice: usage line failed", exc_info=True)
            line = ""
        return f"{base}\n{line}" if line else base

    setattr(_format_session_info, _PATCH_FLAG, True)
    GatewayTurnMixin._format_session_info = _format_session_info
    logger.info("usage-notice: session-info block now carries a usage line")
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
