"""
Dispatch plain-text messages when a command was sent without args (e.g. Telegram menu),
or implicit /chat / /analyze when the user sends normal text in a private chat.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

import config
from utils.formatters import format_error
from utils.followup_state import (
    clear_ai_pending,
    clear_cmd_pending,
    get_ai_pending,
    get_cmd_pending,
    FOLLOWUP_DOCKER_RESTART,
    FOLLOWUP_DOCKER_STOP,
    FOLLOWUP_DOCKER_DSTART,
    FOLLOWUP_DOCKER_LOGS,
    FOLLOWUP_RESTART_SERVICE,
    FOLLOWUP_FIND,
)
from utils.plain_text_ai_intent import plain_text_prefers_analyze
from utils.security import enforce_message_rate_limit_reply, is_user_authorized

logger = logging.getLogger(__name__)


async def unified_pending_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle follow-up text after /ask, /find, etc., or implicit /chat in private."""
    user = update.effective_user
    if not user or not update.message:
        return
    user_id = user.id
    if not is_user_authorized(user_id):
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
    if cmd:
        if not await enforce_message_rate_limit_reply(update, user_id):
            return
        clear_cmd_pending(context)

        from commands import docker_cmds, service, filesystem

        if cmd == FOLLOWUP_DOCKER_RESTART:
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
        return

    # Private chat: plain text without a slash command runs /chat (or /analyze-style when phrasing asks).
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not await enforce_message_rate_limit_reply(update, user_id):
        return

    from commands.alert_ack import handle_acknowledge_all_text

    if await handle_acknowledge_all_text(update, context):
        return

    from commands import ai_cmds

    if plain_text_prefers_analyze(text):
        await ai_cmds.execute_analyze(update, context, user_id, text, implicit=True)
    else:
        await ai_cmds.execute_chat(update, context, user_id, text, implicit=True)
