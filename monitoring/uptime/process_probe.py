"""Read-only /proc process presence checks (no shell)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROC = Path("/proc")


def process_matches(target: str) -> tuple[bool, str]:
    """
    Target formats:
      nginx           — comm or cmdline contains 'nginx'
      cmd:immich      — cmdline contains 'immich'
      name:postgres   — same as bare name
      pid:1234        — process directory exists
    """
    raw = (target or "").strip()
    if not raw:
        return False, "empty target"

    if raw.lower().startswith("pid:"):
        try:
            pid = int(raw[4:].strip())
        except ValueError:
            return False, "invalid pid"
        if (_PROC / str(pid)).is_dir():
            return True, f"pid {pid} running"
        return False, f"pid {pid} not found"

    needle = raw
    mode = "name"
    if raw.lower().startswith("cmd:"):
        needle = raw[4:].strip()
        mode = "cmd"
    elif raw.lower().startswith("name:"):
        needle = raw[5:].strip()
        mode = "name"

    if not needle:
        return False, "empty process name"

    needle_l = needle.lower()
    if not _PROC.is_dir():
        return False, "/proc not available"

    for entry in _PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if mode == "cmd":
                cmdline_f = entry / "cmdline"
                if cmdline_f.is_file():
                    data = cmdline_f.read_bytes().replace(b"\x00", b" ").decode(
                        "utf-8", errors="replace"
                    )
                    if needle_l in data.lower():
                        return True, f"cmdline match pid {entry.name}"
            comm_f = entry / "comm"
            if comm_f.is_file():
                comm = comm_f.read_text(encoding="utf-8", errors="replace").strip("\x00")
                if needle_l in comm.lower():
                    return True, f"comm match pid {entry.name}"
            status_f = entry / "status"
            if mode == "name" and status_f.is_file():
                for line in status_f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("Name:"):
                        pname = line.split(":", 1)[-1].strip().lower()
                        if needle_l in pname:
                            return True, f"status Name match pid {entry.name}"
        except (OSError, PermissionError):
            continue

    return False, f"no process matching '{needle}'"
