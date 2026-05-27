"""Detect Docker image ID changes (updates/redeploys)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from telegram import Bot
from telegram.constants import ParseMode

import config
from database.models import get_db
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)


async def _get_snapshot(name: str) -> Dict[str, str] | None:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            "SELECT image_id, image_tag FROM docker_image_snapshots WHERE container_name = ?",
            (name,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def _upsert_snapshot(name: str, image_id: str, image_tag: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO docker_image_snapshots (container_name, image_id, image_tag, recorded_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(container_name) DO UPDATE SET
                image_id = excluded.image_id,
                image_tag = excluded.image_tag,
                recorded_at = CURRENT_TIMESTAMP
            """,
            (name, image_id, image_tag or ""),
        )
        await db.commit()
    finally:
        await db.close()


def _container_images() -> List[Dict[str, Any]]:
    from services.docker_service import list_containers, get_container

    out = []
    for c in list_containers(all_containers=True, include_stats=False):
        name = (c.get("name") or "").lstrip("/")
        if not name or config.docker_container_ignored_for_alerts(name):
            continue
        try:
            container = get_container(name)
            img = container.image
            image_id = img.id or ""
            tag = img.tags[0] if img.tags else "untagged"
            out.append({"name": name, "image_id": image_id, "image_tag": tag})
        except Exception as e:
            logger.debug("image snapshot %s: %s", name, e)
    return out


async def scan_image_updates(bot: Bot) -> List[str]:
    """Compare current image IDs to DB; alert on change. Returns container names updated."""
    if not config.UPTIME_DOCKER_IMAGE_ALERTS:
        return []
    changed: List[str] = []
    for item in _container_images():
        name = item["name"]
        prev = await _get_snapshot(name)
        cur_id = item["image_id"]
        cur_tag = item["image_tag"]
        if prev is None:
            await _upsert_snapshot(name, cur_id, cur_tag)
            continue
        if prev.get("image_id") == cur_id:
            continue
        changed.append(name)
        await _upsert_snapshot(name, cur_id, cur_tag)
        old_tag = prev.get("image_tag") or "?"
        text = (
            f"📦 <b>Docker image updated</b>\n\n"
            f"<b>Container</b>: <code>{escape_telegram_html(name)}</code>\n"
            f"<b>Was</b>: <code>{escape_telegram_html(old_tag)}</code>\n"
            f"<b>Now</b>: <code>{escape_telegram_html(cur_tag)}</code>\n"
            f"<i>Image ID changed — container may have been recreated or pulled.</i>"
        )
        for uid in config.ALLOWED_USER_IDS:
            try:
                await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error("image update alert %s: %s", uid, e)
    return changed
