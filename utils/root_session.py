"""
Root session manager for temporary elevated file system access.
Allows users to authenticate and gain temporary access to all paths.
"""

import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import asyncio

import config

logger = logging.getLogger(__name__)


class RootSessionManager:
    """
    Manages temporary root sessions for users.
    
    Root sessions allow access to all paths (/) for a limited time.
    Sessions expire after 30 minutes.
    All root access is logged for security audit.
    """
    
    # Store active sessions: {user_id: {'expires_at': datetime, 'started_at': datetime}}
    _sessions: Dict[int, Dict[str, datetime]] = {}
    
    # Session duration (30 minutes)
    SESSION_DURATION = timedelta(minutes=30)
    
    @classmethod
    def _hash_password(cls, password: str) -> str:
        """Hash a password for comparison."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @classmethod
    def authenticate(cls, user_id: int, password: str) -> bool:
        """
        Authenticate a user and create a root session.
        
        Args:
            user_id: Telegram user ID
            password: Password to verify
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # Check if ROOT_PASSWORD is set
            if not hasattr(config, 'ROOT_PASSWORD') or not config.ROOT_PASSWORD:
                logger.warning("ROOT_PASSWORD not configured")
                return False
            
            # Simple password comparison (in production, use bcrypt)
            if password != config.ROOT_PASSWORD:
                logger.warning(f"Failed root login attempt by user {user_id}")
                return False
            
            # Create session
            now = datetime.now()
            expires_at = now + cls.SESSION_DURATION
            
            cls._sessions[user_id] = {
                'started_at': now,
                'expires_at': expires_at
            }
            
            logger.warning(f"Root session created for user {user_id} (expires at {expires_at})")
            return True
        
        except Exception as e:
            logger.error(f"Error in root authentication: {e}")
            return False
    
    @classmethod
    def is_root_session_active(cls, user_id: int) -> bool:
        """
        Check if a user has an active root session.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            True if session is active and not expired
        """
        if user_id not in cls._sessions:
            return False
        
        session = cls._sessions[user_id]
        now = datetime.now()
        
        if now > session['expires_at']:
            # Session expired, remove it
            cls.logout(user_id)
            return False
        
        return True
    
    @classmethod
    def get_allowed_paths_for_user(cls, user_id: int) -> List[str]:
        """
        Get allowed paths for a user based on their root session status.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            List of allowed paths
        """
        if cls.is_root_session_active(user_id):
            logger.info(f"User {user_id} accessing with root session (all paths allowed)")
            return ["/"]  # All paths allowed
        
        # Return default allowed paths
        return config.ALLOWED_PATHS
    
    @classmethod
    def logout(cls, user_id: int) -> bool:
        """
        End a root session.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            True if session was active and ended, False otherwise
        """
        if user_id in cls._sessions:
            session_duration = datetime.now() - cls._sessions[user_id]['started_at']
            del cls._sessions[user_id]
            logger.warning(f"Root session ended for user {user_id} (duration: {session_duration})")
            return True
        
        return False
    
    @classmethod
    def get_session_info(cls, user_id: int) -> Optional[Dict[str, any]]:
        """
        Get information about a user's root session.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            Session info dict or None if no active session
        """
        if not cls.is_root_session_active(user_id):
            return None
        
        session = cls._sessions[user_id]
        now = datetime.now()
        remaining = session['expires_at'] - now
        
        return {
            'active': True,
            'started_at': session['started_at'],
            'expires_at': session['expires_at'],
            'remaining_seconds': int(remaining.total_seconds()),
            'remaining_minutes': int(remaining.total_seconds() // 60)
        }
    
    @classmethod
    async def cleanup_expired_sessions(cls):
        """
        Background task to cleanup expired sessions.
        Should be called periodically.
        """
        while True:
            try:
                now = datetime.now()
                expired_users = []
                
                for user_id, session in cls._sessions.items():
                    if now > session['expires_at']:
                        expired_users.append(user_id)
                
                for user_id in expired_users:
                    cls.logout(user_id)
                    logger.info(f"Auto-expired root session for user {user_id}")
                
                # Check every minute
                await asyncio.sleep(60)
            
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
                await asyncio.sleep(60)
    
    @classmethod
    def get_active_sessions(cls) -> Dict[int, Dict[str, any]]:
        """
        Get all active sessions (for debugging/admin).
        
        Returns:
            Dictionary of active sessions by user_id
        """
        active = {}
        for user_id in list(cls._sessions.keys()):
            info = cls.get_session_info(user_id)
            if info:
                active[user_id] = info
        
        return active
