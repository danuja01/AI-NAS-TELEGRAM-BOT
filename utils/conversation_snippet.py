"""
Convert Telegram HTML bot replies into compact plain text for conversation / RAG context.

Stored alongside structured command_output so follow-up messages (e.g. after /smart or an alert)
still have readable context without shipping raw repr() blobs to the model.
"""

from __future__ import annotations

import html as html_lib
import re


def html_reply_to_context_plain(html: str, max_len: int = 16000) -> str:
    """
    Strip Telegram-safe HTML to whitespace-normalized plain text, capped at ``max_len``.
    """
    if not html or not str(html).strip():
        return ""
    t = html_lib.unescape(str(html))
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</(p|div|tr|h[1-6])>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[ \t\f\v]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = t.strip()
    if len(t) > max_len:
        t = t[: max_len - 40].rstrip() + "\n… (truncated for context)"
    return t
