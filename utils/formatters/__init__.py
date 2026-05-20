"""
Beautiful message formatters for Telegram with emojis and markdown / HTML.
Monitoring-style formatters use Telegram HTML (safe for dynamic system text).
"""

import html
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import config


def escape_telegram_html(value: Any) -> str:
    """Escape dynamic text for Telegram HTML parse mode."""
    return html.escape(str(value), quote=False)


def _h(value: Any) -> str:
    return escape_telegram_html(value)


# GFM bold/italic wrappers around Telegram-style slash commands (LLMs emit **/cmd** often;
# legacy Telegram Markdown does not treat ** as bold, so users see literal asterisks).
_AI_CMD_GFM_BOLD_RE = re.compile(r"\*\*\s*((/\w[\w_-]*))\s*\*\*")
_AI_CMD_GFM_UNDER_BOLD_RE = re.compile(r"__\s*((/\w[\w_-]*))\s*__")
# Italic-style single * around slash commands without touching ** spans
_AI_CMD_STAR_ITALIC_RE = re.compile(r"(?<!\*)\*((/\w[\w_-]*))\*(?!\*)")


def normalize_ai_reply_markdown_for_telegram(text: str) -> str:
    """
    Turn ``**/foobar**``-style wrappers around slash commands into inline code spans.

    Telegram's classic ``Markdown`` mode does not understand GitHub ``**bold**``; unchanged
    text shows stray stars. Backticks survive both legacy Markdown and MarkdownV2 paths.
    """
    if not text:
        return text
    text = _AI_CMD_GFM_BOLD_RE.sub(r"`\1`", text)
    text = _AI_CMD_GFM_UNDER_BOLD_RE.sub(r"`\1`", text)
    text = _AI_CMD_STAR_ITALIC_RE.sub(r"`\1`", text)
    return text


def format_ai_response(text: str) -> str:
    """
    Light cleanup for legacy Markdown replies.

    Prefer ``utils.telegram_reply.reply_ai_markdown_chunked`` for AI output; it uses
    ``telegramify-markdown`` (MarkdownV2) and handles tables and entity escaping.
    """
    if not text:
        return text

    text = normalize_ai_reply_markdown_for_telegram(text)

    # Convert markdown headings to bold text with line breaks
    # ### Heading → **Heading**
    text = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', text, flags=re.MULTILINE)
    
    # Convert bold markdown variations to consistent format
    # __text__ → **text**
    text = re.sub(r'__([^_]+)__', r'**\1**', text)
    
    # Convert italic markdown variations to consistent format  
    # _text_ → _text_ (keep as is, already supported)
    
    # Remove triple backticks for code blocks (Telegram doesn't support well in markdown mode)
    # ```code``` → `code`
    text = re.sub(r'```[\w]*\n?(.+?)\n?```', r'`\1`', text, flags=re.DOTALL)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', r'\n\n', text)
    
    # Remove markdown links that don't work well: [text](url) → text (url)
    text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\1 (\2)', text)
    
    # Clean up leading/trailing whitespace
    text = text.strip()
    
    return text


def format_system_stats(stats: Dict[str, Any]) -> str:
    """Format comprehensive system statistics (Telegram HTML)."""
    msg = "🖥 <b>NAS Status</b>\n\n"

    # CPU
    if "cpu" in stats:
        cpu = stats["cpu"]
        msg += f"<b>CPU:</b> {cpu.get('percent', 0):.1f}%\n"
        if "load_avg" in cpu:
            loads = cpu["load_avg"]
            msg += (
                f"<b>Load:</b> {loads[0]:.2f}, {loads[1]:.2f}, {loads[2]:.2f}\n"
            )

    # Memory
    if "memory" in stats:
        mem = stats["memory"]
        msg += (
            f"<b>RAM:</b> {mem.get('used_gb', 0):.1f}GB / "
            f"{mem.get('total_gb', 0):.1f}GB ({mem.get('percent', 0):.1f}%)\n"
        )

    # Temperature
    if "temperature" in stats and stats["temperature"] is not None:
        temp = stats["temperature"]
        msg += f"<b>Temp:</b> {_h(temp)}°C\n"

    # Disk
    if "disk" in stats:
        disk = stats["disk"]
        msg += (
            f"<b>Disk Free:</b> {disk.get('free_gb', 0):.1f}GB / "
            f"{disk.get('total_gb', 0):.1f}GB\n"
        )

    # Docker
    if "docker" in stats:
        docker = stats["docker"]
        msg += f"<b>Docker:</b> {docker.get('running', 0)} Running\n"

    # Uptime (seconds in comprehensive status payload)
    if "uptime" in stats:
        msg += f"<b>Uptime:</b> {_h(stats['uptime'])}\n"

    return msg


def format_cpu_stats(cpu_stats: Dict[str, Any]) -> str:
    """Format CPU statistics (Telegram HTML)."""
    msg = "💻 <b>CPU Statistics</b>\n\n"

    msg += f"<b>Usage:</b> {cpu_stats.get('percent', 0):.1f}%\n"

    if "per_cpu" in cpu_stats and cpu_stats["per_cpu"]:
        msg += f"<b>Cores:</b> {len(cpu_stats['per_cpu'])}\n"
        cores_str = ", ".join([f"{p:.0f}%" for p in cpu_stats["per_cpu"][:8]])
        msg += f"<b>Per Core:</b> {cores_str}\n"

    if "load_avg" in cpu_stats:
        loads = cpu_stats["load_avg"]
        msg += f"<b>Load Average:</b> {loads[0]:.2f}, {loads[1]:.2f}, {loads[2]:.2f}\n"

    if "frequency" in cpu_stats:
        freq = cpu_stats["frequency"]
        msg += f"<b>Frequency:</b> {freq.get('current', 0):.0f} MHz\n"

    return msg


def format_memory_stats(mem_stats: Dict[str, Any]) -> str:
    """Format memory statistics (Telegram HTML)."""
    msg = "🧠 <b>Memory Statistics</b>\n\n"

    msg += f"<b>Total:</b> {mem_stats.get('total_gb', 0):.2f} GB\n"
    msg += f"<b>Used:</b> {mem_stats.get('used_gb', 0):.2f} GB\n"
    msg += f"<b>Available:</b> {mem_stats.get('available_gb', 0):.2f} GB\n"
    msg += f"<b>Usage:</b> {mem_stats.get('percent', 0):.1f}%\n\n"

    if "swap" in mem_stats:
        swap = mem_stats["swap"]
        msg += "<b>Swap:</b>\n"
        msg += f"  Total: {swap.get('total_gb', 0):.2f} GB\n"
        msg += f"  Used: {swap.get('used_gb', 0):.2f} GB\n"
        msg += f"  Usage: {swap.get('percent', 0):.1f}%\n"

    return msg


def _usage_bar_html(percent: Any, width: int = 10) -> str:
    """Compact Unicode usage bar for Telegram HTML (no pipe tables)."""
    try:
        p = float(percent)
    except (TypeError, ValueError):
        return "▱" * width
    p = max(0.0, min(100.0, p))
    filled = int(round(width * p / 100.0))
    filled = min(width, max(0, filled))
    bar = "▰" * filled + "▱" * (width - filled)
    return f"{bar} <code>{p:.0f}%</code>"


def _omv_size_to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def format_disk_stats(disk_stats: List[Dict[str, Any]]) -> str:
    """Format disk statistics (Telegram HTML)."""
    msg = "💾 <b>Disk Statistics</b>\n\n"

    for disk in disk_stats:
        mnt = disk.get("mountpoint", "Unknown")
        dev = disk.get("device", "N/A")
        msg += f"<b>{_h(mnt)}</b>\n"
        msg += f"  Device: <code>{_h(dev)}</code>\n"
        msg += f"  Total: {disk.get('total_gb', 0):.1f} GB\n"
        msg += f"  Used: {disk.get('used_gb', 0):.1f} GB\n"
        msg += f"  Free: {disk.get('free_gb', 0):.1f} GB\n"
        msg += f"  Usage: {disk.get('percent', 0):.1f}%\n"
        msg += f"  {_usage_bar_html(disk.get('percent', 0))}\n\n"

    return msg


def format_omv_filesystems_panel(rows: List[Dict[str, Any]], max_rows: int = 14) -> str:
    """OMV ``enumerateMountedFilesystems`` as a readable panel (Telegram HTML)."""
    if not rows:
        return ""
    lines: List[str] = []
    lines.append("🧾 <b>OpenMediaVault — filesystems</b>\n")
    for r in rows[:max_rows]:
        mp = r.get("mountpoint") or "—"
        typ = r.get("type") or "—"
        dev = r.get("devicefile") or "—"
        pct = r.get("percentage")
        desc = r.get("description") or ""
        used = r.get("used")
        avail = r.get("available")
        sz = _omv_size_to_int(r.get("size"))
        sz_h = format_bytes(sz) if sz is not None else "—"
        bar = _usage_bar_html(pct if pct is not None else 0)
        lines.append(f"<b>{_h(mp)}</b> <code>{_h(typ)}</code>")
        lines.append(f"  {_h(bar)}")
        lines.append(f"  Device: <code>{_h(dev)}</code>")
        lines.append(f"  OMV used/avail: {_h(used)} / {_h(avail)}  ·  size {_h(sz_h)}")
        if desc:
            lines.append(f"  <i>{_h(desc)}</i>")
        lines.append("")
    if len(rows) > max_rows:
        lines.append(f"<i>… {_h(len(rows) - max_rows)} more not shown</i>\n")
    return "\n".join(lines)


def format_omv_physical_disks_panel(rows: List[Dict[str, Any]], max_rows: int = 16) -> str:
    """OMV ``DiskMgmt::enumerateDevices`` summary (Telegram HTML)."""
    if not rows:
        return ""
    lines: List[str] = []
    lines.append("💿 <b>OpenMediaVault — physical disks</b>\n")
    for r in rows[:max_rows]:
        dev = r.get("devicefile") or r.get("canonicaldevicefile") or "—"
        model = r.get("model") or "—"
        serial = r.get("serialnumber") or "—"
        sz = _omv_size_to_int(r.get("size"))
        sz_h = format_bytes(sz) if sz is not None else "—"
        temp = r.get("temperature")
        pm = r.get("powermode") or "—"
        wwn = r.get("wwn") or ""
        flags = []
        if r.get("isroot"):
            flags.append("root")
        if r.get("isreadonly"):
            flags.append("ro")
        if r.get("israid"):
            flags.append("raid")
        fl = f" ({', '.join(flags)})" if flags else ""
        lines.append(f"<b><code>{_h(dev)}</code></b>{_h(fl)}")
        lines.append(f"  {_h(model)} · {_h(sz_h)}")
        lines.append(
            f"  S/N <code>{_h(serial)}</code>"
            + (f" · WWN <code>{_h(wwn)}</code>" if wwn else "")
        )
        lines.append(f"  SMART temp: {_h(temp) if temp not in (None, '') else '—'} · power {_h(pm)}")
        lines.append("")
    if len(rows) > max_rows:
        lines.append(f"<i>… {_h(len(rows) - max_rows)} more not shown</i>\n")
    return "\n".join(lines)


def format_omv_smart_devices_panel(rows: List[Dict[str, Any]], max_rows: int = 16) -> str:
    """OMV ``Smart::enumerateDevices`` (overall status as seen by OMV)."""
    if not rows:
        return ""
    lines: List[str] = []
    lines.append("🩺 <b>OpenMediaVault — SMART overview</b>\n")
    for r in rows[:max_rows]:
        dev = r.get("devicefile") or "—"
        st = r.get("overallstatus")
        model = r.get("model") or ""
        temp = r.get("temperature")
        sn = r.get("serialnumber") or ""
        lines.append(f"<b><code>{_h(dev)}</code></b>")
        if model:
            lines.append(f"  {_h(model)}")
        if sn:
            lines.append(f"  S/N <code>{_h(sn)}</code>")
        lines.append(f"  OMV status: <code>{_h(st)}</code> · temp {_h(temp) if temp not in (None, '') else '—'}")
        lines.append("")
    if len(rows) > max_rows:
        lines.append(f"<i>… {_h(len(rows) - max_rows)} more not shown</i>\n")
    return "\n".join(lines)


def format_disks_with_omv(
    disk_stats: List[Dict[str, Any]],
    omv_fs: List[Dict[str, Any]],
    omv_disks: List[Dict[str, Any]],
    omv_banner: Optional[str] = None,
) -> str:
    """Live ``psutil`` mounts plus optional OMV RPC panels."""
    msg = format_disk_stats(disk_stats)
    if omv_banner:
        msg += f"\n{_h(omv_banner)}\n"
    if omv_fs:
        msg += "\n" + format_omv_filesystems_panel(omv_fs)
    if omv_disks:
        msg += "\n" + format_omv_physical_disks_panel(omv_disks)
    return msg


def format_smart_with_omv(
    drives: List[Dict[str, Any]],
    omv_smart: List[Dict[str, Any]],
    omv_banner: Optional[str] = None,
) -> str:
    """SMART from smartctl plus optional OMV SMART enumeration."""
    msg = format_smart_data(drives)
    if omv_banner:
        msg += f"\n{_h(omv_banner)}\n"
    if omv_smart:
        msg += "\n" + format_omv_smart_devices_panel(omv_smart)
    return msg


def format_temperature_stats(temp_stats: Dict[str, Any]) -> str:
    """Format temperature statistics (Telegram HTML)."""
    msg = "🌡 <b>Temperature Statistics</b>\n\n"

    if not temp_stats or all(v is None for v in temp_stats.values()):
        msg += "<i>No temperature sensors found</i>\n"
        return msg

    for sensor, temp in temp_stats.items():
        if temp is not None:
            if config.ignore_temperature_sensor_for_alerts(sensor):
                icon = "ℹ️"
            else:
                icon = "🔥" if temp > 70 else "⚠️" if temp > 60 else "✅"
            msg += f"{icon} <b>{_h(sensor)}:</b> {temp:.1f}°C\n"

    return msg


def format_network_stats(net_stats: Dict[str, Any]) -> str:
    """Format network statistics (Telegram HTML)."""
    msg = "🌐 <b>Network Statistics</b>\n\n"

    meta_keys = frozenset(
        {
            "tailscale_ip",
            "outbound_local_ipv4",
            "default_gateway_ipv4",
            "default_route_iface",
        }
    )

    def_iface = net_stats.get("default_route_iface")
    pairs = [(k, v) for k, v in net_stats.items() if k not in meta_keys and isinstance(v, dict)]

    def _iface_sort(name: str) -> tuple[int, str]:
        if def_iface and name == def_iface:
            return (0, name)
        return (1, name)

    pairs.sort(key=lambda kv: _iface_sort(kv[0]))

    out_l = net_stats.get("outbound_local_ipv4")
    gw = net_stats.get("default_gateway_ipv4")
    gw_if = net_stats.get("default_route_iface")
    if out_l or gw or gw_if:
        msg += "<b>Outbound / default route</b>\n"
        if out_l:
            msg += f"  Local IPv4 (outbound probe): <code>{_h(out_l)}</code>\n"
        if gw:
            msg += f"  Default gateway: <code>{_h(gw)}</code>\n"
        if gw_if:
            msg += f"  Default route iface: <code>{_h(gw_if)}</code>\n"
        msg += "\n"

    for interface, stats in pairs:
        up = stats.get("isup")
        if up is True:
            state = "✅ UP"
        elif up is False:
            state = "⬇️ DOWN"
        else:
            state = "❔ state unknown"

        msg += f"<b>{_h(interface)}</b> — {state}\n"

        mtu = stats.get("mtu")
        if mtu:
            msg += f"  MTU: {_h(mtu)}\n"
        duplex = stats.get("duplex")
        if duplex and duplex != "unknown":
            msg += f"  Duplex: {_h(duplex)}\n"
        spd = stats.get("speed_mbps")
        if spd:
            msg += f"  Link speed: {_h(spd)} Mbps\n"

        addrs = stats.get("addresses") or []
        if addrs:
            msg += "  Addresses:\n"
            for a in addrs[:12]:
                fam = a.get("family", "")
                addr = a.get("address", "")
                nm = a.get("netmask") or ""
                scope = f" ({_h(fam)})" if fam else ""
                if nm and fam == "ipv4":
                    line = f"    <code>{_h(addr)}</code> / {_h(nm)}{scope}\n"
                else:
                    line = f"    <code>{_h(addr)}</code>{scope}\n"
                msg += line
            if len(addrs) > 12:
                msg += f"    <i>… {_h(len(addrs) - 12)} more</i>\n"

        msg += f"  Sent: {format_bytes(stats.get('bytes_sent', 0))}\n"
        msg += f"  Received: {format_bytes(stats.get('bytes_recv', 0))}\n"
        ein = stats.get("errors_in", 0)
        eout = stats.get("errors_out", 0)
        if ein or eout:
            msg += f"  Errors in/out: {_h(ein)} / {_h(eout)}\n"
        msg += "\n"

    if not pairs:
        msg += "<i>No non-loopback interfaces found.</i>\n\n"

    if "tailscale_ip" in net_stats:
        ts = net_stats["tailscale_ip"]
        msg += f"<b>Tailscale IPv4:</b> <code>{_h(ts)}</code>\n"
        msg += "<i>(from <code>tailscale ip -4</code>; set NETWORK_TAILSCALE_CLI=false to skip)</i>\n"
    elif getattr(config, "NETWORK_TAILSCALE_CLI", True):
        msg += "<i>Tailscale: no IPv4 (CLI missing or not logged in; disable hints with NETWORK_TAILSCALE_CLI=false).</i>\n"

    return msg


def format_docker_containers(containers: List[Dict[str, Any]]) -> str:
    """Format Docker container list."""
    if not containers:
        return "🐳 **Docker Containers**\n\n_No containers found_"
    
    msg = f"🐳 **Docker Containers** ({len(containers)})\n\n"
    
    for container in containers:
        name = container.get('name', 'Unknown')
        status = container.get('status', 'unknown')
        
        # Status emoji
        if 'running' in status.lower():
            icon = "✅"
        elif 'exited' in status.lower():
            icon = "🔴"
        elif 'paused' in status.lower():
            icon = "⏸"
        else:
            icon = "⚪"
        
        msg += f"{icon} **{name}**\n"
        msg += f"  Status: {status}\n"
        
        if 'cpu' in container:
            msg += f"  CPU: {container['cpu']:.1f}%\n"
        if 'memory' in container:
            msg += f"  RAM: {format_bytes(container['memory'])}\n"
        
        msg += "\n"
    
    return msg


def format_file_list(files: List[Dict[str, Any]], path: str) -> str:
    """Format file listing."""
    msg = f"📁 **{path}**\n\n"
    
    if not files:
        msg += "_Empty directory_\n"
        return msg
    
    # Separate directories and files
    dirs = [f for f in files if f.get('is_dir')]
    files_list = [f for f in files if not f.get('is_dir')]
    
    # Show directories first
    for d in dirs[:20]:  # Limit to 20
        msg += f"📁 `{d.get('name')}`\n"
    
    # Then files
    for f in files_list[:20]:  # Limit to 20
        size = format_bytes(f.get('size', 0))
        msg += f"📄 `{f.get('name')}` ({size})\n"
    
    total = len(dirs) + len(files_list)
    if total > 20:
        msg += f"\n_...and {total - 20} more items_\n"
    
    return msg


def format_file_list_numbered(files: List[Dict[str, Any]], path: str) -> str:
    """
    Format file listing with numbered emojis for downloads.
    
    Directories are shown without numbers.
    Files are numbered with emoji digits (1️⃣-🔟) or plain numbers (11+).
    """
    number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    
    msg = f"📁 **{path}**\n\n"
    
    if not files:
        msg += "_Empty directory_\n"
        return msg
    
    # Separate directories and files
    dirs = [f for f in files if f.get('is_dir')]
    files_list = [f for f in files if not f.get('is_dir')]
    
    # Show directories first (without numbers)
    if dirs:
        msg += "**Directories:**\n"
        for d in dirs[:10]:  # Limit to 10 dirs
            msg += f"📁 `{d.get('name')}`\n"
        if len(dirs) > 10:
            msg += f"_...and {len(dirs) - 10} more directories_\n"
        msg += "\n"
    
    # Show files with numbers
    if files_list:
        msg += "**Files:**\n"
        for idx, f in enumerate(files_list[:20]):  # Limit to 20 files
            # Use emoji for 1-10, plain number for 11+
            if idx < 10:
                number = number_emojis[idx]
            else:
                number = f"{idx + 1}."
            
            size = format_bytes(f.get('size', 0))
            msg += f"{number} `{f.get('name')}` ({size})\n"
        
        if len(files_list) > 20:
            msg += f"\n_...and {len(files_list) - 20} more files_\n"
        
        msg += "\n💡 Use `/download <number>` to download a file\n"
    
    return msg


def format_health_score(score: int, issues: List[str]) -> str:
    """Format system health score (Telegram HTML)."""
    if score >= 90:
        icon = "✅"
        status = "Excellent"
    elif score >= 70:
        icon = "🟢"
        status = "Good"
    elif score >= 50:
        icon = "🟡"
        status = "Fair"
    elif score >= 30:
        icon = "🟠"
        status = "Poor"
    else:
        icon = "🔴"
        status = "Critical"

    msg = f"{icon} <b>System Health: {_h(status)}</b> ({score}/100)\n\n"

    if issues:
        msg += "<b>Issues:</b>\n"
        for issue in issues:
            msg += f"⚠️ {_h(issue)}\n"
    else:
        msg += "✅ No issues detected\n"

    return msg


def format_smart_data(drives: List[Dict[str, Any]]) -> str:
    """Format SMART drive data (Telegram HTML)."""
    if not drives:
        return (
            "💿 <b>Drive Health</b>\n\n"
            "<i>No drives found or smartctl not available</i>"
        )

    msg = "💿 <b>Drive Health</b>\n\n"

    for drive in drives:
        name = drive.get("device", "Unknown")
        health = drive.get("health", "UNKNOWN")
        icon = (
            "✅"
            if health == "PASSED"
            else "❌" if health == "FAILED" else "⚠️"
        )

        msg += f"{icon} <b>{_h(name)}</b>\n"
        msg += f"  Health: {_h(health)}\n"

        if "model" in drive:
            msg += f"  Model: {_h(drive['model'])}\n"
        if "temperature" in drive:
            msg += f"  Temp: {_h(drive['temperature'])}°C\n"
        if "power_on_hours" in drive:
            msg += f"  Power On: {_h(drive['power_on_hours'])} hours\n"
        if "reallocated_sectors" in drive:
            sectors = drive["reallocated_sectors"]
            if sectors > 0:
                msg += f"  ⚠️ Reallocated Sectors: {_h(sectors)}\n"

        msg += "\n"

    return msg


def format_hdd_detail(
    drives: List[Dict[str, Any]],
    history_by_device: Dict[str, List[Dict[str, Any]]],
) -> str:
    """
    Extended HDD/SMART detail: power cycles, start/stop, load cycles, hdparm state,
    and recent counter samples. Uses Telegram HTML.
    """
    if not drives:
        return (
            "💿 <b>HDD detail</b>\n\n"
            "<i>No drives found or smartctl not available</i>"
        )

    msg = (
        "💿 <b>HDD / SMART detail</b>\n\n"
        "<i>SMART exposes cumulative counters, not a timestamped spin-down log. "
        "Samples below are captured on each periodic health SMART check (~15 min).</i>\n\n"
    )

    def _n(v: Any) -> str:
        if v is None:
            return "—"
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return _h(v)

    def _d(cur: Any, prev: Any) -> str:
        if cur is None or prev is None:
            return ""
        try:
            delta = int(cur) - int(prev)
            if delta == 0:
                return " <code>(±0)</code>"
            sign = "+" if delta > 0 else ""
            return f" <code>({sign}{delta} vs last sample)</code>"
        except (TypeError, ValueError):
            return ""

    for drive in drives:
        name = drive.get("device", "Unknown")
        health = drive.get("health", "UNKNOWN")
        icon = (
            "✅"
            if health == "PASSED"
            else "❌" if health == "FAILED" else "⚠️"
        )
        msg += f"{icon} <b>{_h(name)}</b>\n"
        if drive.get("model"):
            msg += f"  Model: {_h(drive['model'])}\n"
        msg += f"  SMART: {_h(health)}\n"

        hist = history_by_device.get(name) or []
        prev = hist[0] if hist else None

        if drive.get("temperature") is not None:
            msg += f"  Temp: {_n(drive['temperature'])}°C\n"
        if drive.get("power_on_hours") is not None:
            msg += f"  Power-on hours: {_n(drive['power_on_hours'])}\n"

        pstate = drive.get("power_state")
        if pstate:
            msg += f"  ATA power state (hdparm): {_h(pstate)}\n"

        if drive.get("start_stop_count") is not None:
            msg += (
                f"  Start/stop count: {_n(drive['start_stop_count'])}"
                f"{_d(drive.get('start_stop_count'), prev.get('start_stop') if prev else None)}\n"
            )
        if drive.get("load_cycle_count") is not None:
            msg += (
                f"  Load cycle count: {_n(drive['load_cycle_count'])}"
                f"{_d(drive.get('load_cycle_count'), prev.get('load_cycle') if prev else None)}\n"
            )
        if drive.get("power_cycle_count") is not None:
            msg += (
                f"  Power cycle count: {_n(drive['power_cycle_count'])}"
                f"{_d(drive.get('power_cycle_count'), prev.get('power_cycles') if prev else None)}\n"
            )
        if drive.get("poweroff_retract_count") is not None:
            msg += f"  Power-off retract: {_n(drive['poweroff_retract_count'])}\n"
        if drive.get("reallocated_sectors"):
            msg += f"  Reallocated sectors: {_n(drive['reallocated_sectors'])}\n"
        if drive.get("pending_sectors"):
            msg += f"  Pending sectors: {_n(drive['pending_sectors'])}\n"

        if hist:
            msg += "  <b>Recent samples</b> (newest first):\n"
            for i, row in enumerate(hist[:10]):
                ts = row.get("recorded_at") or ""
                line = (
                    f"   • {_h(ts)}  start/stop {_n(row.get('start_stop'))}  "
                    f"load {_n(row.get('load_cycle'))}  power {_n(row.get('power_cycles'))}"
                )
                older = hist[i + 1] if i + 1 < len(hist) else None
                if older and row.get("start_stop") is not None and older.get("start_stop") is not None:
                    try:
                        ds = int(row["start_stop"]) - int(older["start_stop"])
                        if ds != 0:
                            line += f"  <code>Δstop {ds:+d}</code>"
                    except (TypeError, ValueError):
                        pass
                if older and row.get("load_cycle") is not None and older.get("load_cycle") is not None:
                    try:
                        dl = int(row["load_cycle"]) - int(older["load_cycle"])
                        if dl != 0:
                            line += f" <code>Δload {dl:+d}</code>"
                    except (TypeError, ValueError):
                        pass
                msg += line + "\n"
        else:
            msg += (
                "  <i>No stored samples yet; wait for the next SMART health interval, "
                "then run again.</i>\n"
            )

        msg += "\n"

    return msg


def format_hdd_detail_with_omv(
    drives: List[Dict[str, Any]],
    history_by_device: Dict[str, List[Dict[str, Any]]],
    omv_disks: Optional[List[Dict[str, Any]]] = None,
    omv_banner: Optional[str] = None,
) -> str:
    """``format_hdd_detail`` with optional OMV physical disk inventory header."""
    prefix = ""
    if omv_banner:
        prefix += f"ℹ️ <i>{_h(omv_banner)}</i>\n\n"
    if omv_disks:
        prefix += format_omv_physical_disks_panel(omv_disks) + "\n"
    return prefix + format_hdd_detail(drives, history_by_device)


def format_error(error_msg: str) -> str:
    """Format error message."""
    return f"❌ **Error**\n\n{error_msg}"


def format_error_html(error_msg: str) -> str:
    """Format error message for Telegram HTML parse mode."""
    return f"❌ <b>Error</b>\n\n{_h(error_msg)}"


def format_success(success_msg: str) -> str:
    """Format success message."""
    return f"✅ {success_msg}"


def format_warning(warning_msg: str) -> str:
    """Format warning message."""
    return f"⚠️ {warning_msg}"


def format_bytes(bytes_value: int) -> str:
    """Format bytes into human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def format_uptime(seconds: int) -> str:
    """Format uptime seconds into readable format."""
    delta = timedelta(seconds=seconds)
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}m")
    
    return " ".join(parts)


def format_progress(current: int, total: int, prefix: str = "") -> str:
    """Format progress bar."""
    percent = (current / total) * 100 if total > 0 else 0
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"{prefix}{bar} {percent:.1f}% ({current}/{total})"
