"""Telegram inline-button handlers for uptime monitor alerts."""

from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from monitoring.uptime import store
from services.docker_service import get_container_logs
from utils.formatters import escape_telegram_html
from utils.security import (
    callback_data_for_user,
    parse_callback_user_id,
    reject_unauthorized_callback,
)
from utils.telegram_reply import reply_text_chunked

logger = logging.getLogger(__name__)

_UPTIME_CB_PREFIXES = ("uack", "uackall", "usil", "ulog", "urst")


def is_uptime_callback(data: str) -> bool:
    if not data:
        return False
    return data.split(":", 1)[0] in _UPTIME_CB_PREFIXES


async def handle_uptime_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not is_uptime_callback(query.data):
        return

    if await reject_unauthorized_callback(query):
        return

    data = query.data
    user_id = update.effective_user.id
    action = data.split(":", 1)[0]
    msg = query.message

    try:
        if action == "uackall":
            await _handle_ack_all(query, user_id)
        elif action == "uack":
            await _handle_ack(query, data, user_id)
        elif action == "usil":
            await _handle_silence(query, data, user_id)
        elif action == "ulog":
            await _handle_logs(update, query, data, user_id)
        elif action == "urst":
            await _handle_restart(query, context, data, user_id)
        else:
            await query.answer()
    except Exception as e:
        logger.error("uptime callback %s failed: %s", data, e, exc_info=True)
        try:
            await query.answer("Action failed.", show_alert=True)
        except Exception:
            pass
        if msg:
            await msg.reply_text(f"❌ Button action failed: {escape_telegram_html(str(e)[:200])}", parse_mode=ParseMode.HTML)


async def _answer(query, text: str = "") -> None:
    try:
        await query.answer(text or None)
    except Exception as e:
        logger.debug("query.answer: %s", e)


async def _clear_keyboard(query) -> None:
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.debug("clear keyboard: %s", e)


async def _handle_ack_all(query, user_id: int) -> None:
    uid, _ = parse_callback_user_id(query.data, "uackall")
    if uid != user_id:
        await _answer(query, "Not your button.")
        return
    from database.memory import acknowledge_all_alerts, get_unacknowledged_alerts

    n = await acknowledge_all_alerts()
    await _answer(query, f"Acked {n}" if n else "None pending")
    await _clear_keyboard(query)
    if query.message:
        if n:
            await query.message.reply_text(
                f"✅ Acknowledged <b>{n}</b> alert(s) in the inbox.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await query.message.reply_text("✅ No unacknowledged alerts were pending.")


async def _handle_ack(query, data: str, user_id: int) -> None:
    """Single Ack button — acknowledges all pending alerts (same as Ack all)."""
    uid, payload = parse_callback_user_id(data, "uack")
    if uid != user_id:
        await _answer(query, "Not your button.")
        return
    from database.memory import acknowledge_all_alerts

    n = await acknowledge_all_alerts()
    await _answer(query, f"Acked {n}" if n else "Done")
    await _clear_keyboard(query)
    if query.message:
        await query.message.reply_text(
            f"✅ Acknowledged <b>{n}</b> alert(s).",
            parse_mode=ParseMode.HTML,
        )


async def _handle_silence(query, data: str, user_id: int) -> None:
    uid, payload = parse_callback_user_id(data, "usil")
    if uid != user_id:
        await _answer(query, "Not your button.")
        return
    mid_s, _, mins_s = (payload or "").partition(":")
    try:
        mid = int(mid_s)
        mins = int(mins_s or "60")
    except ValueError:
        await _answer(query, "Invalid silence data.")
        return
    await store.add_silence(mins, monitor_id=mid, reason="telegram")
    await _answer(query, f"Silenced {mins}m")
    await _clear_keyboard(query)
    if query.message:
        await query.message.reply_text(
            f"🔕 Alerts silenced for monitor #{mid} for <b>{mins}</b> minutes.",
            parse_mode=ParseMode.HTML,
        )


async def _handle_logs(update: Update, query, data: str, user_id: int) -> None:
    uid, container_name = parse_callback_user_id(data, "ulog")
    if uid != user_id:
        await _answer(query, "Not your button.")
        return
    if not container_name:
        await _answer(query, "No container name.")
        return
    await _answer(query, "Fetching logs…")
    try:
        logs = await asyncio.to_thread(get_container_logs, container_name, 40)
        body = escape_telegram_html(logs[:3500])
        await reply_text_chunked(
            update,
            f"📋 <b>Logs</b> <code>{escape_telegram_html(container_name)}</code>\n<pre>{body}</pre>",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        if query.message:
            await query.message.reply_text(f"❌ Logs failed: {e}")


async def _handle_restart(query, context, data: str, user_id: int) -> None:
    uid, container_name = parse_callback_user_id(data, "urst")
    if uid != user_id:
        await _answer(query, "Not your button.")
        return
    if not container_name or not query.message:
        await _answer(query, "Missing container.")
        return
    await _answer(query)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Confirm restart",
                callback_data=callback_data_for_user("dr", user_id, container_name),
            ),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])
    context.user_data["pending_restart"] = container_name
    await query.message.reply_text(
        f"⚠️ Restart container <code>{escape_telegram_html(container_name)}</code>?",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
