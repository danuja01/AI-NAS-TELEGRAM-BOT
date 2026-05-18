"""
File system command handlers.
"""

import logging
import os
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

import config
from utils.security import require_auth, rate_limit
from utils.formatters import format_file_list, format_file_list_numbered, format_error, format_bytes
from utils.followup_state import set_cmd_pending_exclusive, FOLLOWUP_FIND, FOLLOWUP_DOWNLOAD
from utils.file_cache import FileCache
from services.file_service import (
    list_directory, search_files, get_directory_tree,
    get_folder_sizes, preview_file, get_storage_summary
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)

# Bot API document upload limit (leave headroom under 50 MiB hard cap)
TELEGRAM_DOCUMENT_MAX_BYTES = 49 * 1024 * 1024

_CMD_HINT_FIND = (
    "You used /find without a search term.\n\n"
    "Send your **next message** as the filename pattern to search for, or `/cancel` to abort.\n\n"
    "Example: `report.pdf`"
)

_CMD_HINT_DOWNLOAD = (
    "You used /download without numbers.\n\n"
    "Send your **next message** with one or more file numbers (from your last `/ls`), "
    "e.g. `3` or `1 3 5` or `1-5`, or `/cancel` to abort.\n\n"
    "First run `/ls` so files are numbered in the cache."
)


def parse_number_ranges(args: list) -> list:
    """
    Parse number ranges from command arguments.
    
    Examples:
        ["1"] -> [1]
        ["1", "3", "5"] -> [1, 3, 5]
        ["1-5"] -> [1, 2, 3, 4, 5]
        ["1-3", "7", "10-12"] -> [1, 2, 3, 7, 10, 11, 12]
    
    Args:
        args: List of argument strings
    
    Returns:
        Sorted list of unique numbers
    """
    numbers = []
    for arg in args:
        try:
            if '-' in arg and not arg.startswith('-'):
                # Range format: "1-5"
                parts = arg.split('-', 1)
                start = int(parts[0])
                end = int(parts[1])
                if start > end:
                    start, end = end, start
                numbers.extend(range(start, end + 1))
            else:
                # Single number
                numbers.append(int(arg))
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse number argument '{arg}': {e}")
            continue
    
    return sorted(set(numbers))


async def run_find(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, pattern: str):
    """Search for files (from /find args or follow-up text)."""
    try:
        await update.message.reply_text(f"🔍 Searching for '{pattern}'...")

        results = search_files(pattern, user_id=user_id)

        if not results:
            await update.message.reply_text(f"❌ No files found matching '{pattern}'")
            return

        message = f"🔍 **Search Results for '{pattern}'**\n\n"
        message += f"Found {len(results)} file(s):\n\n"

        for result in results[:20]:  # Show max 20 results
            icon = "📁" if result["is_dir"] else "📄"
            size = format_bytes(result["size"]) if not result["is_dir"] else ""
            message += f"{icon} `{result['name']}` {size}\n"
            message += f"   {result['path']}\n\n"

        if len(results) > 20:
            message += f"\n_...and {len(results) - 20} more results_"

        await update.message.reply_text(message, parse_mode="Markdown")

        result_summary = f"Found {len(results)} files matching '{pattern}'"
        await save_conversation(user_id, "user", f"/find {pattern}")
        await save_conversation(user_id, "assistant", message, command_output=result_summary)
        await save_command(user_id, f"/find {pattern}", f"{len(results)} results")

    except PermissionError as e:
        await update.message.reply_text(format_error(str(e)))
    except Exception as e:
        logger.error(f"Error in run_find: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Search failed: {e}"))


async def run_download_from_tokens(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, tokens: list
):
    """Download by index tokens (from /download args split or follow-up)."""
    try:
        numbers = parse_number_ranges(tokens)

        if not numbers:
            await update.message.reply_text(format_error("No valid file numbers provided."))
            return

        # Check if single file or multiple files
        if len(numbers) == 1:
            # Single file download (existing behavior)
            number = numbers[0]
            file_info = FileCache.get_file(user_id, number)

            if not file_info:
                await update.message.reply_text(
                    "❌ File not found in cache.\n\n"
                    "Use `/ls <path>` first to list files, then use `/download <number>`.\n\n"
                    "Note: Cache expires after 10 minutes.",
                    parse_mode="Markdown",
                )
                return

            file_path = file_info["path"]

            # Validate path and security
            from utils.security import validate_path

            if not validate_path(file_path, user_id=user_id):
                await update.message.reply_text(format_error("Access denied to this file."))
                return

            # Check file exists and is a regular file (not a dir / broken symlink)
            path_obj = Path(file_path)
            if not path_obj.is_file():
                await update.message.reply_text(format_error("Path is not a regular file or no longer exists"))
                return

            file_size = path_obj.stat().st_size
            if file_size > TELEGRAM_DOCUMENT_MAX_BYTES:
                await update.message.reply_text(
                    format_error(
                        f"File too large for Telegram ({format_bytes(file_size)}). "
                        f"Max is {format_bytes(TELEGRAM_DOCUMENT_MAX_BYTES)}. "
                        "Use SSH or copy from the NAS directly for large files."
                    )
                )
                return

            send_name = file_info.get("name") or path_obj.name

            # Send file (pass path string; PTB reads reliably; open file handles can fail on some mounts)
            status_msg = await update.message.reply_text(
                f"📤 Preparing to send `{send_name}`...",
                parse_mode="Markdown",
            )

            try:
                await update.message.reply_document(
                    document=str(path_obj.resolve()),
                    filename=send_name,
                    caption=f"📄 {send_name}\nSize: {format_bytes(file_size)}",
                )

                await status_msg.delete()
                logger.info(f"User {user_id} downloaded file: {send_name}")
                await save_command(user_id, f"/download {number}", send_name)

            except Exception as e:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                logger.error(f"Single-file send failed: {e}", exc_info=True)
                raise

        else:
            # Multiple files - create ZIP
            files = FileCache.get_files(user_id, numbers)

            if not files:
                await update.message.reply_text(
                    "❌ No files found in cache.\n\n"
                    "Use `/ls <path>` first to list files, then use `/download <numbers>`.\n\n"
                    "Note: Cache expires after 10 minutes.",
                    parse_mode="Markdown",
                )
                return

            # Validate all file paths
            from utils.security import validate_path

            valid_files = []
            for file_info in files:
                if validate_path(file_info["path"], user_id=user_id) and os.path.exists(file_info["path"]):
                    valid_files.append(file_info)

            if not valid_files:
                await update.message.reply_text(format_error("No valid files found or access denied."))
                return

            # Show status
            status_msg = await update.message.reply_text(
                f"📦 Creating archive with {len(valid_files)} file(s)...",
                parse_mode="Markdown",
            )

            try:
                # Create temporary ZIP file
                import tempfile
                from datetime import datetime
                from services.file_service import create_zip_archive

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                zip_filename = f"files_{timestamp}.zip"

                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
                    temp_zip_path = tmp_file.name

                success, zip_path, zip_size, error_msg = create_zip_archive(valid_files, temp_zip_path)

                if not success:
                    await status_msg.delete()
                    await update.message.reply_text(format_error(f"Failed to create archive: {error_msg}"))
                    try:
                        os.unlink(temp_zip_path)
                    except OSError:
                        pass
                    return

                await status_msg.edit_text(
                    f"📤 Sending archive ({format_bytes(zip_size)})...",
                    parse_mode="Markdown",
                )

                if zip_size > TELEGRAM_DOCUMENT_MAX_BYTES:
                    await status_msg.delete()
                    await update.message.reply_text(
                        format_error(
                            f"Archive too large for Telegram ({format_bytes(zip_size)}). "
                            f"Max is {format_bytes(TELEGRAM_DOCUMENT_MAX_BYTES)}. "
                            "Download fewer files or smaller items."
                        )
                    )
                    try:
                        os.unlink(temp_zip_path)
                    except OSError:
                        pass
                    return

                await update.message.reply_document(
                    document=str(Path(zip_path).resolve()),
                    filename=zip_filename,
                    caption=f"📦 Archive with {len(valid_files)} file(s)\nSize: {format_bytes(zip_size)}",
                )

                await status_msg.delete()

                try:
                    os.unlink(temp_zip_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp ZIP file: {e}")

                logger.info(f"User {user_id} downloaded {len(valid_files)} files as ZIP")
                await save_command(
                    user_id, f'/download {" ".join(map(str, numbers))}', f"{len(valid_files)} files"
                )

            except Exception as e:
                try:
                    await status_msg.delete()
                except Exception:
                    pass
                if "temp_zip_path" in locals():
                    try:
                        os.unlink(temp_zip_path)
                    except OSError:
                        pass
                logger.error(f"Bulk download / ZIP send failed: {e}", exc_info=True)
                raise

    except ValueError as e:
        await update.message.reply_text(format_error(f"Invalid number format: {str(e)}"))
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Download failed: {e}"))


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
    """Handle /ls <path> [--all] command - List directory contents with numbered files."""
    user_id = update.effective_user.id
    
    # Check for --all flag (handle both -- and em-dash — from Telegram)
    apply_filter = True
    args = list(context.args) if context.args else []
    if '--all' in args:
        args.remove('--all')
        apply_filter = False
    elif '—all' in args:  # Telegram converts -- to em-dash
        args.remove('—all')
        apply_filter = False
    elif '-all' in args:  # Single dash variant
        args.remove('-all')
        apply_filter = False
    
    # Handle path resolution
    if not args:
        # Try to get working directory from root session first
        from utils.root_session import RootSessionManager
        working_dir = RootSessionManager.get_working_directory(user_id)
        if working_dir:
            path = working_dir
        else:
            # Default to DOCUMENT_PATH or /app/documents
            path = config.DOCUMENT_PATH or '/app/documents'
    else:
        input_path = ' '.join(args)
        # If relative path (doesn't start with /), prepend working directory or /app/documents
        if not input_path.startswith('/'):
            from utils.root_session import RootSessionManager
            working_dir = RootSessionManager.get_working_directory(user_id)
            base_path = working_dir if working_dir else '/app/documents'
            path = os.path.join(base_path, input_path)
        else:
            path = input_path
    
    try:
        files = list_directory(path, user_id=user_id, apply_filter=apply_filter)
        
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
        set_cmd_pending_exclusive(context, FOLLOWUP_FIND)
        await update.message.reply_text(_CMD_HINT_FIND, parse_mode="Markdown")
        return

    pattern = " ".join(context.args)
    await run_find(update, context, user_id, pattern)


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
    """Handle /download <number(s)> - Download single or multiple files from last ls."""
    user_id = update.effective_user.id

    if not context.args:
        set_cmd_pending_exclusive(context, FOLLOWUP_DOWNLOAD)
        await update.message.reply_text(_CMD_HINT_DOWNLOAD, parse_mode="Markdown")
        return

    await run_download_from_tokens(update, context, user_id, list(context.args))


async def _process_file_upload(update: Update, file_obj, filename: str, subfolder: str = None):
    """Internal helper to process file upload."""
    user_id = update.effective_user.id
    
    try:
        # Determine target folder
        if subfolder:
            target_dir = os.path.join('/app/documents', subfolder)
        else:
            target_dir = '/app/documents'
        
        # Create directory if needed
        os.makedirs(target_dir, exist_ok=True)
        
        # Get file from Telegram
        file = await file_obj.get_file()
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
    if not update.message.document and not update.message.photo:
        await update.message.reply_text(
            "📤 **Upload File to NAS**\n\n"
            "**Usage:**\n"
            "1. Attach a file/photo and use `/uploadfile <subfolder>` as caption (optional)\n"
            "2. Or send `/uploadfile <subfolder>` and then attach file\n\n"
            "**Examples:**\n"
            "• Send file with caption: `/uploadfile DANUJA`\n"
            "• Send file with caption: `/uploadfile` (uploads to /app/documents/)\n\n"
            "⚠️ Root access is required for uploads.",
            parse_mode='Markdown'
        )
        return
    
    # Get document or photo
    if update.message.document:
        file_obj = update.message.document
        filename = file_obj.file_name
    elif update.message.photo:
        # Get the largest photo
        file_obj = update.message.photo[-1]
        filename = f"photo_{file_obj.file_unique_id}.jpg"
    else:
        await update.message.reply_text(format_error("No file attached"))
        return
    
    # Get subfolder from command args
    subfolder = ' '.join(context.args) if context.args else None
    
    await _process_file_upload(update, file_obj, filename, subfolder)


@require_auth
@rate_limit
async def handle_file_with_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle files/photos sent with /uploadfile in caption."""
    user_id = update.effective_user.id
    
    # Check if caption starts with /uploadfile
    caption = update.message.caption or ""
    if not caption.startswith('/uploadfile'):
        return
    
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
    
    # Parse caption for subfolder argument
    parts = caption.split()
    subfolder = ' '.join(parts[1:]) if len(parts) > 1 else None
    
    # Get document or photo
    if update.message.document:
        file_obj = update.message.document
        filename = file_obj.file_name
    elif update.message.photo:
        # Get the largest photo
        file_obj = update.message.photo[-1]
        filename = f"photo_{file_obj.file_unique_id}.jpg"
    else:
        await update.message.reply_text(format_error("No file attached"))
        return
    
    await _process_file_upload(update, file_obj, filename, subfolder)
