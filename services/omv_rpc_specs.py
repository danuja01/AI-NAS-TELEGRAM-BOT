"""
Static allowlist for host-side `omv-rpc` invocations.

Only these (service, method, params JSON) triples may be executed from the bot.
`params` None means omit the fourth CLI argument (PHP receives null).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# key -> (service, method, params_json_or_none)
OMV_RPC_CALLS: Dict[str, Tuple[str, str, Optional[str]]] = {
    "disk_enumerate": ("DiskMgmt", "enumerateDevices", None),
    "filesystem_mounted": ("FileSystemMgmt", "enumerateMountedFilesystems", '{"includeroot": true}'),
    "smart_enumerate": ("Smart", "enumerateDevices", None),
    "smart_list": (
        "Smart",
        "getList",
        '{"start":0,"limit":9999,"sortfield":"devicename","sortdir":"ASC"}',
    ),
    "raid_candidates": ("RaidMgmt", "getCandidates", None),
}


def get_omv_rpc_call(key: str) -> Tuple[str, str, Optional[str]]:
    if key not in OMV_RPC_CALLS:
        raise KeyError(key)
    return OMV_RPC_CALLS[key]
