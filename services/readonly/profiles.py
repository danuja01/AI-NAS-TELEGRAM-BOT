"""
Build argv for every read-only ``host_runner.run_profile`` name (fixed argv, no shell).

All argv construction for ``host_runner.run_profile`` read-only names lives here;
``host_runner`` only keeps mutating operations (apt update/clean, omv-upgrade).
"""

from __future__ import annotations

from typing import Final, List, Optional, Tuple

import config

from services.omv_rpc_specs import OMV_RPC_CALLS
from services.readonly.constants import MAX_DOCKER_HOST_LOG_LINES, TAIL_FOLLOW_TIMEOUT_SECONDS
from services.readonly.fixed_commands import FIXED_ARGV
from services.readonly import validators as v

# First-class read-only profiles (non-fixed-argv table) used by the AI enum
LEGACY_AGENT_PROFILES: Final[frozenset[str]] = frozenset(
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

# Profiles that accept path/unit/container/etc. from the agent tool (validated here)
PARAMETRIC_PROFILE_NAMES: Final[frozenset[str]] = frozenset(
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
        "systemctl_status",
        "systemctl_is_enabled",
        "docker_cli_inspect",
        "docker_cli_logs_tail",
    }
)

# Used by omv_client / Telegram flows, not exposed on the AI enum
INTERNAL_READONLY_PROFILES: Final[frozenset[str]] = frozenset({"omv_rpc"})

EXTENDED_FIXED_NAMES: Final[frozenset[str]] = frozenset(FIXED_ARGV.keys())

PROFILE_NAMES_FOR_AGENT: Final[frozenset[str]] = (
    LEGACY_AGENT_PROFILES | EXTENDED_FIXED_NAMES | PARAMETRIC_PROFILE_NAMES
)

ALL_READONLY_PROFILE_NAMES: Final[frozenset[str]] = PROFILE_NAMES_FOR_AGENT | INTERNAL_READONLY_PROFILES

PROFILES_REQUIRING_TOOL_ARGS: Final[frozenset[str]] = (
    frozenset(
        {
            "systemctl_is_active",
            "journal_tail",
            "systemctl_status",
            "systemctl_is_enabled",
            "du_path",
            "find_large_files",
        }
    )
    | PARAMETRIC_PROFILE_NAMES
)

ZERO_EXTRA_AGENT_PROFILES: Final[frozenset[str]] = PROFILE_NAMES_FOR_AGENT - PROFILES_REQUIRING_TOOL_ARGS


def build_readonly_inner(
    profile: str, extra_args: List[str]
) -> Tuple[Optional[List[str]], Optional[str], Optional[int]]:
    """
    Return ``(argv, error, timeout_cap)`` for a read-only profile.
    ``timeout_cap`` is used by ``host_runner`` to clamp subprocess wait.
    """
    if profile == "apt_list_upgradable":
        if extra_args:
            return None, "this profile takes no extra arguments", None
        return ["apt", "list", "--upgradable"], None, int(config.HOST_EXEC_TIMEOUT_SHORT)

    if profile == "reboot_required":
        if extra_args:
            return None, "this profile takes no extra arguments", None
        inner = [
            "sh",
            "-c",
            "if [ -f /var/run/reboot-required ]; then cat /var/run/reboot-required; "
            "else echo NO_REBOOT_PENDING; fi",
        ]
        return inner, None, int(config.HOST_EXEC_TIMEOUT_SHORT)

    if profile == "systemctl_is_active":
        if len(extra_args) != 1 or not v.validate_systemd_unit(extra_args[0]):
            return (
                None,
                "Invalid systemd unit, or unit not in MONITOR_SYSTEMD_UNITS. "
                "Set HOST_READONLY_SYSTEMD_ANY_UNIT=true to query any syntactically valid unit (read-only).",
                None,
            )
        return ["systemctl", "is-active", extra_args[0]], None, 35

    if profile == "journal_tail":
        if len(extra_args) != 1 or not v.validate_systemd_unit(extra_args[0]):
            return (
                None,
                "Invalid systemd unit, or unit not in MONITOR_SYSTEMD_UNITS. "
                "Set HOST_READONLY_SYSTEMD_ANY_UNIT=true to tail any syntactically valid unit (read-only).",
                None,
            )
        n = str(min(50, max(5, config.JOURNAL_TAIL_LINES)))
        return ["journalctl", "-u", extra_args[0], "-n", n, "--no-pager"], None, 45

    if profile == "du_path":
        if len(extra_args) != 1 or not v.validate_scan_path(extra_args[0]):
            return None, "Invalid or disallowed scan path", None
        return ["du", "-h", "--max-depth=1", extra_args[0]], None, int(config.STORAGE_CMD_TIMEOUT)

    if profile == "find_large_files":
        if len(extra_args) < 2 or not v.validate_scan_path(extra_args[0]):
            return None, "Invalid or disallowed scan path", None
        try:
            min_mb = int(extra_args[1])
            max_n = int(extra_args[2]) if len(extra_args) > 2 else 20
        except ValueError:
            return None, "Invalid find size/limit args", None
        min_mb = max(1, min(min_mb, 10000))
        max_n = max(1, min(max_n, 50))
        inner = [
            "find",
            extra_args[0],
            "-xdev",
            "-type",
            "f",
            "-size",
            f"+{min_mb}M",
            "-printf",
            "%s %p\n",
        ]
        return inner, None, int(config.STORAGE_CMD_TIMEOUT)

    if profile == "systemctl_failed":
        if extra_args:
            return None, "this profile takes no extra arguments", None
        return (
            ["systemctl", "--failed", "--no-pager", "--plain", "--no-legend"],
            None,
            int(config.STORAGE_CMD_TIMEOUT),
        )

    if profile == "omv_rpc":
        if not getattr(config, "OMV_RPC_ENABLED", True):
            return None, "OMV RPC disabled (set OMV_RPC_ENABLED=true)", None
        if len(extra_args) != 1:
            return None, "omv_rpc requires exactly one call_key argument", None
        call_key = extra_args[0]
        if call_key not in OMV_RPC_CALLS:
            return None, "Unknown or disallowed OMV RPC call key", None
        user = getattr(config, "OMV_RPC_USER", "admin") or "admin"
        if not v.validate_omv_rpc_user(user):
            return None, "Invalid OMV_RPC_USER", None
        service, method, params_json = OMV_RPC_CALLS[call_key]
        inner = ["omv-rpc", "-u", user, service, method]
        if params_json is not None:
            inner.append(params_json)
        return inner, None, min(config.HOST_EXEC_TIMEOUT_SHORT, 120)

    if profile in FIXED_ARGV:
        if extra_args:
            return None, "this profile takes no extra arguments", None
        argv, cap = FIXED_ARGV[profile]
        return list(argv), None, cap

    if profile in ("systemctl_status", "systemctl_is_enabled"):
        if len(extra_args) != 1:
            return None, "parameter 'unit' is required (pass as single extra arg)", None
        unit = extra_args[0].strip()
        if not v.validate_systemd_unit(unit):
            return None, "invalid or disallowed systemd unit for this profile", None
        cmd = "status" if profile == "systemctl_status" else "is-enabled"
        return ["systemctl", cmd, unit], None, 35

    if profile == "host_ls_la":
        if len(extra_args) != 1 or not v.validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_ls_la", None
        return ["ls", "-la", extra_args[0]], None, 45

    if profile == "host_du_sh":
        if len(extra_args) != 1 or not v.validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_du_sh", None
        return ["du", "-sh", extra_args[0]], None, int(config.STORAGE_CMD_TIMEOUT)

    if profile in ("host_file_head", "host_file_tail"):
        if len(extra_args) < 1 or not v.validate_scan_path(extra_args[0]):
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
        if len(extra_args) != 1 or not v.validate_scan_path(extra_args[0]):
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
            return None, "host_grep_scan requires path and grep_keyword", None
        path, needle = extra_args[0], (extra_args[1] or "").strip()
        if not v.validate_scan_path(path):
            return None, "invalid or disallowed path for host_grep_scan", None
        if not v.validate_grep_keyword(needle):
            return None, "invalid or disallowed grep_keyword", None
        return ["grep", "-nI", "-F", needle, path], None, 50

    if profile == "host_tail_follow_scan":
        if len(extra_args) != 1 or not v.validate_scan_path(extra_args[0]):
            return None, "invalid or disallowed path for host_tail_follow_scan", None
        path = extra_args[0]
        sec = max(5, min(TAIL_FOLLOW_TIMEOUT_SECONDS, 90))
        cap = sec + 10
        return ["timeout", "--signal=TERM", str(sec), "tail", "-f", "-n", "80", path], None, cap

    if profile == "docker_cli_inspect":
        if len(extra_args) != 1:
            return None, "parameter 'container' is required", None
        c = extra_args[0].strip()
        if not v.validate_docker_name(c):
            return None, "invalid docker name for inspect", None
        return ["docker", "inspect", c], None, 60

    if profile == "docker_cli_logs_tail":
        if len(extra_args) < 1:
            return None, "parameter 'container' is required", None
        c = extra_args[0].strip()
        if not v.validate_docker_name(c):
            return None, "invalid docker name for logs", None
        try:
            n = int(extra_args[1]) if len(extra_args) > 1 else 120
        except ValueError:
            return None, "line_count must be integer", None
        n = max(10, min(n, MAX_DOCKER_HOST_LOG_LINES))
        return ["docker", "logs", "--tail", str(n), c], None, 90

    return None, f"unknown read-only profile: {profile}", None
