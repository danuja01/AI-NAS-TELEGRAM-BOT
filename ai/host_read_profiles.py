"""
OpenAI tool enum for ``nas_host_readonly_profile`` (read-only host_runner names).

Canonical names: ``services.readonly.profiles.PROFILE_NAMES_FOR_AGENT``.
"""

from __future__ import annotations

from typing import Final, FrozenSet, List

from services.readonly.profiles import PROFILE_NAMES_FOR_AGENT

_PRIORITY: Final[List[str]] = [
    "apt_list_upgradable",
    "reboot_required",
    "systemctl_is_active",
    "journal_tail",
    "systemctl_failed",
    "du_path",
    "find_large_files",
]

_PRI_SET = frozenset(_PRIORITY)
HOST_READONLY_PROFILES_ORDERED: Final[List[str]] = [
    p for p in _PRIORITY if p in PROFILE_NAMES_FOR_AGENT
] + sorted(PROFILE_NAMES_FOR_AGENT - _PRI_SET, key=str)
HOST_READONLY_PROFILES: Final[FrozenSet[str]] = frozenset(HOST_READONLY_PROFILES_ORDERED)
