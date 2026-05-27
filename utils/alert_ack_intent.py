"""Detect plain-text intent to acknowledge all pending alerts."""

from __future__ import annotations

import re

_ACK_ALL_PHRASES = (
    "acknowledge all",
    "acknowledged all",
    "ack all",
    "dismiss all alert",
    "clear all alert",
    "clear the alerts",
    "dismiss these alert",
    "mark all as acknowledged",
    "mark all acknowledged",
)

_ACK_ALL_RE = re.compile(
    r"\b(?:i\s+)?(?:have\s+)?(?:'?ve\s+)?ack(?:nowledge)?d(?:ed)?\s+"
    r"(?:all(?:\s+of)?\s+)?(?:these|them|those|issues|alerts?|warnings?|this)\b",
    re.IGNORECASE,
)

_UPDATE_AFTER_ACK_RE = re.compile(
    r"acknowledg(?:e|ed).{0,40}(?:can\s+you|could\s+you|please|pls).{0,20}update",
    re.IGNORECASE,
)


def text_requests_acknowledge_all(text: str) -> bool:
    """True if the user is saying they handled / dismissed all current alerts."""
    t = (text or "").strip().lower()
    if not t or len(t) > 500:
        return False
    if any(p in t for p in _ACK_ALL_PHRASES):
        return True
    if _ACK_ALL_RE.search(text or ""):
        return True
    if _UPDATE_AFTER_ACK_RE.search(text or ""):
        return True
    if "acknowledged" in t and "all" in t:
        return True
    return False
