"""Service dependency graph — suppress cascading alerts."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set

from monitoring.uptime import store

logger = logging.getLogger(__name__)

# In-memory: parent monitor down -> suppress child DOWN notifications this cycle
_suppressed_children: Set[int] = set()
_root_cause_batch: Dict[int, List[str]] = {}


async def should_suppress_child_alert(monitor_id: int) -> bool:
    """True if a parent monitor is currently down."""
    parent_ids = await store.get_parent_ids(monitor_id)
    for pid in parent_ids:
        parent = await store.get_monitor(pid)
        if parent and parent.get("last_status") == "down":
            return True
    return False


async def on_parent_down(parent_id: int, parent_name: str) -> List[str]:
    """Collect affected child monitor names when parent goes down."""
    child_ids = await store.get_children_of(parent_id)
    names: List[str] = []
    for cid in child_ids:
        _suppressed_children.add(cid)
        child = await store.get_monitor(cid)
        if child:
            names.append(child.get("name", f"id:{cid}"))
    if names:
        _root_cause_batch[parent_id] = names
    return names


async def get_suppression_message(parent_id: int) -> str:
    children = _root_cause_batch.get(parent_id, [])
    if not children:
        return ""
    lines = ["<b>Affected services</b> (alerts suppressed):"]
    for n in children:
        lines.append(f"• <code>{n}</code>")
    return "\n".join(lines)


def clear_suppression_cache() -> None:
    _suppressed_children.clear()
    _root_cause_batch.clear()


def is_suppressed(monitor_id: int) -> bool:
    return monitor_id in _suppressed_children
