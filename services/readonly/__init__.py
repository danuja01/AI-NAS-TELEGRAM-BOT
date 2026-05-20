"""
Read-only host command profiles (fixed argv, no shell).

All argv construction for ``host_runner.run_profile`` read-only names lives under
this package; ``host_runner`` keeps only mutating operations (apt update/clean,
omv-upgrade).
"""

from __future__ import annotations

from services.readonly.profiles import (
    ALL_READONLY_PROFILE_NAMES,
    PROFILE_NAMES_FOR_AGENT,
    PROFILES_REQUIRING_TOOL_ARGS,
    ZERO_EXTRA_AGENT_PROFILES,
    build_readonly_inner,
)

__all__ = [
    "ALL_READONLY_PROFILE_NAMES",
    "PROFILE_NAMES_FOR_AGENT",
    "PROFILES_REQUIRING_TOOL_ARGS",
    "ZERO_EXTRA_AGENT_PROFILES",
    "build_readonly_inner",
]
