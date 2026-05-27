"""Multi-stage alert escalation based on consecutive failures."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import config


def escalation_level(monitor: Dict[str, Any]) -> Tuple[str, int]:
    """
    Returns (severity, stage) for current consecutive_failures.
    Stages from UPTIME_ESCALATION_THRESHOLDS e.g. [1, 3, 10].
    """
    failures = int(monitor.get("consecutive_failures") or 0)
    thresholds = config.UPTIME_ESCALATION_THRESHOLDS
    stage = 0
    for i, th in enumerate(thresholds):
        if failures >= th:
            stage = i
    if stage >= 2:
        severity = "critical"
    elif stage == 1:
        severity = "warning"
    else:
        severity = "warning"
    return severity, stage


def should_notify_down(monitor: Dict[str, Any], prev_status: str) -> bool:
    """
    Notify on first transition to down, and at each escalation threshold crossing.
    """
    if prev_status != "down":
        return True
    failures = int(monitor.get("consecutive_failures") or 0)
    return failures in config.UPTIME_ESCALATION_THRESHOLDS
