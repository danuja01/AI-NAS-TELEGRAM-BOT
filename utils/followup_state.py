"""
Shared state for 'send your next message' flows (menu sends /command without args).
"""

from __future__ import annotations

import time
from typing import Optional

from telegram.ext import ContextTypes

FOLLOWUP_TTL_SEC = 900

# AI commands (values match ai_cmds dispatch)
AI_PENDING_KEY = "pending_ai_cmd"
AI_PENDING_TS = "pending_ai_ts"

# Other commands
CMD_PENDING_KEY = "pending_cmd_followup"
CMD_PENDING_TS = "pending_cmd_followup_ts"

FOLLOWUP_ROOTLOGIN = "rootlogin"
FOLLOWUP_SSH = "ssh"
FOLLOWUP_DOCKER_RESTART = "docker_restart"
FOLLOWUP_DOCKER_STOP = "docker_stop"
FOLLOWUP_DOCKER_DSTART = "docker_dstart"
FOLLOWUP_DOCKER_LOGS = "docker_logs"
FOLLOWUP_RESTART_SERVICE = "restart_service"
FOLLOWUP_FIND = "find"
FOLLOWUP_DOWNLOAD = "download"


def clear_ai_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(AI_PENDING_KEY, None)
    context.user_data.pop(AI_PENDING_TS, None)


def clear_cmd_pending(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(CMD_PENDING_KEY, None)
    context.user_data.pop(CMD_PENDING_TS, None)


def clear_all_followup(context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_ai_pending(context)
    clear_cmd_pending(context)


def _ts_alive(ts: Optional[float]) -> bool:
    if ts is None:
        return False
    if (time.time() - ts) > FOLLOWUP_TTL_SEC:
        return False
    return True


def get_ai_pending(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    cmd = context.user_data.get(AI_PENDING_KEY)
    ts = context.user_data.get(AI_PENDING_TS)
    if not cmd or not _ts_alive(ts):
        if cmd:
            clear_ai_pending(context)
        return None
    return str(cmd)


def get_cmd_pending(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
    cmd = context.user_data.get(CMD_PENDING_KEY)
    ts = context.user_data.get(CMD_PENDING_TS)
    if not cmd or not _ts_alive(ts):
        if cmd:
            clear_cmd_pending(context)
        return None
    return str(cmd)


def set_ai_pending_exclusive(context: ContextTypes.DEFAULT_TYPE, cmd: str) -> None:
    clear_cmd_pending(context)
    context.user_data[AI_PENDING_KEY] = cmd
    context.user_data[AI_PENDING_TS] = time.time()


def set_cmd_pending_exclusive(context: ContextTypes.DEFAULT_TYPE, cmd: str) -> None:
    clear_ai_pending(context)
    context.user_data[CMD_PENDING_KEY] = cmd
    context.user_data[CMD_PENDING_TS] = time.time()


def has_any_pending_in_userdata(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return AI_PENDING_KEY in context.user_data or CMD_PENDING_KEY in context.user_data
