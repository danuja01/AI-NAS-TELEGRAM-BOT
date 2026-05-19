"""
Shared catalog of read-only host_runner profiles the agent may invoke (SSH/nsenter).

The evaluator LLM may only map natural language to these names; execution never
runs arbitrary shell from model text.
"""

from __future__ import annotations

from typing import Final, FrozenSet, List

from services.host_runner_readonly import extended_readonly_profile_names

# Original allowlist (kept first for stable UX / docs); extended names follow alphabetically.
_ORIGINAL_ORDERED: Final[List[str]] = [
    "apt_list_upgradable",
    "reboot_required",
    "systemctl_is_active",
    "journal_tail",
    "systemctl_failed",
    "du_path",
    "find_large_files",
]

_EXT_NAMES = extended_readonly_profile_names()
_ORIG_SET = frozenset(_ORIGINAL_ORDERED)

HOST_READONLY_PROFILES_ORDERED: Final[List[str]] = _ORIGINAL_ORDERED + sorted(
    _EXT_NAMES - _ORIG_SET,
    key=str,
)
HOST_READONLY_PROFILES: Final[FrozenSet[str]] = frozenset(HOST_READONLY_PROFILES_ORDERED)
