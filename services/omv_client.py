"""
Read-only OpenMediaVault data via host `omv-rpc` (same RPC surface as the web UI).

Requires ``HOST_EXEC_MODE=nsenter`` or ``ssh`` so the command runs on the OMV host.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import config
from services.host_runner import HostExecResult, run_profile

logger = logging.getLogger(__name__)


def parse_omv_rpc_output(result: HostExecResult) -> Tuple[Any, Optional[str]]:
    """Parse stdout/stderr from ``omv-rpc``. Returns (data, error_message)."""
    if result.error:
        return None, result.error
    raw = (result.stdout or "").strip()
    if not raw and (result.stderr or "").strip():
        raw = (result.stderr or "").strip()
    if not raw:
        return None, "Empty omv-rpc output"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON from omv-rpc: {e}"

    if isinstance(data, dict):
        if data.get("error") is not None:
            err = data["error"]
            if isinstance(err, dict):
                return None, str(err.get("message") or err.get("code") or err)
            return None, str(err)
    return data, None


def _unwrap_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        inner = payload.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def omv_rpc_available() -> bool:
    return bool(getattr(config, "OMV_RPC_ENABLED", True)) and (
        (config.HOST_EXEC_MODE or "none").lower() not in ("none", "")
    )


def run_omv_rpc_sync(call_key: str) -> HostExecResult:
    return run_profile("omv_rpc", extra_args=[call_key], timeout=min(120, config.HOST_EXEC_TIMEOUT_SHORT))


async def omv_rpc_call(call_key: str) -> HostExecResult:
    return await asyncio.to_thread(run_omv_rpc_sync, call_key)


async def fetch_disk_enumerate() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = await omv_rpc_call("disk_enumerate")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


async def fetch_filesystems_mounted() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = await omv_rpc_call("filesystem_mounted")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


async def fetch_smart_devices() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = await omv_rpc_call("smart_enumerate")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


def sync_fetch_disk_enumerate() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = run_omv_rpc_sync("disk_enumerate")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


def sync_fetch_filesystems_mounted() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = run_omv_rpc_sync("filesystem_mounted")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


def sync_fetch_smart_devices() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    r = run_omv_rpc_sync("smart_enumerate")
    data, err = parse_omv_rpc_output(r)
    if err:
        return [], err
    return _unwrap_rows(data), None


def omv_disk_summary_json(disks: List[Dict[str, Any]], limit: int = 24) -> str:
    """Compact JSON for agent tools."""
    slim = []
    for d in disks[:limit]:
        slim.append(
            {
                "devicefile": d.get("devicefile"),
                "model": d.get("model"),
                "serialnumber": d.get("serialnumber"),
                "size": d.get("size"),
                "temperature": d.get("temperature"),
                "powermode": d.get("powermode"),
                "wwn": d.get("wwn"),
                "isroot": d.get("isroot"),
            }
        )
    return json.dumps({"ok": True, "count": len(disks), "disks": slim}, default=str)


def omv_filesystems_summary_json(rows: List[Dict[str, Any]], limit: int = 32) -> str:
    slim = []
    for r in rows[:limit]:
        slim.append(
            {
                "mountpoint": r.get("mountpoint"),
                "devicefile": r.get("devicefile"),
                "type": r.get("type"),
                "percentage": r.get("percentage"),
                "used": r.get("used"),
                "available": r.get("available"),
                "description": r.get("description"),
            }
        )
    return json.dumps({"ok": True, "count": len(rows), "filesystems": slim}, default=str)


def omv_smart_summary_json(rows: List[Dict[str, Any]], limit: int = 24) -> str:
    slim = []
    for r in rows[:limit]:
        slim.append(
            {
                "devicefile": r.get("devicefile"),
                "model": r.get("model"),
                "serialnumber": r.get("serialnumber"),
                "temperature": r.get("temperature"),
                "overallstatus": r.get("overallstatus"),
                "monitor": r.get("monitor"),
            }
        )
    return json.dumps({"ok": True, "count": len(rows), "devices": slim}, default=str)
