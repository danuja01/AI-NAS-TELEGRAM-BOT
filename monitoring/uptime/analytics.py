"""Uptime analytics, MTBF/MTTR, latency sparklines, and periodic reports."""

from __future__ import annotations

import logging
from typing import List, Optional

from telegram import Bot
from telegram.constants import ParseMode

import config
from monitoring.uptime import store
from services.system_monitor import get_memory_stats
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)


def _sparkline(values: List[float], width: int = 20) -> str:
    """ASCII latency sparkline for Telegram (monospace)."""
    if not values:
        return "—"
    blocks = "▁▂▃▄▅▆▇█"
    lo, hi = min(values), max(values)
    if hi <= lo:
        return blocks[4] * min(len(values), width)
    span = hi - lo
    chars = []
    for v in values[-width:]:
        idx = int((v - lo) / span * (len(blocks) - 1))
        chars.append(blocks[max(0, min(idx, len(blocks) - 1))])
    return "".join(chars)


def _fmt_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "n/a"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"


async def build_monitor_stats_report(monitor_name: str, hours: int = 168) -> str:
    m = await store.get_monitor_by_name(monitor_name)
    if not m:
        return f"Monitor <code>{escape_telegram_html(monitor_name)}</code> not found."
    mid = m["id"]
    stats = await store.get_monitor_stats(mid, hours=hours)
    mtbf = await store.compute_mtbf_mttr(mid, hours=hours)
    latencies = await store.get_recent_latencies(mid, limit=24)
    spark = _sparkline(latencies)
    avg_lat = stats.get("avg_latency")
    max_lat = stats.get("max_latency")

    lines = [
        f"📈 <b>Stats: {escape_telegram_html(m['name'])}</b> ({hours}h)",
        "",
        f"<b>Uptime</b>: <code>{stats.get('uptime_pct', m.get('uptime_percentage', 0)):.2f}%</code>",
        f"<b>Checks</b>: <code>{stats.get('n', 0)}</code>",
        f"<b>Incidents</b>: <code>{mtbf.get('incident_count', 0)}</code> "
        f"(<code>{mtbf.get('closed_incidents', 0)}</code> closed)",
        "",
        f"<b>MTBF</b> (mean time between failures): "
        f"<code>{_fmt_duration(mtbf.get('mtbf_seconds'))}</code>",
        f"<b>MTTR</b> (mean time to recover): "
        f"<code>{_fmt_duration(mtbf.get('mttr_seconds'))}</code>",
        f"<b>Longest outage</b>: "
        f"<code>{_fmt_duration(mtbf.get('longest_outage_seconds'))}</code>",
    ]
    if avg_lat is not None:
        lines.append("")
        lines.append(
            f"<b>Latency</b> avg <code>{avg_lat:.0f}ms</code> · "
            f"max <code>{max_lat:.0f}ms</code>"
        )
        lines.append(f"<pre>{spark}</pre> <i>(last {len(latencies)} checks)</i>")
    return "\n".join(lines)


async def build_weekly_report() -> str:
    monitors = await store.list_monitors()
    lines = ["📊 <b>Weekly NAS Monitor Report</b>", ""]
    lines.append("<b>Uptime (7d)</b>:")
    for m in monitors[:40]:
        stats = await store.get_monitor_stats(m["id"], hours=168)
        pct = stats.get("uptime_pct")
        if pct is None:
            pct = m.get("uptime_percentage", 0)
        icon = "🟢" if m.get("last_status") == "up" else "🔴"
        mtbf = await store.compute_mtbf_mttr(m["id"], hours=168)
        extra = ""
        if mtbf.get("incident_count"):
            extra = f" · {mtbf['incident_count']} inc"
        lines.append(
            f"{icon} <code>{escape_telegram_html(m['name'])}</code>: "
            f"<code>{pct:.2f}%</code>{extra}"
        )
    incidents = await store.list_recent_incidents(limit=10)
    if incidents:
        lines.append("")
        lines.append("<b>Recent incidents</b>:")
        for inc in incidents[:5]:
            dur = inc.get("duration_seconds") or "ongoing"
            lines.append(
                f"• <code>{escape_telegram_html(inc.get('monitor_name', '?'))}</code> "
                f"({dur}s)"
            )
    try:
        mem = get_memory_stats()
        lines.append("")
        lines.append(
            f"<b>Current RAM</b>: <code>{mem.get('percent', 0):.1f}%</code> used"
        )
    except Exception:
        pass
    lines.append("")
    lines.append("<i>Per-monitor: /monitor_stats &lt;name&gt;</i>")
    return "\n".join(lines)


async def send_weekly_report(bot: Bot) -> None:
    if not config.ALLOWED_USER_IDS:
        return
    text = await build_weekly_report()
    for uid in config.ALLOWED_USER_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error("weekly report %s: %s", uid, e)
