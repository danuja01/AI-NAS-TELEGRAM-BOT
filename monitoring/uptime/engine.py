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
from monitoring.uptime import escalation
from monitoring.uptime.reboot_watch import check_reboot_and_alert
from monitoring.uptime.docker_images import scan_image_updates

logger = logging.getLogger(__name__)

_engine_task: Optional[asyncio.Task] = None
_bot: Optional[Bot] = None
_previous_status: Dict[int, str] = {}
_tick_count: int = 0


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
    global _tick_count
    _tick_count += 1
    dependencies.clear_suppression_cache()
    try:
        await check_reboot_and_alert(bot)
    except Exception as e:
        logger.debug("reboot watch: %s", e)
    image_iv = max(1, config.UPTIME_DOCKER_IMAGE_SCAN_TICKS)
    if _tick_count % image_iv == 0:
        try:
            await scan_image_updates(bot)
        except Exception as e:
            logger.debug("image scan: %s", e)
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

    fresh = await store.get_monitor(mid) or monitor
    if not escalation.should_notify_down(fresh, prev):
        return

    affected: list = []
    if prev != "down":
        child_ids = await store.get_children_of(mid)
        if child_ids:
            affected = await dependencies.on_parent_down(mid, fresh.get("name", ""))
        await store.open_incident(mid, root_cause=result.error_message)

    sev, stage = escalation.escalation_level(fresh)
    fail_n = int(fresh.get("consecutive_failures") or 0)
    err_msg = result.error_message
    if stage > 0:
        err_msg = f"[escalation stage {stage + 1}] {err_msg} ({fail_n} failures)"

    await notify.send_monitor_down(
        bot,
        fresh,
        err_msg,
        datetime.utcnow(),
        ai_summary="",
        affected_children=affected or None,
        severity=sev,
    )

    if config.UPTIME_SELF_HEAL_ENABLED and fresh.get("type") == "docker":
        await _maybe_self_heal(fresh)


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
