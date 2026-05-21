"""
Service management command handlers.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.security import (
    require_auth,
    rate_limit,
    reject_unauthorized_callback,
    callback_data_for_user,
    parse_callback_user_id,
)
from utils.formatters import format_error, format_success
from utils.followup_state import set_cmd_pending_exclusive, FOLLOWUP_RESTART_SERVICE
from services.service_manager import (
    restart_service, get_service_status, list_common_services,
    reboot_system, shutdown_system
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)

_CMD_HINT_RESTART_SERVICE = (
    "You used /restart_service without a service name.\n\n"
    "Send your **next message** as the systemd service name, or `/cancel` to abort.\n\n"
    "Example: `nginx`"
)


@require_auth
@rate_limit
async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /services command - List system services."""
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("⚙️ Checking services...")
        
        services = list_common_services()
        
        if not services:
            await update.message.reply_text("ℹ️ No services found")
            return
        
        message = "⚙️ **System Services**\n\n"
        
        for service in services:
            state = service.get('state', 'unknown')
            
            if state == 'running':
                icon = "✅"
            elif state == 'inactive':
                icon = "⚪"
            elif state == 'failed':
                icon = "❌"
            else:
                icon = "⚠️"
            
            message += f"{icon} **{service['name']}**: {state}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', '/services')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, '/services', f"{len(services)} services")
        
    except Exception as e:
        logger.error(f"Error in services_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to list services: {e}"))


async def send_restart_service_confirmation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, service_name: str
):
    """Show inline confirm for restarting a systemd service (from /restart_service or follow-up)."""
    try:
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data=callback_data_for_user("rs", user_id, service_name),
                ),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ Restart service `{service_name}`?",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Error in send_restart_service_confirmation: {e}", exc_info=True)
        await update.message.reply_text(format_error(str(e)))


@require_auth
@rate_limit
async def restart_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart_service <name> command - Restart a systemd service."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_RESTART_SERVICE)
        await update.message.reply_text(_CMD_HINT_RESTART_SERVICE, parse_mode="Markdown")
        return

    service_name = context.args[0]
    await send_restart_service_confirmation(update, context, user_id, service_name)


@require_auth
@rate_limit
async def reboot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reboot command - Reboot the system."""
    try:
        # Send confirmation with double-check
        keyboard = [
            [
                InlineKeyboardButton("✅ YES, REBOOT", callback_data=callback_data_for_user("rb", update.effective_user.id)),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **REBOOT SYSTEM**\n\n"
            "This will reboot the entire NAS.\n"
            "All services will be interrupted.\n\n"
            "Are you absolutely sure?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in reboot_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(str(e)))


@require_auth
@rate_limit
async def shutdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /shutdown command - Shutdown the system."""
    try:
        # Send confirmation with double-check
        keyboard = [
            [
                InlineKeyboardButton("✅ YES, SHUTDOWN", callback_data=callback_data_for_user("sd", update.effective_user.id)),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **SHUTDOWN SYSTEM**\n\n"
            "This will shutdown the entire NAS.\n"
            "You will need physical access to restart it.\n\n"
            "Are you absolutely sure?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in shutdown_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(str(e)))


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all confirmation callbacks."""
    query = update.callback_query
    if await reject_unauthorized_callback(query):
        return
    await query.answer()

    data = query.data
    user_id = update.effective_user.id

    if data == "cancel":
        await query.edit_message_text("❌ Action cancelled")
        return

    try:
        uid, service_name = parse_callback_user_id(data, "rs")
        if uid is not None:
            if uid != user_id:
                await query.edit_message_text("🚫 This confirmation is for another user.")
                return
            await query.edit_message_text(f"🔄 Restarting service `{service_name}`...")
            restart_service(service_name)
            await query.edit_message_text(
                format_success(f"Service `{service_name}` restarted successfully"),
                parse_mode="Markdown",
            )
            await save_conversation(user_id, "user", f"/restart_service {service_name}")
            await save_conversation(user_id, "assistant", f"Restarted service {service_name}")
            await save_command(user_id, f"/restart_service {service_name}", "Service restarted")
            return

        uid, _ = parse_callback_user_id(data, "rb")
        if uid is not None:
            if uid != user_id:
                await query.edit_message_text("🚫 This confirmation is for another user.")
                return
            await query.edit_message_text(
                "🔄 **REBOOTING SYSTEM NOW**\n\nThe bot will be offline until the system restarts."
            )
            await save_conversation(user_id, "user", "/reboot")
            await save_conversation(user_id, "assistant", "System reboot initiated")
            await save_command(user_id, "/reboot", "System rebooting")
            reboot_system()
            return

        uid, _ = parse_callback_user_id(data, "sd")
        if uid is not None:
            if uid != user_id:
                await query.edit_message_text("🚫 This confirmation is for another user.")
                return
            await query.edit_message_text(
                "🛑 **SHUTTING DOWN SYSTEM NOW**\n\nPhysical access will be required to restart."
            )
            await save_conversation(user_id, "user", "/shutdown")
            await save_conversation(user_id, "assistant", "System shutdown initiated")
            await save_command(user_id, "/shutdown", "System shutting down")
            shutdown_system()
            return

        if data.startswith("restart_svc_"):
            service_name = data.replace("restart_svc_", "", 1)
            await query.edit_message_text(f"🔄 Restarting service `{service_name}`...")
            restart_service(service_name)
            await query.edit_message_text(
                format_success(f"Service `{service_name}` restarted successfully"),
                parse_mode="Markdown",
            )
            await save_command(user_id, f"/restart_service {service_name}", "Service restarted")
        elif data == "reboot_confirm":
            await query.edit_message_text("🔄 **REBOOTING SYSTEM NOW**\n\nThe bot will be offline until the system restarts.")
            await save_command(user_id, "/reboot", "System rebooting")
            reboot_system()
        elif data == "shutdown_confirm":
            await query.edit_message_text("🛑 **SHUTTING DOWN SYSTEM NOW**\n\nPhysical access will be required to restart.")
            await save_command(user_id, "/shutdown", "System shutting down")
            shutdown_system()
        elif data.startswith(("dr:", "ds:", "drestart_confirm_", "dstop_confirm_", "restart_confirm_", "stop_confirm_")):
            from commands.docker_cmds import handle_docker_confirmation

            await handle_docker_confirmation(update, context)

    except Exception as e:
        logger.error(f"Error in confirmation handler: {e}", exc_info=True)
        await query.edit_message_text(format_error(f"Failed: {e}"), parse_mode="Markdown")
