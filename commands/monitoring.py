"""
Monitoring command handlers.
Provides system monitoring commands using psutil and smartctl.
"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.security import require_auth, rate_limit
from utils.telegram_reply import reply_text_safe
from utils.formatters import (
    escape_telegram_html,
    format_system_stats,
    format_cpu_stats,
    format_memory_stats,
    format_disks_with_omv,
    format_temperature_stats,
    format_network_stats,
    format_health_score,
    format_smart_with_omv,
    format_hdd_detail_with_omv,
    format_uptime,
    format_error_html,
    format_omv_filesystems_panel,
)
from services.omv_client import (
    fetch_disk_enumerate,
    fetch_filesystems_mounted,
    fetch_smart_devices,
    omv_rpc_available,
)
from services.system_monitor import (
    get_comprehensive_status,
    get_cpu_stats,
    get_memory_stats,
    get_disk_stats,
    get_temperatures,
    get_network_stats,
    get_uptime,
    calculate_health_score,
)
from services.smart_monitor import get_all_drives, check_drive_warnings, get_hdparm_power_state
from database.memory import save_conversation, save_command, get_drive_spin_history
from utils.conversation_snippet import html_reply_to_context_plain
from utils.telegram_reply import reply_text_chunked
from utils.network_tools import fetch_public_ipv4, run_ping, validate_ping_target

logger = logging.getLogger(__name__)


def _monitoring_kw():
    """Parse mode for monitoring messages (escaped HTML bodies)."""
    return {"parse_mode": ParseMode.HTML}


@require_auth
@rate_limit
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - Show comprehensive system status."""
    user_id = update.effective_user.id

    try:
        await reply_text_safe(update, "📊 Gathering system status...")

        stats = get_comprehensive_status()

        if "error" in stats:
            await reply_text_safe(update, format_error_html(stats["error"]), **_monitoring_kw())
            return

        message = format_system_stats(stats)
        if omv_rpc_available():
            fs_rows, e_omv = await fetch_filesystems_mounted()
            if fs_rows and not e_omv:
                message += "\n\n" + format_omv_filesystems_panel(fs_rows, max_rows=8)
            elif e_omv:
                message += f"\n\n<i>OMV: {escape_telegram_html(e_omv)}</i>"
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/status")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/status", "System status retrieved")

    except Exception as e:
        logger.error(f"Error in status_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get system status: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def cpu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cpu command - Show CPU statistics."""
    user_id = update.effective_user.id

    try:
        stats = get_cpu_stats()
        message = format_cpu_stats(stats)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/cpu")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/cpu", f"CPU: {stats.get('percent', 0):.1f}%")

    except Exception as e:
        logger.error(f"Error in cpu_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get CPU stats: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def ram_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ram command - Show memory statistics."""
    user_id = update.effective_user.id

    try:
        stats = get_memory_stats()
        message = format_memory_stats(stats)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/ram")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/ram", f"RAM: {stats.get('percent', 0):.1f}%")

    except Exception as e:
        logger.error(f"Error in ram_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get memory stats: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def disk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /disk command - Show disk statistics."""
    user_id = update.effective_user.id

    try:
        stats = get_disk_stats()
        omv_fs: list = []
        omv_disks: list = []
        omv_note = None
        if omv_rpc_available():
            fs_rows, e1 = await fetch_filesystems_mounted()
            dk_rows, e2 = await fetch_disk_enumerate()
            if not e1:
                omv_fs = fs_rows
            if not e2:
                omv_disks = dk_rows
            if e1 and e2:
                omv_note = f"OMV RPC: {e1}"
            elif e1 or e2:
                omv_note = " | ".join(x for x in (e1, e2) if x)
        message = format_disks_with_omv(stats, omv_fs, omv_disks, omv_banner=omv_note)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/disk")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/disk", f"{len(stats)} partitions")

    except Exception as e:
        logger.error(f"Error in disk_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get disk stats: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def temps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /temps command - Show temperature statistics."""
    user_id = update.effective_user.id

    try:
        stats = get_temperatures()
        message = format_temperature_stats(stats)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/temps")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/temps", "Temperature stats retrieved")

    except Exception as e:
        logger.error(f"Error in temps_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get temperatures: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def network_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /network command - Show network statistics."""
    user_id = update.effective_user.id

    try:
        stats = get_network_stats()
        message = format_network_stats(stats)
        if len(message) > 3500:
            await reply_text_chunked(update, message, parse_mode=ParseMode.HTML)
        else:
            await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/network")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/network", "Network stats retrieved")

    except Exception as e:
        logger.error(f"Error in network_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get network stats: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def netpublic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Public IPv4 (HTTPS) plus local outbound IP, default route, Tailscale when available."""
    user_id = update.effective_user.id
    try:
        await reply_text_safe(update, "🌍 Looking up public and local routing…")
        pub = fetch_public_ipv4()
        stats = get_network_stats()
        out_l = stats.get("outbound_local_ipv4")
        gw = stats.get("default_gateway_ipv4")
        gw_if = stats.get("default_route_iface")
        ts = stats.get("tailscale_ip")

        lines = ["🌍 <b>Public &amp; routing</b>\n"]
        if pub:
            lines.append(f"<b>Public IPv4</b> (outbound, via HTTPS): <code>{escape_telegram_html(pub)}</code>")
        else:
            lines.append("<b>Public IPv4:</b> <i>could not resolve (no route, DNS, or HTTP blocked)</i>")
        if out_l:
            lines.append(f"<b>Local outbound IPv4</b> (socket probe): <code>{escape_telegram_html(out_l)}</code>")
        if gw:
            lines.append(f"<b>Default gateway:</b> <code>{escape_telegram_html(gw)}</code>")
        if gw_if:
            lines.append(f"<b>Default interface:</b> <code>{escape_telegram_html(gw_if)}</code>")
        if ts:
            lines.append(f"<b>Tailscale IPv4:</b> <code>{escape_telegram_html(ts)}</code>")
        lines.append("")
        lines.append("<i>For full per-interface addresses and counters, use <code>/network</code>.</i>")
        message = "\n".join(lines)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/netpublic")
        await save_conversation(user_id, "assistant", message, command_output=None)
        await save_command(user_id, "/netpublic", pub or "unavailable")
    except Exception as e:
        logger.error("Error in netpublic_command: %s", e, exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to resolve public IP: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def netping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ICMP ping to a single host or IPv4/IPv6 literal (fixed packet count)."""
    user_id = update.effective_user.id
    try:
        raw = (context.args[0] if context.args else "").strip()
        if not raw:
            await reply_text_safe(
                update,
                "Usage: <code>/netping 1.1.1.1</code> or <code>/netping nas.lan</code>\n"
                "<i>Hostname must be alphanumeric/labels; IPv4 and IPv6 literals allowed.</i>",
                **_monitoring_kw(),
            )
            return
        host = validate_ping_target(raw)
        if not host:
            await reply_text_safe(
                update,
                format_error_html("Invalid target. Use a hostname like `router.lan` or an IP address."),
                **_monitoring_kw(),
            )
            return

        await reply_text_safe(update, f"📡 Pinging <code>{escape_telegram_html(host)}</code>…", **_monitoring_kw())
        code, out, err = run_ping(host)
        tail = (out or "") + (("\n" + err) if err else "")
        tail = tail.strip() or "(no output)"
        if len(tail) > 3500:
            tail = tail[:3490] + "\n…"

        status = "ok" if code == 0 else f"exit {code}"
        message = (
            f"📡 <b>Ping</b> <code>{escape_telegram_html(host)}</code> — <code>{escape_telegram_html(status)}</code>\n\n"
            f"<pre>{escape_telegram_html(tail)}</pre>"
        )
        await reply_text_chunked(update, message, parse_mode=ParseMode.HTML)

        await save_conversation(user_id, "user", f"/netping {host}")
        await save_conversation(user_id, "assistant", message, command_output=None)
        await save_command(user_id, "/netping", f"{host} rc={code}")
    except Exception as e:
        logger.error("Error in netping_command: %s", e, exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Ping failed: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def uptime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /uptime command - Show system uptime."""
    user_id = update.effective_user.id

    try:
        stats = get_uptime()
        uptime_seconds = stats.get("uptime_seconds", 0)
        uptime_str = format_uptime(uptime_seconds)

        message = f"⏱ <b>System Uptime</b>\n\n{escape_telegram_html(uptime_str)}"
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/uptime")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/uptime", uptime_str)

    except Exception as e:
        logger.error(f"Error in uptime_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get uptime: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /health command - Show system health score."""
    user_id = update.effective_user.id

    try:
        await reply_text_safe(update, "🏥 Analyzing system health...")

        score, issues = calculate_health_score()
        message = format_health_score(score, issues)
        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(
            user_id,
            "user",
            "/health",
        )
        await save_conversation(
            user_id,
            "assistant",
            html_reply_to_context_plain(message),
            command_output=None,
        )
        await save_command(user_id, "/health", f"Score: {score}/100")

    except Exception as e:
        logger.error(f"Error in health_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to calculate health: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def smart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /smart command - Show SMART drive health data."""
    user_id = update.effective_user.id

    try:
        await reply_text_safe(update, "💿 Reading SMART data...")

        drives = get_all_drives()

        if not drives:
            await reply_text_safe(
                update,
                "⚠️ No SMART data available.\n\n"
                "Make sure smartmontools is installed:\n"
                "<code>sudo apt install smartmontools</code>",
                **_monitoring_kw(),
            )
            return

        omv_smart: list = []
        omv_note = None
        if omv_rpc_available():
            omv_smart, e_omv = await fetch_smart_devices()
            if e_omv:
                omv_note = e_omv
        message = format_smart_with_omv(drives, omv_smart, omv_note)

        warnings = check_drive_warnings(drives)
        if warnings:
            wlines = "\n".join(escape_telegram_html(w) for w in warnings)
            message += "\n<b>Warnings:</b>\n" + wlines

        await reply_text_safe(update, message, **_monitoring_kw())

        await save_conversation(user_id, "user", "/smart")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/smart", f"{len(drives)} drives checked")

    except Exception as e:
        logger.error(f"Error in smart_command: {e}", exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get SMART data: {e}"), **_monitoring_kw()
        )


@require_auth
@rate_limit
async def drives_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /drives command - Alias for /smart."""
    await smart_command(update, context)


@require_auth
@rate_limit
async def hdddetail_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SMART + spin/load-cycle counters, hdparm power state, recent sampled history."""
    user_id = update.effective_user.id

    try:
        await reply_text_safe(update, "💿 Reading SMART, power state, and history…")

        drives = get_all_drives()
        if not drives:
            await reply_text_safe(
                update,
                "⚠️ No SMART data available.\n\n"
                "Make sure smartmontools is installed and devices are visible in the container.",
                **_monitoring_kw(),
            )
            return

        for d in drives:
            dev = d.get("device") or ""
            if dev:
                d["power_state"] = get_hdparm_power_state(dev)

        history_by_device: dict = {}
        for d in drives:
            dev = d.get("device") or ""
            if dev:
                history_by_device[dev] = await get_drive_spin_history(dev, limit=14)

        omv_disks: list = []
        omv_note = None
        if omv_rpc_available():
            omv_disks, e_omv = await fetch_disk_enumerate()
            if e_omv:
                omv_note = e_omv

        message = format_hdd_detail_with_omv(drives, history_by_device, omv_disks, omv_note)
        warnings = check_drive_warnings(drives)
        if warnings:
            wlines = "\n".join(escape_telegram_html(w) for w in warnings)
            message += "\n<b>Warnings:</b>\n" + wlines

        await reply_text_chunked(update, message, parse_mode=ParseMode.HTML)

        await save_conversation(user_id, "user", "/hdddetail")
        await save_conversation(
            user_id, "assistant", html_reply_to_context_plain(message), command_output=None
        )
        await save_command(user_id, "/hdddetail", f"{len(drives)} drives")

    except Exception as e:
        logger.error("Error in hdddetail_command: %s", e, exc_info=True)
        await reply_text_safe(
            update, format_error_html(f"Failed to get HDD details: {e}"), **_monitoring_kw()
        )
