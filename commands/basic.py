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
from utils.telegram_reply import reply_text_chunked

logger = logging.getLogger(__name__)

# One line per command — command in <code>, then a short explanation (Telegram HTML).
HELP_SECTION_BODIES: dict[str, str] = {
    "mon": (
        "<b>Monitoring</b>\n\n"
        "<code>/status</code> — Full system overview\n"
        "<code>/cpu</code> — CPU usage and load average\n"
        "<code>/ram</code> — Memory usage and swap\n"
        "<code>/disk</code> — Disk usage (live) + OpenMediaVault panels when <code>omv-rpc</code> works on the host\n"
        "<code>/temps</code> — Temperature sensors\n"
        "<code>/network</code> — Interfaces: UP/DOWN, IPs, MTU, traffic, default route, Tailscale IPv4 when available\n"
        "<code>/netpublic</code> — Outbound public IPv4 (HTTPS), local outbound IP, gateway, Tailscale\n"
        "<code>/netping &lt;host&gt;</code> — ICMP ping (4 packets); hostname or IP\n"
        "<code>/uptime</code> — How long the NAS has been up\n"
        "<code>/health</code> — Overall health score with issues list\n"
        "<code>/smart</code> — Drive health (SMART summary)\n"
        "<code>/drives</code> — Same summary as /smart\n"
        "<code>/hdddetail</code> — HDD detail: spin counters, hdparm state, sample history\n"
        "<code>/monitors</code> — Uptime Kuma-style monitor list (auto + manual)\n"
        "<code>/monitor_add</code> — Add HTTP/HTTPS/TCP/ping/DNS/SSL/docker monitor\n"
        "<code>/monitor_discover</code> — Auto-create monitors for running containers\n"
        "<code>/monitor_report</code> — Weekly uptime & incident summary\n"
        "<code>/monitor_stats</code> — MTBF/MTTR + latency sparkline for one monitor\n"
        "<code>/monitor_dashboard</code> — Enable/disable uptime web UI (Tailscale link)\n"
        "<code>/monitor_groups</code> — Monitor groups · <code>/monitor_tag</code> tags\n"
        "<code>/monitor_images</code> — Scan Docker image updates\n"
        "<code>/alerts</code> — Unacknowledged alerts · <code>/alert_ack all</code> or <code>/alert_ack &lt;id&gt;</code>\n"
        "<code>/crowdsec</code> — CrowdSec alerts, bans, and decisions (when enabled)\n"
        "<code>/security</code> — AI NAS Security Assistant summary (CrowdSec)\n"
        "<code>/orchestrator</code> — Resource orchestrator status (pause/stop under pressure)\n"
        "<code>/mitigate_now</code> · <code>/restore_now</code> — Manual orchestrator (admin)\n"
        "<i>Background alerts: CPU/RAM/disk/SMART/Docker/systemd + CrowdSec + custom monitors.</i>\n"
    ),
    "dock": (
        "<b>Docker · storage</b>\n\n"
        "<code>/docker</code> — Dashboard: disk usage summary, counts, container table\n"
        "<code>/containers</code> — Compact running/stopped list with CPU/RAM\n"
        "<code>/dscan</code> — Deep scan: Docker paths, large files, prune estimates\n"
        "<code>/dclean</code> — Safe cleanup (stopped containers, unused images, cache; confirms)\n"
        "<code>/dprune</code> — Quick prune: dangling images and build cache\n"
        "<code>/daggressive</code> — Extra cleanup (unused networks + apt cache; 2-step confirm)\n"
        "<code>/dimages</code> — All images flagged unused/dangling/in use\n"
        "<code>/dbigfiles</code> — Largest files under allow-listed paths\n"
        "<code>/dlogs</code> — Very large log files on scanned paths\n"
        "<code>/dhealth</code> — NAS + Docker combined health snapshot\n"
        "<code>/dstart</code> — Start a container by name\n"
        "<code>/drestart</code> — Restart a container (confirmation)\n"
        "<code>/dstop</code> — Stop a container (confirmation)\n"
        "<code>/dtail</code> — Tail logs from a container\n"
        "<i>Older names /restart /stop /logs redirect to drestart dstop dtail.</i>\n"
    ),
    "files": (
        "<b>Files</b>\n\n"
        "<code>/files</code> — Browse the default document folder\n"
        "<code>/find</code> — Search filenames under allowed roots\n"
        "<code>/tree</code> — Directory tree outline\n"
        "<code>/storage</code> — Disk usage summary for key paths\n"
    ),
    "ai": (
        "<b>AI</b>\n\n"
        "<code>/ask</code> — Ask your indexed documents (RAG)\n"
        "<code>/chat</code> — Free-form chat with the model (in a **private** chat, a normal message without `/` uses the same flow)\n"
        "<code>/summarize</code> — Summarize a topic from documents\n"
        "<code>/explain</code> — Explain a term from documents\n"
        "<code>/analyze</code> — Deeper analysis of pasted or follow-up text\n"
        "<code>/think</code> — Reasoning-focused answer\n"
        "<code>/websearch</code> — Web search + answer\n"
        "<code>/index</code> — Re-build the document index (admin)\n"
        "<code>/clear</code> — Clear conversation history\n"
        "<code>/cancel</code> — Abort when the bot is waiting for your next message\n"
    ),
    "srv": (
        "<b>Services · host</b>\n\n"
        "<code>/services</code> — List systemd services and status\n"
        "<code>/restart_service</code> — Restart one service by name\n"
        "<code>/reboot</code> — Reboot the NAS (confirmation)\n"
        "<code>/shutdown</code> — Shut down the NAS (confirmation)\n"
        "<code>/smtptest &lt;email&gt;</code> — Test SMTP (EMAIL_ALERT_RECIPIENTS only)\n"
        "<code>/updates</code> — Check APT / OMV updates on the host\n"
        "<code>/omv_updates</code> — Updates plus OMV-specific note\n"
        "<code>/upgrade</code> — Run omv-upgrade (strong confirmation)\n"
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
    from utils.security import is_user_authorized

    return is_user_authorized(user_id)


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
        "• <code>/status</code> — system snapshot\n"
        "• <code>/docker</code> — Docker dashboard\n"
        "• <code>/containers</code> — quick container list\n"
        "• <code>/files</code> / <code>/ask</code> / <code>/services</code>\n\n"
        "<i>Tap a category — each message lists one command per line with a short description.</i>"
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
        await reply_text_chunked(
            update,
            body,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
