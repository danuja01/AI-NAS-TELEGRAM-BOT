"""
Root access command handlers.
Allows temporary elevated access to all file system paths.
"""

import logging
import subprocess
import asyncio
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


@require_auth
@rate_limit
async def ssh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ssh <command> - Execute shell commands (root access required)."""
    user_id = update.effective_user.id
    
    # Check if user has active root session
    if not RootSessionManager.is_root_session_active(user_id):
        await update.message.reply_text(
            format_error(
                "❌ **Root Access Required**\n\n"
                "The `/ssh` command requires an active root session.\n"
                "Use `/rootlogin <password>` to gain access."
            )
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/ssh <command>`\n\n"
            "**Examples:**\n"
            "• `/ssh ls -la`\n"
            "• `/ssh mkdir test`\n"
            "• `/ssh df -h`\n"
            "• `/ssh docker ps`\n\n"
            "⚠️ All commands are logged and executed with full privileges.",
            parse_mode='Markdown'
        )
        return
    
    command = ' '.join(context.args)
    
    # Change working directory to /app/documents for relative commands
    # This makes 'ls' show documents folder instead of /app (bot code)
    if not command.startswith('cd ') and not command.startswith('/'):
        command = f'cd /app/documents && {command}'
    
    try:
        # Log the command execution
        logger.warning(f"User {user_id} executing SSH command: {command}")
        
        # Send a "processing" message
        status_msg = await update.message.reply_text(
            f"⚙️ Executing: `{command}`...",
            parse_mode='Markdown'
        )
        
        # Execute the command with a timeout
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        
        try:
            # Wait for command with 60 second timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=60.0
            )
            
            exit_code = process.returncode
            
            # Decode output
            stdout_text = stdout.decode('utf-8', errors='replace').strip()
            stderr_text = stderr.decode('utf-8', errors='replace').strip()
            
            # Format response
            response = f"**Command:** `{command}`\n\n"
            
            if exit_code == 0:
                response += f"✅ **Exit Code:** {exit_code}\n\n"
            else:
                response += f"❌ **Exit Code:** {exit_code}\n\n"
            
            if stdout_text:
                # Truncate if too long (Telegram limit ~4096 chars)
                if len(stdout_text) > 3500:
                    stdout_text = stdout_text[:3500] + "\n... (truncated)"
                response += f"**Output:**\n```\n{stdout_text}\n```\n\n"
            
            if stderr_text:
                if len(stderr_text) > 500:
                    stderr_text = stderr_text[:500] + "\n... (truncated)"
                response += f"**Errors:**\n```\n{stderr_text}\n```"
            
            if not stdout_text and not stderr_text:
                response += "_No output_"
            
            # Delete the "processing" message and send result
            await status_msg.delete()
            await update.message.reply_text(response, parse_mode='Markdown')
            
            # Save to command history
            await save_command(
                user_id, 
                f'/ssh {command}', 
                f'Exit code: {exit_code}'
            )
        
        except asyncio.TimeoutError:
            await status_msg.delete()
            await update.message.reply_text(
                format_error(
                    f"❌ **Command Timeout**\n\n"
                    f"Command: `{command}`\n\n"
                    f"The command took longer than 60 seconds to execute."
                )
            )
            # Try to kill the process
            try:
                process.kill()
            except:
                pass
    
    except Exception as e:
        logger.error(f"Error in ssh_command: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(
                f"❌ **Command Execution Failed**\n\n"
                f"Command: `{command}`\n"
                f"Error: {str(e)}"
            )
        )


@require_auth
@rate_limit
async def cd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cd <path> - Change working directory (root access required)."""
    user_id = update.effective_user.id
    
    # Check if user has active root session
    if not RootSessionManager.is_root_session_active(user_id):
        await update.message.reply_text(
            format_error(
                "❌ **Root Access Required**\n\n"
                "The `/cd` command requires an active root session.\n"
                "Use `/rootlogin <password>` to gain access."
            )
        )
        return
    
    if not context.args:
        # Show current working directory
        current_dir = RootSessionManager.get_working_directory(user_id)
        if current_dir:
            await update.message.reply_text(
                f"📂 **Current Working Directory:**\n`{current_dir}`\n\n"
                f"**Navigation:**\n"
                f"• `/cd <path>` - Change to absolute path\n"
                f"• `/cd media` - Change to media (relative)\n"
                f"• `/cd root` - Go to disk root\n"
                f"• `/cd ..` - Go up one directory",
                parse_mode='Markdown'
            )
        else:
            import config
            default_path = config.DOCUMENT_PATH or '/app/documents'
            await update.message.reply_text(
                f"📂 **No Working Directory Set**\n\n"
                f"Default path: `{default_path}`\n\n"
                f"**Navigation:**\n"
                f"• `/cd <path>` - Change to absolute path\n"
                f"• `/cd media` - Relative path navigation\n"
                f"• `/cd root` - Go to disk root\n"
                f"• `/cd ..` - Go up one directory\n"
                f"• `/cd` - Show current directory",
                parse_mode='Markdown'
            )
        return
    
    target_path = ' '.join(context.args)
    
    # Handle special shortcuts
    import config
    if target_path.lower() == 'root':
        if hasattr(config, 'DISK_ROOT_PATH'):
            target_path = config.DISK_ROOT_PATH
        else:
            await update.message.reply_text(
                format_error("DISK_ROOT_PATH not configured in settings")
            )
            return
    elif target_path == '..':
        # Go up one directory
        current_dir = RootSessionManager.get_working_directory(user_id)
        if current_dir:
            target_path = str(Path(current_dir).parent)
        else:
            await update.message.reply_text(
                format_error("No working directory set. Use `/cd <path>` first.")
            )
            return
    
    try:
        # Validate the path exists and is a directory
        from pathlib import Path
        
        # Handle relative paths based on current working directory
        if not target_path.startswith('/'):
            # Relative path - join with current working directory
            current_dir = RootSessionManager.get_working_directory(user_id)
            if current_dir:
                target_path = str(Path(current_dir) / target_path)
            else:
                # No working directory set, use DOCUMENT_PATH as base
                base_path = config.DOCUMENT_PATH or '/app/documents'
                target_path = str(Path(base_path) / target_path)
        
        path = Path(target_path).resolve()
        
        if not path.exists():
            await update.message.reply_text(
                format_error(f"Path does not exist: `{target_path}`")
            )
            return
        
        if not path.is_dir():
            await update.message.reply_text(
                format_error(f"Path is not a directory: `{target_path}`")
            )
            return
        
        # Validate path is within allowed disk root (if configured)
        import config
        if hasattr(config, 'DISK_ROOT_PATH') and config.DISK_ROOT_PATH:
            # Only validate if the disk root path actually exists
            disk_root_path = Path(config.DISK_ROOT_PATH)
            if disk_root_path.exists():
                disk_root = disk_root_path.resolve()
                try:
                    path.relative_to(disk_root)
                except ValueError:
                    await update.message.reply_text(
                        format_error(
                            f"❌ **Invalid Path**\n\n"
                            f"Path must be within: `{config.DISK_ROOT_PATH}`"
                        )
                    )
                    return
        
        # Set working directory
        if RootSessionManager.set_working_directory(user_id, str(path)):
            # Shorten path for display if it's long
            display_path = str(path)
            if len(display_path) > 60:
                display_path = "..." + display_path[-57:]
            
            await update.message.reply_text(
                format_success(
                    f"📂 **Working Directory Changed**\n\n"
                    f"**New Path:** `{display_path}`\n\n"
                    f"💡 Use `/ls` to view contents\n"
                    f"💡 Use `/cd` without arguments to see current directory"
                )
            )
            await save_command(user_id, f'/cd {target_path}', 'Directory changed')
            logger.warning(f"User {user_id} changed working directory to: {path}")
        else:
            await update.message.reply_text(
                format_error("Failed to set working directory")
            )
    
    except Exception as e:
        logger.error(f"Error in cd_command: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(f"Failed to change directory: {str(e)}")
        )
