"""Format inbound webhooks (Watchtower, cron, custom) for Telegram HTML."""

from __future__ import annotations

import re
from typing import Any, Dict

from utils.formatters import escape_telegram_html


def _extract_container_from_watchtower_message(msg: str) -> str:
    m = re.search(
        r"(?:new\s+update\s+available\s+for|update\s+available\s+for)\s+['\"]?([^\s'\".,]+)",
        msg,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    m = re.search(r"for\s+['\"]?([^\s'\".,]+)['\"]?", msg, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def format_notify_telegram_html(data: Dict[str, Any]) -> str:
    """
    Build Telegram HTML from POST /notify JSON.

    Fields: secret, job, status, message, title, source, container
    """
    source = str(data.get("source") or data.get("job") or "").strip().lower()
    title = str(data.get("title") or "").strip()
    message = str(data.get("message") or data.get("text") or data.get("body") or "").strip()
    status = str(data.get("status") or "").strip().lower()
    container = str(data.get("container") or data.get("name") or "").strip()

    is_watchtower = (
        source in ("watchtower", "wt")
        or "watchtower" in title.lower()
        or message.lower().startswith("watchtower")
    )

    if is_watchtower:
        if message.lower().startswith("watchtower:"):
            message = message.split(":", 1)[-1].strip()
        if not container:
            container = _extract_container_from_watchtower_message(message)
        lines = ["📦 <b>Watchtower</b>"]
        if container:
            lines.append(f"<b>Container</b>: <code>{escape_telegram_html(container)}</code>")
        if message:
            lines.append(escape_telegram_html(message))
        else:
            lines.append("<i>Container image update detected</i>")
        return "\n".join(lines)

    job = escape_telegram_html(source or title or "job")
    st = escape_telegram_html(status or "unknown")
    text = (
        f"🗓 <b>External notification</b>\n"
        f"<b>Source</b>: <code>{job}</code>\n"
        f"<b>Status</b>: <code>{st}</code>\n"
    )
    if message:
        text += f"\n{escape_telegram_html(message)}"
    return text
