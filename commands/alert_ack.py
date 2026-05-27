"""Shared alert acknowledgment helpers for commands, buttons, and plain text."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.memory import acknowledge_all_alerts, get_unacknowledged_alerts
from utils.formatters import escape_telegram_html


async def acknowledge_all_and_reply(update: Update) -> int:
    """
    Acknowledge all pending DB alerts and reply to the user.
    Returns number acknowledged.
    """
    pending_before = len(await get_unacknowledged_alerts())
    n = await acknowledge_all_alerts()
    if n <= 0 and pending_before == 0:
        msg = "✅ No unacknowledged alerts in the database."
    else:
        msg = (
            f"✅ Acknowledged <b>{n}</b> alert(s). "
            f"<code>/alerts</code> should show none pending."
        )
    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
    elif update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(msg, parse_mode=ParseMode.HTML)
    return n


async def handle_acknowledge_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If message text asks to ack all, do it and return True."""
    from utils.alert_ack_intent import text_requests_acknowledge_all

    if not update.message:
        return False
    text = (update.message.text or "").strip()
    if not text_requests_acknowledge_all(text):
        return False
    await acknowledge_all_and_reply(update)
    return True
