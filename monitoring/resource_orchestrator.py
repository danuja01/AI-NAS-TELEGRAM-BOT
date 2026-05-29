"""
Resource-aware container orchestrator: pause/stop low-priority workloads under pressure,
restore when resources recover. Integrated with Telegram alerts.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Protocol

import psutil
from telegram import Bot

import config
from database.memory import save_conversation
from services import resource_orchestrator_service as ros

logger = logging.getLogger(__name__)


class WorkloadDetector(Protocol):
    """Future hook: register workload-specific pressure detectors (Tdarr, Jellyfin, GPU)."""

    def workload_name(self) -> str:
        ...

    def collect_metrics(self) -> Dict[str, float]:
        ...

    def is_pressure_source(self, snapshot: "ResourceSnapshot") -> bool:
        ...


@dataclass(frozen=True)
class ResourceSnapshot:
    ram_percent: float
    cpu_percent: float
    immich_ml_cpu: float
    immich_ml_memory: float
    collected_at: datetime

    @property
    def immich_ml_pressure(self) -> bool:
        return self.immich_ml_cpu >= config.RESOURCE_IMMICH_ML_CPU_BOOST_PERCENT


@dataclass
class MitigationResult:
    paused: List[str]
    stopped: List[str]
    cause: str
    stage: int


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def collect_snapshot() -> ResourceSnapshot:
    ram = float(psutil.virtual_memory().percent)
    cpu = float(psutil.cpu_percent(interval=0.5))
    ml = ros.get_immich_ml_stats()
    return ResourceSnapshot(
        ram_percent=ram,
        cpu_percent=cpu,
        immich_ml_cpu=ml["cpu_percent"],
        immich_ml_memory=ml["memory_bytes"],
        collected_at=datetime.now(timezone.utc),
    )


def should_enter_mitigation(snap: ResourceSnapshot) -> bool:
    ram_hi = config.RESOURCE_RAM_HIGH_PERCENT
    cpu_hi = config.RESOURCE_CPU_HIGH_PERCENT
    if snap.ram_percent >= ram_hi or snap.cpu_percent >= cpu_hi:
        return True
    if snap.immich_ml_pressure and (
        snap.ram_percent >= ram_hi - 10 or snap.cpu_percent >= cpu_hi - 10
    ):
        return True
    return False


def should_escalate_stage2(snap: ResourceSnapshot) -> bool:
    return (
        snap.ram_percent >= config.RESOURCE_RAM_STAGE2_PERCENT
        or snap.cpu_percent >= config.RESOURCE_CPU_STAGE2_PERCENT
    )


def recovery_conditions_met(snap: ResourceSnapshot) -> bool:
    return (
        snap.ram_percent < config.RESOURCE_RAM_RECOVER_PERCENT
        and snap.cpu_percent < config.RESOURCE_CPU_RECOVER_PERCENT
    )


def mitigation_cause(snap: ResourceSnapshot) -> str:
    if snap.immich_ml_pressure:
        return ros.IMMICH_ML_CONTAINER
    if snap.ram_percent >= config.RESOURCE_RAM_HIGH_PERCENT:
        return "high_memory"
    if snap.cpu_percent >= config.RESOURCE_CPU_HIGH_PERCENT:
        return "high_cpu"
    return "resource_pressure"


class ResourceOrchestrator:
    """Coordinates detection, mitigation, recovery, and notifications."""

    def __init__(
        self,
        *,
        state_loader=ros.load_state,
        state_saver=ros.save_state,
        snapshot_collector=collect_snapshot,
    ):
        self._load_state = state_loader
        self._save_state = state_saver
        self._collect_snapshot = snapshot_collector
        self._workload_detectors: List[WorkloadDetector] = []

    def register_workload_detector(self, detector: WorkloadDetector) -> None:
        self._workload_detectors.append(detector)

    def is_enabled(self) -> bool:
        return self._load_state().enabled

    def set_enabled(self, enabled: bool) -> None:
        state = self._load_state()
        state.enabled = enabled
        self._save_state(state)

    def get_status_dict(self) -> Dict[str, Any]:
        state = self._load_state()
        snap = self._collect_snapshot()
        mode = "idle"
        if state.mitigation_active:
            mode = "mitigating"
        elif state.paused_by_orchestrator or state.stopped_by_orchestrator:
            mode = "awaiting_recovery"
        return {
            "enabled": state.enabled,
            "mode": mode,
            "paused": list(state.paused_by_orchestrator),
            "stopped": list(state.stopped_by_orchestrator),
            "last_trigger": state.last_trigger,
            "last_recovery": state.last_recovery,
            "ram_percent": round(snap.ram_percent, 1),
            "cpu_percent": round(snap.cpu_percent, 1),
            "immich_ml_cpu": round(snap.immich_ml_cpu, 1),
            "pause_candidates": list(ros.pause_containers()),
            "stop_candidates": list(ros.stop_containers()),
            "thresholds": {
                "ram_high": config.RESOURCE_RAM_HIGH_PERCENT,
                "ram_recover": config.RESOURCE_RAM_RECOVER_PERCENT,
                "cpu_high": config.RESOURCE_CPU_HIGH_PERCENT,
                "cpu_recover": config.RESOURCE_CPU_RECOVER_PERCENT,
                "recovery_delay_minutes": config.RESOURCE_RECOVERY_DELAY_MINUTES,
            },
        }

    def run_stage1(self, snap: ResourceSnapshot, *, manual: bool = False) -> MitigationResult:
        state = self._load_state()
        statuses = ros.list_known_statuses()
        docker_names = set(statuses.keys())
        paused: List[str] = []

        for logical in ros.pause_containers():
            if logical in state.paused_by_orchestrator:
                continue
            actual = ros.resolve_container_name(docker_names, logical) or logical
            if ros.safe_pause(actual, statuses):
                paused.append(logical)
                state.paused_by_orchestrator.append(logical)
                statuses[logical] = "paused"

        state.mitigation_active = True
        state.stage1_at = ros.utc_now_iso()
        state.recovery_stable_since = ""
        # always record trigger
        state.last_trigger = state.stage1_at
        self._save_state(state)

        return MitigationResult(
            paused=paused,
            stopped=[],
            cause=mitigation_cause(snap),
            stage=1,
        )

    def run_stage2(self, snap: ResourceSnapshot) -> MitigationResult:
        state = self._load_state()
        statuses = ros.list_known_statuses()
        docker_names = set(statuses.keys())
        stopped: List[str] = []

        for logical in ros.stop_containers():
            if logical in state.stopped_by_orchestrator:
                continue
            actual = ros.resolve_container_name(docker_names, logical) or logical
            if ros.safe_stop(actual, statuses):
                stopped.append(logical)
                state.stopped_by_orchestrator.append(logical)
                statuses[logical] = "exited"

        self._save_state(state)
        return MitigationResult(
            paused=[],
            stopped=stopped,
            cause=mitigation_cause(snap),
            stage=2,
        )

    async def restore_all(self, snap: ResourceSnapshot) -> List[str]:
        state = self._load_state()
        restored: List[str] = []
        gap = config.RESOURCE_RESTORE_GAP_SECONDS

        for logical in reversed(state.stopped_by_orchestrator):
            statuses = ros.list_known_statuses()
            actual = ros.resolve_container_name(set(statuses.keys()), logical) or logical
            if ros.safe_start(actual, statuses):
                restored.append(logical)
            await asyncio.sleep(gap)

        for logical in reversed(state.paused_by_orchestrator):
            statuses = ros.list_known_statuses()
            actual = ros.resolve_container_name(set(statuses.keys()), logical) or logical
            if ros.safe_unpause(actual, statuses):
                restored.append(logical)
            await asyncio.sleep(gap)

        state.paused_by_orchestrator = []
        state.stopped_by_orchestrator = []
        state.mitigation_active = False
        state.stage1_at = ""
        state.recovery_stable_since = ""
        state.last_recovery = ros.utc_now_iso()
        self._save_state(state)
        return restored

    async def tick(self, bot: Optional[Bot] = None) -> None:
        state = self._load_state()
        if not state.enabled:
            return

        snap = self._collect_snapshot()

        if state.mitigation_active or state.paused_by_orchestrator or state.stopped_by_orchestrator:
            await self._tick_recovery(bot, snap)
            state = self._load_state()
            if state.mitigation_active:
                await self._tick_stage2(bot, snap)
            return

        if should_enter_mitigation(snap):
            result = self.run_stage1(snap)
            if bot:
                await _notify_stage1(bot, snap, result)

    async def _tick_stage2(self, bot: Optional[Bot], snap: ResourceSnapshot) -> None:
        state = self._load_state()
        if not state.mitigation_active or not state.stage1_at:
            return
        stage1_at = _parse_iso(state.stage1_at)
        if not stage1_at:
            return
        elapsed = datetime.now(timezone.utc) - stage1_at
        if elapsed < timedelta(seconds=config.RESOURCE_STAGE2_DELAY_SECONDS):
            return
        if not should_escalate_stage2(snap):
            return
        if state.stopped_by_orchestrator:
            return
        result = self.run_stage2(snap)
        if result.stopped and bot:
            await _notify_stage2(bot, snap, result)

    async def _tick_recovery(self, bot: Optional[Bot], snap: ResourceSnapshot) -> None:
        state = self._load_state()
        if not (
            state.paused_by_orchestrator
            or state.stopped_by_orchestrator
            or state.mitigation_active
        ):
            return

        if not recovery_conditions_met(snap):
            if state.recovery_stable_since:
                state.recovery_stable_since = ""
                self._save_state(state)
            return

        now = datetime.now(timezone.utc)
        if not state.recovery_stable_since:
            state.recovery_stable_since = ros.utc_now_iso()
            self._save_state(state)
            return

        stable_since = _parse_iso(state.recovery_stable_since)
        if not stable_since:
            return
        delay = timedelta(minutes=config.RESOURCE_RECOVERY_DELAY_MINUTES)
        if now - stable_since < delay:
            return

        restored = await self.restore_all(snap)
        if bot and restored:
            await _notify_recovery(bot, snap, restored)

    async def mitigate_now(self, bot: Optional[Bot] = None) -> MitigationResult:
        snap = self._collect_snapshot()
        r1 = self.run_stage1(snap, manual=True)
        if bot:
            await _notify_stage1(bot, snap, r1)
        snap2 = self._collect_snapshot()
        r2 = MitigationResult(paused=[], stopped=[], cause=r1.cause, stage=1)
        if should_escalate_stage2(snap2):
            r2 = self.run_stage2(snap2)
            if bot:
                await _notify_stage2(bot, snap2, r2)
        return MitigationResult(
            paused=r1.paused,
            stopped=r2.stopped,
            cause=r1.cause,
            stage=2 if r2.stopped else 1,
        )

    async def restore_now(self, bot: Optional[Bot] = None) -> List[str]:
        snap = self._collect_snapshot()
        restored = await self.restore_all(snap)
        if bot and restored:
            await _notify_recovery(bot, snap, restored)
        return restored


_orchestrator: Optional[ResourceOrchestrator] = None


def get_orchestrator() -> ResourceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ResourceOrchestrator()
    return _orchestrator


async def resource_orchestrator_tick(bot: Bot) -> None:
    """Scheduler entry point."""
    if not config.RESOURCE_ORCHESTRATOR_ENABLED and not get_orchestrator().is_enabled():
        return
    try:
        await get_orchestrator().tick(bot)
    except Exception as e:
        logger.error("Resource orchestrator tick failed: %s", e, exc_info=True)


async def _broadcast(bot: Bot, text: str, *, source: str) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.error("Orchestrator notify failed uid=%s: %s", uid, e)
            continue
        try:
            await save_conversation(
                uid,
                "assistant",
                f"[Resource Orchestrator {source}]",
                command_output=text[:12000],
                metadata={"source": source, "subsystem": "resource_orchestrator"},
            )
        except Exception as e:
            logger.warning("Orchestrator persist conversation uid=%s: %s", uid, e)


async def _notify_stage1(bot: Bot, snap: ResourceSnapshot, result: MitigationResult) -> None:
    lines = [
        "⚠ Resource Orchestrator Activated",
        "",
        f"RAM: {snap.ram_percent:.0f}%",
        f"CPU: {snap.cpu_percent:.0f}%",
        "",
        "Cause:",
        result.cause,
        "",
        "Paused:",
    ]
    for name in result.paused:
        lines.append(f"- {name}")
    if not result.paused:
        lines.append("- (none)")
    await _broadcast(bot, "\n".join(lines), source="activated")


async def _notify_stage2(bot: Bot, snap: ResourceSnapshot, result: MitigationResult) -> None:
    lines = [
        "⚠ Resource Pressure Critical",
        "",
        f"RAM: {snap.ram_percent:.0f}%",
        f"CPU: {snap.cpu_percent:.0f}%",
        "",
        "Stopped:",
    ]
    for name in result.stopped:
        lines.append(f"- {name}")
    if not result.stopped:
        lines.append("- (none)")
    await _broadcast(bot, "\n".join(lines), source="critical")


async def _notify_recovery(bot: Bot, snap: ResourceSnapshot, restored: List[str]) -> None:
    lines = [
        "✅ Resource Recovery Complete",
        "",
        f"RAM: {snap.ram_percent:.0f}%",
        f"CPU: {snap.cpu_percent:.0f}%",
        "",
        "Restored:",
    ]
    for name in restored:
        lines.append(f"- {name}")
    await _broadcast(bot, "\n".join(lines), source="recovery")
