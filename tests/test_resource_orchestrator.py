"""Unit tests for resource orchestrator pure logic."""

from datetime import datetime, timezone

import config
from monitoring.resource_orchestrator import (
    ResourceSnapshot,
    recovery_conditions_met,
    should_enter_mitigation,
    should_escalate_stage2,
)


def _snap(ram: float, cpu: float, ml_cpu: float = 0.0) -> ResourceSnapshot:
    return ResourceSnapshot(
        ram_percent=ram,
        cpu_percent=cpu,
        immich_ml_cpu=ml_cpu,
        immich_ml_memory=0.0,
        collected_at=datetime.now(timezone.utc),
    )


def test_should_enter_mitigation_ram():
    assert should_enter_mitigation(_snap(90, 10)) is True
    assert should_enter_mitigation(_snap(50, 10)) is False


def test_should_enter_mitigation_cpu():
    assert should_enter_mitigation(_snap(50, 90)) is True


def test_should_enter_mitigation_immich_boost():
    hi = config.RESOURCE_RAM_HIGH_PERCENT
    boost = config.RESOURCE_IMMICH_ML_CPU_BOOST_PERCENT
    assert should_enter_mitigation(_snap(hi - 5, 50, ml_cpu=boost)) is True


def test_should_escalate_stage2():
    assert should_escalate_stage2(_snap(92, 50)) is True
    assert should_escalate_stage2(_snap(80, 80)) is False


def test_recovery_conditions():
    assert recovery_conditions_met(_snap(60, 40)) is True
    assert recovery_conditions_met(_snap(75, 40)) is False
    assert recovery_conditions_met(_snap(60, 55)) is False
