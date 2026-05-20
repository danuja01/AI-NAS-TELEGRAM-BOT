"""In-code limits for bounded read-only host probes (no .env toggles)."""

from __future__ import annotations

from typing import Final

# host_tail_follow_scan: GNU coreutils `timeout` around `tail -f`
TAIL_FOLLOW_TIMEOUT_SECONDS: Final[int] = 20

# host_ping: loopback only (no LAN/internet probing from the AI tool path)
PING_LOOPBACK_IPV4: Final[str] = "127.0.0.1"
