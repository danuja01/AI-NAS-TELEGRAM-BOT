"""
SMART drive health monitoring service.
Provides HDD/SSD health information using smartmontools.
"""

import subprocess
import logging
import json
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_smart_data(device: str) -> Optional[Dict[str, Any]]:
    """
    Get SMART data for a specific device.
    
    Args:
        device: Device path (e.g., '/dev/sda')
    
    Returns:
        Dictionary with SMART data or None if unavailable
    """
    try:
        # Try to get JSON output from smartctl
        result = subprocess.run(
            ['smartctl', '-a', '-j', device],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode not in [0, 4]:  # 4 means some SMART commands failed but data available
            logger.warning(f"smartctl returned code {result.returncode} for {device}")
        
        data = json.loads(result.stdout)
        
        smart_info = {
            'device': device,
            'model': data.get('model_name', 'Unknown'),
            'serial': data.get('serial_number', 'Unknown'),
            'health': data.get('smart_status', {}).get('passed', False)
        }
        
        # Get temperature
        if 'temperature' in data:
            smart_info['temperature'] = data['temperature'].get('current', None)
        
        # Get power-on hours
        if 'power_on_time' in data:
            smart_info['power_on_hours'] = data['power_on_time'].get('hours', 0)
        
        # Check for reallocated sectors
        if 'ata_smart_attributes' in data:
            for attr in data['ata_smart_attributes'].get('table', []):
                # Reallocated Sectors Count (ID 5)
                if attr.get('id') == 5:
                    smart_info['reallocated_sectors'] = attr.get('raw', {}).get('value', 0)
                # Current Pending Sector Count (ID 197)
                elif attr.get('id') == 197:
                    smart_info['pending_sectors'] = attr.get('raw', {}).get('value', 0)
        
        return smart_info
    
    except subprocess.TimeoutExpired:
        logger.error(f"smartctl timed out for {device}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Failed to parse smartctl JSON output for {device}")
        # Try fallback text parsing
        return _parse_smart_text(device)
    except FileNotFoundError:
        logger.error("smartctl not found. Install smartmontools: sudo apt install smartmontools")
        return None
    except Exception as e:
        logger.error(f"Failed to get SMART data for {device}: {e}")
        return None


def _parse_smart_text(device: str) -> Optional[Dict[str, Any]]:
    """Fallback text parsing for smartctl output."""
    try:
        result = subprocess.run(
            ['smartctl', '-a', device],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        output = result.stdout
        
        smart_info = {
            'device': device,
            'model': 'Unknown',
            'health': 'UNKNOWN'
        }
        
        # Parse model
        model_match = re.search(r'Device Model:\s+(.+)', output)
        if model_match:
            smart_info['model'] = model_match.group(1).strip()
        
        # Parse health status
        if 'PASSED' in output:
            smart_info['health'] = 'PASSED'
        elif 'FAILED' in output:
            smart_info['health'] = 'FAILED'
        
        # Parse temperature
        temp_match = re.search(r'Temperature_Celsius.*?(\d+)', output)
        if temp_match:
            smart_info['temperature'] = int(temp_match.group(1))
        
        return smart_info
    
    except Exception as e:
        logger.error(f"Failed to parse SMART text for {device}: {e}")
        return None


def get_all_drives() -> List[Dict[str, Any]]:
    """
    Get SMART data for all available drives.
    
    Returns:
        List of drive information dictionaries
    """
    drives = []
    
    try:
        # Try to scan for drives
        result = subprocess.run(
            ['smartctl', '--scan'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            logger.warning("Failed to scan for drives with smartctl")
            # Fallback to common device paths
            common_devices = [f'/dev/sd{chr(i)}' for i in range(ord('a'), ord('z')+1)]
            common_devices.extend([f'/dev/nvme{i}n1' for i in range(10)])
        else:
            # Parse scan output
            common_devices = []
            for line in result.stdout.split('\n'):
                if line.strip():
                    device = line.split()[0]
                    common_devices.append(device)

        # Scan can succeed but list nothing inside minimal containers; probe common nodes.
        if not common_devices:
            common_devices = [f'/dev/sd{chr(i)}' for i in range(ord('a'), ord('z') + 1)]
            common_devices.extend([f'/dev/nvme{i}n1' for i in range(10)])
        
        # Get SMART data for each device
        for device in common_devices:
            smart_data = get_smart_data(device)
            if smart_data:
                drives.append(smart_data)
        
        return drives
    
    except FileNotFoundError:
        logger.error("smartctl not found. Install smartmontools.")
        return []
    except Exception as e:
        logger.error(f"Failed to get all drives: {e}")
        return []


def check_drive_warnings(drives: List[Dict[str, Any]]) -> List[str]:
    """
    Check for drive health warnings.
    
    Args:
        drives: List of drive information
    
    Returns:
        List of warning messages
    """
    warnings = []
    
    for drive in drives:
        device = drive.get('device', 'Unknown')
        
        # Check health status
        if drive.get('health') == 'FAILED':
            warnings.append(f"🔴 CRITICAL: {device} SMART health check FAILED!")
        elif drive.get('health') not in ['PASSED', True]:
            warnings.append(f"⚠️ {device} health status unknown")
        
        # Check temperature
        temp = drive.get('temperature')
        if temp and temp > 60:
            warnings.append(f"🔥 {device} temperature high: {temp}°C")
        
        # Check reallocated sectors
        reallocated = drive.get('reallocated_sectors', 0)
        if reallocated > 0:
            warnings.append(f"⚠️ {device} has {reallocated} reallocated sectors")
        
        # Check pending sectors
        pending = drive.get('pending_sectors', 0)
        if pending > 0:
            warnings.append(f"⚠️ {device} has {pending} pending sectors")
    
    return warnings
