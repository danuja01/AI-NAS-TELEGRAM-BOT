"""
Root session manager for temporary elevated file system access.
"""

import logging
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import asyncio

import bcrypt

import config

logger = logging.getLogger(__name__)


class RootSessionManager:
    """
    Manages temporary root sessions for users.

    Elevated sessions expand allowed paths to configured NAS roots (not full /).
    Sessions expire after 30 minutes. All root access is logged.
    """

    _sessions: Dict[int, Dict[str, Any]] = {}
    SESSION_DURATION = timedelta(minutes=30)

    @classmethod
    def _verify_password(cls, password: str) -> bool:
        stored = getattr(config, "ROOT_PASSWORD", "") or ""
        if not stored:
            logger.warning("ROOT_PASSWORD not configured")
            return False
        if stored.startswith("$2"):
            try:
                return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
            except ValueError:
                logger.error("ROOT_PASSWORD bcrypt hash is invalid")
                return False
        logger.warning(
            "ROOT_PASSWORD is plaintext; set a bcrypt hash (scripts/hash_root_password.py)"
        )
        return hmac.compare_digest(password, stored)

    @classmethod
    def get_elevated_allowed_paths(cls) -> List[str]:
        """Paths available during an active root session (not unrestricted /)."""
        candidates = []
        for raw in (
            config.DOCUMENT_PATH or "/app/documents",
            getattr(config, "DISK_ROOT_PATH", "") or "",
            *config.ALLOWED_PATHS,
            "/app/data",
        ):
            p = str(raw).strip()
            if p and p not in candidates:
                candidates.append(p)
        return candidates or ["/app/documents"]

    @classmethod
    def authenticate(cls, user_id: int, password: str) -> bool:
        from utils.security import is_root_login_locked, record_root_login_failure, clear_root_login_failures

        if is_root_login_locked(user_id):
            logger.warning("Root login blocked (lockout) for user %s", user_id)
            return False

        if not cls._verify_password(password):
            record_root_login_failure(user_id)
            logger.warning("Failed root login attempt by user %s", user_id)
            return False

        clear_root_login_failures(user_id)
        now = datetime.now()
        expires_at = now + cls.SESSION_DURATION
        cls._sessions[user_id] = {
            "started_at": now,
            "expires_at": expires_at,
            "working_dir": None,
        }
        logger.warning("Root session created for user %s (expires at %s)", user_id, expires_at)
        return True

    @classmethod
    def is_root_session_active(cls, user_id: int) -> bool:
        if user_id not in cls._sessions:
            return False
        session = cls._sessions[user_id]
        if datetime.now() > session["expires_at"]:
            cls.logout(user_id)
            return False
        return True

    @classmethod
    def get_allowed_paths_for_user(cls, user_id: int) -> List[str]:
        if cls.is_root_session_active(user_id):
            paths = cls.get_elevated_allowed_paths()
            logger.info("User %s root session paths: %s", user_id, paths)
            return paths
        return config.ALLOWED_PATHS

    @classmethod
    def set_working_directory(cls, user_id: int, path: str) -> bool:
        if not cls.is_root_session_active(user_id):
            logger.warning("set_working_dir without root session user=%s", user_id)
            return False
        cls._sessions[user_id]["working_dir"] = path
        logger.info("Working directory set for user %s: %s", user_id, path)
        return True

    @classmethod
    def get_working_directory(cls, user_id: int) -> Optional[str]:
        if not cls.is_root_session_active(user_id):
            return None
        return cls._sessions[user_id].get("working_dir")

    @classmethod
    def logout(cls, user_id: int) -> bool:
        if user_id in cls._sessions:
            duration = datetime.now() - cls._sessions[user_id]["started_at"]
            del cls._sessions[user_id]
            logger.warning("Root session ended for user %s (duration: %s)", user_id, duration)
            return True
        return False

    @classmethod
    def get_session_info(cls, user_id: int) -> Optional[Dict[str, Any]]:
        if not cls.is_root_session_active(user_id):
            return None
        session = cls._sessions[user_id]
        remaining = session["expires_at"] - datetime.now()
        return {
            "active": True,
            "started_at": session["started_at"],
            "expires_at": session["expires_at"],
            "remaining_seconds": int(remaining.total_seconds()),
            "remaining_minutes": int(remaining.total_seconds() // 60),
        }

    @classmethod
    async def cleanup_expired_sessions(cls):
        while True:
            try:
                now = datetime.now()
                for user_id in list(cls._sessions.keys()):
                    if now > cls._sessions[user_id]["expires_at"]:
                        cls.logout(user_id)
                        logger.info("Auto-expired root session for user %s", user_id)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error("Error in session cleanup: %s", e)
                await asyncio.sleep(60)

    @classmethod
    def get_active_sessions(cls) -> Dict[int, Dict[str, Any]]:
        active = {}
        for user_id in list(cls._sessions.keys()):
            info = cls.get_session_info(user_id)
            if info:
                active[user_id] = info
        return active
