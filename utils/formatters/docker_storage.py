"""Telegram HTML formatters for Docker storage commands."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.formatters import escape_telegram_html as _h


def format_docker_dashboard(
    df_stdout: str,
    running: int,
    stopped: int,
    image_count: int,
    volume_count: int,
    docker_active: str,
    containers: List[Dict[str, Any]],
) -> str:
    lines = ["🐳 <b>Docker dashboard</b>", ""]
    lines.append(f"Service: <code>{_h(docker_active)}</code>")
    lines.append(f"Containers: <b>{running}</b> running, <b>{stopped}</b> stopped")
    lines.append(f"Images: <b>{image_count}</b> | Volumes: <b>{volume_count}</b>")
    lines.append("")
    if df_stdout.strip():
        lines.append("<b>docker system df</b>")
        lines.append(f"<pre>{_h(df_stdout.strip()[:3500])}</pre>")
    lines.append("")
    lines.append("<b>Containers</b>")
    for c in containers[:15]:
        name = c.get("Names") or c.get("name") or "?"
        if isinstance(name, list):
            name = name[0].lstrip("/") if name else "?"
        state = c.get("State") or c.get("status") or "?"
        icon = "✅" if str(state).lower() == "running" else "⏸"
        lines.append(f"{icon} <code>{_h(name)}</code> — {_h(state)}")
    if len(containers) > 15:
        lines.append(f"<i>… and {len(containers) - 15} more</i>")
    return "\n".join(lines)


def format_images_report(images: List[Dict[str, Any]]) -> str:
    lines = ["📦 <b>Docker images</b>", ""]
    if not images:
        lines.append("<i>No images found</i>")
        return "\n".join(lines)
    unused = sum(1 for i in images if i.get("unused"))
    dangling = sum(1 for i in images if i.get("dangling"))
    lines.append(f"Total: <b>{len(images)}</b> | Unused: <b>{unused}</b> | Dangling: <b>{dangling}</b>")
    lines.append("")
    for img in images[:25]:
        if img.get("dangling"):
            icon = "🔗"
        elif img.get("unused"):
            icon = "⚠️"
        elif img.get("in_use"):
            icon = "✅"
        else:
            icon = "•"
        lines.append(
            f"{icon} <code>{_h(img.get('repository'))}:{_h(img.get('tag'))}</code> "
            f"— {_h(img.get('size_human'))} ({_h(img.get('created'))})"
        )
    if len(images) > 25:
        lines.append(f"<i>… {len(images) - 25} more</i>")
    return "\n".join(lines)


def format_scan_report(
    df_stdout: str,
    df_verbose: str,
    running: int,
    stopped: int,
    images: List[Dict[str, Any]],
    bundle,
    est,
    builder_du_stdout: str = "",
) -> str:
    unused = sum(1 for i in images if i.get("unused"))
    dangling = sum(1 for i in images if i.get("dangling"))
    lines = ["🔍 <b>Docker storage scan</b>", ""]
    lines.append(f"Containers: <b>{running}</b> running, <b>{stopped}</b> stopped")
    lines.append(f"Images: <b>{len(images)}</b> ({unused} unused, {dangling} dangling)")
    if est:
        lines.append(
            f"Est. reclaimable (dry-run): containers <code>{_h(est.container_reclaim)}</code>, "
            f"images <code>{_h(est.image_reclaim)}</code>, "
            f"build cache <code>{_h(est.builder_reclaim)}</code>"
        )
    lines.append("")
    if df_stdout.strip():
        lines.append("<b>docker system df</b>")
        lines.append(f"<pre>{_h(df_stdout.strip()[:2000])}</pre>")
    if builder_du_stdout.strip():
        lines.append("<b>Build cache</b>")
        lines.append(f"<pre>{_h(builder_du_stdout.strip()[:1500])}</pre>")
    if images:
        lines.append("<b>Top images by size</b>")
        for img in images[:8]:
            flag = " ⚠️ unused" if img.get("unused") else (" 🔗 dangling" if img.get("dangling") else "")
            lines.append(
                f"• <code>{_h(img.get('repository'))}:{_h(img.get('tag'))}</code> "
                f"{_h(img.get('size_human'))}{flag}"
            )
    if bundle.docker_du:
        lines.append("<b>/var/lib/docker (depth 1)</b>")
        for e in bundle.docker_du[:8]:
            lines.append(f"• <code>{_h(e.size)}</code> {_h(e.path)}")
    if bundle.overlay_top:
        lines.append("<b>overlay2 (top)</b>")
        for e in bundle.overlay_top[:6]:
            lines.append(f"• <code>{_h(e.size)}</code> {_h(e.path)}")
    if bundle.large_files:
        lines.append("<b>Large files (top 10)</b>")
        for f in bundle.large_files[:10]:
            lines.append(f"• <code>{_h(f.size_human)}</code> {_h(f.path)}")
    lines.append("")
    lines.append("<b>Safe recommendations</b>")
    lines.append("• Run <code>/dclean</code> for stopped containers + unused images + build cache")
    lines.append("• Run <code>/dprune</code> for quick dangling-only prune")
    lines.append("• Volumes are never removed automatically")
    return "\n".join(lines)


def format_bigfiles(files) -> str:
    lines = ["📁 <b>Largest files</b>", ""]
    if not files:
        lines.append("<i>No files above threshold on scanned paths</i>")
        return "\n".join(lines)
    for f in files:
        lines.append(f"• <code>{_h(f.size_human)}</code> {_h(f.path)}")
        if f.note:
            lines.append(f"  <i>{_h(f.note)}</i>")
    return "\n".join(lines)


def format_huge_logs(files) -> str:
    lines = ["📜 <b>Large log files</b> (&gt; threshold)", ""]
    if not files:
        lines.append("<i>No huge logs found on scanned paths</i>")
        return "\n".join(lines)
    for f in files:
        lines.append(f"• <code>{_h(f.size_human)}</code> {_h(f.path)}")
        lines.append(f"  <i>{_h(f.note)}</i>")
    lines.append("")
    lines.append("<i>Truncate manually; automatic truncate is not enabled in v1.</i>")
    return "\n".join(lines)


def format_prune_result(title: str, result, est=None) -> str:
    lines = [f"🧹 <b>{_h(title)}</b>", ""]
    if est:
        lines.append(
            f"Estimated reclaimable: containers <code>{_h(est.container_reclaim)}</code>, "
            f"images <code>{_h(est.image_reclaim)}</code>, "
            f"cache <code>{_h(est.builder_reclaim)}</code>"
        )
        lines.append("")
    for name, r in result.steps:
        reclaim = ""
        out = getattr(r, "stdout", "") or ""
        err = getattr(r, "stderr", "") or ""
        if out or err:
            import re

            m = re.search(r"reclaimed\s+(\S+)", out + err, re.I)
            if m:
                reclaim = f" reclaimed {m.group(1)}"
        ok = getattr(r, "ok", getattr(r, "exit_code", 1) == 0)
        ec = getattr(r, "exit_code", "?")
        status = "✅" if ok else "❌"
        lines.append(f"{status} {_h(name)} (exit {ec}){reclaim}")
    if result.before_df and result.after_df:
        lines.append("")
        lines.append("<b>Before</b>")
        lines.append(f"<pre>{_h(result.before_df.strip()[:1200])}</pre>")
        lines.append("<b>After</b>")
        lines.append(f"<pre>{_h(result.after_df.strip()[:1200])}</pre>")
    return "\n".join(lines)


def format_dhealth(
    cpu_pct: float,
    mem_pct: float,
    swap_pct: float,
    disks: List[Dict],
    docker_df: str,
    uptime_s: int,
    temp_max: Optional[float],
    failed_units: str,
    running: int,
    stopped: int,
) -> str:
    from utils.formatters import format_uptime

    lines = ["🏥 <b>NAS health report</b>", ""]
    lines.append(f"CPU: <code>{cpu_pct:.1f}%</code> | RAM: <code>{mem_pct:.1f}%</code> | Swap: <code>{swap_pct:.1f}%</code>")
    lines.append(f"Uptime: <code>{_h(format_uptime(uptime_s))}</code>")
    if temp_max is not None:
        lines.append(f"Peak temp (sensors): <code>{temp_max:.1f}°C</code>")
    lines.append(f"Docker: <b>{running}</b> up, <b>{stopped}</b> stopped")
    lines.append("")
    lines.append("<b>Disk</b>")
    for d in disks[:6]:
        lines.append(
            f"• {_h(d.get('mountpoint'))}: <code>{d.get('percent', 0):.1f}%</code> used "
            f"({d.get('free_gb', 0):.1f} GB free)"
        )
    if docker_df.strip():
        lines.append("")
        lines.append("<b>docker system df</b>")
        lines.append(f"<pre>{_h(docker_df.strip()[:1500])}</pre>")
    if failed_units.strip():
        lines.append("")
        lines.append("<b>Failed systemd units</b>")
        lines.append(f"<pre>{_h(failed_units.strip()[:1500])}</pre>")
    else:
        lines.append("")
        lines.append("✅ No failed systemd units reported")
    return "\n".join(lines)
