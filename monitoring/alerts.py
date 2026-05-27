"""
Alert threshold definitions and logic.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import config

logger = logging.getLogger(__name__)


def check_storage_low_disk_alerts(disk_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Alert when any mount exceeds STORAGE_LOW_DISK_PERCENT used."""
    alerts = []
    threshold = getattr(config, "STORAGE_LOW_DISK_PERCENT", 90)
    for disk in disk_stats:
        percent = float(disk.get("percent", 0))
        mountpoint = disk.get("mountpoint", "Unknown")
        if percent >= threshold:
            alerts.append({
                "type": "disk",
                "severity": "critical" if percent >= 95 else "warning",
                "message": (
                    f"Disk almost full on {mountpoint}: {percent:.1f}% used "
                    f"(threshold {threshold}%). Try /dscan and /dclean"
                ),
            })
    return alerts


def check_disk_alerts(disk_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check disk space alerts."""
    alerts = []

    for disk in disk_stats:
        percent = disk.get('percent', 0)
        mountpoint = disk.get('mountpoint', 'Unknown')

        if percent > (100 - config.ALERT_THRESHOLDS['disk_space_percent']):
            severity = 'critical' if percent > 95 else 'warning'
            alerts.append({
                'type': 'disk',
                'severity': severity,
                'message': f"Low disk space on {mountpoint}: {percent:.1f}% used"
            })

    return alerts


def check_cpu_alerts(cpu_percent: float) -> List[Dict[str, Any]]:
    """Check CPU usage alerts."""
    alerts = []

    if cpu_percent > config.ALERT_THRESHOLDS['cpu_percent']:
        severity = 'critical' if cpu_percent > 95 else 'warning'
        alerts.append({
            'type': 'cpu',
            'severity': severity,
            'message': f"High CPU usage: {cpu_percent:.1f}%"
        })

    return alerts


def check_memory_alerts(memory_percent: float) -> List[Dict[str, Any]]:
    """Check memory usage alerts."""
    alerts = []

    if memory_percent > config.ALERT_THRESHOLDS['memory_percent']:
        alerts.append({
            'type': 'memory',
            'severity': 'critical',
            'message': f"Critical memory usage: {memory_percent:.1f}%"
        })

    return alerts


def check_temperature_alerts(temps: Dict[str, float]) -> List[Dict[str, Any]]:
    """Check temperature alerts."""
    alerts = []

    for sensor, temp in temps.items():
        if config.ignore_temperature_sensor_for_alerts(sensor):
            continue
        if temp and temp > config.ALERT_THRESHOLDS['temperature_celsius']:
            severity = 'critical' if temp > 80 else 'warning'
            alerts.append({
                'type': 'temperature',
                'severity': severity,
                'message': f"High temperature on {sensor}: {temp:.1f}°C"
            })

    return alerts


def _normalize_container_name(name: str) -> str:
    return (name or "unknown").lstrip("/").lower()


def _container_is_running(status: str) -> bool:
    s = (status or "").lower()
    return s == "running" or "up" in s.split()


def _container_is_stopped(status: str) -> bool:
    s = (status or "").lower()
    return "exited" in s or "dead" in s


def _intentional_stop_container(container: Dict[str, Any]) -> bool:
    """
    Exited container the operator likely stopped on purpose (Docker restart policy semantics).
    """
    if not config.MONITOR_DOCKER_SKIP_INTENTIONAL_STOP:
        return False
    policy = (container.get("restart_policy") or "no").lower()
    if policy in ("no", "", "unless-stopped"):
        return True
    if policy == "on-failure":
        try:
            code = container.get("exit_code")
            if code is not None and int(code) == 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def check_docker_alerts(
    containers: List[Dict[str, Any]],
    previous_running: Optional[Dict[str, bool]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    """
    Check Docker container alerts.

    Default mode ``unexpected_exit``: only alert when a container was running on the
    previous health check and is now exited/dead (not for containers already stopped).

    Returns (alerts, new_running_state) for the next check.
    """
    alerts: List[Dict[str, Any]] = []
    new_running: Dict[str, bool] = {}
    prev = previous_running if previous_running is not None else {}
    mode = getattr(config, "MONITOR_DOCKER_ALERT_MODE", "unexpected_exit")

    for container in containers:
        name = container.get("name", "Unknown")
        key = _normalize_container_name(name)
        status = (container.get("status") or "").lower()

        if _container_is_running(status):
            new_running[key] = True
            continue

        new_running[key] = False

        if not _container_is_stopped(status):
            continue

        if config.docker_container_ignored_for_alerts(name):
            continue

        if _intentional_stop_container(container):
            continue

        if mode == "unexpected_exit":
            was_running = prev.get(key)
            if was_running is not True:
                continue
        elif mode != "all_exited":
            logger.warning("Unknown MONITOR_DOCKER_ALERT_MODE=%s", mode)
            continue

        policy = container.get("restart_policy") or "unknown"
        exit_code = container.get("exit_code")
        extra = ""
        if exit_code is not None:
            extra = f", exit {exit_code}"
        alerts.append({
            "type": "docker",
            "severity": "warning",
            "message": (
                f"Container '{name}' stopped unexpectedly: {status}"
                f"{extra} (restart: {policy})"
            ),
        })

    return alerts, new_running


def check_docker_unhealthy_alerts(
    containers: List[Dict[str, Any]],
    previous_unhealthy: Optional[Dict[str, bool]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
    """
    Alert on Docker HEALTHCHECK unhealthy or restarting containers.
    Only notifies on transition into unhealthy state (not every tick).
    """
    alerts: List[Dict[str, Any]] = []
    new_state: Dict[str, bool] = {}
    prev = previous_unhealthy if previous_unhealthy is not None else {}

    for container in containers:
        name = container.get("name", "Unknown")
        key = _normalize_container_name(name)
        status = (container.get("status") or "").lower()
        state = container.get("state") or {}
        health = (state.get("Health") or {}).get("Status", "").lower()

        is_bad = status == "restarting" or health == "unhealthy"
        new_state[key] = is_bad

        if not is_bad:
            continue
        if config.docker_container_ignored_for_alerts(name):
            continue
        if prev.get(key) is True:
            continue

        detail = f"status={status}"
        if health == "unhealthy":
            detail = "Docker healthcheck: unhealthy"
        elif status == "restarting":
            detail = "container restarting"
        alerts.append({
            "type": "docker",
            "severity": "critical" if health == "unhealthy" else "warning",
            "message": f"Container '{name}' unhealthy: {detail}",
            "container_name": name.lstrip("/"),
        })

    return alerts, new_state


def check_smart_alerts(drives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check SMART drive health alerts (thresholds; sector deltas are separate)."""
    alerts = []

    for drive in drives:
        device = drive.get('device', 'Unknown')
        health = drive.get('health', 'UNKNOWN')

        if health == 'FAILED':
            alerts.append({
                'type': 'smart',
                'severity': 'critical',
                'message': f"SMART health check FAILED for {device}!"
            })

    return alerts


def check_smart_delta_alerts(
    drives: List[Dict[str, Any]],
    previous: Dict[str, Dict[str, int]],
) -> List[Dict[str, Any]]:
    """Alert when reallocated or pending sector counts increase vs last snapshot."""
    alerts: List[Dict[str, Any]] = []
    for drive in drives or []:
        device = drive.get("device") or ""
        if not device:
            continue
        old = previous.get(device, {"reallocated": 0, "pending": 0})
        try:
            new_r = int(drive.get("reallocated_sectors") or 0)
            new_p = int(drive.get("pending_sectors") or 0)
        except (TypeError, ValueError):
            continue
        if new_r > old["reallocated"]:
            alerts.append(
                {
                    "type": "smart",
                    "severity": "critical",
                    "message": (
                        f"{device}: reallocated sectors increased "
                        f"{old['reallocated']} → {new_r}"
                    ),
                }
            )
        if new_p > old["pending"]:
            alerts.append(
                {
                    "type": "smart",
                    "severity": "warning",
                    "message": (
                        f"{device}: pending sectors increased "
                        f"{old['pending']} → {new_p}"
                    ),
                }
            )
    return alerts
