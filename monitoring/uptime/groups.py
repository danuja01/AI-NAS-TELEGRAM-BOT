"""Monitor groups and tag management."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from database.models import get_db

logger = logging.getLogger(__name__)


async def create_group(name: str, description: str = "") -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "INSERT INTO uptime_monitor_groups (name, description) VALUES (?, ?)",
            (name.strip(), description[:500]),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def list_groups() -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            "SELECT g.*, COUNT(m.monitor_id) AS member_count "
            "FROM uptime_monitor_groups g "
            "LEFT JOIN uptime_monitor_group_members m ON m.group_id = g.id "
            "GROUP BY g.id ORDER BY g.name"
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def add_monitor_to_group(group_name: str, monitor_name: str) -> bool:
    from monitoring.uptime import store

    g = await get_group_by_name(group_name)
    m = await store.get_monitor_by_name(monitor_name)
    if not g or not m:
        return False
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO uptime_monitor_group_members (group_id, monitor_id) "
            "VALUES (?, ?)",
            (g["id"], m["id"]),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_group_by_name(name: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            "SELECT * FROM uptime_monitor_groups WHERE name = ?", (name.strip(),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def list_monitors_in_group(group_name: str) -> List[Dict[str, Any]]:
    from monitoring.uptime import store

    g = await get_group_by_name(group_name)
    if not g:
        return []
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT m.* FROM uptime_monitors m
            JOIN uptime_monitor_group_members gm ON gm.monitor_id = m.id
            WHERE gm.group_id = ?
            ORDER BY m.name
            """,
            (g["id"],),
        )
        rows = await cur.fetchall()
        from monitoring.uptime.store import _row_to_monitor

        return [_row_to_monitor(r) for r in rows]
    finally:
        await db.close()


async def set_monitor_tags(monitor_name: str, tags: List[str]) -> bool:
    from monitoring.uptime import store

    m = await store.get_monitor_by_name(monitor_name)
    if not m:
        return False
    await store.update_monitor(m["id"], tags=tags)
    return True
