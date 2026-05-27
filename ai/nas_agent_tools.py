"""
NAS agent tools for OpenAI function calling: host metrics, Docker reads,
optional allow-listed read-only host profiles (SSH/nsenter via host_runner),
and interactive Docker restart/stop (Telegram confirmation only — same as /drestart /dstop).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import psutil

import config
from ai.agent_telegram import AgentTelegramBindings
from services import docker_service as ds
from services.file_service import get_storage_summary
from services.service_manager import list_common_services
from services.smart_monitor import check_drive_warnings, get_all_drives, get_smart_data
from services.host_runner import run_profile as host_run_profile
from services.omv_client import (
    omv_disk_summary_json,
    omv_filesystems_summary_json,
    omv_rpc_available,
    omv_smart_summary_json,
    sync_fetch_disk_enumerate,
    sync_fetch_filesystems_mounted,
    sync_fetch_smart_devices,
)
from services.system_monitor import (
    calculate_health_score,
    get_cpu_stats,
    get_disk_stats,
    get_memory_stats,
    get_network_stats,
    get_temperatures,
    get_uptime,
)

logger = logging.getLogger(__name__)

_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,253}$")
_SMART_DEVICE_RE = re.compile(
    r"^(/dev/sd[a-z]+|/dev/nvme\d+n\d+(?:p\d+)?|/dev/disk/by-id/[\w./-]+)$"
)

from ai.host_read_profiles import HOST_READONLY_PROFILES, HOST_READONLY_PROFILES_ORDERED
from services.readonly import ZERO_EXTRA_AGENT_PROFILES
from services.readonly.constants import MAX_DOCKER_HOST_LOG_LINES

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


_NAS_HOST_READONLY_PROFILE_TOOL_ENTRY = _tool_entry(
    "nas_host_readonly_profile",
    (
        "Read-only host diagnostics on the OMV/NAS machine via SSH or nsenter (same pipeline as HOST_EXEC_MODE). "
        "**Not** arbitrary shell — only fixed allowlisted profiles (apt/reboot/systemd/journal, du/find under scan paths, "
        "and many fixed argv probes: hostname, uptime, memory/cpu/disk/network summaries, docker/kubectl/helm read-only, "
        "bounded tail -f (timeout), loopback ping, grep -F on scan paths with fixed keywords only, etc.). "
        "Paths for file/dir probes must be under STORAGE_SCAN_PATHS. "
        "Units default to MONITOR_SYSTEMD_UNITS; set HOST_READONLY_SYSTEMD_ANY_UNIT=true to allow other valid unit names. "
        "Requires AGENT_HOST_READONLY_TOOL=true at boot (fixed read-only host profiles only)."
    ),
    {
        "profile": {
            "type": "string",
            "enum": list(HOST_READONLY_PROFILES_ORDERED),
            "description": "Predefined read-only operation; use matching parameters below when required.",
        },
        "unit": {
            "type": "string",
            "description": (
                "systemd unit (e.g. ssh.service, nginx.service). Required for "
                "systemctl_is_active, journal_tail, systemctl_status, and systemctl_is_enabled. "
                "If HOST_READONLY_SYSTEMD_ANY_UNIT=true, any safe unit syntax is accepted (logs may expose secrets)."
            ),
        },
        "path": {
            "type": "string",
            "description": (
                "Absolute path under STORAGE_SCAN_PATHS. Required for du_path, find_large_files, host_ls_la, host_du_sh, "
                "host_stat_file, host_file_cmd, host_readlink, host_realpath, host_file_head, host_file_tail, "
                "host_grep_scan, host_tail_follow_scan."
            ),
        },
        "min_mb": {
            "type": "integer",
            "description": "Minimum file size in MiB for find_large_files (+N M); typical 100–1024.",
        },
        "max_n": {
            "type": "integer",
            "description": "Maximum file entries for find_large_files (optional, default from host_runner).",
        },
        "container": {
            "type": "string",
            "description": "Docker container name or id for docker_cli_inspect and docker_cli_logs_tail.",
        },
        "line_count": {
            "type": "integer",
            "description": (
                "Line count for host_file_head, host_file_tail, and docker_cli_logs_tail (optional). "
                f"docker_cli_logs_tail accepts up to {MAX_DOCKER_HOST_LOG_LINES} lines."
            ),
        },
        "grep_keyword": {
            "type": "string",
            "description": (
                "Fixed substring for host_grep_scan (grep -F): must be an allowlisted diagnostic phrase "
                "defined in server code, not a regex."
            ),
        },
    },
    required=["profile"],
)


# Base OpenAI Chat Completions `tools` (see get_nas_agent_tools() when AGENT_HOST_READONLY_TOOL is enabled).
_NAS_AGENT_TOOLS_BASE: List[Dict[str, Any]] = [
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
        "nas_cpu_stats",
        (
            "CPU utilization for THIS host: **overall percent**, **one percent value per logical CPU thread** "
            "(same source as Telegram `/cpu`), load averages 1/5/15, physical vs logical core counts, optional CPU frequency. "
            "You MUST call this when the user asks about **per-core**, per-thread, per-CPU, or 'which core is busy' — "
            "never claim per-core data is unavailable without calling this tool (or `nas_system_health_snapshot`, "
            "which also returns a per-core list)."
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
            "Live network interfaces: UP/DOWN, MTU, link speed, IPv4/IPv6 addresses, byte counters, "
            "default gateway and interface when readable from /proc/net/route, outbound local IPv4 probe, "
            "and optional Tailscale IPv4 from `tailscale ip -4` when NETWORK_TAILSCALE_CLI=true. "
            "Users can also run `/network`, `/netpublic` (public IP), and `/netping <host>`."
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
        (
            "List Docker containers on the host where the bot runs (running and/or stopped). "
            "For **unused/dangling Docker images** (reclaimable space), tell the user to run Telegram `/dimages` "
            "(or `/dscan` for a full storage + Docker deep scan). `/docker` is only the compact dashboard — "
            "do not suggest it for image-pruning questions."
        ),
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
        (
            "Fetch recent stdout/stderr logs from one Docker container by name or short ID. "
            "Respects the user's requested line count up to the server cap (large tails may be truncated in JSON)."
        ),
        {
            "container": {"type": "string", "description": "Container name or ID"},
            "line_count": {
                "type": "integer",
                "description": f"Number of log lines to tail (1–{MAX_DOCKER_HOST_LOG_LINES}, default 80)",
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
            "Quick live snapshot: overall CPU %, **cpu_percent_per_logical_core** (one value per thread), load average, "
            "memory %, swap, temperature sensors, sample disks, uptime. "
            "Prefer **nas_cpu_stats** for CPU-only questions (includes load + core counts + freq like `/cpu`). "
            "Use this snapshot as a one-shot overview or when you need CPU breakdown plus temps/disks together."
        ),
    ),
    _tool_entry(
        "nas_omv_physical_disks",
        (
            "OpenMediaVault physical disk inventory via host `omv-rpc DiskMgmt enumerateDevices`: "
            "model, serial, WWN, size, OMV-reported SMART temp and power mode. "
            "Requires the bot to reach the OMV host (HOST_EXEC_MODE nsenter/ssh). Use for 'what disks does OMV see'."
        ),
    ),
    _tool_entry(
        "nas_omv_filesystems",
        (
            "OpenMediaVault mounted filesystems via `FileSystemMgmt enumerateMountedFilesystems`: "
            "mountpoint, fstype, OMV usage percent, devicefile. Matches the Storage UI. "
            "Complement with nas_disk_partitions for live psutil usage if needed."
        ),
    ),
    _tool_entry(
        "nas_omv_smart_devices",
        (
            "OpenMediaVault SMART-capable devices via `Smart enumerateDevices`: overall OMV SMART status, model, serial, temperature. "
            "Different from nas_smart_drives (raw smartctl); use both when diagnosing mismatches."
        ),
    ),
    _tool_entry(
        "nas_smart_device_detail",
        (
            "Detailed SMART summary for ONE disk from smartctl JSON (model, health, temp, power-on hours, "
            "reallocated/pending sectors, load/power cycle counts when available). "
            "Pass devicefile like /dev/sda or /dev/nvme0n1."
        ),
        {"device": {"type": "string", "description": "Block device path, e.g. /dev/sda or /dev/nvme0n1"}},
        required=["device"],
    ),
    _tool_entry(
        "nas_request_docker_restart",
        (
            "Send the same inline Confirm/Cancel Telegram message as manual /drestart for one container. "
            "The container does NOT restart until the user taps Confirm. Use only when the user explicitly "
            "wants to restart a named container."
        ),
        {"container": {"type": "string", "description": "Exact Docker container name"}},
        required=["container"],
    ),
    _tool_entry(
        "nas_request_docker_stop",
        (
            "Send the same inline Confirm/Cancel Telegram message as manual /dstop. "
            "The container does NOT stop until the user taps Confirm."
        ),
        {"container": {"type": "string", "description": "Exact Docker container name"}},
        required=["container"],
    ),
    _tool_entry(
        "nas_crowdsec_status",
        (
            "Read-only CrowdSec snapshot from this NAS: recent alerts, active ban decisions, "
            "and metrics via `docker exec` cscli (container name from CROWDSEC_CONTAINER). "
            "Use for security incidents, brute force, bans, attack trends, or whether SSH/services were targeted. "
            "Requires CROWDSEC_MONITOR_ENABLED=true."
        ),
    ),
]


def get_nas_agent_tools(for_rag: bool = False) -> List[Dict[str, Any]]:
    """Tools for Chat Completions, including optional read-only host access when configured."""
    out = []
    for entry in _NAS_AGENT_TOOLS_BASE:
        fn = entry.get("function") or {}
        name = fn.get("name", "")
        if name == "nas_crowdsec_status" and not config.CROWDSEC_MONITOR_ENABLED:
            continue
        out.append(entry)
    if config.AGENT_HOST_READONLY_TOOL:
        out.append(_NAS_HOST_READONLY_PROFILE_TOOL_ENTRY)
    return out


# Default snapshot for legacy imports; prefer ``get_nas_agent_tools(...)``.
NAS_AGENT_TOOLS = get_nas_agent_tools(False)


def _exec_host_readonly_profile(user_id: Optional[int], args: Dict[str, Any]) -> str:
    """
    Invoke host_runner.run_profile for AI-allowlisted profiles only (no shell from the model).
    """
    profile = str(args.get("profile", "")).strip()
    if profile not in HOST_READONLY_PROFILES:
        return json.dumps({"ok": False, "error": f"disallowed profile: {profile!r}"})

    extra: List[str] = []
    if profile in ("systemctl_is_active", "journal_tail", "systemctl_status", "systemctl_is_enabled"):
        unit = str(args.get("unit", "")).strip()
        if not unit:
            return json.dumps({"ok": False, "error": "parameter 'unit' is required for this profile"})
        extra = [unit]
    elif profile == "du_path":
        path = str(args.get("path", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for this profile"})
        extra = [path]
    elif profile == "find_large_files":
        path = str(args.get("path", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for this profile"})
        min_mb = args.get("min_mb")
        if min_mb is None:
            return json.dumps({"ok": False, "error": "parameter 'min_mb' is required for find_large_files"})
        try:
            min_mb_int = int(min_mb)
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "min_mb must be an integer"})
        row = [path, str(min_mb_int)]
        max_n = args.get("max_n")
        if max_n is not None:
            try:
                row.append(str(int(max_n)))
            except (TypeError, ValueError):
                return json.dumps({"ok": False, "error": "max_n must be an integer"})
        extra = row
    elif profile in (
        "host_ls_la",
        "host_du_sh",
        "host_stat_file",
        "host_file_cmd",
        "host_readlink",
        "host_realpath",
    ):
        path = str(args.get("path", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for this profile"})
        extra = [path]
    elif profile in ("host_file_head", "host_file_tail"):
        path = str(args.get("path", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for this profile"})
        extra = [path]
        lc = args.get("line_count")
        if lc is not None:
            try:
                extra.append(str(int(lc)))
            except (TypeError, ValueError):
                return json.dumps({"ok": False, "error": "line_count must be an integer"})
    elif profile == "docker_cli_inspect":
        c = str(args.get("container", "")).strip()
        if not c:
            return json.dumps({"ok": False, "error": "parameter 'container' is required for docker_cli_inspect"})
        extra = [c]
    elif profile == "docker_cli_logs_tail":
        c = str(args.get("container", "")).strip()
        if not c:
            return json.dumps({"ok": False, "error": "parameter 'container' is required for docker_cli_logs_tail"})
        extra = [c]
        lc = args.get("line_count")
        if lc is not None:
            try:
                extra.append(str(int(lc)))
            except (TypeError, ValueError):
                return json.dumps({"ok": False, "error": "line_count must be an integer"})
    elif profile == "host_grep_scan":
        path = str(args.get("path", "")).strip()
        kw = str(args.get("grep_keyword", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for host_grep_scan"})
        if not kw:
            return json.dumps({"ok": False, "error": "parameter 'grep_keyword' is required for host_grep_scan"})
        extra = [path, kw]
    elif profile == "host_tail_follow_scan":
        path = str(args.get("path", "")).strip()
        if not path:
            return json.dumps({"ok": False, "error": "parameter 'path' is required for host_tail_follow_scan"})
        extra = [path]
    elif profile in ZERO_EXTRA_AGENT_PROFILES:
        extra = []
    else:
        return json.dumps({"ok": False, "error": f"unsupported profile routing: {profile}"})

    uid_label = user_id if user_id is not None else "?"
    logger.warning(
        "AGENT_HOST_READONLY_PROFILE user_id=%s profile=%s extra=%s",
        uid_label,
        profile,
        extra,
    )

    result = host_run_profile(profile, extra_args=extra if extra else None)

    payload: Dict[str, Any] = {
        "ok": result.ok,
        "profile": profile,
        "exit_code": result.exit_code,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
    }
    if result.error:
        payload["error"] = result.error
    return json.dumps(payload, default=str)


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
    line_count = max(1, min(int(line_count or 80), MAX_DOCKER_HOST_LOG_LINES))
    try:
        logs = ds.get_container_logs(container, lines=line_count)
        if len(logs) > 48000:
            logs = "…[truncated]…\n" + logs[-48000:]
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
        for name, val in raw.items():
            if name == "tailscale_ip":
                out["tailscale_ipv4"] = val
                continue
            if name in ("outbound_local_ipv4", "default_gateway_ipv4", "default_route_iface"):
                out[name] = val
                continue
            if not isinstance(val, dict):
                continue
            addrs = val.get("addresses") or []
            slim_addrs = []
            for a in addrs[:10]:
                if isinstance(a, dict):
                    slim_addrs.append(
                        {
                            "family": a.get("family"),
                            "address": a.get("address"),
                        }
                    )
            out["interfaces"][name] = {
                "isup": val.get("isup"),
                "mtu": val.get("mtu"),
                "speed_mbps": val.get("speed_mbps"),
                "duplex": val.get("duplex"),
                "addresses": slim_addrs,
                "mb_sent": round(val.get("bytes_sent", 0) / (1024**2), 2),
                "mb_recv": round(val.get("bytes_recv", 0) / (1024**2), 2),
                "errors_in": val.get("errors_in", 0),
                "errors_out": val.get("errors_out", 0),
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


def _omv_physical_disks() -> str:
    if not omv_rpc_available():
        return json.dumps(
            {
                "ok": False,
                "error": "OMV RPC unavailable (HOST_EXEC_MODE=none, OMV_RPC_ENABLED=false, or host unreachable)",
            }
        )
    try:
        rows, err = sync_fetch_disk_enumerate()
        if err:
            return json.dumps({"ok": False, "error": err})
        return omv_disk_summary_json(rows)
    except Exception as e:
        logger.exception("nas_omv_physical_disks")
        return json.dumps({"ok": False, "error": str(e)})


def _omv_filesystems() -> str:
    if not omv_rpc_available():
        return json.dumps(
            {
                "ok": False,
                "error": "OMV RPC unavailable (HOST_EXEC_MODE=none, OMV_RPC_ENABLED=false, or host unreachable)",
            }
        )
    try:
        rows, err = sync_fetch_filesystems_mounted()
        if err:
            return json.dumps({"ok": False, "error": err})
        return omv_filesystems_summary_json(rows)
    except Exception as e:
        logger.exception("nas_omv_filesystems")
        return json.dumps({"ok": False, "error": str(e)})


def _omv_smart_devices() -> str:
    if not omv_rpc_available():
        return json.dumps(
            {
                "ok": False,
                "error": "OMV RPC unavailable (HOST_EXEC_MODE=none, OMV_RPC_ENABLED=false, or host unreachable)",
            }
        )
    try:
        rows, err = sync_fetch_smart_devices()
        if err:
            return json.dumps({"ok": False, "error": err})
        return omv_smart_summary_json(rows)
    except Exception as e:
        logger.exception("nas_omv_smart_devices")
        return json.dumps({"ok": False, "error": str(e)})


def _smart_device_detail(args: Dict[str, Any]) -> str:
    dev = str(args.get("device", "")).strip()
    if not dev or len(dev) > 200 or not _SMART_DEVICE_RE.match(dev):
        return json.dumps({"ok": False, "error": "Invalid device path (use /dev/sdX, /dev/nvme0n1, or /dev/disk/by-id/...)"})
    try:
        info = get_smart_data(dev)
        if not info:
            return json.dumps({"ok": False, "error": f"No SMART data for {dev}"})
        return json.dumps({"ok": True, "device": dev, "smart": info}, default=str)
    except Exception as e:
        logger.exception("nas_smart_device_detail")
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


def _cpu_stats() -> str:
    """Full CPU stats including per-logical-core percents (matches Telegram /cpu)."""
    try:
        raw = get_cpu_stats()
        if not isinstance(raw, dict):
            return json.dumps({"ok": False, "error": "invalid cpu stats"})
        err = raw.get("error")
        per = raw.get("per_cpu")
        if err and not per:
            return json.dumps({"ok": False, "error": str(err)})
        per_list = per if isinstance(per, (list, tuple)) else []
        try:
            per_rounded = [round(float(x), 1) for x in per_list]
        except (TypeError, ValueError):
            per_rounded = []
        payload: Dict[str, Any] = {
            "ok": True,
            "note": "Aligned with Telegram `/cpu`: psutil overall and per-logical-thread cpu_percent samples.",
            "cpu_percent_overall": round(float(raw.get("percent", 0)), 1),
            "cpu_percent_per_logical_core": per_rounded,
            "physical_cores": raw.get("cores"),
            "logical_threads": raw.get("threads"),
        }
        la = raw.get("load_avg")
        if isinstance(la, (list, tuple)) and len(la) >= 3:
            payload["load_average_1_5_15"] = [round(float(la[0]), 2), round(float(la[1]), 2), round(float(la[2]), 2)]
        elif la:
            try:
                payload["load_average"] = [round(float(x), 2) for x in la]
            except (TypeError, ValueError):
                pass
        freq = raw.get("frequency")
        if isinstance(freq, dict) and freq.get("current") is not None:
            try:
                payload["cpu_freq_mhz_current"] = round(float(freq["current"]), 0)
            except (TypeError, ValueError):
                pass
        return json.dumps(payload, default=str)
    except Exception as e:
        logger.exception("nas_cpu_stats")
        return json.dumps({"ok": False, "error": str(e)})


def _system_snapshot() -> str:
    try:
        per_core = psutil.cpu_percent(interval=0.45, percpu=True)
        cpu_percent = (
            round(sum(per_core) / max(len(per_core), 1), 1) if per_core else 0.0
        )
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
            "cpu_percent_per_logical_core": [round(float(x), 1) for x in per_core],
            "cpu_logical_threads": psutil.cpu_count(logical=True),
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


def _crowdsec_status() -> str:
    if not config.CROWDSEC_MONITOR_ENABLED:
        return json.dumps(
            {
                "ok": False,
                "error": "CrowdSec tool disabled (set CROWDSEC_MONITOR_ENABLED=true)",
            }
        )
    try:
        from services.crowdsec_client import gather_crowdsec_snapshot

        snap = gather_crowdsec_snapshot()
        return json.dumps(snap, default=str)[:14000]
    except Exception as e:
        logger.exception("nas_crowdsec_status")
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
        if function_name == "nas_cpu_stats":
            return _cpu_stats()
        if function_name == "nas_disk_partitions":
            return _disk_partitions()
        if function_name == "nas_network_interfaces":
            return _network_brief()
        if function_name == "nas_smart_drives":
            return _smart_drives()
        if function_name == "nas_omv_physical_disks":
            return _omv_physical_disks()
        if function_name == "nas_omv_filesystems":
            return _omv_filesystems()
        if function_name == "nas_omv_smart_devices":
            return _omv_smart_devices()
        if function_name == "nas_smart_device_detail":
            return _smart_device_detail(args)
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
        if function_name == "nas_crowdsec_status":
            return _crowdsec_status()
        if function_name in ("nas_request_docker_restart", "nas_request_docker_stop"):
            return json.dumps(
                {
                    "ok": False,
                    "error": "This action must be dispatched with Telegram context (internal)",
                }
            )
        return json.dumps({"ok": False, "error": f"Unknown tool: {function_name}"})
    except Exception as e:
        logger.exception("run_nas_tool %s", function_name)
        return json.dumps({"ok": False, "error": str(e)})


async def dispatch_nas_agent_tool(
    function_name: str,
    arguments: Dict[str, Any] | None,
    telegram_bind: Optional[AgentTelegramBindings] = None,
) -> str:
    """
    Run one agent tool. Interactive Docker tools require ``telegram_bind`` from a live chat handler.
    """
    args = arguments or {}
    if function_name == "nas_host_readonly_profile":
        if not config.AGENT_HOST_READONLY_TOOL:
            return json.dumps(
                {"ok": False, "error": "nas_host_readonly_profile is disabled (set AGENT_HOST_READONLY_TOOL=true)"}
            )
        uid = telegram_bind.user_id if telegram_bind else None
        return await asyncio.to_thread(_exec_host_readonly_profile, uid, args)

    if function_name == "nas_request_docker_restart":
        if telegram_bind is None:
            return json.dumps(
                {"ok": False, "error": "Docker restart confirmation requires an active Telegram chat context"}
            )
        container = str(args.get("container", "")).strip()
        if not _validate_container_name(container):
            return json.dumps({"ok": False, "error": "Invalid container name"})
        from commands import docker_cmds

        await docker_cmds.send_restart_confirmation(
            telegram_bind.update, telegram_bind.context, telegram_bind.user_id, container
        )
        return json.dumps(
            {
                "ok": True,
                "container": container,
                "message": (
                    "Posted the restart confirmation with inline buttons in this chat. "
                    "Tell the user to tap Confirm or Cancel; nothing restarts until Confirm."
                ),
            }
        )

    if function_name == "nas_request_docker_stop":
        if telegram_bind is None:
            return json.dumps(
                {"ok": False, "error": "Docker stop confirmation requires an active Telegram chat context"}
            )
        container = str(args.get("container", "")).strip()
        if not _validate_container_name(container):
            return json.dumps({"ok": False, "error": "Invalid container name"})
        from commands import docker_cmds

        await docker_cmds.send_stop_confirmation(
            telegram_bind.update, telegram_bind.context, telegram_bind.user_id, container
        )
        return json.dumps(
            {
                "ok": True,
                "container": container,
                "message": (
                    "Posted the stop confirmation with inline buttons. "
                    "Nothing stops until the user taps Confirm."
                ),
            }
        )

    return await asyncio.to_thread(run_nas_tool, function_name, args)
