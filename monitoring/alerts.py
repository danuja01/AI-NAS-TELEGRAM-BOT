"""
Alert threshold definitions and logic.
"""

import logging
from typing import List, Dict, Any

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


def check_docker_alerts(containers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check Docker container alerts."""
    alerts = []
    
    for container in containers:
        status = container.get('status', '').lower()
        name = container.get('name', 'Unknown')
        
        if 'exited' in status or 'dead' in status:
            alerts.append({
                'type': 'docker',
                'severity': 'warning',
                'message': f"Container '{name}' is not running: {status}"
            })
    
    return alerts


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
