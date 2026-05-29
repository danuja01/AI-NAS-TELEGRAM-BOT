"""
Telegram commands for the Resource Orchestrator subsystem.
"""

from __future__ import annotations

import logging
from typing import List

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import config
from monitoring.resource_orchestrator import get_orchestrator
from utils.security import require_auth, rate_limit
from utils.telegram_reply import reply_text_safe

logger = logging.getLogger(__name__)


def _admin_user_ids() -> List[int]:
    return config.MAINTENANCE_ALLOWED_USER_IDS or config.ALLOWED_USER_IDS


def _is_admin(user_id: int) -> bool:
    return user_id in _admin_user_ids()


@require_auth
@rate_limit
async def orchestrator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show orchestrator status."""
    status = get_orchestrator().get_status_dict()
    th = status["thresholds"]
    lines = [
        "<b>Resource Orchestrator</b>",
        "",
        f"<b>Enabled</b>: {'yes' if status['enabled'] else 'no'}",
        f"<b>Current state</b>: <code>{status['mode']}</code>",
        f"<b>RAM / CPU now</b>: <code>{status['ram_percent']}%</code> / "
        f"<code>{status['cpu_percent']}%</code>",
        f"<b>Immich ML CPU</b>: <code>{status['immich_ml_cpu']}%</code>",
        "",
        "<b>Paused containers</b>:",
    ]
    if status["paused"]:
        for name in status["paused"]:
            lines.append(f"  • <code>{name}</code>")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("<b>Stopped containers</b>:")
    if status["stopped"]:
        for name in status["stopped"]:
            lines.append(f"  • <code>{name}</code>")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append(f"<b>Last trigger</b>: <code>{status['last_trigger'] or '—'}</code>")
    lines.append(f"<b>Last recovery</b>: <code>{status['last_recovery'] or '—'}</code>")
    lines.append("")
    lines.append("<b>Thresholds</b>")
    lines.append(
        f"  RAM high / recover: <code>{th['ram_high']}%</code> / "
        f"<code>{th['ram_recover']}%</code>"
    )
    lines.append(
        f"  CPU high / recover: <code>{th['cpu_high']}%</code> / "
        f"<code>{th['cpu_recover']}%</code>"
    )
    lines.append(
        f"  Recovery delay: <code>{th['recovery_delay_minutes']}</code> min"
    )
    await reply_text_safe(update, "\n".join(lines), parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def orchestrator_enable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await reply_text_safe(update, "🚫 Admin only.")
        return
    get_orchestrator().set_enabled(True)
    await reply_text_safe(update, "✅ Resource Orchestrator <b>enabled</b>.", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def orchestrator_disable_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await reply_text_safe(update, "🚫 Admin only.")
        return
    get_orchestrator().set_enabled(False)
    await reply_text_safe(update, "⏸ Resource Orchestrator <b>disabled</b>.", parse_mode=ParseMode.HTML)


@require_auth
@rate_limit
async def mitigate_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await reply_text_safe(update, "🚫 Admin only.")
        return
    await reply_text_safe(update, "⚙️ Running resource mitigation…")
    orch = get_orchestrator()
    if not orch.is_enabled():
        orch.set_enabled(True)
    result = await orch.mitigate_now(context.bot)
    summary = (
        f"Mitigation complete (stage {result.stage}).\n"
        f"Paused: {', '.join(result.paused) or 'none'}\n"
        f"Stopped: {', '.join(result.stopped) or 'none'}"
    )
    await reply_text_safe(update, summary)


@require_auth
@rate_limit
async def restore_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not _is_admin(user_id):
        await reply_text_safe(update, "🚫 Admin only.")
        return
    await reply_text_safe(update, "♻️ Restoring orchestrator-managed containers…")
    restored = await get_orchestrator().restore_now(context.bot)
    if restored:
        await reply_text_safe(update, "✅ Restored: " + ", ".join(restored))
    else:
        await reply_text_safe(update, "No orchestrator-managed containers to restore.")
