"""Re-index documents after container start and notify allowed Telegram users."""

import logging

from telegram.constants import ParseMode
from telegram.ext import Application

import config
from ai.embeddings import is_embeddings_available
from ai.rag_engine import index_documents
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)


async def run_auto_index_on_startup(application: Application) -> None:
    if not config.AUTO_INDEX_ON_START:
        return
    if not config.ALLOWED_USER_IDS:
        logger.warning("AUTO_INDEX_ON_START is set but ALLOWED_USER_IDS is empty; skipping auto-index")
        return

    bot = application.bot
    force = config.AUTO_INDEX_FORCE_REINDEX

    async def _send(text: str) -> None:
        for uid in config.ALLOWED_USER_IDS:
            try:
                await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error("startup auto-index: failed to notify user %s: %s", uid, e)

    if not is_embeddings_available():
        await _send(
            "⚠️ <b>Auto-index skipped</b>\n\nEmbeddings are not available. Check OPENAI / local embedding config."
        )
        return

    await _send(
        "📚 <b>Auto-index started</b>\n\n"
        "Re-indexing documents after startup (this may take a few minutes)."
    )

    try:
        result = await index_documents(force_reindex=force)
        if result.get("success"):
            msg = (
                "✅ <b>Auto-index complete</b>\n\n"
                f"Documents: <code>{result.get('documents_processed', 0)}</code>\n"
                f"Chunks: <code>{result.get('total_chunks', 0)}</code>"
            )
        else:
            msg = (
                "⚠️ <b>Auto-index finished with issues</b>\n\n"
                f"{escape_telegram_html(result.get('message', 'Unknown'))}"
            )
    except Exception as e:
        logger.exception("Auto-index on startup failed")
        msg = f"❌ <b>Auto-index failed</b>\n\n{escape_telegram_html(str(e))}"

    await _send(msg)
