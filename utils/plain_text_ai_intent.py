"""
Heuristics: when a free-form message should use /analyze-style flow instead of /chat.
"""

from __future__ import annotations

import re

# "think:" / "analyze:" at start of message
_PREFIX = re.compile(r"(?is)^\s*(think|analyze)\s*[:\-]\s*\S")

# Phrases that imply deep reasoning / analysis (same tool path as /analyze)
_ANALYZE_PHRASES = re.compile(
    r"(?is)\b("
    r"think\s+(deeply|hard|carefully|thoroughly)|"
    r"please\s+think(\s+about)?|"
    r"(deep|in[-\s]?depth)\s+analysis|"
    r"analyze\s+(this|it|carefully|in\s+depth|the\s+following|thoroughly)|"
    r"step[-\s]?by[-\s]?step\s+(reason|analysis|think)|"
    r"reason\s+(step|carefully|deeply|through\s+this)|"
    r"give\s+me\s+(a\s+)?(deep|thorough)\s+(analysis|breakdown)"
    r")\b"
)


def plain_text_prefers_analyze(text: str) -> bool:
    """True if a non-command message should run the same pipeline as /analyze."""
    t = (text or "").strip()
    if len(t) < 6:
        return False
    if _PREFIX.match(t):
        return True
    return bool(_ANALYZE_PHRASES.search(t))
