"""
Memory management for conversations and command history.
Implements conversation history retrieval for context-aware responses.
"""

import json
import logging
import aiosqlite
from datetime import datetime
from typing import List, Dict, Any, Optional

import config
from database.models import get_db
from utils.security import redact_command_for_storage

logger = logging.getLogger(__name__)


async def save_conversation(
    user_id: int,
    role: str,
    message: str,
    command_output: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Save a conversation message.
    
    Args:
        user_id: Telegram user ID
        role: 'user' or 'assistant'
        message: The message content
        command_output: Optional command output (for context)
        metadata: Optional metadata dictionary
    """
    db = None
    try:
        db = await get_db()
        metadata_json = json.dumps(metadata) if metadata else None
        
        await db.execute(
            """
            INSERT INTO conversations (user_id, role, message, command_output, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, role, message, command_output, metadata_json)
        )
        await db.commit()
        
        logger.debug(f"Saved conversation for user {user_id}: {role}")
    
    except Exception as e:
        logger.error(f"Failed to save conversation: {e}")
    finally:
        if db:
            await db.close()


async def get_recent_context(user_id: int, limit: int = None) -> List[Dict[str, Any]]:
    """
    Get recent conversation history for a user.
    
    Args:
        user_id: Telegram user ID
        limit: Maximum number of messages (defaults to config.CONVERSATION_HISTORY_LENGTH)
    
    Returns:
        List of conversation messages with metadata
    """
    if limit is None:
        limit = config.CONVERSATION_HISTORY_LENGTH
    
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute(
            """
            SELECT id, role, message, command_output, metadata, timestamp
            FROM conversations
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        
        rows = await cursor.fetchall()
        
        # Reverse to get chronological order
        messages = []
        for row in reversed(rows):
            msg = {
                'id': row['id'],
                'role': row['role'],
                'message': row['message'],
                'command_output': row['command_output'],
                'timestamp': row['timestamp']
            }
            
            if row['metadata']:
                try:
                    msg['metadata'] = json.loads(row['metadata'])
                except:
                    pass
            
            messages.append(msg)
        
        return messages
    
    except Exception as e:
        logger.error(f"Failed to get recent context: {e}")
        return []
    finally:
        if db:
            await db.close()


async def build_context_string(user_id: int, limit: int = None) -> str:
    """
    Build a formatted context string from recent conversation history.
    Used for RAG queries to provide conversation context.
    
    Args:
        user_id: Telegram user ID
        limit: Maximum number of messages to include
    
    Returns:
        Formatted context string
    """
    messages = await get_recent_context(user_id, limit)
    
    if not messages:
        return ""
    
    context_parts = ["Recent conversation context:"]
    
    for msg in messages:
        role_label = "You" if msg['role'] == 'user' else "Assistant"
        context_parts.append(f"{role_label}: {msg['message']}")
        
        # Include command output if available
        if msg.get('command_output'):
            context_parts.append(f"[Command Output]: {msg['command_output']}")
    
    return "\n".join(context_parts)


async def clear_conversation_history(user_id: int):
    """
    Clear conversation history for a user.
    
    Args:
        user_id: Telegram user ID
    """
    db = None
    try:
        # Do not use ``async with await get_db()`` — aiosqlite.Connection is already
        # started after ``await connect()``; re-entering __aenter__ raises
        # RuntimeError: threads can only be started once.
        db = await get_db()
        await db.execute(
            "DELETE FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        logger.info(f"Cleared conversation history for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to clear conversation history: {e}")
    finally:
        if db:
            await db.close()


async def save_command(user_id: int, command: str, output_summary: str = None, success: bool = True):
    """
    Save command execution to history.
    
    Args:
        user_id: Telegram user ID
        command: The command that was executed
        output_summary: Brief summary of the output
        success: Whether the command succeeded
    """
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            INSERT INTO command_history (user_id, command, output_summary, success)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, command, output_summary, success)
        )
        await db.commit()
        
        logger.debug(f"Saved command history for user {user_id}: {command}")
    
    except Exception as e:
        logger.error(f"Failed to save command history: {e}")
    finally:
        if db:
            await db.close()


async def get_command_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get recent command history for a user.
    
    Args:
        user_id: Telegram user ID
        limit: Maximum number of commands to retrieve
    
    Returns:
        List of command history entries
    """
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT command, output_summary, success, timestamp
            FROM command_history
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to get command history: {e}")
        return []
    finally:
        if db:
            await db.close()


async def get_user_preferences(user_id: int) -> Dict[str, str]:
    """
    Get user preferences.
    
    Args:
        user_id: Telegram user ID
    
    Returns:
        Dictionary of preferences
    """
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT key, value FROM preferences WHERE user_id = ?",
            (user_id,),
        )

        rows = await cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}

    except Exception as e:
        logger.error(f"Failed to get user preferences: {e}")
        return {}
    finally:
        if db:
            await db.close()


async def set_user_preference(user_id: int, key: str, value: str):
    """
    Set a user preference.
    
    Args:
        user_id: Telegram user ID
        key: Preference key
        value: Preference value
    """
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            INSERT OR REPLACE INTO preferences (user_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (user_id, key, value),
        )
        await db.commit()

    except Exception as e:
        logger.error(f"Failed to set user preference: {e}")
    finally:
        if db:
            await db.close()


async def save_alert(alert_type: str, severity: str, message: str):
    """
    Save an alert to the database.
    
    Args:
        alert_type: Type of alert
        severity: Alert severity level
        message: Alert message
    """
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            INSERT INTO alerts (type, severity, message)
            VALUES (?, ?, ?)
            """,
            (alert_type, severity, message),
        )
        await db.commit()

    except Exception as e:
        logger.error(f"Failed to save alert: {e}")
    finally:
        if db:
            await db.close()


async def get_unacknowledged_alerts() -> List[Dict[str, Any]]:
    """Get all unacknowledged alerts."""
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            """
            SELECT id, type, severity, message, timestamp
            FROM alerts
            WHERE acknowledged = FALSE
            ORDER BY timestamp DESC
            """
        )

        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to get unacknowledged alerts: {e}")
        return []
    finally:
        if db:
            await db.close()


async def acknowledge_alert(alert_id: int):
    """Mark an alert as acknowledged."""
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            UPDATE alerts
            SET acknowledged = TRUE, acknowledged_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (alert_id,),
        )
        await db.commit()

    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
    finally:
        if db:
            await db.close()


async def acknowledge_all_alerts() -> int:
    """Mark every unacknowledged alert as acknowledged. Returns rows updated."""
    db = None
    try:
        db = await get_db()
        cur = await db.execute(
            """
            UPDATE alerts
            SET acknowledged = TRUE, acknowledged_at = CURRENT_TIMESTAMP
            WHERE acknowledged = FALSE
            """
        )
        await db.commit()
        return int(cur.rowcount or 0)
    except Exception as e:
        logger.error("Failed to acknowledge all alerts: %s", e)
        return 0
    finally:
        if db:
            await db.close()


async def get_smart_snapshots_dict() -> Dict[str, Dict[str, int]]:
    """Return {device: {reallocated, pending}} from DB."""
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT device, reallocated, pending FROM smart_snapshots"
        )
        rows = await cur.fetchall()
        await db.close()
        return {
            r["device"]: {"reallocated": r["reallocated"] or 0, "pending": r["pending"] or 0}
            for r in rows
        }
    except Exception as e:
        logger.error("get_smart_snapshots_dict: %s", e)
        return {}


async def upsert_smart_snapshots(drives: List[Dict[str, Any]]):
    """Store latest SMART counters for each drive."""
    if not drives:
        return
    db = None
    try:
        db = await get_db()
        for d in drives:
            dev = d.get("device") or ""
            if not dev:
                continue
            realloc = int(d.get("reallocated_sectors") or 0)
            pending = int(d.get("pending_sectors") or 0)
            await db.execute(
                """
                INSERT INTO smart_snapshots (device, reallocated, pending, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(device) DO UPDATE SET
                    reallocated = excluded.reallocated,
                    pending = excluded.pending,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (dev, realloc, pending),
            )
        await db.commit()
    except Exception as e:
        logger.error("upsert_smart_snapshots: %s", e)
    finally:
        if db:
            await db.close()


async def append_drive_spin_samples(drives: List[Dict[str, Any]]):
    """
    Append one spin/power-cycle counter row per drive (called from periodic health job).
    Retains roughly 30 days of rows (pruned on each run).
    """
    if not drives:
        return
    db = None
    try:
        db = await get_db()
        for d in drives:
            dev = d.get("device") or ""
            if not dev:
                continue
            await db.execute(
                """
                INSERT INTO drive_spin_history (device, start_stop, load_cycle, power_cycles)
                VALUES (?, ?, ?, ?)
                """,
                (
                    dev,
                    d.get("start_stop_count"),
                    d.get("load_cycle_count"),
                    d.get("power_cycle_count"),
                ),
            )
        await db.execute(
            "DELETE FROM drive_spin_history WHERE recorded_at < datetime('now', '-30 days')"
        )
        await db.commit()
    except Exception as e:
        logger.error("append_drive_spin_samples: %s", e)
    finally:
        if db:
            await db.close()


async def get_drive_spin_history(device: str, limit: int = 14) -> List[Dict[str, Any]]:
    """Recent spin-counter samples for one device, newest first."""
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT device, recorded_at, start_stop, load_cycle, power_cycles
            FROM drive_spin_history
            WHERE device = ?
            ORDER BY recorded_at DESC
            LIMIT ?
            """,
            (device, limit),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_drive_spin_history: %s", e)
        return []
    finally:
        if db:
            await db.close()


async def save_storage_snapshot(
    reclaimable_hint: str = "",
    disk_min_free_percent: Optional[float] = None,
    docker_df_excerpt: str = "",
):
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            INSERT INTO storage_snapshots (reclaimable_hint, disk_min_free_percent, docker_df_excerpt)
            VALUES (?, ?, ?)
            """,
            (reclaimable_hint, disk_min_free_percent, docker_df_excerpt),
        )
        await db.execute(
            "DELETE FROM storage_snapshots WHERE recorded_at < datetime('now', '-90 days')"
        )
        await db.commit()
    except Exception as e:
        logger.error("save_storage_snapshot: %s", e)
    finally:
        if db:
            await db.close()


async def add_metric_sample(
    cpu_percent: float,
    memory_percent: float,
    temp_max: Optional[float],
    disk_min_free_percent: Optional[float],
    pending_updates_count: Optional[int] = None,
):
    """Append one metric row."""
    db = None
    try:
        db = await get_db()
        await db.execute(
            """
            INSERT INTO metric_samples
            (cpu_percent, memory_percent, temp_max, disk_min_free_percent, pending_updates_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cpu_percent, memory_percent, temp_max, disk_min_free_percent, pending_updates_count),
        )
        await db.commit()
    except Exception as e:
        logger.error("add_metric_sample: %s", e)
    finally:
        if db:
            await db.close()


async def get_metrics_digest_stats(hours: int = 24) -> Dict[str, Any]:
    """Aggregate metric_samples for digest message."""
    db = None
    try:
        db = await get_db()
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                COUNT(*) AS n,
                AVG(cpu_percent) AS cpu_avg,
                MAX(cpu_percent) AS cpu_max,
                AVG(memory_percent) AS mem_avg,
                MAX(memory_percent) AS mem_max,
                MAX(temp_max) AS temp_max,
                MIN(disk_min_free_percent) AS disk_free_min
            FROM metric_samples
            WHERE recorded_at >= datetime('now', ?)
            """,
            (f"-{int(hours)} hours",),
        )
        row = await cur.fetchone()
        await db.close()
        return dict(row) if row else {}
    except Exception as e:
        logger.error("get_metrics_digest_stats: %s", e)
        return {}
