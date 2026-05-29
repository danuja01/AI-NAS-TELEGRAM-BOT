"""Runtime uptime dashboard toggle and public URL (e.g. Tailscale)."""

from __future__ import annotations

import logging
import secrets
from typing import Optional
from urllib.parse import quote

import config
from database.models import get_db

logger = logging.getLogger(__name__)

_KEY_ENABLED = "dashboard_runtime_enabled"
_KEY_SECRET = "dashboard_generated_secret"

TAILSCALE_ACCESS_NOTE = (
    "⚠️ <b>Connect to Tailscale first</b> on the device you use to open this link. "
    "The dashboard is only reachable on your tailnet (not the public internet)."
)


async def _get_host_state(key: str) -> Optional[str]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            "SELECT value FROM uptime_host_state WHERE key = ?", (key,)
        )
        row = await cur.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def _set_host_state(key: str, value: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO uptime_host_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()


async def is_runtime_enabled() -> bool:
    raw = await _get_host_state(_KEY_ENABLED)
    if raw in ("0", "false"):
        return False
    if raw in ("1", "true"):
        return True
    return config.UPTIME_DASHBOARD_ENABLED


async def set_runtime_enabled(enabled: bool) -> None:
    await _set_host_state(_KEY_ENABLED, "1" if enabled else "0")


async def get_dashboard_secret() -> str:
    if config.UPTIME_DASHBOARD_SECRET:
        return config.UPTIME_DASHBOARD_SECRET
    stored = await _get_host_state(_KEY_SECRET)
    if stored:
        return stored
    new_secret = secrets.token_urlsafe(24)
    await _set_host_state(_KEY_SECRET, new_secret)
    logger.info("Generated dashboard secret (stored in DB; set UPTIME_DASHBOARD_SECRET to pin)")
    return new_secret


def public_host() -> str:
    host = (config.UPTIME_DASHBOARD_PUBLIC_HOST or "").strip()
    if host:
        return host.rstrip("/")
    return "127.0.0.1"


def build_dashboard_url(secret: str) -> str:
    host = public_host()
    port = config.UPTIME_DASHBOARD_PORT
    q = quote(secret, safe="")
    return f"http://{host}:{port}/?secret={q}"


async def format_dashboard_link_message() -> str:
    from utils.formatters import escape_telegram_html

    secret = await get_dashboard_secret()
    url = build_dashboard_url(secret)
    return (
        f"{TAILSCALE_ACCESS_NOTE}\n\n"
        f"📊 <b>Uptime dashboard</b>\n"
        f"<a href=\"{escape_telegram_html(url)}\">Open monitor grid</a>\n\n"
        f"<b>URL</b> (copy if link does not open):\n"
        f"<code>{escape_telegram_html(url)}</code>"
    )
