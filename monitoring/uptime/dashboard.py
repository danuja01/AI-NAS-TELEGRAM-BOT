"""Optional FastAPI dashboard for live monitor status."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import config

logger = logging.getLogger(__name__)
_server_thread: Optional[threading.Thread] = None
_serving_enabled: bool = True


def is_dashboard_server_running() -> bool:
    return _server_thread is not None and _server_thread.is_alive()


def is_dashboard_serving_requests() -> bool:
    return is_dashboard_server_running() and _serving_enabled


def stop_dashboard_serving() -> None:
    """Reject new requests until enabled again (uvicorn thread may keep running)."""
    global _serving_enabled
    _serving_enabled = False


def start_dashboard(bind: Optional[str] = None) -> bool:
    """Start uvicorn in a background thread. Returns False if bind fails."""
    global _server_thread, _serving_enabled
    if is_dashboard_server_running():
        _serving_enabled = True
        return True

    host = (bind or config.UPTIME_DASHBOARD_BIND or "0.0.0.0").strip()
    allowed = ("127.0.0.1", "::1", "localhost", "0.0.0.0")
    if host not in allowed:
        logger.error("UPTIME_DASHBOARD bind not allowed: %s", host)
        return False

    def run():
        try:
            import uvicorn
            from monitoring.uptime.dashboard_app import app

            uvicorn.run(
                app,
                host=host,
                port=config.UPTIME_DASHBOARD_PORT,
                log_level="warning",
            )
        except Exception as e:
            logger.error("Dashboard server failed: %s", e)

    _server_thread = threading.Thread(target=run, name="uptime-dashboard", daemon=True)
    _server_thread.start()
    _serving_enabled = True
    logger.info("Uptime dashboard listening on http://%s:%s", host, config.UPTIME_DASHBOARD_PORT)
    return True
