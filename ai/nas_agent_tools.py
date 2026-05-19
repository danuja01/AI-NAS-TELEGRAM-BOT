"""
Read-only tools the AI agent may call to answer questions with live NAS/Docker data.

Mutating operations (restart/stop/reboot) are intentionally excluded; users run slash-commands.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

import psutil

from services import docker_service as ds
from services.system_monitor import get_disk_stats, get_memory_stats, get_uptime

logger = logging.getLogger(__name__)

_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,253}$")

# OpenAI Chat Completions `tools` schema
NAS_AGENT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "nas_list_docker_containers",
            "description": (
                "List Docker containers on the host where the bot runs. "
                "Use when the user asks what is running, container names, status, or images."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_stopped": {
                        "type": "boolean",
                        "description": (
                            "If true, include stopped/exited containers (like /containers). "
                            "If false, only running containers."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nas_docker_container_logs",
            "description": (
                "Fetch recent stdout/stderr logs from one Docker container by name or short ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {
                        "type": "string",
                        "description": "Container name or ID",
                    },
                    "line_count": {
                        "type": "integer",
                        "description": "Number of log lines (1–200, default 80)",
                    },
                },
                "required": ["container"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nas_docker_unhealthy_containers",
            "description": (
                "List containers that look unhealthy: exited, dead, restarting, or healthcheck unhealthy."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nas_system_health_snapshot",
            "description": (
                "Quick live snapshot: CPU %, memory %, swap, a few disk partitions, uptime seconds. "
                "Use for questions about load, RAM, disk space, or how long the system has been up."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _validate_container_name(name: str) -> bool:
    return bool(name and _CONTAINER_NAME_RE.match(name))


def _simplify_container_row(c: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": c.get("id"),
        "name": c.get("name"),
        "status": c.get("status"),
    }
    if "image" in c:
        row["image"] = c["image"]
    if "cpu" in c:
        row["cpu_percent"] = c.get("cpu")
    if "memory" in c:
        row["memory_bytes"] = c.get("memory")
    return row


def _list_docker_containers(include_stopped: bool) -> str:
    if not ds.DOCKER_AVAILABLE:
        return json.dumps({"ok": False, "error": "Docker SDK not installed in this environment"})
    try:
        containers = ds.list_containers(all_containers=include_stopped)
        rows = [_simplify_container_row(c) for c in containers]
        return json.dumps(
            {"ok": True, "count": len(rows), "include_stopped": include_stopped, "containers": rows},
            default=str,
        )
    except Exception as e:
        logger.exception("nas_list_docker_containers")
        return json.dumps({"ok": False, "error": str(e)})


def _docker_logs(container: str, line_count: int) -> str:
    if not ds.DOCKER_AVAILABLE:
        return json.dumps({"ok": False, "error": "Docker SDK not installed"})
    if not _validate_container_name(container):
        return json.dumps({"ok": False, "error": "Invalid container name"})
    line_count = max(1, min(int(line_count or 80), 200))
    try:
        logs = ds.get_container_logs(container, lines=line_count)
        if len(logs) > 16000:
            logs = "…[truncated]…\n" + logs[-16000:]
        return json.dumps({"ok": True, "container": container, "lines": line_count, "logs": logs})
    except Exception as e:
        logger.warning("nas_docker_container_logs: %s", e)
        return json.dumps({"ok": False, "error": str(e)})


def _docker_unhealthy() -> str:
    if not ds.DOCKER_AVAILABLE:
        return json.dumps({"ok": False, "error": "Docker SDK not installed"})
    try:
        bad = ds.detect_unhealthy_containers()
        rows = [_simplify_container_row(c) for c in bad]
        return json.dumps({"ok": True, "count": len(rows), "unhealthy": rows}, default=str)
    except Exception as e:
        logger.exception("nas_docker_unhealthy_containers")
        return json.dumps({"ok": False, "error": str(e)})


def _system_snapshot() -> str:
    try:
        cpu_percent = float(psutil.cpu_percent(interval=0.25))
        mem = get_memory_stats()
        disks = get_disk_stats()
        uptime = get_uptime()
        disk_brief = [
            {
                "mount": d.get("mountpoint"),
                "used_percent": round(d.get("percent", 0), 1),
                "free_gb": round(d.get("free_gb", 0), 2),
            }
            for d in disks[:8]
        ]
        payload = {
            "ok": True,
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(mem.get("percent", 0), 1) if isinstance(mem, dict) else None,
            "memory_used_gb": round(mem.get("used_gb", 0), 2) if isinstance(mem, dict) else None,
            "swap_percent": mem.get("swap", {}).get("percent") if isinstance(mem, dict) else None,
            "uptime_seconds": uptime.get("uptime_seconds"),
            "disk_partitions_sample": disk_brief,
        }
        return json.dumps(payload, default=str)
    except Exception as e:
        logger.exception("nas_system_health_snapshot")
        return json.dumps({"ok": False, "error": str(e)})


def run_nas_tool(function_name: str, arguments: Dict[str, Any] | None) -> str:
    """
    Execute one tool by name. Returns a short JSON string for the model (never raises).
    """
    args = arguments or {}
    try:
        if function_name == "nas_list_docker_containers":
            include_stopped = bool(args.get("include_stopped", True))
            return _list_docker_containers(include_stopped)
        if function_name == "nas_docker_container_logs":
            return _docker_logs(str(args.get("container", "")), int(args.get("line_count", 80)))
        if function_name == "nas_docker_unhealthy_containers":
            return _docker_unhealthy()
        if function_name == "nas_system_health_snapshot":
            return _system_snapshot()
        return json.dumps({"ok": False, "error": f"Unknown tool: {function_name}"})
    except Exception as e:
        logger.exception("run_nas_tool %s", function_name)
        return json.dumps({"ok": False, "error": str(e)})
