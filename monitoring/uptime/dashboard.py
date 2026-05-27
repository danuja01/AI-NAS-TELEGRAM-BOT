"""Optional FastAPI dashboard for live monitor status."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

import config

logger = logging.getLogger(__name__)
_server_thread: Optional[threading.Thread] = None


def start_dashboard() -> None:
    global _server_thread
    if _server_thread:
        return
    bind = config.UPTIME_DASHBOARD_BIND
    if bind not in ("127.0.0.1", "::1", "localhost"):
        logger.error("UPTIME_DASHBOARD_BIND must be loopback; got %s", bind)
        return

    def run():
        try:
            import uvicorn
            from monitoring.uptime.dashboard_app import app

            uvicorn.run(
                app,
                host=bind,
                port=config.UPTIME_DASHBOARD_PORT,
                log_level="warning",
            )
        except Exception as e:
            logger.error("Dashboard server failed: %s", e)

    _server_thread = threading.Thread(target=run, name="uptime-dashboard", daemon=True)
    _server_thread.start()
    logger.info(
        "Uptime dashboard on http://%s:%s",
        bind,
        config.UPTIME_DASHBOARD_PORT,
    )


def stop_dashboard() -> None:
    pass  # uvicorn daemon thread stops with process
