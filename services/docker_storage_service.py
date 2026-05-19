"""
Docker disk usage, pruning (safe/aggressive), and image analysis.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from utils.shell_exec import ShellResult, run_sync

logger = logging.getLogger(__name__)


def _container_row_running(row: Dict[str, Any]) -> bool:
    """True if dashboard row counts as running (CLI JSON varies by Docker version)."""
    state = (row.get("State") or row.get("state") or "").strip().lower()
    status = (row.get("Status") or row.get("status") or "").strip().lower()
    if state == "running":
        return True
    # docker ps --format json often only has Status: "Up 2 hours", no State
    if status.startswith("up"):
        return True
    return False


def _docker_ps_via_sdk() -> List[Dict[str, Any]]:
    """Container list compatible with dashboard formatter / counts (same socket as SDK image list)."""
    import docker

    client = docker.from_env()
    out: List[Dict[str, Any]] = []
    for c in client.containers.list(all=True):
        name = getattr(c, "name", "") or ""
        status = getattr(c, "status", "") or ""
        image_name = ""
        try:
            tags = c.image.tags or []
            image_name = tags[0] if tags else getattr(c.image, "id", "?")[:19]
        except Exception:
            image_name = "?"
        cid = getattr(c, "short_id", "")
        out.append(
            {
                "ID": cid.replace("sha256:", ""),
                "Names": name.lstrip("/"),
                "Image": image_name or "?",
                "State": status,
                "Status": status,
            }
        )
    return out


# Fixed docker CLI invocations only — never interpolate user input.
DOCKER_DF = ["docker", "system", "df"]
DOCKER_DF_V = ["docker", "system", "df", "-v"]
DOCKER_PS_A = ["docker", "ps", "-a", "--format", "{{json .}}"]
DOCKER_IMAGES = [
    "docker",
    "images",
    "--format",
    "{{.ID}}\t{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}",
]
DOCKER_BUILDER_DU = ["docker", "builder", "du", "--verbose"]
PRUNE_CONTAINER_DRY = ["docker", "container", "prune"]
PRUNE_IMAGE_DRY = ["docker", "image", "prune"]
PRUNE_IMAGE_ALL_DRY = ["docker", "image", "prune", "-a"]
PRUNE_BUILDER_DRY = ["docker", "builder", "prune"]
PRUNE_CONTAINER_F = ["docker", "container", "prune", "-f"]
PRUNE_IMAGE_F = ["docker", "image", "prune", "-f"]
PRUNE_IMAGE_ALL_F = ["docker", "image", "prune", "-a", "-f"]
PRUNE_BUILDER_F = ["docker", "builder", "prune", "-f"]
PRUNE_NETWORK_F = ["docker", "network", "prune", "-f"]


@dataclass
class DockerDfSummary:
    lines: List[str] = field(default_factory=list)
    reclaimable_hint: str = ""
    raw: str = ""


@dataclass
class PruneEstimate:
    container_reclaim: str = "0B"
    image_reclaim: str = "0B"
    builder_reclaim: str = "0B"
    raw_outputs: List[str] = field(default_factory=list)


@dataclass
class PruneResult:
    steps: List[Tuple[str, ShellResult]] = field(default_factory=list)
    before_df: str = ""
    after_df: str = ""


def _parse_reclaimable(text: str) -> str:
    m = re.search(r"Total reclaimed space:\s*(\S+)", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"reclaimed\s+(\S+)", text, re.I)
    if m:
        return m.group(1)
    return "0B"


def docker_system_df(verbose: bool = False) -> ShellResult:
    return run_sync(DOCKER_DF_V if verbose else DOCKER_DF)


def docker_ps_json_lines() -> List[Dict[str, Any]]:
    # Prefer Docker SDK: official image has no docker.io CLI binary, only the socket mount.
    try:
        return _docker_ps_via_sdk()
    except ImportError:
        logger.warning("docker_ps_json_lines: python docker SDK unavailable, trying CLI")
    except Exception as e:
        logger.warning("docker_ps_json_lines: SDK failed (%s); trying CLI", e)

    r = run_sync(DOCKER_PS_A)
    out = []
    if r.error:
        logger.debug(
            "docker_ps_json_lines CLI: argv=%s err=%s stderr=%s",
            r.argv[:3],
            r.error,
            (r.stderr or "")[:200],
        )
    if not r.stdout:
        return out
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def docker_images_table() -> ShellResult:
    return run_sync(DOCKER_IMAGES)


def docker_builder_du() -> ShellResult:
    return run_sync(DOCKER_BUILDER_DU)


def estimate_safe_prune(dry_run_all: bool = False) -> PruneEstimate:
    """Dry-run prune commands (no -f) to estimate reclaimable space."""
    est = PruneEstimate()
    for label, argv in [
        ("container", PRUNE_CONTAINER_DRY),
        ("image", PRUNE_IMAGE_ALL_DRY if dry_run_all else PRUNE_IMAGE_DRY),
        ("builder", PRUNE_BUILDER_DRY),
    ]:
        r = run_sync(argv)
        est.raw_outputs.append(f"--- {label} ---\n{r.stdout}\n{r.stderr}")
        val = _parse_reclaimable(r.stdout + r.stderr)
        if label == "container":
            est.container_reclaim = val
        elif label == "image":
            est.image_reclaim = val
        else:
            est.builder_reclaim = val
    return est


def run_safe_prune(use_all_images: bool = False) -> PruneResult:
    """Prune stopped containers, unused images, build cache. Never volumes."""
    result = PruneResult()
    result.before_df = docker_system_df().stdout
    steps = [
        ("container prune", PRUNE_CONTAINER_F),
        ("image prune", PRUNE_IMAGE_ALL_F if use_all_images else PRUNE_IMAGE_F),
        ("builder prune", PRUNE_BUILDER_F),
    ]
    for name, argv in steps:
        r = run_sync(argv)
        result.steps.append((name, r))
        logger.info(
            "safe_prune %s exit=%s reclaim=%s",
            name,
            r.exit_code,
            _parse_reclaimable(r.stdout + r.stderr),
        )
    result.after_df = docker_system_df().stdout
    return result


def run_aggressive_extras() -> List[Tuple[str, ShellResult]]:
    """Network prune + apt clean on host (via host_runner in caller)."""
    steps = []
    r = run_sync(PRUNE_NETWORK_F)
    steps.append(("network prune", r))
    logger.info("aggressive network prune exit=%s", r.exit_code)
    return steps


def list_images_with_usage() -> List[Dict[str, Any]]:
    """Images with in-use flag via Docker SDK."""
    try:
        import docker
        from docker.errors import DockerException

        client = docker.from_env()
        containers = client.containers.list(all=True)
        used_ids = set()
        for c in containers:
            try:
                used_ids.add(c.image.id)
                if c.image.id:
                    used_ids.add(c.image.id.split(":")[-1][:12])
            except Exception:
                pass
            for tag in c.image.tags or []:
                used_ids.add(tag)

        images = []
        for img in client.images.list():
            short = img.short_id.replace("sha256:", "")
            tags = img.tags or ["<none>:<none>"]
            repo, tag = "<none>", "<none>"
            if tags and tags[0] != "<none>:<none>":
                parts = tags[0].rsplit(":", 1)
                repo = parts[0]
                tag = parts[1] if len(parts) > 1 else "latest"
            dangling = not img.tags
            in_use = img.id in used_ids or short in used_ids or any(t in used_ids for t in tags)
            size = img.attrs.get("Size", 0)
            created = img.attrs.get("Created", "")
            images.append(
                {
                    "id": short,
                    "repository": repo,
                    "tag": tag,
                    "size_bytes": size,
                    "size_human": _human_size(size),
                    "created": created[:10] if created else "?",
                    "dangling": dangling,
                    "in_use": in_use,
                    "unused": not in_use and not dangling,
                }
            )
        images.sort(key=lambda x: x.get("size_bytes", 0), reverse=True)
        return images
    except Exception as e:
        logger.error("list_images_with_usage: %s", e)
        return []


def run_quick_prune() -> PruneResult:
    """dprune: dangling images + builder cache only."""
    result = PruneResult()
    result.before_df = docker_system_df().stdout
    for name, argv in [
        ("image prune (dangling)", PRUNE_IMAGE_F),
        ("builder prune", PRUNE_BUILDER_F),
    ]:
        r = run_sync(argv)
        result.steps.append((name, r))
    result.after_df = docker_system_df().stdout
    return result


def count_containers() -> Tuple[int, int]:
    running = stopped = 0
    for c in docker_ps_json_lines():
        if _container_row_running(c):
            running += 1
        else:
            stopped += 1
    return running, stopped


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}PB"
