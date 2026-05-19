"""
Docker container management (/d* lifecycle commands).
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.formatters import format_docker_containers, format_error, format_success
from utils.followup_state import (
    set_cmd_pending_exclusive,
    FOLLOWUP_DOCKER_RESTART,
    FOLLOWUP_DOCKER_STOP,
    FOLLOWUP_DOCKER_DSTART,
    FOLLOWUP_DOCKER_LOGS,
)
from services.docker_service import (
    list_containers,
    restart_container,
    stop_container,
    start_container,
    get_container_logs,
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)

_CMD_HINT_DOCKER_RESTART = (
    "You used /drestart without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_STOP = (
    "You used /dstop without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_DSTART = (
    "You used /dstart without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_LOGS = (
    "You used /dtail without arguments.\n\n"
    "Send your **next message** as: `container_name` or `container_name 100` (line count), "
    "or `/cancel` to abort."
)


async def _legacy_redirect(update: Update, new_cmd: str):
    await update.message.reply_text(
        f"ℹ️ This command was renamed. Use `{new_cmd}` instead.",
        parse_mode="Markdown",
    )


@require_auth
@rate_limit
async def docker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias: redirect to /ddocker dashboard."""
    from commands.docker_storage_cmds import ddocker_command

    await ddocker_command(update, context)


@require_auth
@rate_limit
async def containers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await docker_command(update, context)


@require_auth
@rate_limit
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _legacy_redirect(update, "/drestart")


@require_auth
@rate_limit
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _legacy_redirect(update, "/dstop")


@require_auth
@rate_limit
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _legacy_redirect(update, "/dtail")


@require_auth
@rate_limit
async def drestart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_RESTART)
        await update.message.reply_text(_CMD_HINT_DOCKER_RESTART, parse_mode="Markdown")
        return
    await send_restart_confirmation(update, context, user_id, context.args[0])


@require_auth
@rate_limit
async def dstop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_STOP)
        await update.message.reply_text(_CMD_HINT_DOCKER_STOP, parse_mode="Markdown")
        return
    await send_stop_confirmation(update, context, user_id, context.args[0])


@require_auth
@rate_limit
async def start_container_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_DSTART)
        await update.message.reply_text(_CMD_HINT_DOCKER_DSTART, parse_mode="Markdown")
        return
    await run_dstart(update, context, user_id, context.args[0])


@require_auth
@rate_limit
async def dtail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_LOGS)
        await update.message.reply_text(_CMD_HINT_DOCKER_LOGS, parse_mode="Markdown")
        return
    container_name = context.args[0]
    lines = int(context.args[1]) if len(context.args) > 1 else 50
    await run_logs(update, context, user_id, container_name, lines)


async def send_restart_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str
):
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"drestart_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        context.user_data["pending_restart"] = container_name
        await update.message.reply_text(
            f"⚠️ Restart container `{container_name}`?\n\nThis will briefly interrupt the service.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("send_restart_confirmation: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare restart: {e}"))


async def send_stop_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str
):
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"dstop_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        context.user_data["pending_stop"] = container_name
        await update.message.reply_text(
            f"⚠️ Stop container `{container_name}`?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("send_stop_confirmation: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare stop: {e}"))


async def run_dstart(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str):
    try:
        await update.message.reply_text(f"🚀 Starting container `{container_name}`...")
        start_container(container_name)
        message = format_success(f"Container `{container_name}` started successfully")
        await update.message.reply_text(message, parse_mode="Markdown")
        await save_conversation(user_id, "user", f"/dstart {container_name}")
        await save_command(user_id, f"/dstart {container_name}", "Container started")
    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error("run_dstart: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Failed to start container: {e}"))


async def run_logs(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str, lines: int = 50
):
    lines = min(lines, 200)
    try:
        await update.message.reply_text(f"📜 Fetching logs for `{container_name}`...")
        logs = get_container_logs(container_name, lines)
        if len(logs) > 4000:
            logs = "...[truncated]\n" + logs[-4000:]
        await update.message.reply_text(f"```\n{logs}\n```", parse_mode="Markdown")
        await save_conversation(user_id, "user", f"/dtail {container_name}")
        await save_command(user_id, f"/dtail {container_name}", f"{lines} lines")
    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error("run_logs: %s", e, exc_info=True)
        await update.message.reply_text(format_error(f"Failed to get logs: {e}"))


async def handle_docker_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "cancel":
        await query.edit_message_text("❌ Action cancelled")
        return
    try:
        if data.startswith("drestart_confirm_"):
            container_name = data.replace("drestart_confirm_", "", 1)
            await query.edit_message_text(f"🔄 Restarting `{container_name}`...")
            restart_container(container_name)
            await query.edit_message_text(
                format_success(f"Container `{container_name}` restarted successfully"),
                parse_mode="Markdown",
            )
            user_id = update.effective_user.id
            await save_command(user_id, f"/drestart {container_name}", "Container restarted")
        elif data.startswith("dstop_confirm_"):
            container_name = data.replace("dstop_confirm_", "", 1)
            await query.edit_message_text(f"🛑 Stopping `{container_name}`...")
            stop_container(container_name)
            await query.edit_message_text(
                format_success(f"Container `{container_name}` stopped successfully"),
                parse_mode="Markdown",
            )
            user_id = update.effective_user.id
            await save_command(user_id, f"/dstop {container_name}", "Container stopped")
        elif data.startswith("restart_confirm_") or data.startswith("stop_confirm_"):
            await query.edit_message_text(
                "ℹ️ Please use /drestart or /dstop (callbacks were renamed).",
                parse_mode="Markdown",
            )
    except ValueError as e:
        await query.edit_message_text(format_error(str(e)), parse_mode="Markdown")
    except Exception as e:
        logger.error("docker confirmation: %s", e, exc_info=True)
        await query.edit_message_text(format_error(f"Failed: {e}"), parse_mode="Markdown")
