"""
Background health monitoring, metrics, digests, and alerting.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

import config
from database.memory import (
    add_metric_sample,
    append_drive_spin_samples,
    get_metrics_digest_stats,
    get_smart_snapshots_dict,
    save_alert,
    save_conversation,
    upsert_smart_snapshots,
)
from monitoring.alerts import (
    check_cpu_alerts,
    check_disk_alerts,
    check_docker_alerts,
    check_docker_unhealthy_alerts,
    check_memory_alerts,
    check_smart_alerts,
    check_smart_delta_alerts,
    check_storage_low_disk_alerts,
    check_temperature_alerts,
)
from monitoring.auto_troubleshoot import (
    run_autotroubleshoot_for_alerts,
    scan_unacknowledged_alerts,
)
from monitoring.cron_notify_server import start_cron_notify_server
from services.docker_service import list_containers
from services.host_runner import run_profile
from services.smart_monitor import get_all_drives
from services.system_monitor import (
    get_cpu_stats,
    get_disk_stats,
    get_memory_stats,
    get_temperatures,
)
from utils.formatters import escape_telegram_html
from utils.conversation_snippet import html_reply_to_context_plain

logger = logging.getLogger(__name__)

_scheduler = None
_last_alert_times: Dict[str, datetime] = {}
_last_systemd_active: Dict[str, bool] = {}
_last_journal_sent: Dict[str, float] = {}
_last_container_running: Dict[str, bool] = {}
_last_container_unhealthy: Dict[str, bool] = {}


async def send_digest(bot: Bot):
    """Send periodic metrics digest to admins."""
    if not config.ALLOWED_USER_IDS:
        return
    hours = max(1, config.DIGEST_INTERVAL_HOURS)
    stats = await get_metrics_digest_stats(hours)
    n = int(stats.get("n") or 0)
    if n < 1:
        logger.debug("Digest skipped: no metric samples yet")
        return
    lines = [
        f"📋 <b>NAS digest</b> (~{hours}h, <code>{n}</code> samples)",
        "",
        f"CPU avg / max: <code>{stats.get('cpu_avg') or 0:.1f}%</code> / "
        f"<code>{stats.get('cpu_max') or 0:.1f}%</code>",
        f"RAM avg / max: <code>{stats.get('mem_avg') or 0:.1f}%</code> / "
        f"<code>{stats.get('mem_max') or 0:.1f}%</code>",
    ]
    if stats.get("temp_max") is not None:
        lines.append(f"Peak temp (reported): <code>{stats['temp_max']:.1f}°C</code>")
    if stats.get("disk_free_min") is not None:
        lines.append(f"Lowest free disk headroom snapshot: <code>{stats['disk_free_min']:.1f}%</code>")
    text = "\n".join(lines)
    plain = html_reply_to_context_plain(text, max_len=12000)
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("digest send failed %s: %s", uid, e)
            continue
        if plain:
            try:
                await save_conversation(
                    uid,
                    "assistant",
                    "[Scheduled NAS digest]",
                    command_output=plain,
                    metadata={"source": "digest"},
                )
            except Exception as e:
                logger.warning("digest persist conversation failed %s: %s", uid, e)


async def record_metrics_sample():
    """Store one row for digest rollups."""
    try:
        cpu = get_cpu_stats()
        mem = get_memory_stats()
        temps = get_temperatures() or {}
        temp_vals = [
            float(t)
            for sk, t in temps.items()
            if t is not None and not config.ignore_temperature_sensor_for_alerts(sk)
        ]
        temp_max = max(temp_vals) if temp_vals else None
        disks = get_disk_stats() or []
        free_pcts: List[float] = []
        for d in disks:
            try:
                used = float(d.get("percent", 0))
                free_pcts.append(100.0 - used)
            except (TypeError, ValueError):
                continue
        disk_min_free = min(free_pcts) if free_pcts else None
        await add_metric_sample(
            float(cpu.get("percent", 0)),
            float(mem.get("percent", 0)),
            temp_max,
            disk_min_free,
            None,
        )
    except Exception as e:
        logger.error("record_metrics_sample: %s", e, exc_info=True)


async def check_system_health(bot: Bot):
    """Perform comprehensive system health check."""
    try:
        logger.debug("Running health check...")
        all_alerts: List[Dict[str, Any]] = []

        cpu_stats = get_cpu_stats()
        cpu_percent = cpu_stats.get("percent", 0)
        all_alerts.extend(check_cpu_alerts(cpu_percent))

        mem_stats = get_memory_stats()
        mem_percent = mem_stats.get("percent", 0)
        all_alerts.extend(check_memory_alerts(mem_percent))

        disk_stats = get_disk_stats()
        all_alerts.extend(check_disk_alerts(disk_stats))
        if config.STORAGE_LOW_DISK_PERCENT:
            all_alerts.extend(check_storage_low_disk_alerts(disk_stats))

        temps = get_temperatures()
        all_alerts.extend(check_temperature_alerts(temps))

        try:
            global _last_container_running, _last_container_unhealthy
            containers = list_containers(all_containers=True, include_stats=False)
            docker_alerts, _last_container_running = check_docker_alerts(
                containers, _last_container_running
            )
            all_alerts.extend(docker_alerts)
            unhealthy_alerts, _last_container_unhealthy = check_docker_unhealthy_alerts(
                containers, _last_container_unhealthy
            )
            all_alerts.extend(unhealthy_alerts)
        except Exception:
            pass

        await _check_systemd_host(all_alerts)

        current_minute = datetime.now().minute
        if current_minute % 15 == 0:
            try:
                prev = await get_smart_snapshots_dict()
                drives = get_all_drives()
                all_alerts.extend(check_smart_delta_alerts(drives, prev))
                all_alerts.extend(check_smart_alerts(drives))
                await upsert_smart_snapshots(drives)
                await append_drive_spin_samples(drives)
            except Exception:
                logger.debug("SMART check skipped", exc_info=True)

        if all_alerts:
            delivered = await send_alerts(bot, all_alerts)
            if delivered and config.AUTOTROUBLESHOOT_ENABLED:
                try:
                    await run_autotroubleshoot_for_alerts(bot, delivered)
                except Exception as e:
                    logger.error("Autotroubleshoot after alerts: %s", e, exc_info=True)

    except Exception as e:
        logger.error("Health check failed: %s", e, exc_info=True)


async def _check_systemd_host(all_alerts: List[Dict[str, Any]]):
    if (config.HOST_EXEC_MODE or "").lower() == "none":
        return
    for unit in config.MONITOR_SYSTEMD_UNITS:
        try:
            r = await asyncio.to_thread(
                run_profile, "systemctl_is_active", extra_args=[unit]
            )
            active = r.ok and (r.stdout or "").strip() == "active"
        except Exception:
            continue
        prev = _last_systemd_active.get(unit)
        _last_systemd_active[unit] = active
        if prev is None:
            continue
        if prev and not active:
            msg = escape_telegram_html(
                f"systemd unit '{unit}' is no longer active"
            )
            snippet = await _journal_snippet(unit)
            if snippet:
                msg = f"{msg}\n\n<b>Recent log</b>\n<pre>{snippet}</pre>"
            all_alerts.append(
                {"type": "systemd", "severity": "critical", "message": msg}
            )
        elif not prev and active:
            all_alerts.append(
                {
                    "type": "systemd",
                    "severity": "info",
                    "message": escape_telegram_html(
                        f"systemd unit '{unit}' recovered (active)"
                    ),
                }
            )


async def _journal_snippet(unit: str) -> str:
    now = time.time()
    last = _last_journal_sent.get(unit, 0)
    if now - last < config.JOURNAL_ALERT_COOLDOWN_SECONDS:
        return ""
    try:
        r = await asyncio.to_thread(
            run_profile, "journal_tail", extra_args=[unit]
        )
        _last_journal_sent[unit] = now
        if r.error or not (r.stdout or "").strip():
            return escape_telegram_html((r.stderr or "")[:800])
        return escape_telegram_html((r.stdout or "").strip()[:3500])
    except Exception:
        return ""


async def send_alerts(bot: Bot, alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Send alerts to authorized users. Returns alerts that were actually delivered."""
    if not config.ALLOWED_USER_IDS:
        logger.warning("No users configured to receive alerts")
        return []

    current_time = datetime.now()
    delivered: List[Dict[str, Any]] = []

    for alert in alerts:
        alert_key = f"{alert['type']}_{alert['message'][:120]}"
        last_time = _last_alert_times.get(alert_key)
        if last_time and (current_time - last_time) < timedelta(hours=1):
            continue

        # Bound in-memory dedup cache
        if len(_last_alert_times) > config.ALERT_DEDUP_CACHE_MAX:
            cutoff = current_time - timedelta(hours=2)
            stale = [k for k, t in _last_alert_times.items() if t < cutoff]
            for k in stale[: len(_last_alert_times) // 2]:
                _last_alert_times.pop(k, None)

        await save_alert(alert["type"], alert["severity"], alert["message"])

        severity_icons = {"info": "ℹ️", "warning": "⚠️", "critical": "🔴"}
        icon = severity_icons.get(alert["severity"], "⚠️")
        raw_msg = alert["message"]
        if "<pre>" in raw_msg:
            message = (
                f"{icon} <b>Alert: {escape_telegram_html(alert['severity'].upper())}</b>\n\n"
                f"{raw_msg}"
            )
        else:
            body = escape_telegram_html(raw_msg)
            message = (
                f"{icon} <b>Alert: {escape_telegram_html(alert['severity'].upper())}</b>\n\n"
                f"{body}"
            )

        for user_id in config.ALLOWED_USER_IDS:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                )
                logger.info("Sent alert to user %s: %s", user_id, alert["type"])
            except Exception as e:
                logger.error("Failed to send alert to user %s: %s", user_id, e)
                continue
            try:
                plain = html_reply_to_context_plain(message, max_len=12000)
                await save_conversation(
                    user_id,
                    "assistant",
                    f"[Bot alert: {alert['type']} / {alert['severity']}]",
                    command_output=plain or raw_msg[:8000],
                    metadata={
                        "source": "health_alert",
                        "alert_type": alert["type"],
                        "severity": alert["severity"],
                    },
                )
            except Exception as e:
                logger.warning("Failed to persist alert to conversation user=%s: %s", user_id, e)

        _last_alert_times[alert_key] = current_time
        delivered.append(alert)

    return delivered


async def start_health_monitoring(bot: Bot):
    """Start background scheduler: health, metrics, digest."""
    global _scheduler

    if _scheduler:
        logger.warning("Health monitoring already started")
        return

    interval = max(1, config.HEALTH_CHECK_INTERVAL)
    metrics_iv = max(5, config.METRICS_SAMPLE_INTERVAL_MINUTES)
    digest_h = max(1, config.DIGEST_INTERVAL_HOURS)

    logger.info(
        "Starting monitoring: health %sm, metrics %sm, digest %sh",
        interval,
        metrics_iv,
        digest_h,
    )

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        check_system_health,
        "interval",
        minutes=interval,
        args=[bot],
        id="health_check",
    )
    _scheduler.add_job(
        record_metrics_sample,
        "interval",
        minutes=metrics_iv,
        id="metrics_sample",
    )
    _scheduler.add_job(
        send_digest,
        "interval",
        hours=digest_h,
        args=[bot],
        id="digest",
    )
    if config.STORAGE_WEEKLY_SCAN_ENABLED:
        from commands.docker_storage_cmds import run_weekly_scan_report

        _scheduler.add_job(
            run_weekly_scan_report,
            "cron",
            day_of_week="sun",
            hour=9,
            minute=0,
            args=[bot],
            id="weekly_storage_scan",
        )
    if config.UPTIME_WEEKLY_REPORT_ENABLED:
        from monitoring.uptime.analytics import send_weekly_report

        _scheduler.add_job(
            send_weekly_report,
            "cron",
            day_of_week=config.UPTIME_WEEKLY_REPORT_DAY[:3],
            hour=8,
            minute=0,
            args=[bot],
            id="uptime_weekly_report",
        )
    if config.AUTOTROUBLESHOOT_ENABLED and config.AUTOTROUBLESHOOT_SCAN_UNACK:
        scan_h = max(1, config.AUTOTROUBLESHOOT_UNACK_SCAN_HOURS)
        _scheduler.add_job(
            scan_unacknowledged_alerts,
            "interval",
            hours=scan_h,
            args=[bot],
            id="autotroubleshoot_unack_scan",
        )
    if config.CROWDSEC_MONITOR_ENABLED:
        from monitoring.crowdsec_monitor import poll_crowdsec_alerts, send_crowdsec_daily_report

        poll_m = max(2, config.CROWDSEC_POLL_MINUTES)
        _scheduler.add_job(
            poll_crowdsec_alerts,
            "interval",
            minutes=poll_m,
            args=[bot],
            id="crowdsec_poll",
        )
        _scheduler.add_job(
            send_crowdsec_daily_report,
            "cron",
            hour=config.CROWDSEC_DAILY_REPORT_HOUR,
            minute=0,
            args=[bot],
            id="crowdsec_daily_report",
        )
        logger.info(
            "CrowdSec monitor: poll every %sm, daily report at %02d:00",
            poll_m,
            config.CROWDSEC_DAILY_REPORT_HOUR,
        )
    _scheduler.start()

    try:
        loop = asyncio.get_running_loop()

        async def broadcast_html(text: str):
            for uid in config.ALLOWED_USER_IDS:
                try:
                    await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error("cron_notify broadcast %s: %s", uid, e)

        start_cron_notify_server(loop, broadcast_html)
    except Exception as e:
        logger.error("cron_notify_server start: %s", e)

    if config.UPTIME_MONITORING_ENABLED:
        try:
            from monitoring.uptime.engine import start_uptime_monitoring

            await start_uptime_monitoring(bot)
        except Exception as e:
            logger.error("Failed to start uptime monitoring: %s", e, exc_info=True)

    await record_metrics_sample()
    await check_system_health(bot)


def stop_health_monitoring():
    """Stop scheduler and cron hook."""
    global _scheduler
    from monitoring.cron_notify_server import stop_cron_notify_server
    from monitoring.uptime.engine import stop_uptime_monitoring

    stop_uptime_monitoring()
    stop_cron_notify_server()
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Health monitoring stopped")
