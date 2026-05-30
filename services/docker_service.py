"""
Docker management service using Docker SDK for Python.
"""

import logging
from typing import List, Dict, Any, Optional

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Docker SDK not available. Install with: pip install docker")

logger = logging.getLogger(__name__)

_docker_client = None


def get_docker_client():
    """Get a shared Docker client instance."""
    global _docker_client
    if not DOCKER_AVAILABLE:
        raise ImportError("Docker SDK not installed")

    if _docker_client is None:
        try:
            _docker_client = docker.from_env()
        except DockerException as e:
            logger.error("Failed to connect to Docker: %s", e)
            raise
    return _docker_client


def list_containers(
    all_containers: bool = False,
    include_stats: bool = True,
) -> List[Dict[str, Any]]:
    """
    List all Docker containers.

    Args:
        all_containers: If True, include stopped containers
        include_stats: If True, fetch per-container stats (CPU/RAM; heavier on RAM/CPU)
    """
    if not DOCKER_AVAILABLE:
        return []

    try:
        client = get_docker_client()
        containers = client.containers.list(all=all_containers)

        container_list = []
        for container in containers:
            try:
                stats = None
                if include_stats and container.status == "running":
                    stats = container.stats(stream=False)

                state = container.attrs.get("State") or {}
                host_cfg = container.attrs.get("HostConfig") or {}
                restart = host_cfg.get("RestartPolicy") or {}
                info = {
                    "id": container.short_id,
                    "name": container.name,
                    "image": container.image.tags[0] if container.image.tags else "unknown",
                    "status": container.status,
                    "state": state,
                    "restart_policy": (restart.get("Name") or "no").lower(),
                    "exit_code": state.get("ExitCode"),
                }

                if stats:
                    cpu_percent = calculate_cpu_percent(stats)
                    memory_usage = stats["memory_stats"].get("usage", 0)
                    info["cpu"] = cpu_percent
                    info["memory"] = memory_usage

                container_list.append(info)

            except Exception as e:
                logger.warning("Failed to get stats for container %s: %s", container.name, e)
                container_list.append({
                    "id": container.short_id,
                    "name": container.name,
                    "status": container.status,
                })

        return container_list

    except DockerException as e:
        logger.error("Failed to list containers: %s", e)
        return []


def calculate_cpu_percent(stats: Dict) -> float:
    """Calculate CPU percentage from Docker stats."""
    try:
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                   stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"]["system_cpu_usage"] - \
                      stats["precpu_stats"]["system_cpu_usage"]

        if system_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * 100.0
            return round(cpu_percent, 2)
    except (KeyError, ZeroDivisionError):
        pass

    return 0.0


def get_container(name_or_id: str):
    """Get a container by name or ID."""
    if not DOCKER_AVAILABLE:
        raise ImportError("Docker SDK not installed")

    try:
        client = get_docker_client()
        return client.containers.get(name_or_id)
    except NotFound:
        raise ValueError(f"Container '{name_or_id}' not found")
    except DockerException as e:
        logger.error("Failed to get container %s: %s", name_or_id, e)
        raise


def restart_container(name_or_id: str) -> bool:
    """Restart a Docker container."""
    try:
        container = get_container(name_or_id)
        container.restart(timeout=10)
        logger.info("Restarted container %s", name_or_id)
        return True

    except Exception as e:
        logger.error("Failed to restart container %s: %s", name_or_id, e)
        raise


def stop_container(name_or_id: str) -> bool:
    """Stop a Docker container."""
    try:
        container = get_container(name_or_id)
        container.stop(timeout=10)
        logger.info("Stopped container %s", name_or_id)
        return True

    except Exception as e:
        logger.error("Failed to stop container %s: %s", name_or_id, e)
        raise


def start_container(name_or_id: str) -> bool:
    """Start a Docker container."""
    try:
        container = get_container(name_or_id)
        container.start()
        logger.info("Started container %s", name_or_id)
        return True

    except Exception as e:
        logger.error("Failed to start container %s: %s", name_or_id, e)
        raise


def pause_container(name_or_id: str) -> bool:
    """Pause a running Docker container."""
    try:
        container = get_container(name_or_id)
        container.pause()
        logger.info("Paused container %s", name_or_id)
        return True
    except Exception as e:
        logger.error("Failed to pause container %s: %s", name_or_id, e)
        raise


def unpause_container(name_or_id: str) -> bool:
    """Unpause a paused Docker container."""
    try:
        container = get_container(name_or_id)
        container.unpause()
        logger.info("Unpaused container %s", name_or_id)
        return True
    except Exception as e:
        logger.error("Failed to unpause container %s: %s", name_or_id, e)
        raise


def get_container_status(name_or_id: str) -> Optional[str]:
    """Return Docker status string (running, paused, exited, …) or None if missing."""
    try:
        container = get_container(name_or_id)
        return (container.status or "").lower()
    except ValueError:
        return None
    except Exception as e:
        logger.warning("get_container_status %s: %s", name_or_id, e)
        return None


def get_container_logs(name_or_id: str, lines: int = 50) -> str:
    """Get logs from a Docker container."""
    try:
        from services.readonly.constants import MAX_DOCKER_HOST_LOG_LINES

        lines = max(1, min(int(lines), MAX_DOCKER_HOST_LOG_LINES))
        container = get_container(name_or_id)
        logs = container.logs(tail=lines, timestamps=True).decode("utf-8", errors="replace")
        return logs

    except Exception as e:
        logger.error("Failed to get logs for container %s: %s", name_or_id, e)
        raise


def detect_unhealthy_containers() -> List[Dict[str, Any]]:
    """Detect unhealthy or crashed containers (no per-container stats)."""
    try:
        all_containers = list_containers(all_containers=True, include_stats=False)

        unhealthy = []
        for container in all_containers:
            status = container.get("status", "").lower()
            state = container.get("state", {})

            if status in ["exited", "dead", "restarting"]:
                unhealthy.append(container)
            elif state.get("Health", {}).get("Status") == "unhealthy":
                unhealthy.append(container)

        return unhealthy

    except Exception as e:
        logger.error("Failed to detect unhealthy containers: %s", e)
        return []


def get_container_stats_summary(name_or_id: str) -> Dict[str, Any]:
    """Get detailed stats for a specific container."""
    try:
        container = get_container(name_or_id)

        if container.status != "running":
            return {"status": container.status, "running": False}

        stats = container.stats(stream=False)

        cpu_percent = calculate_cpu_percent(stats)
        memory_usage = stats["memory_stats"].get("usage", 0)
        memory_limit = stats["memory_stats"].get("limit", 0)
        memory_percent = (memory_usage / memory_limit * 100) if memory_limit > 0 else 0

        networks = stats.get("networks", {})
        total_rx = sum(net.get("rx_bytes", 0) for net in networks.values())
        total_tx = sum(net.get("tx_bytes", 0) for net in networks.values())

        return {
            "status": container.status,
            "running": True,
            "cpu_percent": cpu_percent,
            "memory_usage": memory_usage,
            "memory_limit": memory_limit,
            "memory_percent": memory_percent,
            "network_rx": total_rx,
            "network_tx": total_tx,
        }

    except Exception as e:
        logger.error("Failed to get container stats: %s", e)
        return {"error": str(e)}
