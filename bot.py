"""
NAS Telegram AI Assistant - Main Entry Point
"""

import logging

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeDefault,
    MenuButtonCommands,
    Update,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

import config
from utils.logger import setup_logging
from database.models import init_database
from monitoring.health_checker import start_health_monitoring

# Import command handlers
from commands import basic, monitoring, docker_cmds, filesystem, ai_cmds, service, root_cmds, operations

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred while processing your request. "
                "Please try again or contact the administrator."
            )
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")


# Commands shown in Telegram's "/" menu (keep in sync with CommandHandler registrations)
TELEGRAM_BOT_COMMANDS = [
    BotCommand("start", "Welcome and overview"),
    BotCommand("help", "List all commands"),
    BotCommand("status", "System overview"),
    BotCommand("cpu", "CPU usage"),
    BotCommand("ram", "Memory usage"),
    BotCommand("disk", "Disk partitions"),
    BotCommand("temps", "Temperature sensors"),
    BotCommand("network", "Network stats"),
    BotCommand("uptime", "System uptime"),
    BotCommand("health", "Health score"),
    BotCommand("smart", "Drive SMART"),
    BotCommand("drives", "Same as SMART"),
    BotCommand("docker", "Docker containers"),
    BotCommand("containers", "Docker list alias"),
    BotCommand("dstart", "Start a container"),
    BotCommand("restart", "Restart a container"),
    BotCommand("stop", "Stop a container"),
    BotCommand("logs", "Container logs"),
    BotCommand("files", "Browse files"),
    BotCommand("ls", "List directory"),
    BotCommand("find", "Find files"),
    BotCommand("tree", "Directory tree"),
    BotCommand("storage", "Disk usage paths"),
    BotCommand("download", "Download file"),
    BotCommand("uploadfile", "Upload file"),
    BotCommand("services", "System services"),
    BotCommand("restart_service", "Restart service"),
    BotCommand("reboot", "Reboot (confirm)"),
    BotCommand("shutdown", "Shutdown (confirm)"),
    BotCommand("ask", "Ask documents (RAG)"),
    BotCommand("chat", "Chat with AI"),
    BotCommand("summarize", "Summarize docs"),
    BotCommand("explain", "Explain a term"),
    BotCommand("analyze", "Analyze text"),
    BotCommand("think", "Deep reasoning"),
    BotCommand("websearch", "Web search"),
    BotCommand("index", "Re-index documents"),
    BotCommand("clear", "Clear history"),
    BotCommand("rootlogin", "Root session"),
    BotCommand("rootlogout", "End root"),
    BotCommand("rootstatus", "Root session status"),
    BotCommand("ssh", "Remote shell cmd"),
    BotCommand("cd", "Working directory"),
    BotCommand("updates", "Check APT/OMV updates"),
    BotCommand("omv_updates", "Updates + OMV note"),
    BotCommand("upgrade", "Run omv-upgrade (confirm)"),
]


async def post_init(application: Application):
    """Initialize bot after startup."""
    logger.info("Initializing database...")
    await init_database()

    try:
        # '/' autocomplete and command list: https://core.telegram.org/bots/features#commands
        # Register default scope (private chats + chats without a narrower scope)
        await application.bot.set_my_commands(
            TELEGRAM_BOT_COMMANDS,
            scope=BotCommandScopeDefault(),
        )
        await application.bot.set_my_commands(
            TELEGRAM_BOT_COMMANDS,
            scope=BotCommandScopeAllGroupChats(),
        )
        # Blue "menu" next to the input: show the same command list (overrides e.g. web app default).
        await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

        cmds = await application.bot.get_my_commands(scope=BotCommandScopeDefault())
        logger.info(
            "Bot command menu ready: default scope has %s commands (Telegram returned %s).",
            len(TELEGRAM_BOT_COMMANDS),
            len(cmds),
        )
    except Exception:
        logger.exception(
            "Registering commands or menu button failed — type '/' may show no suggestions. "
            "Fallback: BotFather → /mybots → your bot → Edit Bot → Edit Commands."
        )
    
    logger.info("Starting health monitoring, metrics, digests, cron hook…")
    await start_health_monitoring(application.bot)

    logger.info("Bot initialized successfully!")


def main():
    """Start the bot."""
    logger.info("Starting NAS Telegram AI Assistant...")
    
    # Create application
    application = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Register command handlers - Basic
    application.add_handler(CommandHandler("start", basic.start_command))
    application.add_handler(CommandHandler("help", basic.help_command))
    
    # Register command handlers - Monitoring
    application.add_handler(CommandHandler("status", monitoring.status_command))
    application.add_handler(CommandHandler("cpu", monitoring.cpu_command))
    application.add_handler(CommandHandler("ram", monitoring.ram_command))
    application.add_handler(CommandHandler("disk", monitoring.disk_command))
    application.add_handler(CommandHandler("temps", monitoring.temps_command))
    application.add_handler(CommandHandler("network", monitoring.network_command))
    application.add_handler(CommandHandler("uptime", monitoring.uptime_command))
    application.add_handler(CommandHandler("health", monitoring.health_command))
    application.add_handler(CommandHandler("smart", monitoring.smart_command))
    application.add_handler(CommandHandler("drives", monitoring.drives_command))
    
    # Register command handlers - Docker
    application.add_handler(CommandHandler("docker", docker_cmds.docker_command))
    application.add_handler(CommandHandler("containers", docker_cmds.containers_command))
    application.add_handler(CommandHandler("restart", docker_cmds.restart_command))
    application.add_handler(CommandHandler("stop", docker_cmds.stop_command))
    application.add_handler(CommandHandler("dstart", docker_cmds.start_container_command))
    application.add_handler(CommandHandler("logs", docker_cmds.logs_command))
    
    # Register command handlers - File System
    application.add_handler(CommandHandler("files", filesystem.files_command))
    application.add_handler(CommandHandler("ls", filesystem.ls_command))
    application.add_handler(CommandHandler("find", filesystem.find_command))
    application.add_handler(CommandHandler("tree", filesystem.tree_command))
    application.add_handler(CommandHandler("storage", filesystem.storage_command))
    application.add_handler(CommandHandler("download", filesystem.download_command))
    application.add_handler(CommandHandler("uploadfile", filesystem.upload_command))
    
    # Register message handler for file uploads with caption
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO,
        filesystem.handle_file_with_caption
    ))
    
    # Register command handlers - Service Management
    application.add_handler(CommandHandler("services", service.services_command))
    application.add_handler(CommandHandler("restart_service", service.restart_service_command))
    application.add_handler(CommandHandler("reboot", service.reboot_command))
    application.add_handler(CommandHandler("shutdown", service.shutdown_command))
    
    # Register command handlers - AI
    application.add_handler(CommandHandler("ask", ai_cmds.ask_command))
    application.add_handler(CommandHandler("chat", ai_cmds.chat_command))
    application.add_handler(CommandHandler("summarize", ai_cmds.summarize_command))
    application.add_handler(CommandHandler("explain", ai_cmds.explain_command))
    application.add_handler(CommandHandler("analyze", ai_cmds.analyze_command))
    application.add_handler(CommandHandler("think", ai_cmds.think_command))
    application.add_handler(CommandHandler("websearch", ai_cmds.websearch_command))
    application.add_handler(CommandHandler("index", ai_cmds.index_command))
    application.add_handler(CommandHandler("clear", ai_cmds.clear_command))
    
    # Register command handlers - Root Access
    application.add_handler(CommandHandler("rootlogin", root_cmds.rootlogin_command))
    application.add_handler(CommandHandler("rootlogout", root_cmds.rootlogout_command))
    application.add_handler(CommandHandler("rootstatus", root_cmds.rootstatus_command))
    application.add_handler(CommandHandler("ssh", root_cmds.ssh_command))
    application.add_handler(CommandHandler("cd", root_cmds.cd_command))

    # Host / OMV maintenance
    application.add_handler(CommandHandler("updates", operations.updates_command))
    application.add_handler(CommandHandler("omv_updates", operations.omv_updates_command))
    application.add_handler(CommandHandler("upgrade", operations.upgrade_command))

    application.add_handler(
        CallbackQueryHandler(
            operations.handle_operations_callback,
            pattern=f"^({operations.CB_UPGRADE_CONFIRM}|{operations.CB_UPGRADE_CANCEL})$",
        )
    )

    # Register callback query handler for confirmations
    application.add_handler(CallbackQueryHandler(service.handle_confirmation))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
