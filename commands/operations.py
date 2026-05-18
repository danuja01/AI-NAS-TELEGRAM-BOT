"""
Host maintenance: APT/OMV updates and related Telegram commands.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from database.memory import save_command, save_conversation
from services.host_runner import format_host_result_html, run_profile
from utils.security import require_auth, rate_limit
from utils.telegram_reply import reply_text_safe

logger = logging.getLogger(__name__)

CB_UPGRADE_CONFIRM = "upgrade_omv_confirm"
CB_UPGRADE_CANCEL = "upgrade_omv_cancel"


def _maintenance_user_ids() -> List[int]:
    return config.MAINTENANCE_ALLOWED_USER_IDS or config.ALLOWED_USER_IDS


def _is_maintenance(user_id: int) -> bool:
    return user_id in _maintenance_user_ids()


def _kw():
    return {"parse_mode": ParseMode.HTML}


@require_auth
@rate_limit
async def updates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refresh apt indices and list upgradable packages (host)."""
    user_id = update.effective_user.id
    await reply_text_safe(update, "📦 Checking for updates on host (this may take a minute)…")
    try:
        r1 = await asyncio.to_thread(run_profile, "apt_update")
        r2 = await asyncio.to_thread(run_profile, "apt_list_upgradable")
        r3 = await asyncio.to_thread(run_profile, "reboot_required")

        body: List[str] = []
        if r1.error or not r1.ok:
            body.append(format_host_result_html("apt-get update", r1))
        else:
            body.append("✅ <b>apt-get update</b> finished (exit 0)")

        body.append("")
        body.append(format_host_result_html("Upgradable packages", r2))

        omv_lines = []
        for line in (r2.stdout or "").splitlines():
            if "openmediavault" in line.lower() or "/omv" in line.lower():
                omv_lines.append(line[:200])
        if omv_lines:
            from utils.formatters import escape_telegram_html

            body.append("")
            body.append("<b>OMV-related lines</b>")
            body.append(
                "<pre>" + escape_telegram_html("\n".join(omv_lines[:25])) + "</pre>"
            )

        body.append("")
        body.append(format_host_result_html("Reboot hint", r3))

        await reply_text_safe(update, "\n".join(body), **_kw())
        await save_conversation(user_id, "user", "/updates")
        await save_command(user_id, "/updates", "apt check")
    except Exception as e:
        logger.exception("updates_command")
        from utils.formatters import format_error_html

        await reply_text_safe(update, format_error_html(str(e)), **_kw())


@require_auth
@rate_limit
async def omv_updates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias focus: same as /updates but hints OMV doc."""
    await updates_command(update, context)
    await reply_text_safe(
        update,
        "ℹ️ Major OMV release upgrades are manual: use "
        "<code>omv-release-upgrade</code> per OpenMediaVault docs—not this bot.",
        **_kw(),
    )


@require_auth
@rate_limit
async def upgrade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Confirm-gated host omv-upgrade."""
    user_id = update.effective_user.id
    if not _is_maintenance(user_id):
        await reply_text_safe(
            update,
            "⛔ You are not allowed to run host upgrades. "
            "Set MAINTENANCE_ALLOWED_USER_IDS or ALLOWED_USER_IDS.",
            **_kw(),
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Run omv-upgrade", callback_data=CB_UPGRADE_CONFIRM),
            InlineKeyboardButton("❌ Cancel", callback_data=CB_UPGRADE_CANCEL),
        ]
    ]
    await reply_text_safe(
        update,
        "⚠️ <b>Host upgrade</b>\n\n"
        "This runs <code>omv-upgrade</code> on the NAS host (can take a long time, "
        "may restart services). Confirm only during a maintenance window.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        **_kw(),
    )


async def handle_operations_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle upgrade confirmation (register with pattern ^upgrade_omv_)."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    user_id = update.effective_user.id
    chat_id = query.message.chat_id if query.message else update.effective_chat.id

    if query.data == CB_UPGRADE_CANCEL:
        await query.edit_message_text("❌ Upgrade cancelled.", parse_mode=ParseMode.HTML)
        return

    if query.data != CB_UPGRADE_CONFIRM:
        return

    if not _is_maintenance(user_id):
        await query.edit_message_text(
            "⛔ Not authorized for maintenance.", parse_mode=ParseMode.HTML
        )
        return

    await query.edit_message_text(
        "⏳ <b>omv-upgrade started</b>\n\n"
        "Running on host in background… you will get another message when it finishes.",
        parse_mode=ParseMode.HTML,
    )

    asyncio.create_task(_omv_upgrade_job(context.bot, chat_id, user_id))


async def _omv_upgrade_job(bot, chat_id: int, user_id: int):
    try:
        result = await asyncio.to_thread(run_profile, "omv_upgrade")
        text = format_host_result_html("omv-upgrade finished", result)
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        await save_command(
            user_id,
            "/upgrade",
            f"exit {result.exit_code}",
            success=result.ok,
        )
        await save_conversation(user_id, "assistant", f"omv-upgrade exit {result.exit_code}")
    except Exception as e:
        logger.exception("omv_upgrade_job")
        from utils.formatters import format_error_html

        await bot.send_message(
            chat_id, format_error_html(f"Upgrade task failed: {e}"), parse_mode=ParseMode.HTML
        )
