"""
Optional HTTP hook for cron/job notifications (binds CRON_NOTIFY_BIND:CRON_NOTIFY_PORT).

POST /notify with JSON:
  {"secret": "...", "job": "backup", "status": "ok|fail", "message": "..."}

secret must match CRON_NOTIFY_SECRET. Intended for localhost + docker exec curl from host.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Awaitable, Callable, Optional

import config
from utils.formatters import escape_telegram_html

logger = logging.getLogger(__name__)

_server: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_rate_by_ip: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    return handler.client_address[0] if handler.client_address else "unknown"


def _rate_limit_ok(ip: str) -> bool:
    now = time.time()
    bucket = _rate_by_ip[ip]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= config.CRON_NOTIFY_RATE_PER_MINUTE:
        return False
    bucket.append(now)
    return True


def _secret_ok(provided: str) -> bool:
    expected = config.CRON_NOTIFY_SECRET or ""
    if not expected:
        return False
    return hmac.compare_digest(str(provided), expected)


def _make_handler(schedule_plain_text: Callable[[str], None]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def do_POST(self):  # noqa: N802
            if self.path.rstrip("/") != "/notify":
                self.send_response(404)
                self.end_headers()
                return

            ip = _client_ip(self)
            if not _rate_limit_ok(ip):
                logger.warning("cron_notify: rate limit from %s", ip)
                self.send_response(429)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 65536:
                self.send_response(413)
                self.end_headers()
                return

            body = self.rfile.read(length).decode("utf-8", errors="replace")
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"invalid json")
                return

            if not _secret_ok(data.get("secret", "")):
                logger.warning("cron_notify: bad secret from %s", ip)
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
                if not config.CRON_NOTIFY_SECRET:
                    self.send_response(503)
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def start_cron_notify_server(loop: asyncio.AbstractEventLoop, send_html: Callable[[str], Awaitable[None]]):
    global _server, _server_thread
    if not config.CRON_NOTIFY_SECRET:
        logger.info("CRON_NOTIFY_SECRET unset; cron HTTP notify hook disabled")
        return

    bind = (config.CRON_NOTIFY_BIND or "127.0.0.1").strip()
    if bind not in ("127.0.0.1", "::1", "localhost"):
        logger.error(
            "CRON_NOTIFY_BIND must be loopback (127.0.0.1); got %s — refusing to start",
            bind,
        )
        return

    if len(config.CRON_NOTIFY_SECRET) < 24:
        logger.warning("CRON_NOTIFY_SECRET is short; use at least 24 random bytes")

    def schedule_notify(html_text: str):
        try:
            asyncio.run_coroutine_threadsafe(send_html(html_text), loop)
        except Exception as e:
            logger.error("schedule_notify: %s", e)

    handler = _make_handler(schedule_notify)
    try:
        _server = HTTPServer((bind, config.CRON_NOTIFY_PORT), handler)
    except OSError as e:
        logger.error("cron_notify bind failed: %s", e)
        return

    def serve():
        logger.info("Cron notify HTTP listening on %s:%s", bind, config.CRON_NOTIFY_PORT)
        _server.serve_forever()

    _server_thread = threading.Thread(target=serve, name="cron-notify", daemon=True)
    _server_thread.start()


def stop_cron_notify_server():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server = None
    _server_thread = None
