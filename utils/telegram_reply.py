"""
Safe Telegram reply helpers: effective_message and Markdown/HTML fallbacks.
"""

import logging
from typing import Any, List, Optional

from telegram import Update
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

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
