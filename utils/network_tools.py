"""
Small network helpers for Telegram commands: public IPv4 lookup and safe ping targets.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import subprocess
import urllib.request

logger = logging.getLogger(__name__)

# Hostnames: letter/digit start/end, labels with dot/hyphen inside (no shell metacharacters).
_PING_HOST_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$")

_PUBLIC_IP_URLS = (
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://ifconfig.me/ip",
)


def validate_ping_target(raw: str) -> str | None:
    """
    Accept a single IPv4/IPv6 literal or a conservative hostname.
    Returns normalized host string or None if rejected.
    """
    s = (raw or "").strip()
    if not s or len(s) > 253:
        return None
    try:
        ipaddress.ip_address(s)
        return s
    except ValueError:
        pass
    if _PING_HOST_RE.fullmatch(s):
        return s
    return None


def fetch_public_ipv4(timeout: float = 8.0) -> str | None:
    """Best-effort outbound public IPv4 via HTTPS (no extra dependencies)."""
    for url in _PUBLIC_IP_URLS:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "NAS-Telegram-Bot/1.0"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
            if body and len(body) <= 45 and not any(c in body for c in "\r\n\t<> "):
                try:
                    ipaddress.IPv4Address(body)
                except ValueError:
                    continue
                return body
        except Exception as e:
            logger.debug("fetch_public_ipv4 %s failed: %s", url, e)
            continue
    return None


def run_ping(host: str, count: int = 4, wait_per_packet: int = 5) -> tuple[int, str, str]:
    """
    Run system ping with fixed argv (no shell). Returns (returncode, stdout, stderr).
    Uses IPv6-specific argv when host parses as IPv6.
    """
    try:
        ver = ipaddress.ip_address(host)
        if isinstance(ver, ipaddress.IPv6Address):
            argv = ["ping", "-6", "-c", str(count), "-W", str(wait_per_packet), host]
        else:
            argv = ["ping", "-c", str(count), "-W", str(wait_per_packet), host]
    except ValueError:
        argv = ["ping", "-c", str(count), "-W", str(wait_per_packet), host]

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15 + count * wait_per_packet,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "ping executable not found in PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "ping timed out"
