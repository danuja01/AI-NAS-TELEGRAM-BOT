"""
Service management command handlers.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from utils.security import require_auth, rate_limit
from utils.formatters import format_error, format_success
from services.service_manager import (
    restart_service, get_service_status, list_common_services,
    reboot_system, shutdown_system
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)


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


@require_auth
@rate_limit
async def restart_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart_service <name> command - Restart a systemd service."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/restart_service <service_name>`\n\n"
            "Example: `/restart_service nginx`",
            parse_mode='Markdown'
        )
        return
    
    service_name = context.args[0]
    
    try:
        # Send confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"restart_svc_{service_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ Restart service `{service_name}`?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in restart_service_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(str(e)))


@require_auth
@rate_limit
async def reboot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reboot command - Reboot the system."""
    try:
        # Send confirmation with double-check
        keyboard = [
            [
                InlineKeyboardButton("✅ YES, REBOOT", callback_data="reboot_confirm"),
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
                InlineKeyboardButton("✅ YES, SHUTDOWN", callback_data="shutdown_confirm"),
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
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data == "cancel":
        await query.edit_message_text("❌ Action cancelled")
        return
    
    try:
        # Handle service restart confirmation
        if data.startswith("restart_svc_"):
            service_name = data.replace("restart_svc_", "")
            await query.edit_message_text(f"🔄 Restarting service `{service_name}`...")
            
            restart_service(service_name)
            
            await query.edit_message_text(
                format_success(f"Service `{service_name}` restarted successfully"),
                parse_mode='Markdown'
            )
            
            await save_conversation(user_id, 'user', f'/restart_service {service_name}')
            await save_conversation(user_id, 'assistant', f"Restarted service {service_name}")
            await save_command(user_id, f'/restart_service {service_name}', 'Service restarted')
        
        # Handle reboot confirmation
        elif data == "reboot_confirm":
            await query.edit_message_text("🔄 **REBOOTING SYSTEM NOW**\n\nThe bot will be offline until the system restarts.")
            
            await save_conversation(user_id, 'user', '/reboot')
            await save_conversation(user_id, 'assistant', 'System reboot initiated')
            await save_command(user_id, '/reboot', 'System rebooting')
            
            reboot_system()
        
        # Handle shutdown confirmation
        elif data == "shutdown_confirm":
            await query.edit_message_text("🛑 **SHUTTING DOWN SYSTEM NOW**\n\nPhysical access will be required to restart.")
            
            await save_conversation(user_id, 'user', '/shutdown')
            await save_conversation(user_id, 'assistant', 'System shutdown initiated')
            await save_command(user_id, '/shutdown', 'System shutting down')
            
            shutdown_system()
        
        # Handle Docker confirmations (delegated to docker_cmds module)
        elif data.startswith(("restart_confirm_", "stop_confirm_")):
            from commands.docker_cmds import handle_docker_confirmation
            await handle_docker_confirmation(update, context)
    
    except Exception as e:
        logger.error(f"Error in confirmation handler: {e}", exc_info=True)
        await query.edit_message_text(format_error(f"Failed: {e}"), parse_mode='Markdown')
