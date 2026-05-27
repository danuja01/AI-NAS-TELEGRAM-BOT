"""
CrowdSec security commands: status snapshot and AI incident summaries.
"""

import json
import logging

from telegram import Update
from telegram.ext import ContextTypes

import config
from ai.agent_telegram import AgentTelegramBindings
from ai.gpt_client import generate, generate_with_tools_loop
from ai.security_assistant import crowdsec_security_system_prompt
from services.crowdsec_client import crowdsec_available, gather_crowdsec_snapshot
from utils.security import require_auth, rate_limit
from utils.formatters import format_error
from utils.telegram_reply import reply_ai_markdown_chunked

logger = logging.getLogger(__name__)


def _format_status_text(snap: dict) -> str:
    if not snap.get("ok") and snap.get("errors"):
        return "CrowdSec status: unreachable\n" + "\n".join(snap["errors"][:5])

    alerts = snap.get("alerts") or []
    decisions = snap.get("decisions") or []
    lines = [
        "🛡 **CrowdSec status**",
        f"Container: `{snap.get('container', '?')}`",
        f"Active alerts: **{len(alerts)}**",
        f"Active decisions (bans): **{len(decisions)}**",
    ]
    if snap.get("lapi"):
        lapi = snap["lapi"]
        lines.append(f"LAPI heartbeat: {'OK' if lapi.get('ok') else 'fail'} ({lapi.get('message', '')})")

    if alerts:
        lines.append("\n**Recent alerts:**")
        for a in alerts[:8]:
            lines.append(
                f"• `{a.get('scenario', '?')}` — {a.get('source_ip', '?')} "
                f"({a.get('country', '?')}) → {a.get('target', 'NAS')}"
            )
    elif not decisions:
        lines.append("\n✅ No significant security incidents in the current CrowdSec snapshot.")
    return "\n".join(lines)


@require_auth
@rate_limit
async def crowdsec_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show CrowdSec alerts/decisions snapshot."""
    if not config.CROWDSEC_MONITOR_ENABLED and not crowdsec_available():
        await update.message.reply_text(
            "CrowdSec monitoring is disabled. Set `CROWDSEC_MONITOR_ENABLED=true` in `.env` "
            "and ensure the `crowdsec` container is running.",
        )
        return

    status = await update.message.reply_text("Fetching CrowdSec data…")
    try:
        snap = gather_crowdsec_snapshot()
        text = _format_status_text(snap)
        await status.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error("crowdsec_command: %s", e, exc_info=True)
        await status.edit_text(format_error(str(e)))
    finally:
        pass


@require_auth
@rate_limit
async def security_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    AI security summary using the NAS Security Assistant persona.
    Optional args are passed as the user's question.
    """
    user_id = update.effective_user.id
    args = context.args or []
    question = " ".join(args).strip() or (
        "Summarize current CrowdSec security posture: meaningful incidents, blocked attacks, "
        "severity, affected services, and whether anything looks like a successful intrusion."
    )

    if not config.CROWDSEC_MONITOR_ENABLED and not crowdsec_available():
        await update.message.reply_text(
            "CrowdSec is not available. Enable `CROWDSEC_MONITOR_ENABLED` and verify the crowdsec container.",
        )
        return

    status = await update.message.reply_text("🛡 Analyzing security posture…")
    try:
        snap = gather_crowdsec_snapshot()
        evidence = json.dumps(snap, default=str)[:12000]
        bind = AgentTelegramBindings(update, context, user_id)

        if config.CROWDSEC_MONITOR_ENABLED:
            answer = await generate_with_tools_loop(
                prompt=question,
                context=f"## CrowdSec evidence (read-only)\n{evidence}",
                system_prompt=crowdsec_security_system_prompt(),
                model=config.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=2500,
                telegram_bindings=bind,
            )
        else:
            answer = await generate(
                prompt=question,
                context=f"## CrowdSec evidence\n{evidence}",
                system_prompt=crowdsec_security_system_prompt(),
                model=config.DEFAULT_MODEL,
                temperature=0.3,
                max_tokens=2500,
            )

        await status.delete()
        await reply_ai_markdown_chunked(update, answer)
    except Exception as e:
        logger.error("security_command: %s", e, exc_info=True)
        await status.edit_text(format_error(str(e)))
