"""Detect NAS reboots via psutil boot_time and alert Telegram."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode

import config
from database.models import get_db
from services.system_monitor import get_uptime
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)

_BOOT_KEY = "last_boot_time"


async def _get_stored_boot() -> Optional[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT value FROM uptime_host_state WHERE key = ?", (_BOOT_KEY,)
        )
        row = await cur.fetchone()
        return int(row[0]) if row else None
    except (TypeError, ValueError):
        return None
    finally:
        await db.close()


async def _set_stored_boot(boot_ts: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO uptime_host_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (_BOOT_KEY, str(boot_ts)),
        )
        await db.commit()
    finally:
        await db.close()


async def check_reboot_and_alert(bot: Bot) -> bool:
    """
    Returns True if a reboot was detected and alert sent.
    """
    if not config.UPTIME_REBOOT_ALERT_ENABLED:
        return False
    uptime = get_uptime()
    boot_ts = int(uptime.get("uptime_seconds", 0))
    # get_uptime returns uptime_seconds; we need boot_time
    try:
        import psutil
        boot_time = int(psutil.boot_time())
    except Exception:
        return False

    prev = await _get_stored_boot()
    if prev is None:
        await _set_stored_boot(boot_time)
        return False

    if boot_time == prev:
        return False

    await _set_stored_boot(boot_time)
    boot_dt = datetime.fromtimestamp(boot_time).strftime("%Y-%m-%d %H:%M:%S UTC")
    prev_dt = datetime.fromtimestamp(prev).strftime("%Y-%m-%d %H:%M:%S UTC")
    text = (
        f"🔄 <b>NAS reboot detected</b>\n\n"
        f"Previous boot: <code>{escape_telegram_html(prev_dt)}</code>\n"
        f"Current boot: <code>{escape_telegram_html(boot_dt)}</code>\n"
        f"Uptime now: <code>{uptime.get('uptime_seconds', 0)}s</code>"
    )
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("reboot alert %s: %s", uid, e)
    return True
