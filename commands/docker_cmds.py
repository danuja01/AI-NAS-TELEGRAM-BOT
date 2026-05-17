"""
Docker management command handlers.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.formatters import format_docker_containers, format_error, format_success
from services.docker_service import (
    list_containers, restart_container, stop_container,
    start_container, get_container_logs, detect_unhealthy_containers
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)


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
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        container_summary = "\n".join([f"{c['name']}: {c['status']}" for c in containers])
        await save_conversation(user_id, 'user', '/docker')
        await save_conversation(user_id, 'assistant', message, command_output=container_summary)
        await save_command(user_id, '/docker', f"{len(containers)} containers")
        
    except Exception as e:
        logger.error(f"Error in docker_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to list containers: {e}"))


@require_auth
@rate_limit
async def containers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /containers command - Alias for /docker."""
    await docker_command(update, context)


@require_auth
@rate_limit
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart <container> command - Restart a Docker container."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/restart <container_name>`\n\n"
            "Example: `/restart nginx`",
            parse_mode='Markdown'
        )
        return
    
    container_name = context.args[0]
    
    try:
        # Send confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"restart_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Store pending action
        context.user_data['pending_restart'] = container_name
        
        await update.message.reply_text(
            f"⚠️ Restart container `{container_name}`?\n\nThis will briefly interrupt the service.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in restart_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare restart: {e}"))


@require_auth
@rate_limit
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop <container> command - Stop a Docker container."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/stop <container_name>`\n\n"
            "Example: `/stop nginx`",
            parse_mode='Markdown'
        )
        return
    
    container_name = context.args[0]
    
    try:
        # Send confirmation
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"stop_confirm_{container_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data="cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        context.user_data['pending_stop'] = container_name
        
        await update.message.reply_text(
            f"⚠️ Stop container `{container_name}`?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in stop_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to prepare stop: {e}"))


@require_auth
@rate_limit
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start_container <container> command - Start a Docker container."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/start <container_name>`\n\n"
            "Example: `/start nginx`",
            parse_mode='Markdown'
        )
        return
    
    container_name = context.args[0]
    
    try:
        await update.message.reply_text(f"🚀 Starting container `{container_name}`...")
        
        start_container(container_name)
        
        message = format_success(f"Container `{container_name}` started successfully")
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', f'/start {container_name}')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, f'/start {container_name}', 'Container started')
        
    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in start_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to start container: {e}"))


@require_auth
@rate_limit
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs <container> [lines] command - Show container logs."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/logs <container_name> [lines]`\n\n"
            "Example: `/logs nginx 100`",
            parse_mode='Markdown'
        )
        return
    
    container_name = context.args[0]
    lines = int(context.args[1]) if len(context.args) > 1 else 50
    
    # Limit lines to prevent spam
    lines = min(lines, 200)
    
    try:
        await update.message.reply_text(f"📜 Fetching logs for `{container_name}`...")
        
        logs = get_container_logs(container_name, lines)
        
        # Truncate if too long for Telegram
        if len(logs) > 4000:
            logs = logs[-4000:]
            logs = "...[truncated]\n" + logs
        
        await update.message.reply_text(f"```\n{logs}\n```", parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', f'/logs {container_name}')
        await save_conversation(user_id, 'assistant', f"Logs for {container_name}")
        await save_command(user_id, f'/logs {container_name}', f"{lines} lines")
        
    except ValueError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in logs_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to get logs: {e}"))


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
                parse_mode='Markdown'
            )
            
            user_id = update.effective_user.id
            await save_conversation(user_id, 'user', f'/restart {container_name}')
            await save_conversation(user_id, 'assistant', f"Restarted {container_name}")
            await save_command(user_id, f'/restart {container_name}', 'Container restarted')
        
        # Handle stop confirmation
        elif data.startswith("stop_confirm_"):
            container_name = data.replace("stop_confirm_", "")
            await query.edit_message_text(f"🛑 Stopping `{container_name}`...")
            
            stop_container(container_name)
            await query.edit_message_text(
                format_success(f"Container `{container_name}` stopped successfully"),
                parse_mode='Markdown'
            )
            
            user_id = update.effective_user.id
            await save_conversation(user_id, 'user', f'/stop {container_name}')
            await save_conversation(user_id, 'assistant', f"Stopped {container_name}")
            await save_command(user_id, f'/stop {container_name}', 'Container stopped')
    
    except ValueError as e:
        await query.edit_message_text(format_error(str(e)), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in docker confirmation: {e}", exc_info=True)
        await query.edit_message_text(format_error(f"Failed: {e}"), parse_mode='Markdown')
