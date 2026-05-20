"""
Catalog of read-only ``host_runner.run_profile`` names exposed to the AI.

The canonical set is ``all_agent_host_readonly_names()`` in
``services/host_runner_readonly`` (legacy runner profiles + extended fixed-argv
profiles). This module only defines **display order** for the OpenAI tool enum:
original runner profiles first, then the rest sorted alphabetically.
"""

from __future__ import annotations

from typing import Final, FrozenSet, List

from services.host_runner_readonly import all_agent_host_readonly_names

_LEGACY_FIRST: Final[List[str]] = [
    "apt_list_upgradable",
    "reboot_required",
    "systemctl_is_active",
    "journal_tail",
    "systemctl_failed",
    "du_path",
    "find_large_files",
]

_ALL = all_agent_host_readonly_names()
_LEGACY_SET = frozenset(_LEGACY_FIRST)

HOST_READONLY_PROFILES_ORDERED: Final[List[str]] = _LEGACY_FIRST + sorted(
    _ALL - _LEGACY_SET,
    key=str,
)
HOST_READONLY_PROFILES: Final[FrozenSet[str]] = frozenset(HOST_READONLY_PROFILES_ORDERED)
