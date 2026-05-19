"""Bindings so OpenAI tool dispatch can send Telegram UI (e.g. Docker confirm keyboards)."""

from __future__ import annotations

from dataclasses import dataclass

from telegram import Update
from telegram.ext import ContextTypes


@dataclass(frozen=True)
class AgentTelegramBindings:
    """Minimal Telegram context for interactive agent tools."""

    update: Update
    context: ContextTypes.DEFAULT_TYPE
    user_id: int
