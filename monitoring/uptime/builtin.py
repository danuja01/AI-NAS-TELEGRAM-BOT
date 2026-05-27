"""Seed built-in monitors and auto-discover Docker containers."""

from __future__ import annotations

import logging

import config
from monitoring.uptime import store

logger = logging.getLogger(__name__)


async def ensure_builtin_monitors() -> None:
    """Create default connectivity monitors if missing."""
    builtins = []
    if config.UPTIME_BUILTIN_INTERNET:
        builtins.extend([
            ("internet-https", "https", config.UPTIME_BUILTIN_HTTP_URL, 120),
            ("internet-ping", "ping", "1.1.1.1", 120),
        ])
    if config.UPTIME_BUILTIN_DNS_HOST:
        builtins.append(
            ("dns-resolve", "dns", config.UPTIME_BUILTIN_DNS_HOST, 180),
        )
    for name, mtype, target, interval in builtins:
        existing = await store.get_monitor_by_name(name)
        if existing:
            continue
        try:
            await store.create_monitor(
                name,
                mtype,
                target,
                interval_seconds=interval,
                tags=["builtin", "connectivity"],
            )
            logger.info("Created builtin monitor: %s", name)
        except Exception as e:
            logger.debug("builtin monitor %s: %s", name, e)

    # systemd units from config
    if (config.HOST_EXEC_MODE or "").lower() != "none":
        for unit in config.MONITOR_SYSTEMD_UNITS:
            name = f"systemd-{unit}"
            if await store.get_monitor_by_name(name):
                continue
            try:
                await store.create_monitor(
                    name,
                    "systemd",
                    unit,
                    interval_seconds=120,
                    tags=["builtin", "systemd"],
                )
            except Exception:
                pass

    if config.UPTIME_BUILTIN_TAILSCALE and config.NETWORK_TAILSCALE_CLI:
        if not await store.get_monitor_by_name("tailscale-mesh"):
            try:
                await store.create_monitor(
                    "tailscale-mesh",
                    "tailscale",
                    "online",
                    interval_seconds=120,
                    tags=["builtin", "network", "tailscale"],
                )
            except Exception:
                pass

    if config.UPTIME_BUILTIN_CLOUDFLARED:
        if not await store.get_monitor_by_name("cloudflare-tunnel"):
            try:
                await store.create_monitor(
                    "cloudflare-tunnel",
                    "cloudflared",
                    config.UPTIME_CLOUDFLARED_TARGET,
                    interval_seconds=120,
                    tags=["builtin", "network", "cloudflare"],
                )
            except Exception:
                pass


async def sync_docker_monitors() -> None:
    """Auto-create docker-type monitors for running containers."""
    from services.docker_service import list_containers

    containers = list_containers(all_containers=True, include_stats=False)
    for c in containers:
        if config.docker_container_ignored_for_alerts(c.get("name", "")):
            continue
        name = f"docker-{c.get('name', '').lstrip('/')}"
        if await store.get_monitor_by_name(name):
            continue
        if (c.get("status") or "").lower() not in ("running", "restarting"):
            continue
        try:
            await store.create_monitor(
                name,
                "docker",
                c.get("name", ""),
                interval_seconds=60,
                tags=["auto", "docker"],
            )
            logger.info("Auto monitor for container %s", c.get("name"))
        except Exception:
            pass
