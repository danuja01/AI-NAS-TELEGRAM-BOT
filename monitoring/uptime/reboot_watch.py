"""Detect NAS reboots via psutil boot_time and alert Telegram + email."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

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


def _current_boot_time() -> Optional[int]:
    try:
        import psutil

        return int(psutil.boot_time())
    except Exception:
        return None


async def _detect_boot_change() -> Optional[Tuple[int, int]]:
    """
    Return (current_boot_time, previous_boot_time) when the host has restarted.
    Seeds storage on first run without treating it as a reboot.
    """
    boot_time = _current_boot_time()
    if boot_time is None:
        return None

    prev = await _get_stored_boot()
    if prev is None:
        await _set_stored_boot(boot_time)
        return None

    if boot_time == prev:
        return None

    await _set_stored_boot(boot_time)
    return boot_time, prev


async def _send_back_online_email(boot_time: int, previous_boot_time: int) -> None:
    from services.email_service import send_back_online_alert

    uptime = get_uptime()
    uptime_seconds = int(uptime.get("uptime_seconds", 0) or 0)
    try:
        await asyncio.to_thread(
            send_back_online_alert,
            boot_time=boot_time,
            previous_boot_time=previous_boot_time,
            uptime_seconds=uptime_seconds,
        )
    except Exception as e:
        logger.error("back-online email failed: %s", e)


async def check_reboot_and_alert(bot: Bot) -> bool:
    """
    Returns True if a reboot was detected and alert sent.
    """
    change = await _detect_boot_change()
    if not change:
        return False

    boot_time, prev = change
    uptime = get_uptime()
    boot_dt = datetime.fromtimestamp(boot_time, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    prev_dt = datetime.fromtimestamp(prev, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    if config.UPTIME_REBOOT_ALERT_ENABLED:
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

    await _send_back_online_email(boot_time, prev)
    return True


async def check_reboot_on_startup(bot: Bot) -> None:
    """Run once after bot startup so back-online email is not delayed until the first uptime tick."""
    try:
        await check_reboot_and_alert(bot)
    except Exception as e:
        logger.error("startup reboot check failed: %s", e)
