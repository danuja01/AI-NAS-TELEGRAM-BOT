"""Start/stop serving the uptime dashboard (thread + runtime flag)."""

from __future__ import annotations

import logging

import config
from monitoring.uptime import dashboard_settings
from monitoring.uptime.dashboard import (
    is_dashboard_server_running,
    start_dashboard,
    stop_dashboard_serving,
)

logger = logging.getLogger(__name__)


async def ensure_dashboard_server() -> bool:
    """Start HTTP server if needed. Returns False on bind failure."""
    if is_dashboard_server_running():
        return True
    listen = (config.UPTIME_DASHBOARD_LISTEN or "0.0.0.0").strip()
    return start_dashboard(bind=listen)


async def enable_dashboard_via_bot() -> tuple[bool, str]:
    """Enable runtime dashboard and start server."""
    await dashboard_settings.set_runtime_enabled(True)
    if not await ensure_dashboard_server():
        await dashboard_settings.set_runtime_enabled(False)
        return False, (
            "Could not start dashboard (port in use or bind failed). "
            f"Check port {config.UPTIME_DASHBOARD_PORT} and docker compose ports."
        )
    return True, "Dashboard enabled."


async def disable_dashboard_via_bot() -> str:
    await dashboard_settings.set_runtime_enabled(False)
    stop_dashboard_serving()
    return "Dashboard disabled. Link will not work until you turn it on again."


async def dashboard_status_text() -> str:
    import config
    from utils.formatters import escape_telegram_html

    runtime = await dashboard_settings.is_runtime_enabled()
    running = is_dashboard_server_running()
    env_auto = config.UPTIME_DASHBOARD_ENABLED
    host = dashboard_settings.public_host()
    port = config.UPTIME_DASHBOARD_PORT

    lines = [
        "📊 <b>Uptime dashboard</b>\n",
        f"<b>Bot toggle</b>: {'ON' if runtime else 'OFF'}",
        f"<b>HTTP server</b>: {'running' if running else 'stopped'}",
        f"<b>Auto on boot</b> (<code>UPTIME_DASHBOARD_ENABLED</code>): "
        f"{'yes' if env_auto else 'no'}",
        f"<b>Public host</b>: <code>{escape_telegram_html(host)}</code>",
        f"<b>Port</b>: <code>{port}</code>\n",
        "<b>Commands</b>:",
        "<code>/monitor_dashboard on</code> — enable + start",
        "<code>/monitor_dashboard off</code> — disable",
        "<code>/monitor_dashboard link</code> — Tailscale URL",
    ]
    if runtime and running:
        lines.append("\n" + dashboard_settings.TAILSCALE_ACCESS_NOTE)
    return "\n".join(lines)
