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

import config
from services import docker_service as ds
from services.file_service import get_storage_summary
from services.service_manager import list_common_services
from services.smart_monitor import check_drive_warnings, get_all_drives
from services.system_monitor import (
    calculate_health_score,
    get_disk_stats,
    get_memory_stats,
    get_network_stats,
    get_temperatures,
    get_uptime,
)

logger = logging.getLogger(__name__)

_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,253}$")

_MAX_SERVICES = 45
_MAX_SMART_DRIVES = 12


def _tool_entry(
    name: str,
    description: str,
    properties: Dict[str, Any] | None = None,
    required: List[str] | None = None,
) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


# OpenAI Chat Completions `tools` schema (read-only; mirrors /temps, /health, /disk, etc.)
NAS_AGENT_TOOLS: List[Dict[str, Any]] = [
    _tool_entry(
        "nas_temperature_sensors",
        (
            "Read current hardware temperature sensors (°C) from this host via psutil — same source as /temps. "
            "You MUST call this when the user asks whether their NAS temperatures are normal, too hot, idle vs load, "
            "or anything about 'my' sensor readings. Never answer from generic hardware advice alone without calling this first."
        ),
    ),
    _tool_entry(
        "nas_health_score",
        (
            "Compute a simple 0–100 health score and a list of issues (CPU, RAM, disk space, temperatures) for THIS host. "
            "Similar signals to /health. Use when asked about overall health, 'is something wrong', or stability."
        ),
    ),
    _tool_entry(
        "nas_disk_partitions",
        (
            "List mounted disk partitions with used/free GB and usage percent (like /disk). "
            "Use for disk space, full volumes, or mountpoint questions."
        ),
    ),
    _tool_entry(
        "nas_network_interfaces",
        (
            "Per-interface byte/packet counters and optional Tailscale IPv4 (like /network). "
            "Use for bandwidth, interface names, or transfer totals."
        ),
    ),
    _tool_entry(
        "nas_smart_drives",
        (
            "SMART summary for detected drives via smartctl (like /smart): model, self-test health, drive temperature if reported, "
            "power-on hours, reallocated/pending sectors when present. Use for drive health or disk temperature from SMART."
        ),
    ),
    _tool_entry(
        "nas_systemd_services",
        (
            "List monitored systemd services and running/inactive/failed state (like /services). "
            "Only works when systemctl is available on the host."
        ),
    ),
    _tool_entry(
        "nas_storage_allowed_paths",
        (
            "Disk usage for paths in ALLOWED_PATHS from config (similar idea to /storage). "
            "Use for configured data roots, not every mount."
        ),
    ),
    _tool_entry(
        "nas_list_docker_containers",
        "List Docker containers on the host where the bot runs (running and/or stopped).",
        {
            "include_stopped": {
                "type": "boolean",
                "description": (
                    "If true, include stopped/exited containers (like /containers). "
                    "If false, only running containers."
                ),
            }
        },
    ),
    _tool_entry(
        "nas_docker_container_logs",
        "Fetch recent stdout/stderr logs from one Docker container by name or short ID.",
        {
            "container": {"type": "string", "description": "Container name or ID"},
            "line_count": {
                "type": "integer",
                "description": "Number of log lines (1–200, default 80)",
            },
        },
        required=["container"],
    ),
    _tool_entry(
        "nas_docker_unhealthy_containers",
        "List containers that look unhealthy: exited, dead, restarting, or healthcheck unhealthy.",
    ),
    _tool_entry(
        "nas_system_health_snapshot",
        (
            "Quick live snapshot: CPU %, load average, memory %, swap, temperature sensors, sample disks, uptime. "
            "Use as a one-shot overview or after other focused tools if you still need CPU/load + temps together."
        ),
    ),
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


def _temperature_sensors() -> str:
    try:
        temps = get_temperatures()
        sensors = []
        for label, celsius in sorted(temps.items(), key=lambda x: str(x[0])):
            if celsius is None:
                continue
            chip = str(label).split("_")[0] if "_" in str(label) else str(label)
            ignored = config.ignore_temperature_sensor_for_alerts(chip) or config.ignore_temperature_sensor_for_alerts(
                str(label)
            )
            sensors.append(
                {
                    "sensor": str(label),
                    "celsius": round(float(celsius), 1),
                    "ignored_for_alert_rollup": ignored,
                }
            )
        return json.dumps({"ok": True, "count": len(sensors), "sensors": sensors}, default=str)
    except Exception as e:
        logger.exception("nas_temperature_sensors")
        return json.dumps({"ok": False, "error": str(e)})


def _health_score() -> str:
    try:
        score, issues = calculate_health_score()
        return json.dumps(
            {
                "ok": True,
                "health_score_0_to_100": score,
                "issues": issues[:25],
            },
            default=str,
        )
    except Exception as e:
        logger.exception("nas_health_score")
        return json.dumps({"ok": False, "error": str(e)})


def _disk_partitions() -> str:
    try:
        disks = get_disk_stats()
        brief = [
            {
                "mount": d.get("mountpoint"),
                "device": d.get("device"),
                "used_percent": round(d.get("percent", 0), 1),
                "used_gb": round(d.get("used_gb", 0), 2),
                "free_gb": round(d.get("free_gb", 0), 2),
                "total_gb": round(d.get("total_gb", 0), 2),
            }
            for d in disks
        ]
        return json.dumps({"ok": True, "partitions": brief}, default=str)
    except Exception as e:
        logger.exception("nas_disk_partitions")
        return json.dumps({"ok": False, "error": str(e)})


def _network_brief() -> str:
    try:
        raw = get_network_stats()
        out: Dict[str, Any] = {"ok": True, "interfaces": {}}
        for name, counters in raw.items():
            if name == "tailscale_ip":
                out["tailscale_ipv4"] = counters
                continue
            if not isinstance(counters, dict):
                continue
            out["interfaces"][name] = {
                "mb_sent": round(counters.get("bytes_sent", 0) / (1024**2), 2),
                "mb_recv": round(counters.get("bytes_recv", 0) / (1024**2), 2),
                "errors_in": counters.get("errors_in", 0),
                "errors_out": counters.get("errors_out", 0),
            }
        return json.dumps(out, default=str)
    except Exception as e:
        logger.exception("nas_network_interfaces")
        return json.dumps({"ok": False, "error": str(e)})


def _smart_drives() -> str:
    try:
        drives = get_all_drives()
        slim = []
        for d in drives[:_MAX_SMART_DRIVES]:
            slim.append(
                {
                    "device": d.get("device"),
                    "model": d.get("model"),
                    "health": d.get("health"),
                    "temperature_c": d.get("temperature"),
                    "power_on_hours": d.get("power_on_hours"),
                    "reallocated_sectors": d.get("reallocated_sectors"),
                    "pending_sectors": d.get("pending_sectors"),
                }
            )
        warnings = check_drive_warnings(drives)[:15]
        return json.dumps(
            {"ok": True, "drive_count": len(drives), "drives": slim, "warnings": warnings},
            default=str,
        )
    except Exception as e:
        logger.exception("nas_smart_drives")
        return json.dumps({"ok": False, "error": str(e)})


def _systemd_services() -> str:
    try:
        services = list_common_services()[:_MAX_SERVICES]
        return json.dumps({"ok": True, "count": len(services), "services": services}, default=str)
    except Exception as e:
        logger.exception("nas_systemd_services")
        return json.dumps({"ok": False, "error": str(e)})


def _storage_paths() -> str:
    try:
        if not config.ALLOWED_PATHS:
            return json.dumps(
                {
                    "ok": True,
                    "paths": [],
                    "note": "ALLOWED_PATHS is empty in configuration",
                }
            )
        summary = get_storage_summary()
        return json.dumps({"ok": True, "paths": summary}, default=str)
    except Exception as e:
        logger.exception("nas_storage_allowed_paths")
        return json.dumps({"ok": False, "error": str(e)})


def _system_snapshot() -> str:
    try:
        cpu_percent = float(psutil.cpu_percent(interval=0.25))
        load_avg: tuple[float, ...] | tuple[()] = ()
        if hasattr(psutil, "getloadavg"):
            try:
                load_avg = psutil.getloadavg()
            except Exception:
                load_avg = ()
        mem = get_memory_stats()
        disks = get_disk_stats()
        uptime = get_uptime()
        temps = get_temperatures()
        temp_list = [
            {"sensor": k, "celsius": round(float(v), 1)}
            for k, v in sorted(temps.items(), key=lambda x: str(x[0]))
            if v is not None
        ][:24]
        disk_brief = [
            {
                "mount": d.get("mountpoint"),
                "used_percent": round(d.get("percent", 0), 1),
                "free_gb": round(d.get("free_gb", 0), 2),
            }
            for d in disks[:10]
        ]
        payload = {
            "ok": True,
            "cpu_percent": round(cpu_percent, 1),
            "load_average": [round(x, 2) for x in load_avg] if load_avg else None,
            "memory_percent": round(mem.get("percent", 0), 1) if isinstance(mem, dict) else None,
            "memory_used_gb": round(mem.get("used_gb", 0), 2) if isinstance(mem, dict) else None,
            "swap_percent": mem.get("swap", {}).get("percent") if isinstance(mem, dict) else None,
            "uptime_seconds": uptime.get("uptime_seconds"),
            "temperatures_c": temp_list,
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
        if function_name == "nas_temperature_sensors":
            return _temperature_sensors()
        if function_name == "nas_health_score":
            return _health_score()
        if function_name == "nas_disk_partitions":
            return _disk_partitions()
        if function_name == "nas_network_interfaces":
            return _network_brief()
        if function_name == "nas_smart_drives":
            return _smart_drives()
        if function_name == "nas_systemd_services":
            return _systemd_services()
        if function_name == "nas_storage_allowed_paths":
            return _storage_paths()
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
