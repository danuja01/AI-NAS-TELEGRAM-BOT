"""Persistence layer for uptime monitors."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config
from database.models import get_db

logger = logging.getLogger(__name__)

MONITOR_TYPES = frozenset({
    "http", "https", "tcp", "ping", "docker", "process", "dns",
    "keyword", "ssl", "push", "systemd",
})


def _row_to_monitor(row) -> Dict[str, Any]:
    d = dict(row)
    d["enabled"] = bool(d.get("enabled"))
    d["maintenance_mode"] = bool(d.get("maintenance_mode"))
    if d.get("tags"):
        try:
            d["tags_list"] = json.loads(d["tags"]) if d["tags"].startswith("[") else [
                t.strip() for t in d["tags"].split(",") if t.strip()
            ]
        except json.JSONDecodeError:
            d["tags_list"] = [t.strip() for t in (d["tags"] or "").split(",") if t.strip()]
    else:
        d["tags_list"] = []
    return d


async def list_monitors(enabled_only: bool = False) -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        q = "SELECT * FROM uptime_monitors"
        if enabled_only:
            q += " WHERE enabled = 1 AND maintenance_mode = 0"
        q += " ORDER BY name"
        cur = await db.execute(q)
        rows = await cur.fetchall()
        return [_row_to_monitor(r) for r in rows]
    finally:
        await db.close()


async def get_monitor(monitor_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute("SELECT * FROM uptime_monitors WHERE id = ?", (monitor_id,))
        row = await cur.fetchone()
        return _row_to_monitor(row) if row else None
    finally:
        await db.close()


async def get_monitor_by_name(name: str) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            "SELECT * FROM uptime_monitors WHERE name = ?", (name.strip(),)
        )
        row = await cur.fetchone()
        return _row_to_monitor(row) if row else None
    finally:
        await db.close()


async def create_monitor(
    name: str,
    mtype: str,
    target: str,
    *,
    interval_seconds: Optional[int] = None,
    timeout_seconds: int = 10,
    retries: int = 1,
    keyword: str = "",
    expected_status: Optional[int] = None,
    tags: Optional[List[str]] = None,
    enabled: bool = True,
) -> int:
    mtype = mtype.lower().strip()
    if mtype not in MONITOR_TYPES:
        raise ValueError(f"Invalid monitor type: {mtype}")
    tags_json = json.dumps(tags or [])
    iv = interval_seconds or config.UPTIME_DEFAULT_INTERVAL
    db = await get_db()
    try:
        cur = await db.execute(
            """
            INSERT INTO uptime_monitors
            (name, type, target, interval_seconds, enabled, keyword,
             timeout_seconds, retries, tags, expected_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                mtype,
                target.strip(),
                iv,
                1 if enabled else 0,
                keyword or None,
                timeout_seconds,
                retries,
                tags_json,
                expected_status,
            ),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def update_monitor(monitor_id: int, **fields) -> bool:
    allowed = {
        "name", "type", "target", "interval_seconds", "enabled", "maintenance_mode",
        "keyword", "timeout_seconds", "retries", "tags", "expected_status",
        "notify_route", "escalation_stage", "parent_monitor_id",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0
    if "maintenance_mode" in updates:
        updates["maintenance_mode"] = 1 if updates["maintenance_mode"] else 0
    if "tags" in updates and isinstance(updates["tags"], list):
        updates["tags"] = json.dumps(updates["tags"])
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [monitor_id]
    db = await get_db()
    try:
        await db.execute(f"UPDATE uptime_monitors SET {cols} WHERE id = ?", vals)
        await db.commit()
        return True
    finally:
        await db.close()


async def delete_monitor(monitor_id: int) -> bool:
    db = await get_db()
    try:
        await db.execute("DELETE FROM uptime_monitors WHERE id = ?", (monitor_id,))
        await db.commit()
        return True
    finally:
        await db.close()


async def record_heartbeat(
    monitor_id: int,
    success: bool,
    latency_ms: Optional[float],
    status_code: Optional[int] = None,
    error_message: str = "",
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO uptime_heartbeats
            (monitor_id, success, latency_ms, status_code, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (monitor_id, 1 if success else 0, latency_ms, status_code, error_message[:2000]),
        )
        status = "up" if success else "down"
        if success:
            await db.execute(
                """
                UPDATE uptime_monitors SET
                    last_check = CURRENT_TIMESTAMP,
                    last_status = ?,
                    response_time_ms = ?,
                    consecutive_successes = consecutive_successes + 1,
                    consecutive_failures = 0
                WHERE id = ?
                """,
                (status, latency_ms, monitor_id),
            )
        else:
            await db.execute(
                """
                UPDATE uptime_monitors SET
                    last_check = CURRENT_TIMESTAMP,
                    last_status = ?,
                    consecutive_failures = consecutive_failures + 1,
                    consecutive_successes = 0
                WHERE id = ?
                """,
                (status, monitor_id),
            )
        await db.commit()
        await _recompute_uptime_pct(db, monitor_id)
        await _prune_old_heartbeats(db)
    finally:
        await db.close()


async def _recompute_uptime_pct(db, monitor_id: int, days: int = 7) -> None:
    cur = await db.execute(
        """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS ok
        FROM uptime_heartbeats
        WHERE monitor_id = ? AND checked_at >= datetime('now', ?)
        """,
        (monitor_id, f"-{days} days"),
    )
    row = await cur.fetchone()
    if row and row[0] and row[0] > 0:
        pct = 100.0 * (row[1] or 0) / row[0]
        await db.execute(
            "UPDATE uptime_monitors SET uptime_percentage = ? WHERE id = ?",
            (round(pct, 2), monitor_id),
        )


async def _prune_old_heartbeats(db) -> None:
    days = config.UPTIME_HEARTBEAT_RETENTION_DAYS
    await db.execute(
        "DELETE FROM uptime_heartbeats WHERE checked_at < datetime('now', ?)",
        (f"-{days} days",),
    )


async def get_due_monitors() -> List[Dict[str, Any]]:
    """Monitors that should run on this tick."""
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT * FROM uptime_monitors
            WHERE enabled = 1 AND maintenance_mode = 0
            AND (
                last_check IS NULL
                OR datetime(last_check, '+' || interval_seconds || ' seconds') <= datetime('now')
            )
            """
        )
        rows = await cur.fetchall()
        return [_row_to_monitor(r) for r in rows]
    finally:
        await db.close()


async def open_incident(monitor_id: int, root_cause: str = "") -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            """
            SELECT id FROM uptime_incidents
            WHERE monitor_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
            """,
            (monitor_id,),
        )
        existing = await cur.fetchone()
        if existing:
            return existing[0]
        cur = await db.execute(
            """
            INSERT INTO uptime_incidents (monitor_id, root_cause)
            VALUES (?, ?)
            """,
            (monitor_id, root_cause[:1000]),
        )
        await db.commit()
        return cur.lastrowid
    finally:
        await db.close()


async def update_incident_ai_summary(monitor_id: int, ai_summary: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            UPDATE uptime_incidents SET ai_summary = ?
            WHERE monitor_id = ? AND ended_at IS NULL
            """,
            (ai_summary[:8000], monitor_id),
        )
        await db.commit()
    finally:
        await db.close()


async def close_incident(monitor_id: int, ai_summary: str = "") -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT * FROM uptime_incidents
            WHERE monitor_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
            """,
            (monitor_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        started = datetime.fromisoformat(str(row["started_at"]).replace("Z", ""))
        ended = datetime.utcnow()
        duration = int((ended - started).total_seconds())
        await db.execute(
            """
            UPDATE uptime_incidents SET
                ended_at = CURRENT_TIMESTAMP,
                duration_seconds = ?,
                ai_summary = ?
            WHERE id = ?
            """,
            (duration, ai_summary[:8000] if ai_summary else None, row["id"]),
        )
        await db.commit()
        return {**dict(row), "duration_seconds": duration}
    finally:
        await db.close()


async def get_open_incident(monitor_id: int) -> Optional[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT * FROM uptime_incidents
            WHERE monitor_id = ? AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
            """,
            (monitor_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def add_dependency(parent_id: int, child_id: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT OR IGNORE INTO uptime_dependencies (parent_monitor_id, child_monitor_id)
            VALUES (?, ?)
            """,
            (parent_id, child_id),
        )
        await db.commit()
    finally:
        await db.close()


async def get_children_of(parent_id: int) -> List[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT child_monitor_id FROM uptime_dependencies WHERE parent_monitor_id = ?",
            (parent_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]
    finally:
        await db.close()


async def get_parent_ids(child_id: int) -> List[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT parent_monitor_id FROM uptime_dependencies WHERE child_monitor_id = ?",
            (child_id,),
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]
    finally:
        await db.close()


async def is_silenced(monitor_id: int, tags: List[str]) -> bool:
    db = await get_db()
    try:
        cur = await db.execute(
            """
            SELECT 1 FROM uptime_silences
            WHERE until_at > datetime('now')
            AND (monitor_id = ? OR monitor_id IS NULL)
            LIMIT 1
            """,
            (monitor_id,),
        )
        if await cur.fetchone():
            return True
        for tag in tags:
            cur = await db.execute(
                """
                SELECT 1 FROM uptime_silences
                WHERE until_at > datetime('now') AND tag = ?
                """,
                (tag,),
            )
            if await cur.fetchone():
                return True
        return False
    finally:
        await db.close()


async def add_silence(
    until_minutes: int,
    monitor_id: Optional[int] = None,
    tag: Optional[str] = None,
    reason: str = "",
) -> None:
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO uptime_silences (monitor_id, tag, until_at, reason)
            VALUES (?, ?, datetime('now', ?), ?)
            """,
            (monitor_id, tag, f"+{until_minutes} minutes", reason[:500]),
        )
        await db.commit()
    finally:
        await db.close()


async def get_monitor_stats(monitor_id: int, hours: int = 168) -> Dict[str, Any]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT
                COUNT(*) AS n,
                AVG(latency_ms) AS avg_latency,
                MAX(latency_ms) AS max_latency,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS ok
            FROM uptime_heartbeats
            WHERE monitor_id = ? AND checked_at >= datetime('now', ?)
            """,
            (monitor_id, f"-{hours} hours"),
        )
        row = await cur.fetchone()
        d = dict(row) if row else {}
        n = d.get("n") or 0
        ok = d.get("ok") or 0
        d["uptime_pct"] = round(100.0 * ok / n, 2) if n else None
        cur2 = await db.execute(
            """
            SELECT COUNT(*) FROM uptime_incidents
            WHERE monitor_id = ? AND started_at >= datetime('now', ?)
            """,
            (monitor_id, f"-{hours} hours"),
        )
        d["incident_count"] = (await cur2.fetchone())[0]
        return d
    finally:
        await db.close()


async def list_recent_incidents(limit: int = 20) -> List[Dict[str, Any]]:
    db = await get_db()
    try:
        db.row_factory = __import__("aiosqlite").Row
        cur = await db.execute(
            """
            SELECT i.*, m.name AS monitor_name, m.type AS monitor_type
            FROM uptime_incidents i
            JOIN uptime_monitors m ON m.id = i.monitor_id
            ORDER BY i.started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def register_push_token(monitor_id: int) -> str:
    import secrets
    token = secrets.token_urlsafe(24)
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO uptime_push_tokens (token, monitor_id) VALUES (?, ?)",
            (token, monitor_id),
        )
        await db.commit()
        return token
    finally:
        await db.close()


async def record_push_heartbeat(token: str) -> Optional[int]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT monitor_id FROM uptime_push_tokens WHERE token = ?",
            (token,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        mid = row[0]
        await db.execute(
            "UPDATE uptime_push_tokens SET last_seen = CURRENT_TIMESTAMP WHERE token = ?",
            (token,),
        )
        await db.commit()
        return mid
    finally:
        await db.close()
