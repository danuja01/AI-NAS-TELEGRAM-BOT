"""Background uptime monitor engine."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from telegram import Bot

import config
from monitoring.uptime import dependencies, notify, probes, store
from monitoring.uptime.builtin import ensure_builtin_monitors, sync_docker_monitors
from monitoring.uptime.diagnostics import diagnose_monitor_failure

logger = logging.getLogger(__name__)

_engine_task: Optional[asyncio.Task] = None
_bot: Optional[Bot] = None
_previous_status: Dict[int, str] = {}


async def start_uptime_monitoring(bot: Bot) -> None:
    global _engine_task, _bot
    if _engine_task and not _engine_task.done():
        return
    _bot = bot
    await ensure_builtin_monitors()
    if config.UPTIME_AUTO_DISCOVER_DOCKER:
        try:
            await sync_docker_monitors()
        except Exception as e:
            logger.warning("Docker monitor sync: %s", e)
    if config.UPTIME_DASHBOARD_ENABLED:
        try:
            from monitoring.uptime.dashboard import start_dashboard

            start_dashboard()
        except Exception as e:
            logger.warning("Dashboard start failed: %s", e)
    _engine_task = asyncio.create_task(_engine_loop(), name="uptime-engine")
    logger.info("Uptime monitoring engine started (tick=%ss)", config.UPTIME_TICK_SECONDS)


def stop_uptime_monitoring() -> None:
    global _engine_task
    if _engine_task:
        _engine_task.cancel()
        _engine_task = None
    try:
        from monitoring.uptime.dashboard import stop_dashboard

        stop_dashboard()
    except Exception:
        pass


async def _engine_loop() -> None:
    tick = config.UPTIME_TICK_SECONDS
    while True:
        try:
            if _bot:
                await run_monitor_tick(_bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("uptime tick error: %s", e, exc_info=True)
        await asyncio.sleep(tick)


async def run_monitor_tick(bot: Bot) -> None:
    dependencies.clear_suppression_cache()
    due = await store.get_due_monitors()
    for monitor in due:
        await _check_one(bot, monitor)


async def _check_one(bot: Bot, monitor: Dict) -> None:
    mid = monitor["id"]
    if await store.is_silenced(mid, monitor.get("tags_list") or []):
        return

    result = await probes.run_probe(monitor)
    await store.record_heartbeat(
        mid,
        result.success,
        result.latency_ms,
        result.status_code,
        result.error_message,
    )

    prev = _previous_status.get(mid, monitor.get("last_status", "unknown"))
    new_status = "up" if result.success else "down"
    _previous_status[mid] = new_status

    if result.success:
        if prev == "down":
            closed = await store.close_incident(mid)
            downtime = (closed or {}).get("duration_seconds", 0)
            fresh = await store.get_monitor(mid)
            if fresh:
                await notify.send_monitor_up(bot, fresh, downtime)
        return

    # Failed
    if await dependencies.should_suppress_child_alert(mid):
        await store.open_incident(mid, root_cause="suppressed: parent down")
        return

    if prev != "down":
        affected: list = []
        child_ids = await store.get_children_of(mid)
        if child_ids:
            affected = await dependencies.on_parent_down(mid, monitor.get("name", ""))

        await store.open_incident(mid, root_cause=result.error_message)
        ai_summary = await diagnose_monitor_failure(monitor, result.error_message)
        if ai_summary:
            await store.update_incident_ai_summary(mid, ai_summary)

        await notify.send_monitor_down(
            bot,
            monitor,
            result.error_message,
            datetime.utcnow(),
            ai_summary=ai_summary,
            affected_children=affected or None,
        )

        if config.UPTIME_SELF_HEAL_ENABLED and monitor.get("type") == "docker":
            await _maybe_self_heal(monitor)


async def _maybe_self_heal(monitor: Dict) -> None:
    """Optional container restart with cooldown (no confirmation — use env flag)."""
    from services.docker_service import restart_container

    name = monitor.get("target", "").lstrip("/")
    failures = int(monitor.get("consecutive_failures") or 0)
    if failures > config.UPTIME_SELF_HEAL_MAX_RESTARTS:
        return
    try:
        await asyncio.to_thread(restart_container, name)
        logger.info("Self-heal restarted container %s", name)
    except Exception as e:
        logger.warning("Self-heal failed for %s: %s", name, e)


async def record_push_for_monitor(token: str) -> bool:
    mid = await store.record_push_heartbeat(token)
    if not mid:
        return False
    await store.record_heartbeat(mid, True, 0.0)
    return True
