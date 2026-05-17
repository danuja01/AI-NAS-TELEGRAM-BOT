"""
File system service with security restrictions.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import config
from utils.security import validate_path, sanitize_filename

logger = logging.getLogger(__name__)


def list_directory(path_str: str) -> List[Dict[str, Any]]:
    """
    List contents of a directory.
    
    Args:
        path_str: Directory path
    
    Returns:
        List of file/directory information
    """
    if not validate_path(path_str):
        raise PermissionError(f"Access to path '{path_str}' is not allowed")
    
    try:
        path = Path(path_str).resolve()
        
        if not path.exists():
            raise FileNotFoundError(f"Path '{path_str}' does not exist")
        
        if not path.is_dir():
            raise NotADirectoryError(f"'{path_str}' is not a directory")
        
        items = []
        
        for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            try:
                stat = item.stat()
                
                items.append({
                    'name': item.name,
                    'path': str(item),
                    'is_dir': item.is_dir(),
                    'size': stat.st_size if item.is_file() else 0,
                    'modified': stat.st_mtime
                })
            except Exception as e:
                logger.warning(f"Failed to stat {item}: {e}")
                continue
        
        return items
    
    except Exception as e:
        logger.error(f"Failed to list directory {path_str}: {e}")
        raise


def search_files(pattern: str, base_path: str = None, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Search for files matching a pattern.
    
    Args:
        pattern: Filename pattern to search for
        base_path: Base directory to search in (defaults to DOCUMENT_PATH)
        max_results: Maximum number of results
    
    Returns:
        List of matching file information
    """
    if base_path is None:
        base_path = config.DOCUMENT_PATH
    
    if not validate_path(base_path):
        raise PermissionError(f"Access to path '{base_path}' is not allowed")
    
    try:
        path = Path(base_path).resolve()
        pattern_lower = pattern.lower()
        
        results = []
        
        for item in path.rglob('*'):
            if len(results) >= max_results:
                break
            
            if not validate_path(str(item), user_id=user_id):
                continue
            
            if pattern_lower in item.name.lower():
                try:
                    stat = item.stat()
                    results.append({
                        'name': item.name,
                        'path': str(item),
                        'is_dir': item.is_dir(),
                        'size': stat.st_size if item.is_file() else 0,
                        'modified': stat.st_mtime
                    })
                except Exception as e:
                    logger.warning(f"Failed to stat {item}: {e}")
                    continue
        
        return results
    
    except Exception as e:
        logger.error(f"Failed to search files: {e}")
        raise


def get_directory_tree(path_str: str, max_depth: int = 3, current_depth: int = 0) -> List[str]:
    """
    Get directory tree structure.
    
    Args:
        path_str: Directory path
        max_depth: Maximum depth to traverse
        current_depth: Current recursion depth
    
    Returns:
        List of tree lines
    """
    if not validate_path(path_str):
        raise PermissionError(f"Access to path '{path_str}' is not allowed")
    
    try:
        path = Path(path_str).resolve()
        
        if not path.exists() or not path.is_dir():
            raise NotADirectoryError(f"'{path_str}' is not a valid directory")
        
        tree_lines = []
        indent = "  " * current_depth
        
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        
        for i, item in enumerate(items):
            is_last = i == len(items) - 1
            prefix = "└─ " if is_last else "├─ "
            
            icon = "📁" if item.is_dir() else "📄"
            tree_lines.append(f"{indent}{prefix}{icon} {item.name}")
            
            # Recurse into directories if not at max depth
            if item.is_dir() and current_depth < max_depth:
                try:
                    if validate_path(str(item), user_id=user_id):
                        subtree = get_directory_tree(str(item), max_depth, current_depth + 1, user_id=user_id)
                        tree_lines.extend(subtree)
                except:
                    pass
        
        return tree_lines
    
    except Exception as e:
        logger.error(f"Failed to get directory tree: {e}")
        raise


def get_folder_sizes(path_str: str) -> List[Dict[str, Any]]:
    """
    Get sizes of folders in a directory.
    
    Args:
        path_str: Directory path
    
    Returns:
        List of folder information with sizes
    """
    if not validate_path(path_str):
        raise PermissionError(f"Access to path '{path_str}' is not allowed")
    
    try:
        path = Path(path_str).resolve()
        
        if not path.exists() or not path.is_dir():
            raise NotADirectoryError(f"'{path_str}' is not a valid directory")
        
        folders = []
        
        for item in path.iterdir():
            if item.is_dir() and validate_path(str(item), user_id=user_id):
                try:
                    size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                    folders.append({
                        'name': item.name,
                        'path': str(item),
                        'size': size
                    })
                except Exception as e:
                    logger.warning(f"Failed to calculate size for {item}: {e}")
                    continue
        
        # Sort by size descending
        folders.sort(key=lambda x: x['size'], reverse=True)
        
        return folders
    
    except Exception as e:
        logger.error(f"Failed to get folder sizes: {e}")
        raise


def preview_file(path_str: str, lines: int = 20) -> str:
    """
    Preview first N lines of a text file.
    
    Args:
        path_str: File path
        lines: Number of lines to read
    
    Returns:
        File content preview
    """
    if not validate_path(path_str):
        raise PermissionError(f"Access to path '{path_str}' is not allowed")
    
    try:
        path = Path(path_str).resolve()
        
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"'{path_str}' is not a valid file")
        
        # Check file size (limit to 1MB for preview)
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("File too large for preview (max 1MB)")
        
        # Try to read as text
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content_lines = []
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    content_lines.append(line.rstrip())
                
                return '\n'.join(content_lines)
        except UnicodeDecodeError:
            return "Binary file - cannot preview"
    
    except Exception as e:
        logger.error(f"Failed to preview file: {e}")
        raise


def get_storage_summary() -> List[Dict[str, Any]]:
    """Get storage summary for allowed paths."""
    summary = []
    
    for allowed_path in config.ALLOWED_PATHS:
        try:
            path = Path(allowed_path).resolve()
            
            if not path.exists():
                continue
            
            # Get disk usage for this path
            stat = os.statvfs(str(path))
            
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            
            summary.append({
                'path': str(path),
                'total_gb': total / (1024**3),
                'used_gb': used / (1024**3),
                'free_gb': free / (1024**3),
                'percent': (used / total * 100) if total > 0 else 0
            })
        
        except Exception as e:
            logger.warning(f"Failed to get storage summary for {allowed_path}: {e}")
            continue
    
    return summary
