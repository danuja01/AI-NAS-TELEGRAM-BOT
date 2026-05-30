"""Unit tests for resource orchestrator pure logic."""

from datetime import datetime, timezone

import config
from monitoring.resource_orchestrator import (
    ResourceSnapshot,
    recovery_conditions_met,
    should_enter_mitigation,
    should_escalate_stage2,
    should_skip_mitigation,
)
from services.resource_orchestrator_service import (
    ContainerUsage,
    detect_heavy_containers,
)


def _snap(
    ram: float,
    cpu: float,
    heavy: frozenset[str] | None = None,
) -> ResourceSnapshot:
    return ResourceSnapshot(
        ram_percent=ram,
        cpu_percent=cpu,
        heavy_containers=heavy or frozenset(),
        container_usages=(),
        collected_at=datetime.now(timezone.utc),
    )


def test_should_enter_mitigation_ram():
    assert should_enter_mitigation(_snap(90, 10)) is True
    assert should_enter_mitigation(_snap(50, 10)) is False


def test_should_enter_mitigation_cpu():
    assert should_enter_mitigation(_snap(50, 90)) is True


def test_should_enter_mitigation_heavy_workload_boost():
    hi = config.RESOURCE_RAM_HIGH_PERCENT
    assert should_enter_mitigation(_snap(hi - 5, 50, heavy=frozenset({"tdarr"}))) is True


def test_should_escalate_stage2():
    assert should_escalate_stage2(_snap(92, 50)) is True
    assert should_escalate_stage2(_snap(80, 80)) is False


def test_recovery_conditions():
    assert recovery_conditions_met(_snap(60, 40)) is True
    assert recovery_conditions_met(_snap(75, 40)) is False
    assert recovery_conditions_met(_snap(60, 55)) is False


def test_parse_container_lists_from_config():
    assert "affine" in config.RESOURCE_PAUSE_CONTAINERS
    assert "jellyfin" in config.RESOURCE_STOP_CONTAINERS
    assert "tailscale" in config.RESOURCE_CRITICAL_CONTAINERS


def test_should_skip_heavy_container():
    snap = _snap(90, 50, heavy=frozenset({"immich_machine_learning", "tdarr"}))
    assert should_skip_mitigation("immich_machine_learning", snap) is True
    assert should_skip_mitigation("jellyfin", snap) is False


def test_detect_heavy_containers_by_ram():
    usages = [
        ContainerUsage("immich_machine_learning", 30.0, 900 * 1024 * 1024, 11.0),
        ContainerUsage("jellyfin", 2.0, 100 * 1024 * 1024, 1.2),
    ]
    heavy = detect_heavy_containers(usages, system_ram_percent=88, system_cpu_percent=40)
    assert "immich_machine_learning" in heavy
    assert "jellyfin" not in heavy
