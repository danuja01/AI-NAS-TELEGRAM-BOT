"""
Service management module for systemd services and system operations.
"""

import subprocess
import logging
import shutil
from typing import List, Dict, Any, Optional

import config
from services.readonly.validators import validate_systemd_unit

logger = logging.getLogger(__name__)


def _validate_restart_unit(service_name: str) -> str:
    name = (service_name or "").strip()
    if not name:
        raise ValueError("Service name is required")
    allowed = getattr(config, "RESTART_SERVICE_ALLOWED_UNITS", None) or config.MONITOR_SYSTEMD_UNITS
    if name not in allowed:
        raise ValueError(
            f"Service `{name}` is not in RESTART_SERVICE_ALLOWED_UNITS. "
            f"Allowed: {', '.join(allowed)}"
        )
    if not validate_systemd_unit(name):
        raise ValueError(f"Invalid systemd unit name: {name}")
    return name


def is_systemctl_available() -> bool:
    """
    Check if systemctl is available on the system.
    
    Returns False when running in Docker containers or systems without systemd.
    
    Returns:
        True if systemctl command is available
    """
    return shutil.which('systemctl') is not None


def restart_service(service_name: str) -> bool:
    """
    Restart a systemd service.
    
    Args:
        service_name: Name of the service
    
    Returns:
        True if successful
    """
    try:
        result = subprocess.run(
            ['systemctl', 'restart', service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to restart {service_name}: {result.stderr}")
        
        logger.info(f"Successfully restarted service: {service_name}")
        return True
    
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Restart of {service_name} timed out")
    except Exception as e:
        logger.error(f"Failed to restart service {service_name}: {e}")
        raise


def get_service_status(service_name: str) -> Dict[str, Any]:
    """
    Get status of a systemd service.
    
    Args:
        service_name: Name of the service
    
    Returns:
        Dictionary with service status information
    """
    # Check if systemctl is available (not in Docker container)
    if not is_systemctl_available():
        return {
            'name': service_name,
            'active': False,
            'state': 'unavailable',
            'error': 'systemctl not available (running in container)'
        }
    
    try:
        result = subprocess.run(
            ['systemctl', 'status', service_name],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # systemctl status returns 0 for active, 3 for inactive, 4 for not found
        status = {
            'name': service_name,
            'active': result.returncode == 0,
            'output': result.stdout
        }
        
        # Parse output for more details
        if 'active (running)' in result.stdout.lower():
            status['state'] = 'running'
        elif 'inactive' in result.stdout.lower():
            status['state'] = 'inactive'
        elif 'failed' in result.stdout.lower():
            status['state'] = 'failed'
        else:
            status['state'] = 'unknown'
        
        return status
    
    except Exception as e:
        logger.error(f"Failed to get status for {service_name}: {e}")
        return {
            'name': service_name,
            'active': False,
            'state': 'error',
            'error': str(e)
        }


def list_common_services() -> List[Dict[str, Any]]:
    """
    List common services and their status.
    
    Returns:
        List of service information
    """
    # Check if systemctl is available
    if not is_systemctl_available():
        logger.info("Running in container environment - systemctl not available")
        return []
    
    common_services = [
        'docker',
        'nginx',
        'apache2',
        'postgresql',
        'mysql',
        'redis',
        'jellyfin',
        'plex',
        'samba',
        'ssh',
        'tailscaled'
    ]
    
    services = []
    
    for service in common_services:
        try:
            status = get_service_status(service)
            if status['state'] != 'error':  # Only include if service exists
                services.append(status)
        except:
            continue
    
    return services


def reboot_system() -> bool:
    """
    Reboot the system.
    
    Returns:
        True if reboot command executed successfully
    """
    try:
        logger.warning("SYSTEM REBOOT INITIATED")
        
        result = subprocess.run(
            ['sudo', 'reboot'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to reboot system: {e}")
        raise


def shutdown_system() -> bool:
    """
    Shutdown the system.
    
    Returns:
        True if shutdown command executed successfully
    """
    try:
        logger.warning("SYSTEM SHUTDOWN INITIATED")
        
        result = subprocess.run(
            ['sudo', 'shutdown', 'now'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        return True
    
    except Exception as e:
        logger.error(f"Failed to shutdown system: {e}")
        raise
