"""Telegram notifications for uptime monitor events."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

import config
from database.memory import save_alert, save_conversation
from monitoring.uptime import dependencies
from utils.conversation_snippet import html_reply_to_context_plain
from utils.formatters import escape_telegram_html
from utils.security import callback_data_for_user

logger = logging.getLogger(__name__)


def _alert_keyboard(monitor: Dict[str, Any], user_id: int) -> InlineKeyboardMarkup:
    mid = monitor["id"]
    name = monitor.get("name", "")
    mtype = monitor.get("type", "")
    rows = [
        [
            InlineKeyboardButton(
                "✅ Ack all",
                callback_data=callback_data_for_user("uackall", user_id),
            ),
            InlineKeyboardButton(
                "🔕 Silence 1h",
                callback_data=callback_data_for_user("usil", user_id, f"{mid}:60"),
            ),
        ],
    ]
    if config.UPTIME_AI_BUTTON and config.OPENAI_API_KEY:
        try:
            rows.append([
                InlineKeyboardButton(
                    "🤖 AI assist",
                    callback_data=callback_data_for_user("uai", user_id, str(mid)),
                ),
            ])
        except ValueError as e:
            logger.warning("alert keyboard uai for %s: %s", name, e)
    if mtype == "docker":
        cname = monitor.get("target", "").lstrip("/")[:40]
        try:
            rows.append([
                InlineKeyboardButton(
                    "📋 Logs",
                    callback_data=callback_data_for_user("ulog", user_id, cname),
                ),
                InlineKeyboardButton(
                    "🔄 Restart",
                    callback_data=callback_data_for_user("urst", user_id, cname),
                ),
            ])
        except ValueError as e:
            logger.warning("alert keyboard truncated for %s: %s", name, e)
    elif mtype in ("systemd", "process"):
        unit = (monitor.get("target", "") or "")[:40]
        try:
            rows.append([
                InlineKeyboardButton(
                    "🔄 Restart service",
                    callback_data=callback_data_for_user("rs", user_id, unit),
                ),
            ])
        except ValueError as e:
            logger.warning("alert keyboard rs for %s: %s", name, e)
    return InlineKeyboardMarkup(rows)


async def send_monitor_down(
    bot: Bot,
    monitor: Dict[str, Any],
    result_error: str,
    incident_started: datetime,
    ai_summary: str = "",
    affected_children: Optional[List[str]] = None,
    severity: str = "critical",
) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    name = monitor.get("name", "monitor")
    mtype = monitor.get("type", "")
    err = escape_telegram_html(result_error or "check failed")
    msg_plain = (
        f"🚨 {name} DOWN\n"
        f"Monitor: {name} ({mtype})\n"
        f"Error: {result_error}\n"
    )
    text = (
        f"🚨 <b>{escape_telegram_html(name)} DOWN</b>\n\n"
        f"<b>Monitor</b>: <code>{escape_telegram_html(name)}</code> "
        f"(<code>{escape_telegram_html(mtype)}</code>)\n"
        f"<b>Target</b>: <code>{escape_telegram_html(monitor.get('target', ''))}</code>\n"
        f"<b>Error</b>: {err}\n"
    )
    if affected_children:
        text += "\n<b>Root cause — affected services:</b>\n"
        for c in affected_children:
            text += f"• <code>{escape_telegram_html(c)}</code>\n"
    icons = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}
    icon = icons.get(severity, "🔴")
    text = text.replace("🚨", icon, 1)

    await save_alert("uptime", severity, msg_plain[:2000])

    for uid in config.ALLOWED_USER_IDS:
        kb = _alert_keyboard(monitor, uid)
        try:
            await bot.send_message(
                uid,
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception as e:
            logger.error("uptime down alert %s: %s", uid, e)
            continue
        if ai_summary:
            from utils.telegram_reply import bot_send_ai_markdown

            await bot_send_ai_markdown(
                bot,
                uid,
                ai_summary,
                title="AI Analysis",
            )
        plain = html_reply_to_context_plain(text, max_len=12000)
        if plain:
            conv_out = plain
            if ai_summary:
                conv_out = f"{plain}\n\n[AI Analysis]\n{ai_summary[:4000]}"
            await save_conversation(
                uid,
                "assistant",
                f"[Monitor DOWN: {name}]",
                command_output=conv_out,
                metadata={"source": "uptime_alert", "monitor_id": monitor["id"]},
            )


async def send_monitor_up(
    bot: Bot,
    monitor: Dict[str, Any],
    downtime_seconds: int,
) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    name = monitor.get("name", "monitor")
    mins = max(1, downtime_seconds // 60)
    text = (
        f"✅ <b>{escape_telegram_html(name)} recovered</b>\n\n"
        f"Downtime: ~{mins} min (<code>{downtime_seconds}s</code>)\n"
        f"Uptime (7d): <code>{monitor.get('uptime_percentage', 0):.2f}%</code>"
    )
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("uptime up alert %s: %s", uid, e)
