"""
CrowdSec background monitor: Telegram alerts, deduplication, daily security report.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from telegram import Bot
from telegram.constants import ParseMode

import config
from database.memory import save_conversation
from services.crowdsec_client import (
    fetch_alerts,
    fetch_decisions,
    gather_crowdsec_snapshot,
    infer_target_service,
    normalize_alert,
    normalize_decision,
)

logger = logging.getLogger(__name__)

# Dedup: key -> last sent time
_last_alert_sent: Dict[str, datetime] = {}
# Track seen alert/decision ids across polls
_seen_alert_ids: Set[str] = set()
_seen_decision_keys: Set[str] = set()
# Rolling window for spike detection (ip -> count in window)
_ip_window_counts: Dict[str, int] = {}
_window_started: Optional[datetime] = None
_baseline_complete: bool = False

_SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

_LOW_NOISE = (
    "community",
    "blocklist",
    "capi",
    "fire-list",
    "fire list",
)

_HIGH_PATTERNS = (
    "exploit",
    "cve",
    "rce",
    "sqli",
    "lfi",
    "rfi",
    "shell",
    "bruteforce",
    "brute-force",
    "brute_force",
    "ssh-bf",
    "ssh:bruteforce",
)

_MEDIUM_PATTERNS = (
    "scan",
    "crawl",
    "probe",
    "http",
    "404",
    "wordpress",
    "nikto",
    "dirb",
)


def classify_severity(
    scenario: str,
    target: str,
    *,
    events_count: int = 0,
    ip_repeat_count: int = 1,
    is_new_block: bool = False,
) -> str:
    """Return HIGH, MEDIUM, or LOW for an incident."""
    s = (scenario or "").lower()
    t = (target or "").lower()

    if any(p in s for p in _HIGH_PATTERNS):
        if "ssh" in s or t == "ssh":
            return "HIGH"
        if events_count >= 5 or ip_repeat_count >= 3:
            return "HIGH"
        if "exploit" in s or "cve" in s:
            return "HIGH"

    if t in ("ssh", "filebrowser", "portainer"):
        if any(x in s for x in ("brute", "auth", "login", "scan", "exploit", "bf")):
            return "HIGH"
        if is_new_block:
            return "HIGH"

    if ip_repeat_count >= 4:
        return "HIGH"

    if any(p in s for p in _MEDIUM_PATTERNS):
        return "MEDIUM"

    if any(p in s for p in _LOW_NOISE):
        if events_count <= 1 and ip_repeat_count <= 1:
            return "LOW"

    if events_count <= 1 and ip_repeat_count <= 1:
        return "LOW"

    return "MEDIUM"


def _reason_text(scenario: str, target: str, severity: str, events_count: int) -> str:
    s = (scenario or "").lower()
    if "ssh" in s and ("brute" in s or "bf" in s):
        return (
            "Multiple failed SSH login attempts detected and blocked automatically."
        )
    if "exploit" in s or "cve" in s:
        return "Exploit or vulnerability probing detected; CrowdSec blocked the source."
    if "brute" in s or "bf" in s:
        return f"Brute-force activity against {target} was detected and blocked."
    if "scan" in s or "crawl" in s:
        return f"Scanning or crawler activity targeting {target} was blocked."
    if severity == "LOW":
        return "Low-risk scan or community blocklist match; no action required unless volume spikes."
    return f"Suspicious activity against {target} was detected and blocked ({events_count} events)."


def format_telegram_alert(
    scenario: str,
    source_ip: str,
    country: str,
    target: str,
    severity: str,
    reason: str,
) -> str:
    """User-specified CrowdSec alert layout (plain text)."""
    return (
        "🚨 CrowdSec Alert\n\n"
        f"Type: {scenario}\n"
        f"IP: {source_ip or '?'}\n"
        f"Country: {country or '?'}\n"
        f"Target: {target}\n"
        "Action: Blocked\n"
        f"Severity: {severity}\n\n"
        "Reason:\n"
        f"{reason}"
    )


def format_daily_report(stats: Dict[str, Any], incidents: List[str]) -> str:
    if not incidents:
        return "✅ No significant security incidents detected."

    lines = [
        "🛡 NAS Security Daily Report",
        "",
        f"Blocked IPs: {stats.get('blocked_ips', 0)}",
        f"Top attack type: {stats.get('top_scenario', '—')}",
        f"Top attacking country: {stats.get('top_country', '—')}",
        f"Most targeted service: {stats.get('top_target', '—')}",
        "",
        "Recent incidents:",
    ]
    for inc in incidents[:5]:
        lines.append(f"* {inc}")
    lines.extend(
        [
            "",
            "Overall status:",
            stats.get("overall_status", "No successful intrusions detected."),
        ]
    )
    if stats.get("trend_note"):
        lines.extend(["", stats["trend_note"]])
    return "\n".join(lines)


def _alert_id_key(alert: Dict[str, Any]) -> str:
    aid = alert.get("id")
    if aid is not None:
        return f"alert:{aid}"
    return f"alert:{alert.get('scenario')}:{alert.get('source_ip')}"


def _decision_key(dec: Dict[str, Any]) -> str:
    did = dec.get("id")
    if did is not None:
        return f"dec:{did}"
    return f"dec:{dec.get('scenario')}:{dec.get('source_ip')}"


def _should_send_alert(dedup_key: str, severity: str) -> bool:
    now = datetime.now()
    last = _last_alert_sent.get(dedup_key)
    cooldown_min = max(5, int(getattr(config, "CROWDSEC_ALERT_COOLDOWN_MINUTES", 60)))
    if severity == "HIGH":
        cooldown_min = max(15, cooldown_min // 2)
    if last and (now - last) < timedelta(minutes=cooldown_min):
        return False
    return True


def _mark_sent(dedup_key: str) -> None:
    _last_alert_sent[dedup_key] = datetime.now()
    if len(_last_alert_sent) > 500:
        cutoff = datetime.now() - timedelta(hours=24)
        stale = [k for k, t in _last_alert_sent.items() if t < cutoff]
        for k in stale[:250]:
            _last_alert_sent.pop(k, None)


def _min_severity_rank(name: str) -> int:
    floor = (getattr(config, "CROWDSEC_ALERT_MIN_SEVERITY", "MEDIUM") or "MEDIUM").upper()
    return _SEVERITY_ORDER.get(floor, 1)


def _meets_floor(severity: str) -> bool:
    return _SEVERITY_ORDER.get(severity.upper(), 0) >= _min_severity_rank(severity)


def _bump_ip_window(ip: str) -> int:
    global _window_started
    now = datetime.now()
    window_min = max(5, int(getattr(config, "CROWDSEC_SPIKE_WINDOW_MINUTES", 15)))
    if _window_started is None or (now - _window_started) > timedelta(minutes=window_min):
        _ip_window_counts.clear()
        _window_started = now
    if ip:
        _ip_window_counts[ip] = _ip_window_counts.get(ip, 0) + 1
    return _ip_window_counts.get(ip, 0)


def _detect_spike(total_new: int) -> Optional[str]:
    threshold = max(3, int(getattr(config, "CROWDSEC_SPIKE_THRESHOLD", 8)))
    if total_new >= threshold:
        return (
            f"⚠️ Attack volume is elevated: {total_new} new events in the last check "
            f"(threshold {threshold}). Consider reviewing CrowdSec dashboards."
        )
    top_ip = max(_ip_window_counts.items(), key=lambda x: x[1], default=(None, 0))
    if top_ip[0] and top_ip[1] >= max(3, threshold // 2):
        return f"⚠️ Repeated activity from {top_ip[0]} ({top_ip[1]} events in the spike window)."
    return None


async def _broadcast_plain(bot: Bot, text: str, *, source: str) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(chat_id=uid, text=text)
        except Exception as e:
            logger.error("CrowdSec notify failed uid=%s: %s", uid, e)
            continue
        try:
            await save_conversation(
                uid,
                "assistant",
                f"[CrowdSec {source}]",
                command_output=text[:12000],
                metadata={"source": source, "subsystem": "crowdsec"},
            )
        except Exception as e:
            logger.warning("CrowdSec persist conversation uid=%s: %s", uid, e)


def _aggregate_key(norm: Dict[str, Any]) -> str:
    return f"{norm.get('scenario','')}:{norm.get('source_ip','')}"


async def poll_crowdsec_alerts(bot: Bot) -> None:
    """Poll alerts/decisions and send Telegram notifications for new meaningful events."""
    if not getattr(config, "CROWDSEC_MONITOR_ENABLED", False):
        return

    ok_a, raw_alerts, err_a = fetch_alerts()
    ok_d, raw_decisions, err_d = fetch_decisions()
    if not ok_a and not ok_d:
        logger.warning("CrowdSec poll failed: %s; %s", err_a, err_d)
        return

    new_items: List[Tuple[str, Dict[str, Any], bool]] = []

    for raw in raw_alerts or []:
        norm = normalize_alert(raw)
        key = _alert_id_key(norm)
        if key in _seen_alert_ids:
            continue
        _seen_alert_ids.add(key)
        new_items.append(("alert", norm, False))

    for raw in raw_decisions or []:
        norm = normalize_decision(raw)
        key = _decision_key(norm)
        if key in _seen_decision_keys:
            continue
        _seen_decision_keys.add(key)
        new_items.append(("decision", norm, True))

    if not new_items:
        return

    global _baseline_complete
    if not _baseline_complete:
        _baseline_complete = True
        logger.info(
            "CrowdSec baseline: seeded %s alerts, %s decisions (no notifications)",
            len(_seen_alert_ids),
            len(_seen_decision_keys),
        )
        return

    ip_counts: Counter[str] = Counter()
    for _, norm, _ in new_items:
        ip = norm.get("source_ip") or ""
        if ip:
            ip_counts[ip] += 1

    spike_note = _detect_spike(len(new_items))
    aggregated_sent: Set[str] = set()
    to_send: List[str] = []

    for kind, norm, is_decision in new_items:
        scenario = norm.get("scenario") or "unknown"
        ip = norm.get("source_ip") or "?"
        country = norm.get("country") or "?"
        target = norm.get("target") or infer_target_service(scenario, norm.get("raw") or {})
        events_count = int(norm.get("events_count") or 0)
        ip_repeat = ip_counts.get(ip, 1)
        window_count = _bump_ip_window(ip) if ip and ip != "?" else 0
        ip_repeat = max(ip_repeat, window_count)

        severity = classify_severity(
            scenario,
            target,
            events_count=events_count,
            ip_repeat_count=ip_repeat,
            is_new_block=is_decision,
        )

        if not _meets_floor(severity):
            continue

        agg = _aggregate_key(norm)
        if agg in aggregated_sent and severity != "HIGH":
            continue

        dedup_key = f"{agg}:{severity}"
        if not _should_send_alert(dedup_key, severity):
            continue

        reason = _reason_text(scenario, target, severity, events_count)
        body = format_telegram_alert(scenario, ip, country, target, severity, reason)
        to_send.append(body)
        aggregated_sent.add(agg)
        _mark_sent(dedup_key)

    if spike_note and to_send:
        to_send.append(spike_note)

    for msg in to_send:
        await _broadcast_plain(bot, msg, source="crowdsec_alert")


async def send_crowdsec_daily_report(bot: Bot) -> None:
    """Scheduled NAS Security Daily Report."""
    if not getattr(config, "CROWDSEC_MONITOR_ENABLED", False):
        return

    snap = gather_crowdsec_snapshot()
    if not snap.get("ok") and not snap.get("decisions"):
        await _broadcast_plain(
            bot,
            "🛡 NAS Security Daily Report\n\nCrowdSec unreachable. Check the crowdsec container and cscli.",
            source="crowdsec_daily",
        )
        return

    decisions = snap.get("decisions") or []
    alerts = snap.get("alerts") or []
    blocked_ips = len({d.get("source_ip") for d in decisions if d.get("source_ip")})

    scenarios = [a.get("scenario") or "unknown" for a in alerts] + [
        d.get("scenario") or "unknown" for d in decisions
    ]
    countries = [a.get("country") for a in alerts if a.get("country") and a.get("country") != "?"]
    targets = [a.get("target") for a in alerts] + [d.get("target") for d in decisions]

    sc = Counter(scenarios)
    cc = Counter(countries)
    tc = Counter(targets)

    recent: List[str] = []
    for a in (alerts[:3] if alerts else decisions[:3]):
        recent.append(
            f"{a.get('scenario', '?')} from {a.get('source_ip', '?')} "
            f"({a.get('country', '?')}) → {a.get('target', 'NAS')}"
        )

    stats = {
        "blocked_ips": blocked_ips,
        "top_scenario": sc.most_common(1)[0][0] if sc else "—",
        "top_country": cc.most_common(1)[0][0] if cc else "—",
        "top_target": tc.most_common(1)[0][0] if tc else "—",
        "overall_status": "No successful intrusions detected.",
        "trend_note": "",
    }

    unique_countries = len({c for c in countries if c and c != "?"})
    if unique_countries >= 5:
        stats["trend_note"] = (
            f"Activity from {unique_countries} countries in the current CrowdSec window — "
            "possible distributed scanning."
        )

    if not recent and blocked_ips == 0:
        text = "✅ No significant security incidents detected."
    else:
        text = format_daily_report(stats, recent)

    await _broadcast_plain(bot, text, source="crowdsec_daily")


def reset_crowdsec_monitor_state() -> None:
    """For tests: clear dedup caches."""
    global _baseline_complete
    _last_alert_sent.clear()
    _seen_alert_ids.clear()
    _seen_decision_keys.clear()
    _ip_window_counts.clear()
    _baseline_complete = False
