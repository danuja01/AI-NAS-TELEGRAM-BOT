"""Validation helpers for readonly host argv (no shell)."""

from __future__ import annotations

import re
from typing import Final

import config

_SCAN_PATH_RE = re.compile(r"^/[a-zA-Z0-9_./-]+$")
_DOCKER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,253}$")
_GENERIC_SYSTEMD_UNIT_RE = re.compile(r"^[a-zA-Z0-9:@_.\-\\]{1,240}$")
_UNIT_RE = re.compile(r"^[a-zA-Z0-9_.@-]+$")

# grep -F needles: exact allowlist + character class (defense in depth)
_GREP_ALLOWED: Final[frozenset[str]] = frozenset(
    {
        "error",
        "warn",
        "warning",
        "fail",
        "failed",
        "Failed password",
        "authentication failure",
    }
)
_GREP_CHARS_OK = re.compile(r"^[A-Za-z0-9 _.,+-]+$")

_OMV_RPC_USER_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")


def validate_scan_path(path: str) -> bool:
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


def validate_systemd_unit(unit: str) -> bool:
    if not _generic_systemd_unit_syntax_ok(unit):
        return False
    if getattr(config, "HOST_READONLY_SYSTEMD_ANY_UNIT", False):
        return True
    if not unit or not _UNIT_RE.match(unit):
        return False
    return unit in config.MONITOR_SYSTEMD_UNITS


def validate_docker_name(name: str) -> bool:
    return bool(name and _DOCKER_NAME_RE.match(name))


def validate_readonly_docker_name(name: str) -> bool:
    return validate_docker_name((name or "").strip())


def validate_grep_keyword(needle: str) -> bool:
    """
    Fixed-string grep only: must match allowlist and safe charset.
    Blocks obvious attempts to pivot into env/secrets (e.g. ``$``, ``=``, backticks).
    """
    s = (needle or "").strip()
    if not s or len(s) > 120:
        return False
    if s not in _GREP_ALLOWED:
        return False
    if not _GREP_CHARS_OK.fullmatch(s):
        return False
    low = s.lower()
    blocked = (
        "secret",
        "token",
        "apikey",
        "api_key",
        "password=",
        "private_key",
        "authorization:",
        "bearer ",
    )
    if any(b in low for b in blocked):
        return False
    return True


def validate_omv_rpc_user(user: str) -> bool:
    return bool(_OMV_RPC_USER_RE.match(user))
