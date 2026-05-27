"""Uptime analytics and periodic reports."""

from __future__ import annotations

import logging
from typing import List

from telegram import Bot
from telegram.constants import ParseMode

import config
from monitoring.uptime import store
from services.system_monitor import get_memory_stats
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)


async def build_weekly_report() -> str:
    monitors = await store.list_monitors()
    lines = ["📊 <b>Weekly NAS Monitor Report</b>", ""]
    lines.append("<b>Uptime (7d)</b>:")
    for m in monitors[:40]:
        stats = await store.get_monitor_stats(m["id"], hours=168)
        pct = stats.get("uptime_pct")
        if pct is None:
            pct = m.get("uptime_percentage", 0)
        icon = "🟢" if m.get("last_status") == "up" else "🔴"
        lines.append(
            f"{icon} <code>{escape_telegram_html(m['name'])}</code>: "
            f"<code>{pct:.2f}%</code>"
        )
    incidents = await store.list_recent_incidents(limit=10)
    if incidents:
        lines.append("")
        lines.append("<b>Recent incidents</b>:")
        for inc in incidents[:5]:
            dur = inc.get("duration_seconds") or "ongoing"
            lines.append(
                f"• <code>{escape_telegram_html(inc.get('monitor_name', '?'))}</code> "
                f"({dur}s)"
            )
    try:
        mem = get_memory_stats()
        lines.append("")
        lines.append(
            f"<b>Current RAM</b>: <code>{mem.get('percent', 0):.1f}%</code> used"
        )
    except Exception:
        pass
    return "\n".join(lines)


async def send_weekly_report(bot: Bot) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    text = await build_weekly_report()
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("weekly report %s: %s", uid, e)
