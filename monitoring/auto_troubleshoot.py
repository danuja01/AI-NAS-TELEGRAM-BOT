"""
Autonomous troubleshooting: gather evidence on health alerts, analyze with AI,
notify admins with hypotheses, possibilities, and risks (advisory only — no auto-fix).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from telegram import Bot
from telegram.constants import ParseMode

import config
from database.memory import acknowledge_alert, get_unacknowledged_alerts, save_conversation
from utils.conversation_snippet import html_reply_to_context_plain
from utils.formatters import escape_telegram_html
from utils.telegram_reply import split_text_for_telegram

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

_last_diagnosis_at: Dict[str, float] = {}

_AUTOTROUBLESHOOT_SYSTEM = """You are an autonomous NAS monitoring assistant performing \
read-only incident triage. You receive structured alerts and live evidence from the host.

Your job (like a careful junior sysadmin):
1. Summarize what is wrong in plain language.
2. List the strongest hypotheses ranked by likelihood, citing evidence.
3. Note what was cross-checked in the evidence and what is still uncertain.
4. Suggest verification steps the human can run (bot commands like /status, /docker, /smart, \
/dscan, or host checks) — do NOT claim you already ran destructive actions.
5. List possible remediations as options only, each with risks and prerequisites.
6. State what you would NOT do automatically and why.

Hard rules:
- Never instruct the bot to reboot, prune, upgrade, delete files, or restart services without \
explicit human confirmation.
- Do not invent metrics, log lines, or SMART values not present in the evidence.
- If evidence is thin, say so and list what to collect next.
- Use short sections with these exact headings:
  ## Summary
  ## Evidence reviewed
  ## Hypotheses
  ## Verification steps
  ## Possible actions (with risks)
  ## Uncertainty / false positives
- No markdown tables. Bullet lists only. Keep under 2500 words."""


def _severity_meets_minimum(severity: str) -> bool:
    min_rank = _SEVERITY_RANK.get(config.AUTOTROUBLESHOOT_MIN_SEVERITY, 1)
    return _SEVERITY_RANK.get((severity or "").lower(), 0) >= min_rank


def _incident_cooldown_key(alerts: List[Dict[str, Any]]) -> str:
    types = sorted({a.get("type", "?") for a in alerts})
    sev = max((_SEVERITY_RANK.get((a.get("severity") or "").lower(), 0) for a in alerts), default=0)
    return f"{'+'.join(types)}:{sev}"


def _on_cooldown(key: str) -> bool:
    last = _last_diagnosis_at.get(key, 0.0)
    window = max(15, config.AUTOTROUBLESHOOT_COOLDOWN_MINUTES) * 60
    return (time.time() - last) < window


def _mark_cooldown(key: str) -> None:
    _last_diagnosis_at[key] = time.time()


async def _gather_evidence(alerts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Collect read-only snapshots relevant to the alert types."""
    from services.docker_service import list_containers
    from services.host_runner import run_profile
    from services.smart_monitor import get_all_drives
    from services.system_monitor import (
        get_comprehensive_status,
        get_cpu_stats,
        get_disk_stats,
        get_memory_stats,
        get_temperatures,
    )

    alert_types: Set[str] = {a.get("type", "") for a in alerts}
    evidence: Dict[str, Any] = {
        "gathered_at": datetime.utcnow().isoformat() + "Z",
        "host_exec_mode": config.HOST_EXEC_MODE,
        "alerts": [
            {
                "type": a.get("type"),
                "severity": a.get("severity"),
                "message": (a.get("message") or "")[:500],
            }
            for a in alerts
        ],
    }

    try:
        evidence["baseline"] = get_comprehensive_status()
    except Exception as e:
        evidence["baseline_error"] = str(e)

    if alert_types & {"cpu", "memory"}:
        evidence["cpu"] = get_cpu_stats()
        evidence["memory"] = get_memory_stats()

    if alert_types & {"disk"}:
        evidence["disks"] = get_disk_stats()

    if alert_types & {"temperature"}:
        evidence["temperatures"] = get_temperatures()

    if alert_types & {"docker"}:
        try:
            evidence["docker_containers"] = list_containers(all_containers=True, include_stats=False)
        except Exception as e:
            evidence["docker_error"] = str(e)

    if alert_types & {"smart"}:
        try:
            evidence["smart_drives"] = get_all_drives()
        except Exception as e:
            evidence["smart_error"] = str(e)

    if alert_types & {"systemd"} and (config.HOST_EXEC_MODE or "").lower() != "none":
        units = list(config.MONITOR_SYSTEMD_UNITS)
        failed_out = ""
        try:
            r = await asyncio.to_thread(run_profile, "systemctl_failed")
            if r.stdout:
                failed_out = (r.stdout or "").strip()[:2000]
        except Exception:
            pass
        if failed_out:
            evidence["systemctl_failed"] = failed_out

        journals: Dict[str, str] = {}
        for unit in units[:5]:
            try:
                r = await asyncio.to_thread(
                    run_profile, "journal_tail", extra_args=[unit]
                )
                if r.stdout and r.stdout.strip():
                    journals[unit] = (r.stdout or "").strip()[:1500]
            except Exception:
                continue
        if journals:
            evidence["journal_tails"] = journals

    return evidence


def _evidence_to_context(evidence: Dict[str, Any]) -> str:
    try:
        raw = json.dumps(evidence, indent=2, default=str)
    except (TypeError, ValueError):
        raw = str(evidence)
    limit = max(4000, config.AUTOTROUBLESHOOT_EVIDENCE_MAX_CHARS)
    if len(raw) > limit:
        raw = raw[: limit - 80] + "\n… (evidence truncated) …"
    return raw


def _format_diagnosis_header_html(alerts: List[Dict[str, Any]]) -> str:
    types = ", ".join(sorted({a.get("type", "?") for a in alerts}))
    return (
        "🔍 <b>Autonomous troubleshooting</b>\n"
        f"<i>Advisory only — nothing was changed on the host.</i>\n"
        f"Triggers: <code>{escape_telegram_html(types)}</code>"
    )


async def _run_ai_analysis(
    alerts: List[Dict[str, Any]], evidence: Dict[str, Any]
) -> Optional[str]:
    from ai.gpt_client import generate, generate_with_thinking

    alert_lines = "\n".join(
        f"- [{a.get('severity', '?').upper()}] {a.get('type')}: "
        f"{(a.get('message') or '')[:400]}"
        for a in alerts
    )
    prompt = (
        "The NAS monitoring bot raised the following alert(s). "
        "Analyze using only the evidence JSON below.\n\n"
        f"=== Alerts ===\n{alert_lines}\n\n"
        "Produce the sectioned report described in your system instructions."
    )
    context = _evidence_to_context(evidence)

    try:
        if config.AUTOTROUBLESHOOT_USE_THINKING:
            return await generate_with_thinking(
                prompt=prompt,
                context=context,
                system_prompt=_AUTOTROUBLESHOOT_SYSTEM,
            )
        return await generate(
            prompt=prompt,
            context=context,
            system_prompt=_AUTOTROUBLESHOOT_SYSTEM,
            model=config.AUTOTROUBLESHOOT_MODEL,
            temperature=0.3,
            max_tokens=config.AUTOTROUBLESHOOT_MAX_TOKENS,
        )
    except Exception as e:
        logger.error("Autotroubleshoot AI failed: %s", e, exc_info=True)
        return None


async def _notify_users(
    bot: Bot,
    header_html: str,
    analysis_markdown: str,
    metadata: Dict[str, Any],
) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    from utils.telegram_reply import bot_send_ai_markdown

    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, header_html, parse_mode=ParseMode.HTML)
            if analysis_markdown and analysis_markdown.strip():
                await bot_send_ai_markdown(
                    bot,
                    uid,
                    analysis_markdown,
                    title="",
                )
        except Exception as e:
            logger.error("Autotroubleshoot send failed uid=%s: %s", uid, e)
            continue
        plain = html_reply_to_context_plain(
            header_html + "\n\n" + (analysis_markdown or ""), max_len=12000
        )
        if plain:
            try:
                await save_conversation(
                    uid,
                    "assistant",
                    "[Autonomous troubleshooting report]",
                    command_output=plain,
                    metadata=metadata,
                )
            except Exception as e:
                logger.warning(
                    "Autotroubleshoot persist conversation uid=%s: %s", uid, e
                )


async def _acknowledge_related_db_alerts(alerts: List[Dict[str, Any]]) -> None:
    """Mark recent matching unacknowledged DB rows so periodic scans do not re-fire."""
    if not config.AUTOTROUBLESHOOT_ACK_ALERTS:
        return
    try:
        pending = await get_unacknowledged_alerts()
    except Exception:
        return
    if not pending:
        return
    cutoff = datetime.utcnow() - timedelta(hours=2)
    want_types = {a.get("type") for a in alerts}
    for row in pending:
        if row.get("type") not in want_types:
            continue
        ts = row.get("timestamp")
        if ts:
            try:
                if isinstance(ts, str):
                    dt = datetime.fromisoformat(ts.replace("Z", ""))
                else:
                    dt = ts
                if dt < cutoff:
                    continue
            except (TypeError, ValueError):
                pass
        try:
            await acknowledge_alert(int(row["id"]))
        except Exception as e:
            logger.debug("ack alert %s: %s", row.get("id"), e)


async def run_autotroubleshoot_for_alerts(
    bot: Bot, alerts: List[Dict[str, Any]]
) -> bool:
    """
    Run diagnosis for alerts that were just raised (or passed in).
    Returns True if a report was sent.
    """
    if not config.AUTOTROUBLESHOOT_ENABLED:
        return False
    if not config.OPENAI_API_KEY:
        logger.debug("Autotroubleshoot skipped: no OPENAI_API_KEY")
        return False
    if not alerts:
        return False

    eligible = [a for a in alerts if _severity_meets_minimum(a.get("severity", ""))]
    if not eligible:
        return False

    max_n = max(1, config.AUTOTROUBLESHOOT_MAX_ALERTS_PER_RUN)
    batch = eligible[:max_n]

    key = _incident_cooldown_key(batch)
    if _on_cooldown(key):
        logger.debug("Autotroubleshoot on cooldown for %s", key)
        return False

    logger.info(
        "Autotroubleshoot starting for %s alert(s) types=%s",
        len(batch),
        key,
    )

    evidence = await _gather_evidence(batch)
    analysis = await _run_ai_analysis(batch, evidence)
    if not analysis or not analysis.strip():
        return False

    header = _format_diagnosis_header_html(batch)
    await _notify_users(
        bot,
        header,
        analysis,
        metadata={
            "source": "autotroubleshoot",
            "alert_types": sorted({a.get("type") for a in batch}),
            "severity_max": max(
                batch,
                key=lambda a: _SEVERITY_RANK.get((a.get("severity") or "").lower(), 0),
            ).get("severity"),
        },
    )
    _mark_cooldown(key)
    await _acknowledge_related_db_alerts(batch)
    return True


async def scan_unacknowledged_alerts(bot: Bot) -> bool:
    """
    Periodic pass: diagnose stale unacknowledged alerts (e.g. missed during downtime).
    """
    if not config.AUTOTROUBLESHOOT_ENABLED:
        return False
    if not config.AUTOTROUBLESHOOT_SCAN_UNACK:
        return False

    pending = await get_unacknowledged_alerts()
    if not pending:
        return False

    cutoff = datetime.utcnow() - timedelta(
        hours=max(1, config.AUTOTROUBLESHOOT_UNACK_MAX_AGE_HOURS)
    )
    fresh: List[Dict[str, Any]] = []
    for row in pending[: config.AUTOTROUBLESHOOT_MAX_ALERTS_PER_RUN]:
        if not _severity_meets_minimum(row.get("severity", "")):
            continue
        ts = row.get("timestamp")
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", ""))
            else:
                dt = ts or cutoff
            if dt < cutoff:
                continue
        except (TypeError, ValueError):
            continue
        fresh.append(
            {
                "type": row.get("type"),
                "severity": row.get("severity"),
                "message": row.get("message"),
            }
        )

    if not fresh:
        return False
    return await run_autotroubleshoot_for_alerts(bot, fresh)
