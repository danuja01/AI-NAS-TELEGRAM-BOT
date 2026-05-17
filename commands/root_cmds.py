"""
Root access command handlers.
Allows temporary elevated access to all file system paths.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.formatters import format_success, format_error
from utils.root_session import RootSessionManager
from database.memory import save_command

logger = logging.getLogger(__name__)


@require_auth
@rate_limit
async def rootlogin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rootlogin <password> - Activate temporary root access."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/rootlogin <password>`\n\n"
            "⚠️ Root access grants full file system access for 30 minutes.\n"
            "All root actions are logged for security audit.",
            parse_mode='Markdown'
        )
        return
    
    password = ' '.join(context.args)
    
    try:
        # Attempt authentication
        if RootSessionManager.authenticate(user_id, password):
            await update.message.reply_text(
                format_success(
                    "🔓 **Root Access Granted**\n\n"
                    "You now have full file system access for **30 minutes**.\n\n"
                    "⚠️ All actions are logged.\n"
                    "Use `/rootstatus` to check remaining time.\n"
                    "Use `/rootlogout` to end session early."
                )
            )
            await save_command(user_id, '/rootlogin', 'Root access granted')
            logger.warning(f"User {user_id} gained root access")
        else:
            await update.message.reply_text(
                format_error(
                    "❌ **Authentication Failed**\n\n"
                    "Invalid password. This incident has been logged."
                )
            )
            await save_command(user_id, '/rootlogin', 'Failed - invalid password')
            logger.warning(f"Failed root login attempt by user {user_id}")
    
    except Exception as e:
        logger.error(f"Error in rootlogin_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Root login failed: {e}"))


@require_auth
@rate_limit
async def rootlogout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rootlogout - End root access session."""
    user_id = update.effective_user.id
    
    try:
        if RootSessionManager.logout(user_id):
            await update.message.reply_text(
                format_success(
                    "🔒 **Root Session Ended**\n\n"
                    "File access restored to normal permissions."
                )
            )
            await save_command(user_id, '/rootlogout', 'Root session ended')
            logger.warning(f"User {user_id} ended root session")
        else:
            await update.message.reply_text(
                "ℹ️ You don't have an active root session."
            )
    
    except Exception as e:
        logger.error(f"Error in rootlogout_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Logout failed: {e}"))


@require_auth
@rate_limit
async def rootstatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rootstatus - Check root session status."""
    user_id = update.effective_user.id
    
    try:
        session_info = RootSessionManager.get_session_info(user_id)
        
        if session_info:
            minutes = session_info['remaining_minutes']
            seconds = session_info['remaining_seconds'] % 60
            
            await update.message.reply_text(
                f"🔓 **Root Session Active**\n\n"
                f"**Started:** {session_info['started_at'].strftime('%H:%M:%S')}\n"
                f"**Expires:** {session_info['expires_at'].strftime('%H:%M:%S')}\n"
                f"**Time Remaining:** {minutes}m {seconds}s\n\n"
                f"⚠️ All actions are being logged.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🔒 **No Active Root Session**\n\n"
                "You are using standard file permissions.\n"
                "Use `/rootlogin <password>` to activate root access.",
                parse_mode='Markdown'
            )
        
        await save_command(user_id, '/rootstatus', 'Status checked')
    
    except Exception as e:
        logger.error(f"Error in rootstatus_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Status check failed: {e}"))
