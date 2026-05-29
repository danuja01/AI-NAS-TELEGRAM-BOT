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


def test_parse_container_lists_from_config():
    import config
    assert "affine" in config.RESOURCE_PAUSE_CONTAINERS
    assert "jellyfin" in config.RESOURCE_STOP_CONTAINERS
    assert "immich" in config.RESOURCE_CRITICAL_CONTAINERS
    assert "immich" not in config.RESOURCE_PAUSE_CONTAINERS


def test_should_skip_immich_under_ml_pressure():
    from datetime import datetime, timezone
    from monitoring.resource_orchestrator import ResourceSnapshot, should_skip_mitigation
    snap = ResourceSnapshot(
        ram_percent=90,
        cpu_percent=50,
        immich_ml_cpu=60,
        immich_ml_memory=500 * 1024 * 1024,
        collected_at=datetime.now(timezone.utc),
    )
    assert snap.immich_driven_pressure is True
    assert should_skip_mitigation("immich", snap) is True
    assert should_skip_mitigation("jellyfin", snap) is False
