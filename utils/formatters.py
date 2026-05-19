"""
Beautiful message formatters for Telegram with emojis and markdown / HTML.
Monitoring-style formatters use Telegram HTML (safe for dynamic system text).
"""

import html
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any

import config


def escape_telegram_html(value: Any) -> str:
    """Escape dynamic text for Telegram HTML parse mode."""
    return html.escape(str(value), quote=False)


def _h(value: Any) -> str:
    return escape_telegram_html(value)


def format_ai_response(text: str) -> str:
    """
    Format AI response for Telegram by converting markdown to Telegram-friendly format.
    
    Args:
        text: Raw AI response with markdown
    
    Returns:
        Cleaned text formatted for Telegram
    """
    if not text:
        return text
    
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
        msg += f"  Usage: {disk.get('percent', 0):.1f}%\n\n"

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

    for interface, stats in net_stats.items():
        if interface == "tailscale_ip" or not isinstance(stats, dict):
            continue

        msg += f"<b>{_h(interface)}</b>\n"
        msg += f"  Sent: {format_bytes(stats.get('bytes_sent', 0))}\n"
        msg += f"  Received: {format_bytes(stats.get('bytes_recv', 0))}\n"

        if "speed_mbps" in stats:
            spd = stats["speed_mbps"]
            msg += f"  Speed: {_h(spd)} Mbps\n"

        msg += "\n"

    if "tailscale_ip" in net_stats:
        ts = net_stats["tailscale_ip"]
        msg += f"<b>Tailscale IP:</b> <code>{_h(ts)}</code>\n"

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
