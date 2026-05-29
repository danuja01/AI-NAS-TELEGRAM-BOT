"""AI-assisted diagnostics when a monitor fails."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import config

logger = logging.getLogger(__name__)

_last_ai_at: Dict[int, float] = {}


async def diagnose_monitor_failure(
    monitor: Dict[str, Any],
    error: str,
    *,
    on_demand: bool = False,
) -> str:
    """Return AI summary text or empty if disabled/cooldown."""
    if not config.OPENAI_API_KEY:
        return ""
    if not on_demand and not config.UPTIME_AI_ON_INCIDENT:
        return ""
    mid = monitor["id"]
    if not on_demand:
        cooldown = max(15, config.UPTIME_AI_COOLDOWN_MINUTES) * 60
        if time.time() - _last_ai_at.get(mid, 0) < cooldown:
            return ""

    evidence = await _gather_evidence(monitor, error)
    try:
        from ai.gpt_client import generate

        prompt = (
            f"Monitor '{monitor.get('name')}' ({monitor.get('type')}) "
            f"target={monitor.get('target')} failed: {error}\n\n"
            f"Evidence JSON:\n{evidence}\n\n"
            "Give a short root-cause analysis (3-5 bullets), confidence 0-100%, "
            "severity (low/medium/high/critical), and 2-3 safe verification steps. "
            "No auto-fix commands. Max 400 words."
        )
        text = await generate(
            prompt=prompt,
            system_prompt="You are a NAS homelab SRE. Be concise and factual.",
            model=config.AUTOTROUBLESHOOT_MODEL,
            max_tokens=800,
            temperature=0.3,
        )
        _last_ai_at[mid] = time.time()
        return (text or "").strip()
    except Exception as e:
        logger.warning("uptime AI diagnostics failed: %s", e)
        return ""


async def _gather_evidence(monitor: Dict[str, Any], error: str) -> str:
    import json

    mtype = monitor.get("type", "")
    data: Dict[str, Any] = {"error": error, "monitor": monitor.get("name")}

    try:
        from services.system_monitor import (
            get_cpu_stats,
            get_disk_stats,
            get_memory_stats,
        )

        data["cpu"] = get_cpu_stats()
        data["memory"] = get_memory_stats()
        data["disks"] = get_disk_stats()[:8]
    except Exception:
        pass

    if mtype == "docker":
        try:
            from services.docker_service import get_container_logs, list_containers

            name = monitor.get("target", "").lstrip("/")
            data["containers"] = [
                {"name": c.get("name"), "status": c.get("status")}
                for c in list_containers(all_containers=True, include_stats=False)[:20]
            ]
            data["logs_tail"] = (await _safe_logs(name))[:3000]
        except Exception as e:
            data["docker_error"] = str(e)

    return json.dumps(data, default=str)[: config.AUTOTROUBLESHOOT_EVIDENCE_MAX_CHARS]


async def _safe_logs(name: str) -> str:
    from services.docker_service import get_container_logs

    return await __import__("asyncio").to_thread(get_container_logs, name, 30)
