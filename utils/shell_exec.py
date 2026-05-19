"""
Allowlisted subprocess execution with timeouts (no shell=True, no user argv).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Sequence

import config

logger = logging.getLogger(__name__)


@dataclass
class ShellResult:
    argv: List[str]
    exit_code: int
    stdout: str
    stderr: str
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.exit_code == 0


def _truncate(s: str, limit: int = 12000) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 40] + "\n\n… (truncated) …\n"


def run_sync(argv: Sequence[str], timeout: Optional[int] = None) -> ShellResult:
    """Run fixed argv list locally (e.g. docker CLI in container)."""
    argv_list = list(argv)
    to = timeout if timeout is not None else config.STORAGE_CMD_TIMEOUT
    logger.debug("shell_exec local: %s timeout=%s", argv_list[:3], to)
    try:
        proc = subprocess.run(
            argv_list,
            capture_output=True,
            text=True,
            timeout=to if to > 0 else None,
        )
        return ShellResult(
            argv=argv_list,
            exit_code=proc.returncode,
            stdout=_truncate(proc.stdout or ""),
            stderr=_truncate(proc.stderr or "", limit=4000),
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (
            e.stdout.decode(errors="replace") if e.stdout else ""
        )
        err = e.stderr if isinstance(e.stderr, str) else (
            e.stderr.decode(errors="replace") if e.stderr else ""
        )
        return ShellResult(
            argv=argv_list,
            exit_code=-1,
            stdout=_truncate(out),
            stderr=_truncate(err, limit=4000),
            error=f"Timeout after {to}s",
        )
    except FileNotFoundError as e:
        return ShellResult(argv_list, -1, "", "", error=str(e))
    except Exception as e:
        logger.exception("shell_exec failed")
        return ShellResult(argv_list, -1, "", "", error=str(e))


async def run_async(argv: Sequence[str], timeout: Optional[int] = None) -> ShellResult:
    return await asyncio.to_thread(run_sync, list(argv), timeout)
