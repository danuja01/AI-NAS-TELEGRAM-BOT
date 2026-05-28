"""
CrowdSec security commands: status snapshot and AI incident summaries.
"""

import json
import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

import config
from ai.agent_telegram import AgentTelegramBindings
from ai.gpt_client import generate, generate_with_tools_loop
from ai.security_assistant import crowdsec_security_system_prompt
from services.crowdsec_client import crowdsec_available, crowdsec_probe, gather_crowdsec_snapshot
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


def _crowdsec_disabled_hint() -> str:
    """Explain why /crowdsec may refuse to run (config vs Docker/cscli)."""
    lines = []
    raw = os.getenv("CROWDSEC_MONITOR_ENABLED")
    if not config.CROWDSEC_MONITOR_ENABLED:
        lines.append(
            "• `CROWDSEC_MONITOR_ENABLED` is **off inside the running bot** "
            f"(process env: {raw!r})."
        )
        lines.append(
            "  On Docker: setting `.env` alone is not enough — the variable must be listed under "
            "`environment:` in `docker-compose.yml` (or use `env_file: .env`), then recreate:"
        )
        lines.append("  `docker compose up -d --force-recreate`")
    ok, probe_msg = crowdsec_probe()
    if not ok:
        lines.append(
            f"• CrowdSec `cscli` probe failed: {probe_msg}"
        )
        lines.append(
            f"  Check `CROWDSEC_CONTAINER` (now: `{config.CROWDSEC_CONTAINER}`), that CrowdSec is running, "
            "and that `/var/run/docker.sock` is mounted (the bot uses the Docker Python SDK, not the docker CLI)."
        )
    return "\n".join(lines)


@require_auth
@rate_limit
async def crowdsec_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show CrowdSec alerts/decisions snapshot."""
    if not config.CROWDSEC_MONITOR_ENABLED and not crowdsec_available():
        await update.message.reply_text(
            "CrowdSec is not available from the bot.\n\n" + _crowdsec_disabled_hint(),
            parse_mode="Markdown",
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
            "CrowdSec is not available from the bot.\n\n" + _crowdsec_disabled_hint(),
            parse_mode="Markdown",
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
