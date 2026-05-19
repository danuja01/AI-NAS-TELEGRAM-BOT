"""
Host storage scans on allowlisted paths only (du / find).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import config
from services.host_runner import run_profile

logger = logging.getLogger(__name__)


@dataclass
class DuEntry:
    path: str
    size: str


@dataclass
class LargeFile:
    path: str
    size_bytes: int
    size_human: str
    note: str = ""


@dataclass
class ScanBundle:
    docker_du: List[DuEntry] = field(default_factory=list)
    overlay_top: List[DuEntry] = field(default_factory=list)
    large_files: List[LargeFile] = field(default_factory=list)
    huge_logs: List[LargeFile] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _file_safety_note(path: str) -> str:
    p = path.lower()
    if "/var/log" in p or p.endswith(".log"):
        return "Log file — truncate or rotate, do not delete blindly"
    if "/apt" in p or "cache" in p:
        return "May be apt cache — apt-get clean"
    if "/docker" in p and "json.log" in p:
        return "Container log — consider docker logs limits or truncate"
    if p.endswith((".tmp", ".temp")):
        return "Temp file — verify not in use"
    return "Review before deleting"


def du_directory(path: str) -> List[DuEntry]:
    r = run_profile("du_path", extra_args=[path], timeout=config.STORAGE_CMD_TIMEOUT)
    if r.error:
        logger.warning("du_path %s: %s", path, r.error)
        return []
    entries = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        size, p = parts[0].strip(), parts[1].strip()
        if p:
            entries.append(DuEntry(path=p, size=size))
    entries.sort(key=lambda e: _du_sort_key(e.size), reverse=True)
    return entries


def _du_sort_key(size: str) -> float:
    m = re.match(r"([\d.]+)([KMGTP]?)", size)
    if not m:
        return 0
    val = float(m.group(1))
    mult = {"K": 1, "M": 2, "G": 3, "T": 4, "P": 5}.get(m.group(2) or "", 0)
    return val * (1024 ** mult)


def find_large_files(min_mb: Optional[int] = None, max_results: int = 20) -> List[LargeFile]:
    min_mb = min_mb or config.STORAGE_FIND_MIN_MB
    found: List[LargeFile] = []
    for root in config.STORAGE_SCAN_PATHS:
        r = run_profile(
            "find_large_files",
            extra_args=[root, str(min_mb), str(max_results)],
            timeout=config.STORAGE_CMD_TIMEOUT,
        )
        if r.error:
            logger.warning("find_large_files %s: %s", root, r.error)
            continue
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            try:
                nbytes = int(parts[0])
            except ValueError:
                continue
            path = parts[1]
            found.append(
                LargeFile(
                    path=path,
                    size_bytes=nbytes,
                    size_human=_human_size(nbytes),
                    note=_file_safety_note(path),
                )
            )
    found.sort(key=lambda x: x.size_bytes, reverse=True)
    return found[:max_results]


def _scan_roots_for_logs() -> List[str]:
    candidates = ["/var/log", "/var/lib/docker/containers"]
    roots = []
    for root in candidates:
        for p in config.STORAGE_SCAN_PATHS:
            pr = p.rstrip("/") or "/"
            if root == pr or root.startswith(pr + "/") or pr.startswith(root):
                roots.append(root)
                break
    return list(dict.fromkeys(roots))


def find_huge_logs(min_mb: Optional[int] = None) -> List[LargeFile]:
    """Logs over threshold under /var/log and container json logs."""
    min_mb = min_mb or config.STORAGE_LOG_MIN_MB
    roots = _scan_roots_for_logs()
    found: List[LargeFile] = []
    for root in roots:
        r = run_profile(
            "find_large_files",
            extra_args=[root, str(min_mb), "30"],
            timeout=config.STORAGE_CMD_TIMEOUT,
        )
        if r.error:
            continue
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) != 2:
                continue
            try:
                nbytes = int(parts[0])
            except ValueError:
                continue
            path = parts[1]
            if "log" not in path.lower():
                continue
            found.append(
                LargeFile(
                    path=path,
                    size_bytes=nbytes,
                    size_human=_human_size(nbytes),
                    note=_file_safety_note(path),
                )
            )
    found.sort(key=lambda x: x.size_bytes, reverse=True)
    return found


def scan_overlay2_top(n: int = 10) -> List[DuEntry]:
    base = "/var/lib/docker/overlay2"
    entries = du_directory(base)
    return entries[:n]


def run_full_scan_bundle() -> ScanBundle:
    bundle = ScanBundle()
    bundle.docker_du = du_directory("/var/lib/docker")
    bundle.overlay_top = scan_overlay2_top(10)
    bundle.large_files = find_large_files()
    bundle.huge_logs = find_huge_logs()
    return bundle
