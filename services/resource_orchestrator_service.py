"""
Docker operations, workload detection, and persistent state for the Resource Orchestrator.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

import config
from services import docker_service

logger = logging.getLogger(__name__)


def critical_containers() -> frozenset[str]:
    return config.RESOURCE_CRITICAL_CONTAINERS


def pause_containers() -> tuple[str, ...]:
    return config.RESOURCE_PAUSE_CONTAINERS


def stop_containers() -> tuple[str, ...]:
    return config.RESOURCE_STOP_CONTAINERS


def normalize_container_name(name: str) -> str:
    return (name or "").strip().lstrip("/").lower()


def is_critical(name: str) -> bool:
    return normalize_container_name(name) in critical_containers()


@dataclass(frozen=True)
class ContainerUsage:
    """Per-container resource usage from Docker stats."""

    name: str
    cpu_percent: float
    memory_bytes: int
    memory_percent_of_system: float


@dataclass
class OrchestratorPersistedState:
    """JSON-serializable orchestrator state."""

    enabled: bool = False
    paused_by_orchestrator: List[str] = field(default_factory=list)
    stopped_by_orchestrator: List[str] = field(default_factory=list)
    last_trigger: str = ""
    last_recovery: str = ""
    mitigation_active: bool = False
    stage1_at: str = ""
    recovery_stable_since: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "paused_by_orchestrator": list(self.paused_by_orchestrator),
            "stopped_by_orchestrator": list(self.stopped_by_orchestrator),
            "last_trigger": self.last_trigger,
            "last_recovery": self.last_recovery,
            "mitigation_active": self.mitigation_active,
            "stage1_at": self.stage1_at,
            "recovery_stable_since": self.recovery_stable_since,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestratorPersistedState":
        return cls(
            enabled=bool(data.get("enabled", False)),
            paused_by_orchestrator=[
                normalize_container_name(n)
                for n in (data.get("paused_by_orchestrator") or [])
                if n
            ],
            stopped_by_orchestrator=[
                normalize_container_name(n)
                for n in (data.get("stopped_by_orchestrator") or [])
                if n
            ],
            last_trigger=str(data.get("last_trigger") or ""),
            last_recovery=str(data.get("last_recovery") or ""),
            mitigation_active=bool(data.get("mitigation_active", False)),
            stage1_at=str(data.get("stage1_at") or ""),
            recovery_stable_since=str(data.get("recovery_stable_since") or ""),
        )


def _state_path() -> Path:
    return Path(config.RESOURCE_ORCHESTRATOR_STATE_PATH)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_state() -> OrchestratorPersistedState:
    path = _state_path()
    if not path.is_file():
        return OrchestratorPersistedState(
            enabled=config.RESOURCE_ORCHESTRATOR_ENABLED,
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return OrchestratorPersistedState.from_dict(raw if isinstance(raw, dict) else {})
    except Exception as e:
        logger.error("Failed to load orchestrator state from %s: %s", path, e)
        return OrchestratorPersistedState(
            enabled=config.RESOURCE_ORCHESTRATOR_ENABLED,
        )


def save_state(state: OrchestratorPersistedState) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(state.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
    except Exception as e:
        logger.error("Failed to save orchestrator state to %s: %s", path, e)
        raise


def collect_running_container_usage() -> List[ContainerUsage]:
    """Docker stats for all running containers (name, CPU %, RAM vs system)."""
    if not docker_service.DOCKER_AVAILABLE:
        return []
    total_ram = psutil.virtual_memory().total
    usages: List[ContainerUsage] = []
    try:
        client = docker_service.get_docker_client()
        for container in client.containers.list():
            if (container.status or "").lower() != "running":
                continue
            try:
                stats = container.stats(stream=False)
                mem = int(stats.get("memory_stats", {}).get("usage") or 0)
                cpu = float(docker_service.calculate_cpu_percent(stats))
                name = normalize_container_name(container.name)
                if not name:
                    continue
                mem_pct = (mem / total_ram * 100.0) if total_ram > 0 else 0.0
                usages.append(
                    ContainerUsage(
                        name=name,
                        cpu_percent=round(cpu, 2),
                        memory_bytes=mem,
                        memory_percent_of_system=round(mem_pct, 2),
                    )
                )
            except Exception as e:
                logger.debug("stats for %s: %s", container.name, e)
    except Exception as e:
        logger.warning("collect_running_container_usage: %s", e)
    return usages


def detect_heavy_containers(
    usages: List[ContainerUsage],
    *,
    system_ram_percent: float,
    system_cpu_percent: float,
) -> frozenset[str]:
    """
    Containers driving pressure — skipped for pause/stop so they can keep working.

    Uses live Docker memory/CPU. Under RAM pressure, also protects top memory consumers.
    """
    if not config.RESOURCE_PROTECT_HEAVY_CONTAINERS or not usages:
        return frozenset()

    min_bytes = config.RESOURCE_HEAVY_MIN_MEMORY_MB * 1024 * 1024
    ram_hi = config.RESOURCE_RAM_HIGH_PERCENT
    system_ram_stressed = system_ram_percent >= ram_hi - 5

    eligible = [
        u
        for u in usages
        if not is_critical(u.name) and u.memory_bytes >= min_bytes
    ]
    eligible.sort(key=lambda u: u.memory_bytes, reverse=True)

    heavy: Dict[str, int] = {}

    for u in eligible:
        if u.memory_percent_of_system >= config.RESOURCE_HEAVY_RAM_PERCENT:
            heavy[u.name] = u.memory_bytes
        elif u.cpu_percent >= config.RESOURCE_HEAVY_CPU_PERCENT:
            heavy[u.name] = u.memory_bytes

    if system_ram_stressed:
        for u in eligible[: config.RESOURCE_HEAVY_MAX_PROTECT]:
            heavy[u.name] = u.memory_bytes
    elif system_cpu_percent >= config.RESOURCE_CPU_HIGH_PERCENT - 5:
        by_cpu = sorted(eligible, key=lambda u: u.cpu_percent, reverse=True)
        for u in by_cpu[: config.RESOURCE_HEAVY_MAX_PROTECT]:
            if u.cpu_percent >= config.RESOURCE_HEAVY_CPU_PERCENT * 0.5:
                heavy[u.name] = u.memory_bytes

    ranked = sorted(heavy.items(), key=lambda item: item[1], reverse=True)
    return frozenset(name for name, _ in ranked[: config.RESOURCE_HEAVY_MAX_PROTECT])


def list_known_statuses() -> Dict[str, str]:
    """Map normalized container name -> Docker status (running, paused, exited, …)."""
    out: Dict[str, str] = {}
    if not docker_service.DOCKER_AVAILABLE:
        return out
    try:
        for info in docker_service.list_containers(all_containers=True, include_stats=False):
            name = normalize_container_name(info.get("name", ""))
            if name:
                out[name] = (info.get("status") or "").lower()
    except Exception as e:
        logger.warning("list_known_statuses: %s", e)
    return out


def resolve_container_name(candidates: Set[str], logical_name: str) -> Optional[str]:
    """Find actual Docker name (case preserved) for a logical lowercase name."""
    key = normalize_container_name(logical_name)
    for name in candidates:
        if normalize_container_name(name) == key:
            return name
    return key if key in candidates else None


def safe_pause(name: str, statuses: Dict[str, str]) -> bool:
    """Pause only if running and not critical."""
    key = normalize_container_name(name)
    if is_critical(key):
        logger.warning("Refusing to pause critical container %s", name)
        return False
    status = statuses.get(key)
    if status is None:
        logger.info("Pause skipped: container %s not found", name)
        return False
    if status != "running":
        logger.info("Pause skipped: %s status=%s (not running)", name, status)
        return False
    try:
        docker_service.pause_container(name)
        return True
    except Exception as e:
        logger.error("pause failed for %s: %s", name, e)
        return False


def safe_unpause(name: str, statuses: Dict[str, str]) -> bool:
    key = normalize_container_name(name)
    if statuses.get(key) != "paused":
        logger.info("Unpause skipped: %s not paused", name)
        return False
    try:
        docker_service.unpause_container(name)
        return True
    except Exception as e:
        logger.error("unpause failed for %s: %s", name, e)
        return False


def safe_stop(name: str, statuses: Dict[str, str]) -> bool:
    key = normalize_container_name(name)
    if is_critical(key):
        logger.warning("Refusing to stop critical container %s", name)
        return False
    status = statuses.get(key)
    if status is None:
        logger.info("Stop skipped: container %s not found", name)
        return False
    if status != "running":
        logger.info("Stop skipped: %s status=%s (not running)", name, status)
        return False
    try:
        docker_service.stop_container(name)
        return True
    except Exception as e:
        logger.error("stop failed for %s: %s", name, e)
        return False


def safe_start(name: str, statuses: Dict[str, str]) -> bool:
    key = normalize_container_name(name)
    status = statuses.get(key)
    if status == "running":
        return True
    if status not in ("exited", "created", "dead"):
        logger.info("Start skipped: %s status=%s", name, status)
        return False
    try:
        docker_service.start_container(name)
        return True
    except Exception as e:
        logger.error("start failed for %s: %s", name, e)
        return False
