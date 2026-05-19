"""
Safe Telegram reply helpers: effective_message and Markdown/HTML fallbacks.
"""

import logging
from typing import Any, List, Optional

from telegram import Message, Update
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def delete_message_safe(message: Message | None) -> None:
    """Delete a bot message (e.g. transient status); ignore permission or gone errors."""
    if message is None:
        return
    try:
        await message.delete()
    except BadRequest as e:
        logger.debug("delete_message_safe: %s", e)
    except Exception as e:
        logger.debug("delete_message_safe: %s", e)

# https://core.telegram.org/method/messages.sendMessage
TELEGRAM_MESSAGE_MAX_CHARS = 4096


def get_reply_target(update: Update):
    """Message or ChannelPost suitable for `.reply_text` when present."""
    return update.effective_message


def split_text_for_telegram(
    text: str, chunk_size: int = 3900, hard_limit: int = TELEGRAM_MESSAGE_MAX_CHARS
) -> List[str]:
    """
    Split long text on newlines so each part fits in one Telegram message.
    chunk_size should stay below hard_limit to leave room for part counters.
    """
    if len(text) <= hard_limit:
        return [text]
    chunks: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_size, n)
        if end < n:
            window = text[i:end]
            cut = window.rfind("\n\n")
            if cut < chunk_size // 3:
                cut = window.rfind("\n")
            if cut > 80:
                end = i + cut + 1
        chunks.append(text[i:end])
        i = end
    return chunks


async def reply_text_chunked(
    update: Update,
    text: str,
    *,
    parse_mode: Optional[str] = None,
    **kwargs: Any,
) -> bool:
    """
    Reply in one or more messages so nothing exceeds Telegram length limits.
    """
    em = update.effective_message
    if em is None:
        logger.warning(
            "reply_text_chunked: no effective_message (update_id=%s)",
            getattr(update, "update_id", None),
        )
        return False
    parts = split_text_for_telegram(text)
    total = len(parts)
    for idx, part in enumerate(parts):
        body = f"[{idx + 1}/{total}]\n{part}" if total > 1 else part
        if len(body) > TELEGRAM_MESSAGE_MAX_CHARS:
            body = body[: TELEGRAM_MESSAGE_MAX_CHARS - 30] + "\n…(trimmed)"
        try:
            await em.reply_text(body, parse_mode=parse_mode, **kwargs)
        except BadRequest as e:
            err = str(e).lower()
            if parse_mode and ("can't parse entities" in err or "parse" in err):
                logger.warning("reply_text_chunked: parse_mode failed; sending plain")
                await em.reply_text(body, parse_mode=None, **kwargs)
            elif "too long" in err:
                await em.reply_text(body[:4080], parse_mode=None, **kwargs)
            else:
                raise
    return True


async def reply_ai_markdown_chunked(
    update: Update,
    raw_markdown: str,
    *,
    max_utf16: int = 3800,
    **kwargs: Any,
) -> bool:
    """
    Convert LLM Markdown (including GFM tables) to Telegram via ``telegramify-markdown`` → MarkdownV2,
    splitting safely for the UTF-16 length limit. Falls back to ``format_ai_response`` + legacy Markdown.
    """
    em = update.effective_message
    if em is None:
        logger.warning(
            "reply_ai_markdown_chunked: no effective_message (update_id=%s)",
            getattr(update, "update_id", None),
        )
        return False

    kwargs = {k: v for k, v in kwargs.items() if k != "parse_mode"}

    raw = (raw_markdown or "").strip()
    if not raw:
        await em.reply_text("(empty response)", parse_mode=None)
        return True

    try:
        from telegram.constants import ParseMode
        from telegramify_markdown import convert, split_markdownv2
    except ImportError:
        from utils.formatters import format_ai_response

        return await reply_text_chunked(
            update, format_ai_response(raw_markdown or ""), parse_mode="Markdown", **kwargs
        )

    try:
        text, entities = convert(raw_markdown or "")
        parts = split_markdownv2(text, entities, max_utf16_len=max_utf16)
    except Exception as e:
        logger.warning("reply_ai_markdown_chunked: convert failed (%s); using fallback", e)
        from utils.formatters import format_ai_response

        return await reply_text_chunked(
            update, format_ai_response(raw_markdown or ""), parse_mode="Markdown", **kwargs
        )

    if not parts:
        from utils.formatters import format_ai_response

        return await reply_text_chunked(
            update, format_ai_response(raw_markdown or ""), parse_mode="Markdown", **kwargs
        )

    for part in parts:
        chunk = (part or "").strip()
        if not chunk:
            continue
        try:
            await em.reply_text(chunk, parse_mode=ParseMode.MARKDOWN_V2, **kwargs)
        except BadRequest as e:
            err = str(e).lower()
            logger.warning("reply_ai_markdown_chunked: send failed (%s); retrying plain", e)
            if "too long" in err:
                await em.reply_text(chunk[:4080], parse_mode=None, **kwargs)
            else:
                await em.reply_text(chunk, parse_mode=None, **kwargs)
    return True


async def reply_text_safe(
    update: Update,
    text: str,
    *,
    parse_mode: Optional[str] = None,
    **kwargs: Any,
) -> bool:
    """
    Reply using effective_message. Retries without parse_mode on entity parse errors.
    Returns False if nothing to reply to.
    """
    em = update.effective_message
    if em is None:
        logger.warning(
            "reply_text_safe: no effective_message (update_id=%s)",
            getattr(update, "update_id", None),
        )
        return False
    try:
        await em.reply_text(text, parse_mode=parse_mode, **kwargs)
        return True
    except BadRequest as e:
        err_l = str(e).lower()
        if "too long" in err_l:
            logger.warning("reply_text_safe: message too long; splitting")
            return await reply_text_chunked(update, text, parse_mode=parse_mode, **kwargs)
        if parse_mode and ("can't parse entities" in err_l or "parse" in err_l):
            logger.warning("reply_text_safe: parse_mode failed (%s); retrying plain text", e)
            await em.reply_text(text, parse_mode=None, **kwargs)
            return True
        raise
