"""
Docker disk usage, pruning (safe/aggressive), and image analysis.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import shutil

from utils.shell_exec import ShellResult, run_sync

logger = logging.getLogger(__name__)


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}PB"


def _sdk_client():  # lazily typed
    import docker

    return docker.from_env()


def _human_space_bytes(space: Any) -> str:
    try:
        n = int(space or 0)
    except (TypeError, ValueError):
        return "0B"
    if n <= 0:
        return "0B"
    return _human_size(n)


def _docker_cli_available() -> bool:
    return shutil.which("docker") is not None


def _shell_result_from_sdk(
    argv_label: List[str],
    *,
    stdout: str,
    stderr: str = "",
    exit_code: int = 0,
    error: Optional[str] = None,
) -> ShellResult:
    return ShellResult(
        argv=list(argv_label),
        exit_code=exit_code,
        stdout=stdout[:12000],
        stderr=stderr[:4000],
        error=error,
    )


def _prune_containers_sdk() -> ShellResult:
    try:
        cli = _sdk_client()
        resp = cli.containers.prune()
        deleted = resp.get("ContainersDeleted") or []
        space = resp.get("SpaceReclaimed") or 0
        out = (
            f"Deleted {len(deleted)} container(s).\n"
            f"Total reclaimed space: {_human_space_bytes(space)}\n"
        )
        return _shell_result_from_sdk(["sdk", "container", "prune"], stdout=out)
    except Exception as exc:
        logger.exception("containers.prune sdk")
        return _shell_result_from_sdk(
            ["sdk", "container", "prune"],
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            error=str(exc),
        )


def _prune_images_sdk(dangling_only: bool) -> ShellResult:
    try:
        cli = _sdk_client()
        if dangling_only:
            filters: Dict[str, Any] = {"dangling": True}
            label = "dangling images"
        else:
            filters = {"dangling": False}
            label = "unused images (-a semantics)"
        try:
            resp = cli.images.prune(filters=filters)
        except Exception as inner:
            if not dangling_only:
                logger.warning(
                    "image prune all-unused failed (%s); retrying dangling-only", inner
                )
                return _prune_images_sdk(True)
            raise inner
        deleted = resp.get("ImagesDeleted") or []
        space = resp.get("SpaceReclaimed") or 0
        out = (
            f"Deleted {len(deleted)} image(s) ({label}).\n"
            f"Total reclaimed space: {_human_space_bytes(space)}\n"
        )
        return _shell_result_from_sdk(
            ["sdk", "image", "prune", "dangling" if dangling_only else "all-unused"],
            stdout=out,
        )
    except Exception as exc:
        logger.exception("images.prune sdk")
        return _shell_result_from_sdk(
            ["sdk", "image", "prune"],
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            error=str(exc),
        )


def _prune_builder_sdk() -> ShellResult:
    try:
        cli = _sdk_client()
        api = cli.api
        if not getattr(api, "prune_builds", None):
            return _shell_result_from_sdk(
                ["sdk", "builder", "prune"],
                stdout="",
                stderr="Build cache prune not supported by this Engine API.",
                exit_code=-1,
                error="prune_builds unavailable",
            )
        resp = api.prune_builds(filters=None) or {}
        deleted = resp.get("CachesDeleted") or resp.get("SpaceReclaimed")
        reclaimed = resp.get("SpaceReclaimed", 0)
        if isinstance(deleted, list):
            cnt = len(deleted)
            out = (
                f"Deleted {cnt} build cache record(s).\n"
                f"Total reclaimed space: {_human_space_bytes(reclaimed)}\n"
            )
        else:
            out = f"Build cache prune done.\nTotal reclaimed space: {_human_space_bytes(reclaimed)}\n"
        return _shell_result_from_sdk(["sdk", "builder", "prune"], stdout=out)
    except Exception as exc:
        logger.exception("builder prune sdk")
        return _shell_result_from_sdk(
            ["sdk", "builder", "prune"],
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            error=str(exc),
        )


def _prune_networks_sdk() -> ShellResult:
    try:
        cli = _sdk_client()
        resp = cli.networks.prune()
        nets = resp.get("NetworksDeleted") or []
        space = resp.get("SpaceReclaimed") or 0
        out = (
            f"Deleted {len(nets)} unused network(s).\n"
            f"Total reclaimed space: {_human_space_bytes(space)}\n"
        )
        return _shell_result_from_sdk(["sdk", "network", "prune"], stdout=out)
    except Exception as exc:
        logger.exception("network prune sdk")
        return _shell_result_from_sdk(
            ["sdk", "network", "prune"],
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            error=str(exc),
        )


def _docker_df_sdk(verbose: bool = False) -> ShellResult:
    """Approximate docker system df using Engine DiskUsage."""
    try:
        cli = _sdk_client()
        d = cli.df()
        lines: List[str] = ["Docker disk usage (API)", ""]
        if d.get("LayersSize") is not None:
            lines.append(f"  Layers total: {_human_space_bytes(d['LayersSize'])}")
        images = d.get("Images") or []
        containers = d.get("Containers") or []
        vols = d.get("Volumes") or []
        bcache = d.get("BuildCache") or []

        tb_size = lambda rows, key='Size': sum(int(x.get(key) or 0) for x in rows if isinstance(x, dict))

        if images:
            active = sum(1 for img in images if isinstance(img, dict) and int(img.get("Containers") or 0) > 0)
            size_sum = tb_size(images, "Size")
            lines.append(
                f"  Images:       {len(images)} total · {active} in use · size ~{_human_space_bytes(size_sum)}"
            )
        if containers:
            running = sum(1 for x in containers if isinstance(x, dict) and x.get("State") == "running")
            lines.append(
                f"  Containers:   {len(containers)} total · ~{running} running · "
                f"writable layer ~{_human_space_bytes(tb_size(containers, 'SizeRw'))}"
            )
        if vols:
            lines.append(f"  Volumes:      {len(vols)} local volume(s)")
        if bcache:
            bc_bytes = tb_size(bcache)
            lines.append(f"  Build cache:  {len(bcache)} entr(y/ies), size ~{_human_space_bytes(bc_bytes)}")
        if verbose and images[:5]:
            lines.append("")
            lines.append("(verbose sample — repo tags)")
            for img in images[:5]:
                if not isinstance(img, dict):
                    continue
                tid = (str(img.get("Id") or "?"))[:13]
                tags = ",".join((img.get("RepoTags") or [])[:3]) or "(none)"
                lines.append(f"    {tid} … {tags}")
        text = "\n".join(lines) + "\n"
        return _shell_result_from_sdk(["sdk", "df"], stdout=text)
    except Exception as exc:
        logger.warning("docker df sdk: %s", exc)
        return _shell_result_from_sdk(
            ["sdk", "df"],
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            error=str(exc),
        )



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
    r_cli: Optional[ShellResult] = None
    if _docker_cli_available():
        r_cli = run_sync(DOCKER_DF_V if verbose else DOCKER_DF)
        if r_cli.ok and (r_cli.stdout or "").strip():
            return r_cli
        if r_cli.error:
            logger.debug("docker_system_df CLI failed (%s); trying SDK", r_cli.error)
    sdk = _docker_df_sdk(verbose)
    if sdk.ok or (sdk.stdout or "").strip():
        return sdk
    if r_cli is not None:
        return r_cli
    return sdk


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
    """Dry-run prune via CLI when available; otherwise approximate from SDK data."""
    est = PruneEstimate()
    if _docker_cli_available():
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

    imgs = list_images_with_usage()
    dang = sum(int(i.get("size_bytes") or 0) for i in imgs if i.get("dangling"))
    uns = sum(int(i.get("size_bytes") or 0) for i in imgs if i.get("unused"))
    est.image_reclaim = _human_size(dang + (uns if dry_run_all else 0))
    stopped = sum(1 for c in docker_ps_json_lines() if not _container_row_running(c))
    est.container_reclaim = f"{stopped} stopped (size varies)"
    try:
        d = _sdk_client().df()
        bc = d.get("BuildCache") or []
        bc_bytes = sum(int(x.get("Size") or 0) for x in bc if isinstance(x, dict))
        est.builder_reclaim = _human_size(bc_bytes) if bc_bytes else "0B"
    except Exception:
        est.builder_reclaim = "n/a"
    est.raw_outputs.append(
        "--- note ---\nNo docker CLI in container; rough estimate from images + build cache API."
    )
    return est


def run_safe_prune(use_all_images: bool = False) -> PruneResult:
    """Prune stopped containers, unused images, build cache. Never volumes."""
    result = PruneResult()
    result.before_df = docker_system_df().stdout
    if _docker_cli_available():
        steps_cli: List[Tuple[str, List[str]]] = [
            ("container prune", PRUNE_CONTAINER_F),
            ("image prune", PRUNE_IMAGE_ALL_F if use_all_images else PRUNE_IMAGE_F),
            ("builder prune", PRUNE_BUILDER_F),
        ]
        for name, argv in steps_cli:
            r = run_sync(argv)
            result.steps.append((name, r))
            logger.info(
                "safe_prune %s exit=%s reclaim=%s",
                name,
                r.exit_code,
                _parse_reclaimable(r.stdout + r.stderr),
            )
    else:
        result.steps.append(("container prune", _prune_containers_sdk()))
        result.steps.append(
            ("image prune", _prune_images_sdk(dangling_only=not use_all_images))
        )
        result.steps.append(("builder prune", _prune_builder_sdk()))
        for name, r in result.steps:
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
    steps: List[Tuple[str, ShellResult]] = []
    if _docker_cli_available():
        r = run_sync(PRUNE_NETWORK_F)
    else:
        r = _prune_networks_sdk()
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
    if _docker_cli_available():
        for name, argv in [
            ("image prune (dangling)", PRUNE_IMAGE_F),
            ("builder prune", PRUNE_BUILDER_F),
        ]:
            r = run_sync(argv)
            result.steps.append((name, r))
    else:
        result.steps.append(("image prune (dangling)", _prune_images_sdk(True)))
        result.steps.append(("builder prune", _prune_builder_sdk()))
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
