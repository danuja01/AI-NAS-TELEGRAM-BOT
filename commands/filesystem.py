"""
File system command handlers.
"""

import logging
import os
from telegram import Update
from telegram.ext import ContextTypes

import config
from utils.security import require_auth, rate_limit
from utils.formatters import format_file_list, format_file_list_numbered, format_error, format_bytes
from utils.file_cache import FileCache
from services.file_service import (
    list_directory, search_files, get_directory_tree,
    get_folder_sizes, preview_file, get_storage_summary
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)


@require_auth
@rate_limit
async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /files command - Browse default document path."""
    user_id = update.effective_user.id
    
    if not config.DOCUMENT_PATH:
        await update.message.reply_text(
            "⚠️ No document path configured.\n\n"
            "Set DOCUMENT_PATH in .env file."
        )
        return
    
    try:
        files = list_directory(config.DOCUMENT_PATH)
        message = format_file_list(files, config.DOCUMENT_PATH)
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', '/files')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, '/files', f"{len(files)} items")
        
    except PermissionError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in files_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to list files: {e}"))


@require_auth
@rate_limit
async def ls_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ls <path> command - List directory contents with numbered files."""
    user_id = update.effective_user.id
    
    # Handle path resolution
    if not context.args:
        # Default to DOCUMENT_PATH or /app/documents
        path = config.DOCUMENT_PATH or '/app/documents'
    else:
        input_path = ' '.join(context.args)
        # If relative path (doesn't start with /), prepend /app/documents
        if not input_path.startswith('/'):
            path = os.path.join('/app/documents', input_path)
        else:
            path = input_path
    
    try:
        files = list_directory(path, user_id=user_id)
        
        # Store files in cache for download
        FileCache.store_files(user_id, files, path)
        
        # Format with numbers
        message = format_file_list_numbered(files, path)
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', f'/ls {path}')
        await save_conversation(user_id, 'assistant', message, 
                              command_output=f"Listed {len(files)} items in {path}")
        await save_command(user_id, f'/ls {path}', f"{len(files)} items")
        
    except PermissionError:
        await update.message.reply_text(
            format_error(f"Access to path '{path}' is not allowed.\n\nOnly paths within ALLOWED_PATHS can be accessed.\nUse `/rootlogin <password>` for full access.")
        )
    except FileNotFoundError:
        await update.message.reply_text(format_error(f"Path '{path}' does not exist"))
    except NotADirectoryError:
        await update.message.reply_text(format_error(f"'{path}' is not a directory"))
    except Exception as e:
        logger.error(f"Error in ls_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to list directory: {e}"))


@require_auth
@rate_limit
async def find_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /find <filename> command - Search for files."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/find <filename>`\n\n"
            "Example: `/find report.pdf`",
            parse_mode='Markdown'
        )
        return
    
    pattern = ' '.join(context.args)
    
    try:
        await update.message.reply_text(f"🔍 Searching for '{pattern}'...")
        
        results = search_files(pattern, user_id=user_id)
        
        if not results:
            await update.message.reply_text(f"❌ No files found matching '{pattern}'")
            return
        
        message = f"🔍 **Search Results for '{pattern}'**\n\n"
        message += f"Found {len(results)} file(s):\n\n"
        
        for result in results[:20]:  # Show max 20 results
            icon = "📁" if result['is_dir'] else "📄"
            size = format_bytes(result['size']) if not result['is_dir'] else ""
            message += f"{icon} `{result['name']}` {size}\n"
            message += f"   {result['path']}\n\n"
        
        if len(results) > 20:
            message += f"\n_...and {len(results) - 20} more results_"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        result_summary = f"Found {len(results)} files matching '{pattern}'"
        await save_conversation(user_id, 'user', f'/find {pattern}')
        await save_conversation(user_id, 'assistant', message, command_output=result_summary)
        await save_command(user_id, f'/find {pattern}', f"{len(results)} results")
        
    except PermissionError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in find_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Search failed: {e}"))


@require_auth
@rate_limit
async def tree_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tree [path] command - Show directory tree."""
    user_id = update.effective_user.id
    
    path = ' '.join(context.args) if context.args else config.DOCUMENT_PATH
    
    if not path:
        await update.message.reply_text("❌ No path specified and no default path configured")
        return
    
    try:
        await update.message.reply_text("🌳 Building directory tree...")
        
        tree_lines = get_directory_tree(path, max_depth=2)
        
        if not tree_lines:
            await update.message.reply_text("❌ Empty directory or access denied")
            return
        
        message = f"🌳 **Directory Tree: {path}**\n\n"
        message += "```\n" + '\n'.join(tree_lines[:50]) + "\n```"
        
        if len(tree_lines) > 50:
            message += f"\n_...and {len(tree_lines) - 50} more items_"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', f'/tree {path}')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, f'/tree {path}', 'Tree displayed')
        
    except PermissionError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in tree_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to build tree: {e}"))


@require_auth
@rate_limit
async def storage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /storage command - Show storage usage summary."""
    user_id = update.effective_user.id
    
    try:
        await update.message.reply_text("💾 Calculating storage usage...")
        
        summary = get_storage_summary()
        
        if not summary:
            await update.message.reply_text("⚠️ No storage information available")
            return
        
        message = "💾 **Storage Summary**\n\n"
        
        for storage in summary:
            message += f"**{storage['path']}**\n"
            message += f"  Total: {storage['total_gb']:.1f} GB\n"
            message += f"  Used: {storage['used_gb']:.1f} GB\n"
            message += f"  Free: {storage['free_gb']:.1f} GB\n"
            message += f"  Usage: {storage['percent']:.1f}%\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Save to conversation history
        await save_conversation(user_id, 'user', '/storage')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, '/storage', 'Storage summary')
        
    except Exception as e:
        logger.error(f"Error in storage_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to get storage info: {e}"))


@require_auth
@rate_limit
async def download_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /download <number> - Download file from last ls."""
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/download <number>`\n\n"
            "First use `/ls <path>` to list files with numbers.",
            parse_mode='Markdown'
        )
        return
    
    try:
        number = int(context.args[0])
        file_info = FileCache.get_file(user_id, number)
        
        if not file_info:
            await update.message.reply_text(
                "❌ File not found in cache.\n\n"
                "Use `/ls <path>` first to list files, then use `/download <number>`.\n\n"
                "Note: Cache expires after 10 minutes.",
                parse_mode='Markdown'
            )
            return
        
        file_path = file_info['path']
        
        # Validate path and security
        from utils.security import validate_path
        if not validate_path(file_path, user_id=user_id):
            await update.message.reply_text(
                format_error("Access denied to this file.")
            )
            return
        
        # Check file exists
        if not os.path.exists(file_path):
            await update.message.reply_text(
                format_error("File no longer exists")
            )
            return
        
        # Send file
        status_msg = await update.message.reply_text(
            f"📤 Preparing to send `{file_info['name']}`...",
            parse_mode='Markdown'
        )
        
        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=file_info['name'],
                    caption=f"📄 {file_info['name']}\nSize: {format_bytes(file_info['size'])}"
                )
            
            await status_msg.delete()
            logger.info(f"User {user_id} downloaded file: {file_info['name']}")
            await save_command(user_id, f'/download {number}', file_info['name'])
        
        except Exception as e:
            await status_msg.delete()
            raise e
        
    except ValueError:
        await update.message.reply_text(
            format_error("Invalid number. Please provide a valid file number.")
        )
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Download failed: {e}"))


@require_auth
@rate_limit
async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /uploadfile - Upload file to documents folder (requires root)."""
    user_id = update.effective_user.id
    
    # Check root access
    from utils.root_session import RootSessionManager
    if not RootSessionManager.is_root_session_active(user_id):
        await update.message.reply_text(
            format_error(
                "❌ **Root Access Required**\n\n"
                "File uploads require an active root session.\n"
                "Use `/rootlogin <password>` first."
            )
        )
        return
    
    # Check if file is attached
    if not update.message.document:
        await update.message.reply_text(
            "📤 **Upload File to NAS**\n\n"
            "**Usage:**\n"
            "1. Use `/uploadfile <subfolder>` (optional)\n"
            "2. Attach your file to the message\n\n"
            "**Examples:**\n"
            "• `/uploadfile DANUJA` (upload to /app/documents/DANUJA/)\n"
            "• `/uploadfile` (upload to /app/documents/)\n\n"
            "⚠️ Root access is required for uploads.",
            parse_mode='Markdown'
        )
        return
    
    try:
        document = update.message.document
        filename = document.file_name
        
        # Determine target folder
        if context.args:
            subfolder = ' '.join(context.args)
            target_dir = os.path.join('/app/documents', subfolder)
        else:
            target_dir = '/app/documents'
        
        # Create directory if needed
        os.makedirs(target_dir, exist_ok=True)
        
        # Get file from Telegram
        file = await document.get_file()
        target_path = os.path.join(target_dir, filename)
        
        # Check if file already exists
        if os.path.exists(target_path):
            await update.message.reply_text(
                f"⚠️ File `{filename}` already exists in `{target_dir}`.\n\n"
                f"Overwriting...",
                parse_mode='Markdown'
            )
        
        status_msg = await update.message.reply_text(
            f"📥 Uploading `{filename}`...",
            parse_mode='Markdown'
        )
        
        # Download file to server
        await file.download_to_drive(target_path)
        
        file_size = os.path.getsize(target_path)
        
        await status_msg.delete()
        await update.message.reply_text(
            f"✅ **File Uploaded Successfully!**\n\n"
            f"**Name:** `{filename}`\n"
            f"**Size:** {format_bytes(file_size)}\n"
            f"**Location:** `{target_path}`\n\n"
            f"💡 Use `/ls {os.path.dirname(target_path).replace('/app/documents/', '')}` to view",
            parse_mode='Markdown'
        )
        
        logger.warning(f"User {user_id} uploaded file: {target_path} ({format_bytes(file_size)})")
        await save_command(user_id, '/uploadfile', f"{filename} to {target_dir}")
        
    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Upload failed: {e}"))
