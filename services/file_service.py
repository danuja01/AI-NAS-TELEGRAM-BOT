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


def list_directory(path_str: str, user_id: int = None, apply_filter: bool = True) -> List[Dict[str, Any]]:
    """
    List contents of a directory.
    
    Args:
        path_str: Directory path
        user_id: Optional user ID for root access validation
        apply_filter: Whether to apply folder filtering at disk root level
    
    Returns:
        List of file/directory information
    """
    if not validate_path(path_str, user_id=user_id):
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
        
        # Apply folder filtering if at disk root level
        if apply_filter and hasattr(config, 'DISK_ROOT_PATH') and hasattr(config, 'VISIBLE_ROOT_FOLDERS'):
            try:
                # Only apply filter if disk root path exists
                disk_root_path = Path(config.DISK_ROOT_PATH)
                if disk_root_path.exists():
                    disk_root = disk_root_path.resolve()
                    if path == disk_root:
                        # Filter to only show whitelisted folders and all files
                        items = [
                            item for item in items 
                            if not item['is_dir'] or item['name'] in config.VISIBLE_ROOT_FOLDERS
                        ]
                        logger.info(f"Applied folder filter at disk root, showing {len(items)} items")
            except Exception as e:
                logger.warning(f"Failed to apply folder filter: {e}")
        
        return items
    
    except Exception as e:
        logger.error(f"Failed to list directory {path_str}: {e}")
        raise


def search_files(pattern: str, base_path: str = None, user_id: int = None, max_results: int = 50) -> List[Dict[str, Any]]:
    """
    Search for files matching a pattern.
    
    Args:
        pattern: Filename pattern to search for
        base_path: Base directory to search in (defaults to DOCUMENT_PATH)
        user_id: Optional user ID for root access validation
        max_results: Maximum number of results
    
    Returns:
        List of matching file information
    """
    if base_path is None:
        base_path = config.DOCUMENT_PATH
    
    if not validate_path(base_path, user_id=user_id):
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


def get_directory_tree(path_str: str, max_depth: int = 3, current_depth: int = 0, user_id: int = None) -> List[str]:
    """
    Get directory tree structure.
    
    Args:
        path_str: Directory path
        max_depth: Maximum depth to traverse
        current_depth: Current recursion depth
        user_id: Optional user ID for root access validation
    
    Returns:
        List of tree lines
    """
    if not validate_path(path_str, user_id=user_id):
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


def get_folder_sizes(path_str: str, user_id: int = None) -> List[Dict[str, Any]]:
    """
    Get sizes of folders in a directory.
    
    Args:
        path_str: Directory path
        user_id: Optional user ID for root access validation
    
    Returns:
        List of folder information with sizes
    """
    if not validate_path(path_str, user_id=user_id):
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


def preview_file(path_str: str, lines: int = 20, user_id: int = None) -> str:
    """
    Preview first N lines of a text file.
    
    Args:
        path_str: File path
        lines: Number of lines to read
        user_id: Optional user ID for root access validation
    
    Returns:
        File content preview
    """
    if not validate_path(path_str, user_id=user_id):
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


def create_zip_archive(files: List[Dict[str, Any]], output_path: str, max_files: int = 50) -> tuple:
    """
    Create ZIP archive from file list.
    
    Args:
        files: List of file dicts with 'path' and 'name'
        output_path: Path for output ZIP file
        max_files: Maximum number of files to include
    
    Returns:
        Tuple of (success: bool, zip_path: str, total_size: int, error_msg: str)
    """
    import zipfile
    
    try:
        # Limit number of files
        if len(files) > max_files:
            return (False, "", 0, f"Too many files. Maximum is {max_files} files per archive.")
        
        # Calculate total size before creating ZIP
        total_size = 0
        max_size = 2 * 1024 * 1024 * 1024  # 2GB limit
        
        for file_info in files:
            file_path = Path(file_info['path'])
            if file_path.exists() and file_path.is_file():
                total_size += file_path.stat().st_size
        
        if total_size > max_size:
            return (False, "", 0, f"Total size exceeds 2GB limit ({total_size / (1024**3):.2f} GB)")
        
        # Create ZIP archive
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_info in files:
                file_path = Path(file_info['path'])
                if file_path.exists() and file_path.is_file():
                    try:
                        # Use just the filename in the archive
                        arcname = file_info['name']
                        zipf.write(file_path, arcname=arcname)
                        logger.info(f"Added to ZIP: {arcname}")
                    except Exception as e:
                        logger.warning(f"Failed to add {file_info['name']} to ZIP: {e}")
                        continue
        
        # Get final ZIP size
        zip_size = Path(output_path).stat().st_size
        
        logger.info(f"Created ZIP archive: {output_path} ({len(files)} files, {zip_size} bytes)")
        return (True, output_path, zip_size, "")
    
    except Exception as e:
        logger.error(f"Failed to create ZIP archive: {e}")
        return (False, "", 0, str(e))
