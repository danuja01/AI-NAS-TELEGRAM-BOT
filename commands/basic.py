"""
Basic command handlers for the NAS Telegram AI Assistant.
Includes /start and /help commands.
"""

import logging

import config
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit

logger = logging.getLogger(__name__)

# Short HTML snippets for /help buttons (Telegram HTML: no arbitrary tags; stick to b/code/br).
HELP_SECTION_BODIES: dict[str, str] = {
    "mon": (
        "<b>Monitoring</b>\n\n"
        "<code>/status</code> overview\n"
        "<code>/cpu</code> <code>/ram</code> <code>/disk</code>\n"
        "<code>/temps</code> <code>/network</code> <code>/uptime</code>\n"
        "<code>/health</code> score\n"
        "<code>/smart</code> <code>/drives</code> SMART\n"
        "<code>/hdddetail</code> HDD detail + samples"
    ),
    "dock": (
        "<b>Docker · storage</b>\n\n"
        "<code>/docker</code> dashboard (df, counts, table)\n"
        "<code>/containers</code> compact list + CPU/RAM\n"
        "<code>/dscan</code> full scan · <code>/dhealth</code> report\n"
        "<code>/dclean</code> · <code>/dprune</code> · <code>/daggressive</code>\n"
        "<code>/dimages</code> · <code>/dbigfiles</code> · <code>/dlogs</code>\n"
        "<code>/dstart</code> · <code>/drestart</code> · "
        "<code>/dstop</code> · <code>/dtail</code>"
    ),
    "files": (
        "<b>Files</b>\n\n"
        "<code>/files</code> browse docs path\n"
        "<code>/ls</code> <code>[path]</code> · <code>/ls --all</code>\n"
        "<code>/find</code> · <code>/tree</code> · <code>/storage</code>\n"
        "<code>/download</code> · <code>/uploadfile</code>\n"
        "<code>/cd</code> (root session)"
    ),
    "ai": (
        "<b>AI</b>\n\n"
        "<code>/ask</code> docs (RAG) · <code>/chat</code>\n"
        "<code>/summarize</code> · <code>/explain</code>\n"
        "<code>/analyze</code> · <code>/think</code>\n"
        "<code>/websearch</code> · <code>/index</code>\n"
        "<code>/clear</code> · <code>/cancel</code> pending prompts"
    ),
    "srv": (
        "<b>Services · host</b>\n\n"
        "<code>/services</code> · <code>/restart_service</code>\n"
        "<code>/reboot</code> · <code>/shutdown</code>\n"
        "<code>/updates</code> · <code>/omv_updates</code> · <code>/upgrade</code>\n"
        "<code>/rootlogin</code> · <code>/rootstatus</code> · "
        "<code>/rootlogout</code> · <code>/ssh</code>"
    ),
}

_HELP_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Monitoring", callback_data="help:mon"),
            InlineKeyboardButton("Docker · storage", callback_data="help:dock"),
        ],
        [
            InlineKeyboardButton("Files", callback_data="help:files"),
            InlineKeyboardButton("AI", callback_data="help:ai"),
        ],
        [InlineKeyboardButton("Services · host", callback_data="help:srv")],
    ]
)


def _help_user_allowed(user_id: int) -> bool:
    if not config.ALLOWED_USER_IDS:
        return True
    return user_id in config.ALLOWED_USER_IDS


@require_auth
@rate_limit
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Welcome message."""
    user = update.effective_user

    welcome_msg = f"""
👋 **Welcome to NAS AI Assistant, {user.first_name}!**

I'm your private DevOps and AI assistant for managing your NAS. I can help you with:

🖥 **System Monitoring**
Monitor CPU, RAM, disk, temperatures, and system health

🐳 **Docker Management**
Dashboard, storage scans, and container control

📁 **File System**
Browse, search, and manage files safely

⚙️ **Services**
Manage system services, reboot, shutdown

🤖 **AI Assistant**
Ask questions about your documents using RAG
Search the internet for current information

📊 **Alerts**
Automatic notifications for system issues

Use /help for a compact guide (full lists under the buttons).
"""
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")
    logger.info(f"User {user.id} started the bot")


@require_auth
@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Short /help + category buttons (details on tap)."""
    intro = (
        "<b>NAS Assistant</b>\n"
        "Monitoring, Docker, files, and AI in one place.\n\n"
        "<b>Tip:</b> type <code>/</code> — Telegram shows every command with a short hint.\n\n"
        "<b>Highlights</b>\n"
        "• <code>/status</code> · <code>/docker</code> · <code>/containers</code>\n"
        "• <code>/ls</code> · <code>/ask</code> · <code>/services</code>\n\n"
        "<i>Tap a category below for the full command list.</i>"
    )
    await update.message.reply_text(
        intro,
        parse_mode=ParseMode.HTML,
        reply_markup=_HELP_KEYBOARD,
        disable_web_page_preview=True,
    )
    logger.info("Help command used by user %s", update.effective_user.id)


async def help_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline keyboard under /help — send one category block."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("help:"):
        return

    user = query.from_user
    if not _help_user_allowed(user.id):
        await query.answer("Unauthorized.", show_alert=True)
        return

    key = query.data.replace("help:", "", 1)
    body = HELP_SECTION_BODIES.get(key)
    if not body:
        await query.answer()
        return

    await query.answer()
    if query.message:
        await query.message.reply_text(
            body,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
