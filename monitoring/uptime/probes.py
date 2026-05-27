"""Probe implementations for uptime monitors."""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp

from utils.network_tools import run_ping, validate_ping_target

logger = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    success: bool
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    error_message: str = ""


async def run_probe(monitor: Dict[str, Any]) -> ProbeResult:
    mtype = (monitor.get("type") or "").lower()
    runners = {
        "http": _probe_http,
        "https": _probe_https,
        "tcp": _probe_tcp,
        "ping": _probe_ping,
        "dns": _probe_dns,
        "ssl": _probe_ssl,
        "keyword": _probe_keyword,
        "docker": _probe_docker,
        "process": _probe_systemd,
        "systemd": _probe_systemd,
        "push": _probe_push,
    }
    fn = runners.get(mtype)
    if not fn:
        return ProbeResult(False, error_message=f"Unknown monitor type: {mtype}")
    timeout = max(1, int(monitor.get("timeout_seconds") or 10))
    retries = max(0, int(monitor.get("retries") or 0))
    last = ProbeResult(False, error_message="no attempts")
    for attempt in range(retries + 1):
        try:
            last = await fn(monitor, timeout)
            if last.success:
                return last
        except Exception as e:
            last = ProbeResult(False, error_message=str(e)[:500])
        if attempt < retries:
            await asyncio.sleep(0.5)
    return last


async def _probe_http(monitor: Dict, timeout: int, use_tls: bool = False) -> ProbeResult:
    target = monitor["target"].strip()
    if not target.startswith("http"):
        target = ("https://" if use_tls else "http://") + target
    expected = monitor.get("expected_status")
    t0 = asyncio.get_event_loop().time()
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(target, allow_redirects=True, ssl=use_tls) as resp:
                latency = (asyncio.get_event_loop().time() - t0) * 1000
                ok = 200 <= resp.status < 400
                if expected is not None:
                    ok = resp.status == int(expected)
                if not ok:
                    return ProbeResult(
                        False,
                        latency,
                        resp.status,
                        f"HTTP {resp.status}",
                    )
                return ProbeResult(True, latency, resp.status)
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


async def _probe_https(monitor: Dict, timeout: int) -> ProbeResult:
    return await _probe_http(monitor, timeout, use_tls=True)


async def _probe_keyword(monitor: Dict, timeout: int) -> ProbeResult:
    base = await _probe_http(monitor, timeout)
    if not base.success:
        return base
    keyword = (monitor.get("keyword") or "").strip()
    if not keyword:
        return base
    target = monitor["target"].strip()
    if not target.startswith("http"):
        target = "http://" + target
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(target) as resp:
                body = await resp.text(errors="replace")
                if keyword.lower() not in body.lower():
                    return ProbeResult(
                        False,
                        base.latency_ms,
                        resp.status,
                        f"Keyword '{keyword}' not found",
                    )
                return base
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


async def _probe_tcp(monitor: Dict, timeout: int) -> ProbeResult:
    target = monitor["target"].strip()
    host, port = target, 80
    if ":" in target:
        host, _, port_s = target.rpartition(":")
        port = int(port_s)
    t0 = asyncio.get_event_loop().time()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_tcp_connect, host, port, timeout),
            timeout=timeout + 2,
        )
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        return ProbeResult(True, latency)
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


def _tcp_connect(host: str, port: int, timeout: int) -> None:
    with socket.create_connection((host, port), timeout=timeout):
        pass


async def _probe_ping(monitor: Dict, timeout: int) -> ProbeResult:
    host = validate_ping_target(monitor["target"])
    if not host:
        return ProbeResult(False, error_message="Invalid ping target")
    t0 = asyncio.get_event_loop().time()
    rc, out, err = await asyncio.to_thread(run_ping, host, 1, min(5, timeout))
    latency = (asyncio.get_event_loop().time() - t0) * 1000
    if rc == 0:
        return ProbeResult(True, latency)
    return ProbeResult(False, latency, error_message=(err or out or "ping failed")[:500])


async def _probe_dns(monitor: Dict, timeout: int) -> ProbeResult:
    host = monitor["target"].strip()
    t0 = asyncio.get_event_loop().time()
    try:
        await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, None),
            timeout=timeout,
        )
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        return ProbeResult(True, latency)
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


async def _probe_ssl(monitor: Dict, timeout: int) -> ProbeResult:
    target = monitor["target"].strip()
    host = target
    port = 443
    if ":" in target:
        host, _, port_s = target.rpartition(":")
        port = int(port_s)
    warn_days = int((monitor.get("keyword") or "14").strip() or "14")
    t0 = asyncio.get_event_loop().time()
    try:
        days_left = await asyncio.wait_for(
            asyncio.to_thread(_ssl_days_remaining, host, port),
            timeout=timeout + 2,
        )
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        if days_left < 0:
            return ProbeResult(False, latency, error_message="Certificate expired")
        if days_left <= warn_days:
            return ProbeResult(
                False,
                latency,
                error_message=f"SSL expires in {days_left} days",
            )
        return ProbeResult(True, latency, error_message=f"OK ({days_left}d)")
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


def _ssl_days_remaining(host: str, port: int) -> int:
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
    exp = cert.get("notAfter")
    if not exp:
        return 999
    exp_dt = datetime.strptime(exp, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    delta = exp_dt - datetime.now(timezone.utc)
    return delta.days


async def _probe_docker(monitor: Dict, timeout: int) -> ProbeResult:
    from services.docker_service import get_container

    name = monitor["target"].strip().lstrip("/")
    t0 = asyncio.get_event_loop().time()
    try:
        container = await asyncio.to_thread(get_container, name)
        status = (container.status or "").lower()
        state = container.attrs.get("State") or {}
        health = (state.get("Health") or {}).get("Status", "").lower()
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        if status != "running":
            return ProbeResult(False, latency, error_message=f"Container {status}")
        if health == "unhealthy":
            return ProbeResult(False, latency, error_message="Healthcheck unhealthy")
        return ProbeResult(True, latency)
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


async def _probe_systemd(monitor: Dict, timeout: int) -> ProbeResult:
    import config
    from services.host_runner import run_profile

    unit = monitor["target"].strip()
    if (config.HOST_EXEC_MODE or "").lower() == "none":
        return ProbeResult(False, error_message="Host exec disabled")
    t0 = asyncio.get_event_loop().time()
    try:
        r = await asyncio.wait_for(
            asyncio.to_thread(run_profile, "systemctl_is_active", extra_args=[unit]),
            timeout=timeout,
        )
        latency = (asyncio.get_event_loop().time() - t0) * 1000
        active = r.ok and (r.stdout or "").strip() == "active"
        if active:
            return ProbeResult(True, latency)
        return ProbeResult(
            False,
            latency,
            error_message=(r.stderr or r.stdout or "not active")[:500],
        )
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])


async def _probe_push(monitor: Dict, timeout: int) -> ProbeResult:
    from monitoring.uptime.store import get_monitor

    mid = monitor["id"]
    m = await get_monitor(mid)
    if not m:
        return ProbeResult(False, error_message="Monitor missing")
    last = m.get("last_check")
    if not last:
        return ProbeResult(False, error_message="No push heartbeat yet")
    # Push monitors: success if heartbeat within 2x interval
    iv = max(60, int(m.get("interval_seconds") or 60))
    try:
        from datetime import datetime

        last_dt = datetime.fromisoformat(str(last).replace("Z", ""))
        age = (datetime.utcnow() - last_dt).total_seconds()
        if age <= iv * 2:
            return ProbeResult(True, age * 1000)
        return ProbeResult(False, error_message=f"Stale push ({int(age)}s)")
    except Exception as e:
        return ProbeResult(False, error_message=str(e)[:500])
