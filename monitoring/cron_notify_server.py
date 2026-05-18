"""
Optional HTTP hook for cron/job notifications (binds CRON_NOTIFY_BIND:CRON_NOTIFY_PORT).

POST /notify with JSON:
  {"secret": "...", "job": "backup", "status": "ok|fail", "message": "..."}

secret must match CRON_NOTIFY_SECRET. Intended for localhost + docker exec curl from host.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Awaitable, Callable, Optional

import config
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)

_server: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None


def _make_handler(schedule_plain_text: Callable[[str], None]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/notify":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"invalid json")
                return

            secret = data.get("secret", "")
            if not config.CRON_NOTIFY_SECRET or secret != config.CRON_NOTIFY_SECRET:
                logger.warning("cron_notify: bad secret from %s", self.client_address[0])
                self.send_response(403)
                self.end_headers()
                return

            job = escape_telegram_html(str(data.get("job", "job")))
            status = escape_telegram_html(str(data.get("status", "unknown")))
            msg = escape_telegram_html(str(data.get("message", "")))

            text = (
                f"🗓 <b>Cron / scheduled job</b>\n"
                f"<b>Job</b>: <code>{job}</code>\n"
                f"<b>Status</b>: <code>{status}</code>\n"
            )
            if msg:
                text += f"\n{msg}"

            schedule_plain_text(text)
            self.send_response(204)
            self.end_headers()

        def do_GET(self):  # noqa: N802
            if self.path.rstrip("/") == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def start_cron_notify_server(loop: asyncio.AbstractEventLoop, send_html: Callable[[str], Awaitable[None]]):
    """
    send_html: async (html str) -> None, broadcast to admins.
    """
    global _server, _server_thread
    if not config.CRON_NOTIFY_SECRET:
        logger.info("CRON_NOTIFY_SECRET unset; cron HTTP notify hook disabled")
        return

    def schedule_notify(html_text: str):
        try:
            asyncio.run_coroutine_threadsafe(send_html(html_text), loop)
        except Exception as e:
            logger.error("schedule_notify: %s", e)

    handler = _make_handler(schedule_notify)
    try:
        _server = HTTPServer((config.CRON_NOTIFY_BIND, config.CRON_NOTIFY_PORT), handler)
    except OSError as e:
        logger.error("cron_notify bind failed: %s", e)
        return

    def serve():
        logger.info(
            "Cron notify HTTP listening on %s:%s",
            config.CRON_NOTIFY_BIND,
            config.CRON_NOTIFY_PORT,
        )
        _server.serve_forever()

    _server_thread = threading.Thread(target=serve, name="cron-notify", daemon=True)
    _server_thread.start()


def stop_cron_notify_server():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server = None
    _server_thread = None
