"""
File system command handlers.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from utils.security import require_auth, rate_limit
from utils.formatters import format_file_list, format_error
from utils.followup_state import set_cmd_pending_exclusive, FOLLOWUP_FIND
from services.file_service import (
    list_directory, search_files, get_directory_tree,
    get_storage_summary
)
from database.memory import save_conversation, save_command

logger = logging.getLogger(__name__)

_CMD_HINT_FIND = (
    "You used /find without a search term.\n\n"
    "Send your **next message** as the filename pattern to search for, or `/cancel` to abort.\n\n"
    "Example: `report.pdf`"
)


async def run_find(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, pattern: str):
    """Search for files (from /find args or follow-up text)."""
    try:
        await update.message.reply_text(f"🔍 Searching for '{pattern}'...")

        results = search_files(pattern, user_id=user_id)

        if not results:
            await update.message.reply_text(f"❌ No files found matching '{pattern}'")
            return

        from utils.formatters import format_bytes

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

        await save_conversation(user_id, 'user', '/storage')
        await save_conversation(user_id, 'assistant', message)
        await save_command(user_id, '/storage', 'Storage summary')

    except Exception as e:
        logger.error(f"Error in storage_command: {e}", exc_info=True)
        await update.message.reply_text(format_error(f"Failed to get storage info: {e}"))
