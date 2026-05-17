"""
Beautiful message formatters for Telegram with emojis and markdown.
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Any


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
    """Format comprehensive system statistics."""
    msg = "🖥 **NAS Status**\n\n"
    
    # CPU
    if 'cpu' in stats:
        cpu = stats['cpu']
        msg += f"**CPU:** {cpu.get('percent', 0):.1f}%\n"
        if 'load_avg' in cpu:
            loads = cpu['load_avg']
            msg += f"**Load:** {loads[0]:.2f}, {loads[1]:.2f}, {loads[2]:.2f}\n"
    
    # Memory
    if 'memory' in stats:
        mem = stats['memory']
        msg += f"**RAM:** {mem.get('used_gb', 0):.1f}GB / {mem.get('total_gb', 0):.1f}GB ({mem.get('percent', 0):.1f}%)\n"
    
    # Temperature
    if 'temperature' in stats and stats['temperature']:
        temp = stats['temperature']
        msg += f"**Temp:** {temp}°C\n"
    
    # Disk
    if 'disk' in stats:
        disk = stats['disk']
        msg += f"**Disk Free:** {disk.get('free_gb', 0):.1f}GB / {disk.get('total_gb', 0):.1f}GB\n"
    
    # Docker
    if 'docker' in stats:
        docker = stats['docker']
        msg += f"**Docker:** {docker.get('running', 0)} Running\n"
    
    # Uptime
    if 'uptime' in stats:
        msg += f"**Uptime:** {stats['uptime']}\n"
    
    return msg


def format_cpu_stats(cpu_stats: Dict[str, Any]) -> str:
    """Format CPU statistics."""
    msg = "💻 **CPU Statistics**\n\n"
    
    msg += f"**Usage:** {cpu_stats.get('percent', 0):.1f}%\n"
    
    if 'per_cpu' in cpu_stats and cpu_stats['per_cpu']:
        msg += f"**Cores:** {len(cpu_stats['per_cpu'])}\n"
        cores_str = ", ".join([f"{p:.0f}%" for p in cpu_stats['per_cpu'][:8]])  # Show first 8
        msg += f"**Per Core:** {cores_str}\n"
    
    if 'load_avg' in cpu_stats:
        loads = cpu_stats['load_avg']
        msg += f"**Load Average:** {loads[0]:.2f}, {loads[1]:.2f}, {loads[2]:.2f}\n"
    
    if 'frequency' in cpu_stats:
        freq = cpu_stats['frequency']
        msg += f"**Frequency:** {freq.get('current', 0):.0f} MHz\n"
    
    return msg


def format_memory_stats(mem_stats: Dict[str, Any]) -> str:
    """Format memory statistics."""
    msg = "🧠 **Memory Statistics**\n\n"
    
    msg += f"**Total:** {mem_stats.get('total_gb', 0):.2f} GB\n"
    msg += f"**Used:** {mem_stats.get('used_gb', 0):.2f} GB\n"
    msg += f"**Available:** {mem_stats.get('available_gb', 0):.2f} GB\n"
    msg += f"**Usage:** {mem_stats.get('percent', 0):.1f}%\n\n"
    
    if 'swap' in mem_stats:
        swap = mem_stats['swap']
        msg += "**Swap:**\n"
        msg += f"  Total: {swap.get('total_gb', 0):.2f} GB\n"
        msg += f"  Used: {swap.get('used_gb', 0):.2f} GB\n"
        msg += f"  Usage: {swap.get('percent', 0):.1f}%\n"
    
    return msg


def format_disk_stats(disk_stats: List[Dict[str, Any]]) -> str:
    """Format disk statistics."""
    msg = "💾 **Disk Statistics**\n\n"
    
    for disk in disk_stats:
        msg += f"**{disk.get('mountpoint', 'Unknown')}**\n"
        msg += f"  Device: `{disk.get('device', 'N/A')}`\n"
        msg += f"  Total: {disk.get('total_gb', 0):.1f} GB\n"
        msg += f"  Used: {disk.get('used_gb', 0):.1f} GB\n"
        msg += f"  Free: {disk.get('free_gb', 0):.1f} GB\n"
        msg += f"  Usage: {disk.get('percent', 0):.1f}%\n\n"
    
    return msg


def format_temperature_stats(temp_stats: Dict[str, Any]) -> str:
    """Format temperature statistics."""
    msg = "🌡 **Temperature Statistics**\n\n"
    
    if not temp_stats or all(v is None for v in temp_stats.values()):
        msg += "_No temperature sensors found_\n"
        return msg
    
    for sensor, temp in temp_stats.items():
        if temp is not None:
            icon = "🔥" if temp > 70 else "⚠️" if temp > 60 else "✅"
            msg += f"{icon} **{sensor}:** {temp:.1f}°C\n"
    
    return msg


def format_network_stats(net_stats: Dict[str, Any]) -> str:
    """Format network statistics."""
    msg = "🌐 **Network Statistics**\n\n"
    
    for interface, stats in net_stats.items():
        # Skip non-interface entries (like tailscale_ip)
        if interface == 'tailscale_ip' or not isinstance(stats, dict):
            continue
            
        msg += f"**{interface}**\n"
        msg += f"  Sent: {format_bytes(stats.get('bytes_sent', 0))}\n"
        msg += f"  Received: {format_bytes(stats.get('bytes_recv', 0))}\n"
        
        if 'speed_mbps' in stats:
            msg += f"  Speed: {stats['speed_mbps']} Mbps\n"
        
        msg += "\n"
    
    if 'tailscale_ip' in net_stats:
        msg += f"**Tailscale IP:** `{net_stats['tailscale_ip']}`\n"
    
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
    """Format system health score."""
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
    
    msg = f"{icon} **System Health: {status}** ({score}/100)\n\n"
    
    if issues:
        msg += "**Issues:**\n"
        for issue in issues:
            msg += f"⚠️ {issue}\n"
    else:
        msg += "✅ No issues detected\n"
    
    return msg


def format_smart_data(drives: List[Dict[str, Any]]) -> str:
    """Format SMART drive data."""
    if not drives:
        return "💿 **Drive Health**\n\n_No drives found or smartctl not available_"
    
    msg = "💿 **Drive Health**\n\n"
    
    for drive in drives:
        name = drive.get('device', 'Unknown')
        health = drive.get('health', 'UNKNOWN')
        
        icon = "✅" if health == "PASSED" else "❌" if health == "FAILED" else "⚠️"
        
        msg += f"{icon} **{name}**\n"
        msg += f"  Health: {health}\n"
        
        if 'model' in drive:
            msg += f"  Model: {drive['model']}\n"
        if 'temperature' in drive:
            msg += f"  Temp: {drive['temperature']}°C\n"
        if 'power_on_hours' in drive:
            msg += f"  Power On: {drive['power_on_hours']} hours\n"
        if 'reallocated_sectors' in drive:
            sectors = drive['reallocated_sectors']
            if sectors > 0:
                msg += f"  ⚠️ Reallocated Sectors: {sectors}\n"
        
        msg += "\n"
    
    return msg


def format_error(error_msg: str) -> str:
    """Format error message."""
    return f"❌ **Error**\n\n{error_msg}"


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
