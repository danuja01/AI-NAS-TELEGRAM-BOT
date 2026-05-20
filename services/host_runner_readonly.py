"""
Allowlisted host command profiles for the AI ``nas_host_readonly_profile`` tool.

Execution uses **fixed argv lists** (no shell). Path-based operations only accept
prefixes in ``config.STORAGE_SCAN_PATHS``. Literals such as ``/etc/fstab`` are
embedded in code, never from user-controlled strings.

**Split vs ``host_runner.run_profile``:** The first seven names in
``HOST_READONLY_PROFILES_LEGACY_IN_RUNNER`` are implemented directly in
``host_runner.py`` (historical paths: apt, reboot banner, systemd journal/is-active,
``du``/``find`` on scan roots). Everything else in this module is built here so
``run_profile`` stays a thin dispatcher.

**Owner-requested profiles** (``grep``, ``tail -f``, ``printenv``, ``ping``,
``omv-salt stage run``): ``grep`` only allows fixed substrings from
``HOST_READONLY_GREP_KEYWORDS``; ``tail -f`` is wrapped in GNU ``timeout``;
``ping`` uses ``HOST_READONLY_PING_HOST`` only (not free-form model text).
``printenv`` and ``omv-salt stage run`` are fixed argv — they can still expose secrets
or change Salt state depending on your OMV setup; enable only when you accept that risk.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Final, FrozenSet, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)

_SCAN_PATH_RE = re.compile(r"^/[a-zA-Z0-9_./-]+$")
_DOCKER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,253}$")
_GENERIC_SYSTEMD_UNIT_RE = re.compile(r"^[a-zA-Z0-9:@_.\-\\]{1,240}$")
_UNIT_RE = re.compile(r"^[a-zA-Z0-9_.@-]+$")
_PING_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")

# Profiles whose argv is built in ``services.host_runner.run_profile`` (not here).
HOST_READONLY_PROFILES_LEGACY_IN_RUNNER: Final[FrozenSet[str]] = frozenset(
    {
        "apt_list_upgradable",
        "reboot_required",
        "systemctl_is_active",
        "journal_tail",
        "systemctl_failed",
        "du_path",
        "find_large_files",
    }
)


def _validate_scan_path(path: str) -> bool:
    if not path or not _SCAN_PATH_RE.match(path):
        return False
    path = path.rstrip("/") or "/"
    for allowed in config.STORAGE_SCAN_PATHS:
        root = allowed.rstrip("/") or "/"
        if path == root or path.startswith(root + "/"):
            return True
    return False


def _generic_systemd_unit_syntax_ok(unit: str) -> bool:
    if not unit or len(unit) > 240:
        return False
    if "/" in unit or "`" in unit or "\x00" in unit or any(c in unit for c in " \t\n\r\f\v|;&$()"):
        return False
    first = unit[0]
    if not (first.isalnum() or first in ("_", ":")):
        return False
    return bool(_GENERIC_SYSTEMD_UNIT_RE.match(unit))


def _validate_systemd_unit(unit: str) -> bool:
    if not _generic_systemd_unit_syntax_ok(unit):
        return False
    if getattr(config, "HOST_READONLY_SYSTEMD_ANY_UNIT", False):
        return True
    if not unit or not _UNIT_RE.match(unit):
        return False
    return unit in config.MONITOR_SYSTEMD_UNITS


def _validate_docker_name(name: str) -> bool:
    return bool(name and _DOCKER_NAME_RE.match(name))


def validate_readonly_docker_name(name: str) -> bool:
    """True if ``name`` is safe for fixed ``docker inspect`` / ``docker logs`` argv (no shell)."""
    return _validate_docker_name((name or "").strip())


def _validate_ping_target(host: str) -> bool:
    h = (host or "").strip()
    if not h or len(h) > 253:
        return False
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        pass
    if any(c in h for c in " \t\n\r;$()`|&<>\"'\\"):
        return False
    return bool(_PING_HOSTNAME_RE.fullmatch(h))


# (argv, max_timeout_seconds cap for subprocess)
_READONLY_FIXED: dict[str, tuple[list[str], int]] = {
    "host_hostname": (["hostname"], 15),
    "host_hostnamectl": (["hostnamectl"], 20),
    "host_uname_a": (["uname", "-a"], 15),
    "host_uptime_cmd": (["uptime"], 15),
    "host_whoami": (["whoami"], 15),
    "host_id": (["id"], 15),
    "host_date": (["date"], 15),
    "host_timedatectl": (["timedatectl", "status"], 25),
    "host_pwd": (["pwd"], 15),
    "host_printenv": (["printenv"], 30),
    "host_last_n": (["last", "-n", "40"], 25),
    "host_lastlog": (["lastlog"], 45),
    "host_w": (["w"], 20),
    "host_who": (["who"], 15),
    "host_users": (["users"], 15),
    "host_top_bn1": (["top", "-b", "-n", "1"], 45),
    "host_free_h": (["free", "-h"], 15),
    "host_vmstat": (["vmstat", "1", "3"], 25),
    "host_iostat_sn": (["iostat", "-y", "1", "3"], 35),
    "host_mpstat_sn": (["mpstat", "1", "3"], 35),
    "host_lscpu": (["lscpu"], 25),
    "host_nproc": (["nproc"], 10),
    "host_cat_proc_cpuinfo": (["cat", "/proc/cpuinfo"], 20),
    "host_cat_proc_meminfo": (["cat", "/proc/meminfo"], 20),
    "host_ps_aux_cpu": (["ps", "aux", "--sort=-%cpu"], 30),
    "host_ps_aux_mem": (["ps", "aux", "--sort=-%mem"], 30),
    "host_pstree": (["pstree", "-p", "-a"], 25),
    "host_df_h": (["df", "-h"], 30),
    "host_lsblk": (["lsblk", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,MODEL,SERIAL"], 30),
    "host_blkid": (["blkid"], 30),
    "host_mount": (["mount"], 25),
    "host_findmnt": (["findmnt"], 25),
    "host_cat_fstab": (["cat", "/etc/fstab"], 15),
    "host_fdisk_l": (["fdisk", "-l"], 60),
    "host_parted_l": (["parted", "-l"], 60),
    "host_smartctl_scan": (["smartctl", "--scan"], 30),
    "host_nvme_list": (["nvme", "list"], 25),
    "host_dmesg_T": (["dmesg", "-T"], 35),
    "host_ip_br_addr": (["ip", "-br", "addr"], 20),
    "host_ip_route": (["ip", "route"], 20),
    "host_ss_tulpn": (["ss", "-tulpn"], 25),
    "host_hostname_I": (["hostname", "-I"], 10),
    "host_sensors_a": (["sensors", "-A"], 30),
    "host_lsusb": (["lsusb"], 25),
    "host_lspci": (["lspci"], 25),
    "host_pidstat_sn": (["pidstat", "1", "2"], 30),
    "host_lsof_listeners": (["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], 35),
    "docker_cli_ps": (["docker", "ps"], 30),
    "docker_cli_ps_a": (["docker", "ps", "-a"], 45),
    "docker_cli_images": (["docker", "images"], 60),
    "docker_cli_volume_ls": (["docker", "volume", "ls"], 25),
    "docker_cli_network_ls": (["docker", "network", "ls"], 25),
    "docker_cli_stats": (["docker", "stats", "--no-stream"], 90),
    "docker_cli_system_df": (["docker", "system", "df"], 45),
    "docker_cli_info": (["docker", "info"], 60),
    "docker_cli_version": (["docker", "version"], 30),
    "docker_compose_ps": (["docker", "compose", "ps"], 45),
    "kubectl_get_pods": (["kubectl", "get", "pods", "-A", "-o", "wide", "--request-timeout=20s"], 45),
    "kubectl_get_nodes": (["kubectl", "get", "nodes", "-o", "wide", "--request-timeout=20s"], 35),
    "helm_list_a": (["helm", "list", "-A", "--max", "200"], 45),
    "service_status_all": (["service", "--status-all"], 60),
    "systemctl_list_units": (
        ["systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"],
        45,
    ),
    "systemctl_list_timers": (["systemctl", "list-timers", "--all", "--no-pager"], 35),
    "omv_salt_stage_run": (["omv-salt", "stage", "run"], 300),
}


def extended_readonly_profile_names() -> frozenset[str]:
    return frozenset(_READONLY_FIXED.keys()) | frozenset(
        {
            "host_ls_la",
            "host_du_sh",
            "host_file_head",
            "host_file_tail",
            "host_stat_file",
            "host_file_cmd",
            "host_readlink",
            "host_realpath",
            "host_grep_scan",
            "host_tail_follow_scan",
            "host_ping",
            "systemctl_status",
            "systemctl_is_enabled",
            "docker_cli_inspect",
            "docker_cli_logs_tail",
        }
    )


def all_agent_host_readonly_names() -> frozenset[str]:
    """Every profile name the agent may pass to ``host_runner.run_profile`` (legacy + this module)."""
    return HOST_READONLY_PROFILES_LEGACY_IN_RUNNER | extended_readonly_profile_names()


def build_readonly_extended_inner(
    profile: str, extra_args: List[str]
) -> Tuple[Optional[List[str]], Optional[str], Optional[int]]:
    """
    Build argv for extended read-only profiles. Returns (inner, error, timeout_cap).
    """
    if profile in _READONLY_FIXED:
        if extra_args:
            return None, "this profile takes no extra arguments", None
        argv, cap = _READONLY_FIXED[profile]
        return list(argv), None, cap

    if profile == "host_ping":
        if extra_args:
            return None, "host_ping takes no arguments (set HOST_READONLY_PING_HOST in .env)", None
        host = getattr(config, "HOST_READONLY_PING_HOST", "127.0.0.1") or "127.0.0.1"
        host = str(host).strip()
        if not _validate_ping_target(host):
            return None, "invalid HOST_READONLY_PING_HOST in configuration", None
        return ["ping", "-c", "4", "-W", "5", host], None, 35

    if profile in ("systemctl_status", "systemctl_is_enabled"):
        if len(extra_args) != 1:
            return None, "parameter 'unit' is required (pass as single extra arg)", None
        unit = extra_args[0].strip()
        if not _validate_systemd_unit(unit):
            return None, "invalid or disallowed systemd unit for this profile", None
        inner = ["systemctl", "status" if profile == "systemctl_status" else "is-enabled", unit]
        return inner, None, 35

    if profile == "host_ls_la":
        if len(extra_args) != 1 or not _validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_ls_la", None
        return ["ls", "-la", extra_args[0]], None, 45

    if profile == "host_du_sh":
        if len(extra_args) != 1 or not _validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_du_sh", None
        return ["du", "-sh", extra_args[0]], None, int(config.STORAGE_CMD_TIMEOUT)

    if profile in ("host_file_head", "host_file_tail"):
        if len(extra_args) < 1 or not _validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for file read", None
        path = extra_args[0]
        try:
            nlines = int(extra_args[1]) if len(extra_args) > 1 else (80 if profile == "host_file_head" else 120)
        except ValueError:
            return None, "lines must be an integer", None
        nlines = max(1, min(nlines, 2000))
        cmd = "head" if profile == "host_file_head" else "tail"
        return [cmd, "-n", str(nlines), path], None, 40

    if profile in ("host_stat_file", "host_file_cmd", "host_readlink", "host_realpath"):
        if len(extra_args) != 1 or not _validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path", None
        path = extra_args[0]
        if profile == "host_stat_file":
            return ["stat", path], None, 20
        if profile == "host_file_cmd":
            return ["file", "-b", path], None, 20
        if profile == "host_readlink":
            return ["readlink", "-f", path], None, 15
        return ["realpath", path], None, 15

    if profile == "host_grep_scan":
        if len(extra_args) != 2:
            return None, "host_grep_scan requires path and grep_keyword (fixed allowlist only)", None
        path, needle = extra_args[0], (extra_args[1] or "").strip()
        if not _validate_scan_path(path):
            return None, "invalid or disallowed path for host_grep_scan", None
        allowed = getattr(config, "HOST_READONLY_GREP_KEYWORDS", ()) or ()
        if needle not in allowed:
            return None, "grep_keyword not in HOST_READONLY_GREP_KEYWORDS allowlist", None
        return ["grep", "-nI", "-F", needle, path], None, 50

    if profile == "host_tail_follow_scan":
        if len(extra_args) != 1 or not _validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_tail_follow_scan", None
        path = extra_args[0]
        sec = int(getattr(config, "HOST_READONLY_TAIL_F_SECONDS", 20))
        sec = max(5, min(sec, 90))
        cap = sec + 10
        return ["timeout", "--signal=TERM", str(sec), "tail", "-f", "-n", "80", path], None, cap

    if profile == "docker_cli_inspect":
        if len(extra_args) != 1:
            return None, "parameter 'container' is required", None
        c = extra_args[0].strip()
        if not _validate_docker_name(c):
            return None, "invalid docker name for inspect", None
        return ["docker", "inspect", c], None, 60

    if profile == "docker_cli_logs_tail":
        if len(extra_args) < 1:
            return None, "parameter 'container' is required", None
        c = extra_args[0].strip()
        if not _validate_docker_name(c):
            return None, "invalid docker name for logs", None
        try:
            n = int(extra_args[1]) if len(extra_args) > 1 else 120
        except ValueError:
            return None, "line_count must be integer", None
        n = max(10, min(n, 500))
        return ["docker", "logs", "--tail", str(n), c], None, 60

    return None, None, None
