"""
Background health monitoring and alerting.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

import config
from services.system_monitor import (
    get_cpu_stats, get_memory_stats, get_disk_stats, get_temperatures
)
from services.docker_service import list_containers
from services.smart_monitor import get_all_drives
from monitoring.alerts import (
    check_disk_alerts, check_cpu_alerts, check_memory_alerts,
    check_temperature_alerts, check_docker_alerts, check_smart_alerts
)
from database.memory import save_alert, get_unacknowledged_alerts
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)

# Global scheduler
_scheduler = None
_last_alert_times = {}  # Track last alert time per type to prevent spam


async def check_system_health(bot: Bot):
    """Perform comprehensive system health check."""
    try:
        logger.debug("Running health check...")
        
        all_alerts = []
        
        # Check CPU
        cpu_stats = get_cpu_stats()
        cpu_percent = cpu_stats.get('percent', 0)
        all_alerts.extend(check_cpu_alerts(cpu_percent))
        
        # Check Memory
        mem_stats = get_memory_stats()
        mem_percent = mem_stats.get('percent', 0)
        all_alerts.extend(check_memory_alerts(mem_percent))
        
        # Check Disk
        disk_stats = get_disk_stats()
        all_alerts.extend(check_disk_alerts(disk_stats))
        
        # Check Temperatures
        temps = get_temperatures()
        all_alerts.extend(check_temperature_alerts(temps))
        
        # Check Docker
        try:
            containers = list_containers(all_containers=True)
            all_alerts.extend(check_docker_alerts(containers))
        except:
            pass  # Docker may not be available
        
        # Check SMART (less frequently as it's slow)
        current_minute = datetime.now().minute
        if current_minute % 15 == 0:  # Every 15 minutes
            try:
                drives = get_all_drives()
                all_alerts.extend(check_smart_alerts(drives))
            except:
                pass  # SMART may not be available
        
        # Send alerts
        if all_alerts:
            await send_alerts(bot, all_alerts)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)


async def send_alerts(bot: Bot, alerts: List[Dict[str, Any]]):
    """Send alerts to authorized users."""
    if not config.ALLOWED_USER_IDS:
        logger.warning("No users configured to receive alerts")
        return
    
    current_time = datetime.now()
    
    for alert in alerts:
        alert_key = f"{alert['type']}_{alert['message']}"
        
        # Check cooldown (don't spam same alert within 1 hour)
        last_time = _last_alert_times.get(alert_key)
        if last_time and (current_time - last_time) < timedelta(hours=1):
            continue
        
        # Save to database
        await save_alert(alert['type'], alert['severity'], alert['message'])
        
        # Format alert message
        severity_icons = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🔴'
        }
        
        icon = severity_icons.get(alert['severity'], '⚠️')
        sev = escape_telegram_html(alert['severity'].upper())
        body = escape_telegram_html(alert['message'])
        message = f"{icon} <b>Alert: {sev}</b>\n\n{body}"

        # Send to all authorized users
        for user_id in config.ALLOWED_USER_IDS:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=ParseMode.HTML,
                )
                logger.info(f"Sent alert to user {user_id}: {alert['type']}")
            except Exception as e:
                logger.error(f"Failed to send alert to user {user_id}: {e}")
        
        # Update last alert time
        _last_alert_times[alert_key] = current_time


async def start_health_monitoring(bot: Bot):
    """Start the background health monitoring scheduler."""
    global _scheduler
    
    if _scheduler:
        logger.warning("Health monitoring already started")
        return
    
    logger.info(f"Starting health monitoring (interval: {config.HEALTH_CHECK_INTERVAL} minutes)")
    
    _scheduler = AsyncIOScheduler()
    
    # Schedule health checks
    _scheduler.add_job(
        check_system_health,
        'interval',
        minutes=config.HEALTH_CHECK_INTERVAL,
        args=[bot],
        id='health_check'
    )
    
    _scheduler.start()
    
    logger.info("Health monitoring started")
    
    # Run initial check
    await check_system_health(bot)


def stop_health_monitoring():
    """Stop the health monitoring scheduler."""
    global _scheduler
    
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Health monitoring stopped")
