"""
Execute allowlisted commands on the NAS host from inside Docker.

Modes:
- nsenter: join host init namespaces (use docker compose pid: host + privileged)
- ssh:    BatchMode SSH to HOST_SSH (e.g. admin@192.168.1.5)
- none:   disabled (returns structured error)
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import config

logger = logging.getLogger(__name__)

_UNIT_RE = re.compile(r"^[a-zA-Z0-9_.@-]+$")
# Allowlisted absolute paths for storage scans (must match config.STORAGE_SCAN_PATHS prefix)
_SCAN_PATH_RE = re.compile(r"^/[a-zA-Z0-9_./-]+$")


@dataclass
class HostExecResult:
    profile: str
    exit_code: int
    stdout: str
    stderr: str
    error: Optional[str] = None  # configuration / validation error

    @property
    def ok(self) -> bool:
        return self.error is None and self.exit_code == 0


def _truncate(s: str, limit: int = 12000) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 40] + "\n\n… (truncated) …\n"


def _validate_unit(unit: str) -> bool:
    if not unit or not _UNIT_RE.match(unit):
        return False
    return unit in config.MONITOR_SYSTEMD_UNITS


def _validate_scan_path(path: str) -> bool:
    if not path or not _SCAN_PATH_RE.match(path):
        return False
    path = path.rstrip("/") or "/"
    for allowed in config.STORAGE_SCAN_PATHS:
        root = allowed.rstrip("/") or "/"
        if path == root or path.startswith(root + "/"):
            return True
    return False


def _build_argv_nsenter(inner: Sequence[str]) -> List[str]:
    pid = str(config.HOST_NSENTER_PID)
    return ["nsenter", "-t", pid, "-m", "-u", "-i", "-n", "-p", "--", *inner]


def _build_argv_ssh(inner: Sequence[str]) -> List[str]:
    base = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    extra = getattr(config, "HOST_SSH_EXTRA_ARGS", []) or []
    if extra:
        base.extend(extra)
    base.append(config.HOST_SSH)
    base.append("--")
    base.extend(inner)
    return base


def _resolve_wrapper(inner: Sequence[str]) -> Tuple[List[str], Optional[str]]:
    mode = (config.HOST_EXEC_MODE or "none").lower()
    if mode == "none":
        return [], "Host execution disabled (set HOST_EXEC_MODE=nsenter or ssh)"
    if mode == "nsenter":
        if not shutil.which("nsenter"):
            return [], "nsenter not found in container"
        return _build_argv_nsenter(inner), None
    if mode == "ssh":
        if not config.HOST_SSH:
            return [], "HOST_SSH not set (user@host)"
        if not shutil.which("ssh"):
            return [], "ssh not found in container"
        return _build_argv_ssh(inner), None
    return [], f"Unknown HOST_EXEC_MODE: {config.HOST_EXEC_MODE}"


def run_profile(
    profile: str,
    *,
    extra_args: Optional[Sequence[str]] = None,
    timeout: Optional[int] = None,
    env: Optional[dict] = None,
) -> HostExecResult:
    """
    Run a predefined host operation. Only allowlisted profiles are executed.
    """
    extra_args = list(extra_args or [])
    to: Optional[int] = timeout if timeout is not None else config.HOST_EXEC_TIMEOUT_SHORT

    inner: Optional[List[str]] = None

    if profile == "apt_update":
        inner = ["apt-get", "update", "-qq"]
    elif profile == "apt_list_upgradable":
        inner = ["apt", "list", "--upgradable"]
    elif profile == "reboot_required":
        inner = ["sh", "-c", "if [ -f /var/run/reboot-required ]; then cat /var/run/reboot-required; else echo NO_REBOOT_PENDING; fi"]
    elif profile == "omv_upgrade":
        inner = [
            "sh",
            "-c",
            "export DEBIAN_FRONTEND=noninteractive; "
            "if command -v omv-upgrade >/dev/null 2>&1; then exec omv-upgrade; "
            "elif [ -x /usr/sbin/omv-upgrade ]; then exec /usr/sbin/omv-upgrade; "
            "else echo 'omv-upgrade not found' >&2; exit 127; fi",
        ]
        raw_to = config.HOST_OMV_UPGRADE_TIMEOUT
        to = None if raw_to <= 0 else raw_to
    elif profile == "systemctl_is_active":
        if len(extra_args) != 1 or not _validate_unit(extra_args[0]):
            return HostExecResult(
                profile, -1, "", "", error="Invalid or disallowed systemd unit"
            )
        inner = ["systemctl", "is-active", extra_args[0]]
    elif profile == "journal_tail":
        if len(extra_args) != 1 or not _validate_unit(extra_args[0]):
            return HostExecResult(
                profile, -1, "", "", error="Invalid or disallowed systemd unit"
            )
        n = str(min(50, max(5, config.JOURNAL_TAIL_LINES)))
        inner = ["journalctl", "-u", extra_args[0], "-n", n, "--no-pager"]
    elif profile == "du_path":
        if len(extra_args) != 1 or not _validate_scan_path(extra_args[0]):
            return HostExecResult(profile, -1, "", "", error="Invalid or disallowed scan path")
        inner = ["du", "-h", "--max-depth=1", extra_args[0]]
        to = config.STORAGE_CMD_TIMEOUT
    elif profile == "find_large_files":
        if len(extra_args) < 2 or not _validate_scan_path(extra_args[0]):
            return HostExecResult(profile, -1, "", "", error="Invalid or disallowed scan path")
        try:
            min_mb = int(extra_args[1])
            max_n = int(extra_args[2]) if len(extra_args) > 2 else 20
        except ValueError:
            return HostExecResult(profile, -1, "", "", error="Invalid find size/limit args")
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
        to = config.STORAGE_CMD_TIMEOUT
    elif profile == "systemctl_failed":
        inner = ["systemctl", "--failed", "--no-pager", "--plain", "--no-legend"]
        to = config.STORAGE_CMD_TIMEOUT
    elif profile == "apt_clean":
        inner = ["apt-get", "clean", "-qq"]
        to = config.STORAGE_CMD_TIMEOUT
    else:
        return HostExecResult(profile, -1, "", "", error=f"Unknown profile: {profile}")

    argv, err = _resolve_wrapper(inner)
    if err:
        return HostExecResult(profile, -1, "", "", error=err)

    run_env = None
    if env:
        import os

        run_env = os.environ.copy()
        run_env.update(env)

    logger.info(
        "host_runner profile=%s argv0=%s timeout=%s",
        profile,
        argv[0] if argv else None,
        "none" if to is None else str(to),
    )
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=to,
            env=run_env,
        )
        return HostExecResult(
            profile,
            proc.returncode,
            _truncate(proc.stdout or ""),
            _truncate(proc.stderr or "", limit=4000),
        )
    except subprocess.TimeoutExpired as e:
        out_dec = e.stdout if isinstance(e.stdout, str) else (
            e.stdout.decode(errors="replace") if e.stdout else ""
        )
        err_dec = e.stderr if isinstance(e.stderr, str) else (
            e.stderr.decode(errors="replace") if e.stderr else ""
        )
        display_to = "unlimited" if to is None else f"{to}s"
        err_msg = f"Timeout (limit {display_to}) for profile {profile}"
        if profile == "omv_upgrade":
            err_msg += (
                ". The subprocess was killed; the host may have incomplete dpkg. "
                "On the NAS run: sudo dpkg --configure -a && sudo apt --fix-broken install. "
                "Avoid OMV Workbench Apply until that succeeds. "
                "Set HOST_OMV_UPGRADE_TIMEOUT higher or to 0 (no limit) in .env."
            )
        return HostExecResult(
            profile,
            -1,
            _truncate(out_dec),
            _truncate(err_dec, limit=4000),
            error=err_msg,
        )
    except Exception as e:
        logger.exception("host_runner failed")
        return HostExecResult(profile, -1, "", "", error=str(e))


def format_host_result_html(title: str, result: HostExecResult) -> str:
    """Format HostExecResult for Telegram HTML."""
    from utils.formatters import escape_telegram_html

    lines = [
        f"<b>{escape_telegram_html(title)}</b>",
        "",
    ]
    if result.error:
        lines.append(f"⚠️ <b>Error</b>: {escape_telegram_html(result.error)}")
    lines.append(f"<b>Exit</b>: <code>{result.exit_code}</code>")
    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out:
        lines.append("")
        lines.append("<b>stdout</b>")
        lines.append(f"<pre>{escape_telegram_html(out)}</pre>")
    if err:
        lines.append("")
        lines.append("<b>stderr</b>")
        lines.append(f"<pre>{escape_telegram_html(err)}</pre>")
    return "\n".join(lines)
