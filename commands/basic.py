"""
Basic command handlers for the NAS Telegram AI Assistant.
Includes /start and /help commands.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit

logger = logging.getLogger(__name__)


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
Control and monitor your Docker containers

📁 **File System**
Browse, search, and manage files safely

⚙️ **Services**
Manage system services, reboot, shutdown

🤖 **AI Assistant**
Ask questions about your documents using RAG
Search the internet for current information

📊 **Alerts**
Automatic notifications for system issues

Use /help to see all available commands.
"""
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')
    logger.info(f"User {user.id} started the bot")


@require_auth
@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - Show all available commands."""
    
    help_msg = """
📚 **Available Commands**

**📊 Monitoring**
`/status` - Comprehensive system overview
`/cpu` - CPU usage and load
`/ram` - Memory statistics
`/disk` - Disk usage
`/temps` - Temperature sensors
`/network` - Network statistics
`/uptime` - System uptime
`/health` - System health score
`/smart` - Drive health (SMART data)
`/drives` - List all drives
`/hdddetail` - HDD details: power/spin counters, hdparm state, sample history

**🐳 Docker & storage**
`/docker` — List Docker containers (CPU/RAM where available)
`/containers` — Same as `/docker`
`/ddocker` — Docker dashboard (system df + service state)
`/dscan` - Full Docker + disk scan
`/dclean` - Safe cleanup (confirm)
`/dprune` - Quick dangling prune
`/daggressive` - Aggressive cleanup (2-step confirm)
`/dimages` - List images (unused/dangling)
`/dbigfiles` - Largest files (allowlisted paths)
`/dlogs` - Huge log files
`/dhealth` - NAS + Docker health report
`/dstart` / `/drestart` / `/dstop` / `/dtail` - Container control

**📁 File System**
`/files` - Browse default document path
`/ls [path]` - List directory with numbered files
`/ls --all` - Show all folders (including hidden)
`/download <number>` - Download single file
`/download 1-3 7` - Bulk download as ZIP
`/uploadfile [subfolder]` - Upload file (requires root)
`/find <filename>` - Search for files
`/tree [path]` - Show directory tree
`/storage` - Storage usage summary
`/cd <path>` - Change working directory (requires root)
`/cd root` - Go to disk root (requires root)
`/cd` - Show current directory

**⚙️ Services**
`/services` - List system services
`/restart_service <name>` - Restart a service
`/reboot` - Reboot the system (requires confirmation)
`/shutdown` - Shutdown the system (requires confirmation)

**🤖 AI Assistant**
`/ask <question>` - Ask about your documents (RAG)
`/chat <message>` - General AI chat
`/summarize <topic>` - Summarize documents
`/explain <term>` - Explain from documents
`/analyze <text>` - Deep analysis (uses o1-mini)
`/think <question>` - Complex reasoning
`/websearch <query>` - Search the internet
`/index` - Re-index documents (admin only)
`/clear` - Clear conversation history
`/cancel` - Cancel when the bot is waiting for your next message (after /analyze, /ask, etc.)

**🔐 Root Access**
`/rootlogin <password>` - Temporary root access (30min)
`/rootstatus` - Check root session status
`/rootlogout` - End root session
`/ssh <command>` - Execute shell commands (requires root)
`/cd <path>` - Navigate to any directory (requires root)

**ℹ️ General**
`/start` - Welcome message
`/help` - Show this help message

**💡 Tips:**
• Follow-up questions work naturally - I remember context!
• After /cpu, you can ask "why is it high?"
• After /docker, you can say "restart the first one"
• Use /clear to start a fresh conversation

**📁 File Management Tips:**
• `/ls` uses your working directory (set with /cd)
• `/cd root` → `/ls` shows: documents/, media/, photos/, tutorials/
• `/ls --all` reveals hidden system folders at disk root
• `/download 1-3 5-7` downloads files 1,2,3,5,6,7 as ZIP
• Cache expires after 10 minutes, re-run /ls if needed
• Root access grants full file system access - use with caution!
"""
    
    await update.message.reply_text(help_msg, parse_mode='Markdown')
    logger.info(f"Help command used by user {update.effective_user.id}")
