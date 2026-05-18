"""
Dispatch plain-text messages when a command was sent without args (e.g. Telegram menu).
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from utils.formatters import format_error
from utils.followup_state import (
    clear_ai_pending,
    clear_cmd_pending,
    get_ai_pending,
    get_cmd_pending,
    FOLLOWUP_ROOTLOGIN,
    FOLLOWUP_SSH,
    FOLLOWUP_DOCKER_RESTART,
    FOLLOWUP_DOCKER_STOP,
    FOLLOWUP_DOCKER_DSTART,
    FOLLOWUP_DOCKER_LOGS,
    FOLLOWUP_RESTART_SERVICE,
    FOLLOWUP_FIND,
    FOLLOWUP_DOWNLOAD,
)
from utils.security import enforce_message_rate_limit_reply

logger = logging.getLogger(__name__)


async def unified_pending_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle next text message after /ask, /rootlogin, /restart, etc. without arguments."""
    user = update.effective_user
    if not user or not update.message:
        return
    user_id = user.id
    if config.ALLOWED_USER_IDS and user_id not in config.ALLOWED_USER_IDS:
        return

    text = (update.message.text or "").strip()
    if not text:
        return

    ai_cmd = get_ai_pending(context)
    if ai_cmd:
        if not await enforce_message_rate_limit_reply(update, user_id):
            return
        clear_ai_pending(context)
        from commands import ai_cmds

        if ai_cmd == "ask":
            await ai_cmds.execute_ask(update, context, user_id, text)
        elif ai_cmd == "chat":
            await ai_cmds.execute_chat(update, context, user_id, text)
        elif ai_cmd == "summarize":
            await ai_cmds.execute_summarize(update, context, user_id, text)
        elif ai_cmd == "explain":
            await ai_cmds.execute_explain(update, context, user_id, text)
        elif ai_cmd == "analyze":
            await ai_cmds.execute_analyze(update, context, user_id, text)
        elif ai_cmd == "think":
            await ai_cmds.execute_think(update, context, user_id, text)
        elif ai_cmd == "websearch":
            await ai_cmds.execute_websearch(update, context, user_id, text)
        return

    cmd = get_cmd_pending(context)
    if not cmd:
        return

    if not await enforce_message_rate_limit_reply(update, user_id):
        return
    clear_cmd_pending(context)

    from commands import root_cmds, docker_cmds, service, filesystem

    if cmd == FOLLOWUP_ROOTLOGIN:
        await root_cmds.run_rootlogin_attempt(update, context, user_id, text)
    elif cmd == FOLLOWUP_SSH:
        await root_cmds.run_ssh_command(update, context, user_id, text)
    elif cmd == FOLLOWUP_DOCKER_RESTART:
        name = text.split()[0]
        await docker_cmds.send_restart_confirmation(update, context, user_id, name)
    elif cmd == FOLLOWUP_DOCKER_STOP:
        name = text.split()[0]
        await docker_cmds.send_stop_confirmation(update, context, user_id, name)
    elif cmd == FOLLOWUP_DOCKER_DSTART:
        name = text.split()[0]
        await docker_cmds.run_dstart(update, context, user_id, name)
    elif cmd == FOLLOWUP_DOCKER_LOGS:
        parts = text.split()
        if not parts:
            await update.message.reply_text(
                format_error("Send a container name, e.g. `nginx` or `nginx 100`."),
                parse_mode="Markdown",
            )
            return
        cname = parts[0]
        if len(parts) > 1:
            try:
                lines = int(parts[1])
            except ValueError:
                await update.message.reply_text(
                    format_error("Invalid line count; use a number or omit for default 50."),
                    parse_mode="Markdown",
                )
                return
        else:
            lines = 50
        await docker_cmds.run_logs(update, context, user_id, cname, lines)
    elif cmd == FOLLOWUP_RESTART_SERVICE:
        sname = text.split()[0]
        await service.send_restart_service_confirmation(update, context, user_id, sname)
    elif cmd == FOLLOWUP_FIND:
        await filesystem.run_find(update, context, user_id, text)
    elif cmd == FOLLOWUP_DOWNLOAD:
        await filesystem.run_download_from_tokens(update, context, user_id, text.split())
