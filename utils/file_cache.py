"""
File cache manager for storing recent file listings.
Allows users to download files by number from recent /ls commands.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FileCache:
    """
    Manages in-memory cache of file listings per user.
    
    Users can browse files with /ls and then download by number with /download.
    Cache expires after 10 minutes.
    """
    
    # Store cache per user: {user_id: {'files': [...], 'path': str, 'timestamp': datetime}}
    _cache: Dict[int, Dict[str, Any]] = {}
    
    # Cache duration (10 minutes)
    CACHE_DURATION = timedelta(minutes=10)
    
    @classmethod
    def store_files(cls, user_id: int, files: List[Dict[str, Any]], path: str):
        """
        Store file listing for a user.
        
        Args:
            user_id: Telegram user ID
            files: List of file dictionaries from list_directory()
            path: Directory path that was listed
        """
        try:
            # Only cache actual files (not directories)
            file_list = [f for f in files if not f.get('is_dir')]
            
            cls._cache[user_id] = {
                'files': file_list,
                'path': path,
                'timestamp': datetime.now()
            }
            
            logger.info(f"Cached {len(file_list)} files for user {user_id} from {path}")
        
        except Exception as e:
            logger.error(f"Failed to cache files: {e}")
    
    @classmethod
    def get_file(cls, user_id: int, number: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a file by number from user's cache.
        
        Args:
            user_id: Telegram user ID
            number: File number (1-indexed)
        
        Returns:
            File dictionary or None if not found/expired
        """
        try:
            if user_id not in cls._cache:
                return None
            
            cache_entry = cls._cache[user_id]
            
            # Check if cache expired
            age = datetime.now() - cache_entry['timestamp']
            if age > cls.CACHE_DURATION:
                logger.info(f"Cache expired for user {user_id}")
                del cls._cache[user_id]
                return None
            
            # Get file by number (1-indexed)
            files = cache_entry['files']
            if 1 <= number <= len(files):
                file_info = files[number - 1]  # Convert to 0-indexed
                logger.info(f"Retrieved file #{number} for user {user_id}: {file_info['name']}")
                return file_info
            else:
                logger.warning(f"File number {number} out of range for user {user_id}")
                return None
        
        except Exception as e:
            logger.error(f"Failed to retrieve file from cache: {e}")
            return None
    
    @classmethod
    def get_files(cls, user_id: int, numbers: List[int]) -> List[Dict[str, Any]]:
        """
        Retrieve multiple files by numbers from user's cache.
        
        Args:
            user_id: Telegram user ID
            numbers: List of file numbers (1-indexed)
        
        Returns:
            List of file dictionaries (only valid files)
        """
        try:
            if user_id not in cls._cache:
                return []
            
            cache_entry = cls._cache[user_id]
            
            # Check if cache expired
            age = datetime.now() - cache_entry['timestamp']
            if age > cls.CACHE_DURATION:
                logger.info(f"Cache expired for user {user_id}")
                del cls._cache[user_id]
                return []
            
            # Get files by numbers (1-indexed)
            files = cache_entry['files']
            result = []
            
            for number in numbers:
                if 1 <= number <= len(files):
                    file_info = files[number - 1]  # Convert to 0-indexed
                    result.append(file_info)
                else:
                    logger.warning(f"File number {number} out of range for user {user_id}")
            
            logger.info(f"Retrieved {len(result)} files for user {user_id}")
            return result
        
        except Exception as e:
            logger.error(f"Failed to retrieve files from cache: {e}")
            return []
    
    @classmethod
    def get_cache_info(cls, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get information about user's cache.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            Cache info dict or None if no cache
        """
        if user_id not in cls._cache:
            return None
        
        cache_entry = cls._cache[user_id]
        age = datetime.now() - cache_entry['timestamp']
        
        if age > cls.CACHE_DURATION:
            del cls._cache[user_id]
            return None
        
        return {
            'file_count': len(cache_entry['files']),
            'path': cache_entry['path'],
            'age_seconds': int(age.total_seconds()),
            'expires_in_seconds': int((cls.CACHE_DURATION - age).total_seconds())
        }
    
    @classmethod
    def clear_cache(cls, user_id: int) -> bool:
        """
        Clear cache for a specific user.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            True if cache was cleared, False if no cache existed
        """
        if user_id in cls._cache:
            del cls._cache[user_id]
            logger.info(f"Cleared cache for user {user_id}")
            return True
        return False
    
    @classmethod
    def cleanup_expired(cls):
        """Remove all expired cache entries."""
        now = datetime.now()
        expired_users = []
        
        for user_id, cache_entry in cls._cache.items():
            age = now - cache_entry['timestamp']
            if age > cls.CACHE_DURATION:
                expired_users.append(user_id)
        
        for user_id in expired_users:
            del cls._cache[user_id]
            logger.info(f"Auto-cleaned expired cache for user {user_id}")
        
        return len(expired_users)
