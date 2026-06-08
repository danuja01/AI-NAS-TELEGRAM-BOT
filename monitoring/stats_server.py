"""
Lightweight GET /stats HTTP server for LAN dashboards (Homarr, scripts).

Binds STATS_HTTP_BIND:STATS_HTTP_PORT (compose default 0.0.0.0:8765).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse

import config

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
    limit = max(1, config.STATS_HTTP_RATE_PER_MINUTE)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _make_handler():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("%s - %s", self.address_string(), fmt % args)

        def _send_json(self, status: int, payload: dict):
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            path = urlparse(self.path).path.rstrip("/") or "/"
            ip = _client_ip(self)

            if path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            if path != "/stats":
                self.send_response(404)
                self.end_headers()
                return

            if not _rate_limit_ok(ip):
                logger.warning("stats HTTP: rate limit from %s", ip)
                self.send_response(429)
                self.end_headers()
                return

            from services.system_monitor import get_simple_stats

            payload = get_simple_stats()
            logger.info("stats HTTP: served /stats to %s", ip)
            self._send_json(200, payload)

    return Handler


def start_stats_server():
    """Start GET /stats on STATS_HTTP_BIND:STATS_HTTP_PORT."""
    global _server, _server_thread
    if not config.STATS_HTTP_ENABLED:
        logger.info("STATS_HTTP_ENABLED=false; /stats HTTP server disabled")
        return
    if _server is not None:
        return

    bind = (config.STATS_HTTP_BIND or "0.0.0.0").strip()
    port = config.STATS_HTTP_PORT
    loopback = ("127.0.0.1", "::1", "localhost")
    if bind not in loopback and bind != "0.0.0.0":
        logger.error("STATS_HTTP_BIND must be 127.0.0.1 or 0.0.0.0; got %s", bind)
        return

    try:
        _server = HTTPServer((bind, port), _make_handler())
    except OSError as e:
        logger.error("stats HTTP bind failed on %s:%s: %s", bind, port, e)
        return

    def serve():
        logger.info("Stats HTTP listening on %s:%s (GET /stats, GET /health)", bind, port)
        _server.serve_forever()

    _server_thread = threading.Thread(target=serve, name="stats-http", daemon=True)
    _server_thread.start()


def stop_stats_server():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server = None
    _server_thread = None
