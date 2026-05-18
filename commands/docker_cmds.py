"""
Docker management command handlers.
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
    detect_unhealthy_containers,
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)

_CMD_HINT_DOCKER_RESTART = (
    "You used /restart without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_STOP = (
    "You used /stop without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_DSTART = (
    "You used /dstart without a container name.\n\n"
    "Send your **next message** as the container name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)

_CMD_HINT_DOCKER_LOGS = (
    "You used /logs without arguments.\n\n"
    "Send your **next message** as: `container_name` or `container_name 100` (line count), "
    "or `/cancel` to abort."
)


@require_auth
@rate_limit
async def docker_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /docker command - List all Docker containers."""
    user_id = update.effective_user.id

    try:
        await update.message.reply_text("🐳 Fetching Docker containers...")

        containers = list_containers(all_containers=True)

        if not containers:
            await update.message.reply_text(
                "ℹ️ No Docker containers found.\n\n"
                "Make sure Docker is running and you have permission to access it."
            )
            return

        message = format_docker_containers(containers)
        await update.message.reply_text(message, parse_mode="Markdown")

        # Save to conversation history
        container_summary = "\n".join([f"{c['name']}: {c['status']}" for c in containers])
        await save_conversation(user_id, "user", "/docker")
        await save_conversation(user_id, "assistant", message, command_output=container_summary)
        await save_command(user_id, "/docker", f"{len(containers)} containers")

    except Exception as e:
        logger.error(f"Error in docker_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to list containers: {e}"))


@require_auth
@rate_limit
async def containers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /containers command - Alias for /docker."""
    await docker_command(update, context)


async def send_restart_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str
):
    """Show inline confirm for restarting a container (from /restart or follow-up text)."""
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"restart_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data["pending_restart"] = container_name
        await update.message.reply_text(
            f"⚠️ Restart container `{container_name}`?\n\nThis will briefly interrupt the service.",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error in send_restart_confirmation: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare restart: {e}"))


async def send_stop_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str
):
    """Show inline confirm for stopping a container (from /stop or follow-up text)."""
    try:
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"stop_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data["pending_stop"] = container_name
        await update.message.reply_text(
            f"⚠️ Stop container `{container_name}`?",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error in send_stop_confirmation: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare stop: {e}"))


async def run_dstart(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str):
    """Start a container (from /dstart args or follow-up)."""
    try:
        await update.message.reply_text(f"🚀 Starting container `{container_name}`...")

        start_container(container_name)

        message = format_success(f"Container `{container_name}` started successfully")
        await update.message.reply_text(message, parse_mode="Markdown")

        await save_conversation(user_id, "user", f"/dstart {container_name}")
        await save_conversation(user_id, "assistant", message)
        await save_command(user_id, f"/dstart {container_name}", "Container started")

    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in run_dstart: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to start container: {e}"))


async def run_logs(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, container_name: str, lines: int = 50
):
    """Fetch container logs (from /logs args or follow-up)."""
    lines = min(lines, 200)
    try:
        await update.message.reply_text(f"📜 Fetching logs for `{container_name}`...")

        logs = get_container_logs(container_name, lines)

        if len(logs) > 4000:
            logs = logs[-4000:]
            logs = "...[truncated]\n" + logs

        await update.message.reply_text(f"```\n{logs}\n```", parse_mode="Markdown")

        await save_conversation(user_id, "user", f"/logs {container_name}")
        await save_conversation(user_id, "assistant", f"Logs for {container_name}")
        await save_command(user_id, f"/logs {container_name}", f"{lines} lines")

    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in run_logs: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to get logs: {e}"))


@require_auth
@rate_limit
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart <container> command - Restart a Docker container."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_RESTART)
        await update.message.reply_text(_CMD_HINT_DOCKER_RESTART, parse_mode="Markdown")
        return

    container_name = context.args[0]
    await send_restart_confirmation(update, context, user_id, container_name)


@require_auth
@rate_limit
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop <container> command - Stop a Docker container."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_STOP)
        await update.message.reply_text(_CMD_HINT_DOCKER_STOP, parse_mode="Markdown")
        return

    container_name = context.args[0]
    await send_stop_confirmation(update, context, user_id, container_name)


@require_auth
@rate_limit
async def start_container_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dstart <container> - Start a Docker container (not /start — that is the bot welcome)."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_DSTART)
        await update.message.reply_text(_CMD_HINT_DOCKER_DSTART, parse_mode="Markdown")
        return

    container_name = context.args[0]
    await run_dstart(update, context, user_id, container_name)


@require_auth
@rate_limit
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs <container> [lines] command - Show container logs."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOCKER_LOGS)
        await update.message.reply_text(_CMD_HINT_DOCKER_LOGS, parse_mode="Markdown")
        return

    container_name = context.args[0]
    lines = int(context.args[1]) if len(context.args) > 1 else 50
    await run_logs(update, context, user_id, container_name, lines)


async def handle_docker_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation callbacks for Docker actions."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "cancel":
        await query.edit_message_text("❌ Action cancelled")
        return

    try:
        # Handle restart confirmation
        if data.startswith("restart_confirm_"):
            container_name = data.replace("restart_confirm_", "")
            await query.edit_message_text(f"🔄 Restarting `{container_name}`...")

            restart_container(container_name)
            await query.edit_message_text(
                format_success(f"Container `{container_name}` restarted successfully"),
                parse_mode="Markdown",
            )

            user_id = update.effective_user.id
            await save_conversation(user_id, "user", f"/restart {container_name}")
            await save_conversation(user_id, "assistant", f"Restarted {container_name}")
            await save_command(user_id, f"/restart {container_name}", "Container restarted")

        # Handle stop confirmation
        elif data.startswith("stop_confirm_"):
            container_name = data.replace("stop_confirm_", "")
            await query.edit_message_text(f"🛑 Stopping `{container_name}`...")

            stop_container(container_name)
            await query.edit_message_text(
                format_success(f"Container `{container_name}` stopped successfully"),
                parse_mode="Markdown",
            )

            user_id = update.effective_user.id
            await save_conversation(user_id, "user", f"/stop {container_name}")
            await save_conversation(user_id, "assistant", f"Stopped {container_name}")
            await save_command(user_id, f"/stop {container_name}", "Container stopped")

    except ValueError as e:
        await query.edit_message_text(format_error(str(e)), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in docker confirmation: {e}", exc_info=True)
        await query.edit_message_text(format_error(f"Failed: {e}"), parse_mode="Markdown")
