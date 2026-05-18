"""
Safe Telegram reply helpers: effective_message and Markdown/HTML fallbacks.
"""

import logging
from typing import Any, Optional

from telegram import Update
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


def get_reply_target(update: Update):
    """Message or ChannelPost suitable for `.reply_text` when present."""
    return update.effective_message


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
        if parse_mode and ("can't parse entities" in err_l or "parse" in err_l):
            logger.warning("reply_text_safe: parse_mode failed (%s); retrying plain text", e)
            await em.reply_text(text, parse_mode=None, **kwargs)
            return True
        raise
