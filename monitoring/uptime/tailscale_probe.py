"""Tailscale health checks: host CLI, Docker container, or container-running fallback."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional, Tuple

import config

logger = logging.getLogger(__name__)


def _parse_tailscale_json(stdout: str) -> Tuple[bool, str]:
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError as e:
        return False, f"invalid JSON: {e}"
    self_node = data.get("Self") or {}
    if self_node.get("Online") is True:
        ips = self_node.get("TailscaleIPs") or []
        return True, f"online {ips[0] if ips else ''}"
    backend = (self_node.get("BackendState") or "unknown").lower()
    return False, f"offline ({backend})"


def _tailscale_cli_status(timeout: int) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "tailscale CLI not in PATH"
    except subprocess.TimeoutExpired:
        return False, "tailscale CLI timed out"
    if proc.returncode != 0:
        return False, (proc.stderr or "tailscale status failed").strip()[:500]
    ok, msg = _parse_tailscale_json(proc.stdout)
    return ok, msg


def _tailscale_docker_status(container: str, timeout: int) -> Tuple[bool, str]:
    name = (container or "").strip().lstrip("/")
    if not name:
        return False, "empty container name"
    try:
        proc = subprocess.run(
            ["docker", "exec", name, "tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "docker CLI not in PATH"
    except subprocess.TimeoutExpired:
        return False, f"docker exec {name} timed out"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "docker exec failed").strip()[:500]
        return False, err
    ok, msg = _parse_tailscale_json(proc.stdout)
    return ok, f"{name}: {msg}"


def _find_tailscale_container() -> Optional[str]:
    try:
        from services.docker_service import list_containers

        for c in list_containers(all_containers=True, include_stats=False):
            name = (c.get("name") or "").lstrip("/").lower()
            if (c.get("status") or "").lower() != "running":
                continue
            if "tailscale" in name:
                return c.get("name", "").lstrip("/")
    except Exception as e:
        logger.debug("find tailscale container: %s", e)
    return None


def _tailscale_interface_up() -> Tuple[bool, str]:
    """Check for tailscale0 / tailscale1 interface without CLI."""
    from pathlib import Path

    net = Path("/sys/class/net")
    if not net.is_dir():
        return False, "no /sys/class/net"
    for iface in net.iterdir():
        if iface.name.startswith("tailscale"):
            oper = iface / "operstate"
            state = oper.read_text().strip() if oper.is_file() else "unknown"
            if state in ("up", "unknown"):
                return True, f"interface {iface.name} {state}"
    return False, "no tailscale interface"


def default_tailscale_target() -> str:
    """Monitor target string for built-in tailscale-mesh."""
    mode = (config.UPTIME_TAILSCALE_PROBE or "auto").strip().lower()
    cname = (config.UPTIME_TAILSCALE_CONTAINER or "tailscale").strip()
    if mode == "cli":
        return "cli"
    if mode == "docker":
        return f"docker:{cname}"
    if mode == "container":
        return f"container:{cname}"
    if mode == "interface":
        return "interface"
    if mode.startswith("docker:") or mode.startswith("container:"):
        return mode
    # auto
    if cname and cname not in ("auto", "online"):
        return f"docker:{cname}"
    return "docker:auto"


def run_tailscale_check(target: str, timeout: int) -> Tuple[bool, str]:
    """
    Target modes:
      cli | online     — host tailscale binary
      docker:<name>    — docker exec tailscale status --json
      docker:auto      — find running *tailscale* container
      container:<name> — only verify container is running
      interface        — tailscale0 net iface present
    """
    t = (target or "auto").strip().lower()
    if t in ("cli", "online", ""):
        return _tailscale_cli_status(timeout)
    if t == "docker:auto":
        found = _find_tailscale_container()
        if not found:
            ok, msg = _tailscale_interface_up()
            if ok:
                return True, f"{msg} (no container match)"
            return False, "no running tailscale container found"
        return _tailscale_docker_status(found, timeout)
    if t.startswith("docker:"):
        return _tailscale_docker_status(t[7:], timeout)
    if t.startswith("container:"):
        from services.docker_service import get_container

        name = t[10:].strip()
        try:
            c = get_container(name)
            if (c.status or "").lower() == "running":
                return True, f"container {name} running"
            return False, f"container {name} status={c.status}"
        except Exception as e:
            return False, str(e)[:500]
    if t == "interface":
        return _tailscale_interface_up()
    # legacy / unknown → try cli then docker auto
    ok, msg = _tailscale_cli_status(timeout)
    if ok or "not in PATH" not in msg:
        return ok, msg
    return run_tailscale_check("docker:auto", timeout)
