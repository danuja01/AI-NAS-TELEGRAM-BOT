"""
Shared catalog of read-only host_runner profiles the agent may invoke (SSH/nsenter).

The evaluator LLM may only map natural language to these names; execution never
runs arbitrary shell from model text.
"""

from __future__ import annotations

from typing import Final, FrozenSet, List

HOST_READONLY_PROFILES_ORDERED: Final[List[str]] = [
    "apt_list_upgradable",
    "reboot_required",
    "systemctl_is_active",
    "journal_tail",
    "systemctl_failed",
    "du_path",
    "find_large_files",
]

HOST_READONLY_PROFILES: Final[FrozenSet[str]] = frozenset(HOST_READONLY_PROFILES_ORDERED)
