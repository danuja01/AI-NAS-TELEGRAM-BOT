"""
System monitoring service using psutil.
Provides comprehensive system statistics.
"""

import psutil
import platform
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def get_cpu_stats() -> Dict[str, Any]:
    """Get CPU statistics."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
        load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
        
        stats = {
            'percent': cpu_percent,
            'per_cpu': cpu_per_core,
            'load_avg': load_avg,
            'cores': psutil.cpu_count(logical=False),
            'threads': psutil.cpu_count(logical=True)
        }
        
        # Get frequency if available
        try:
            freq = psutil.cpu_freq()
            if freq:
                stats['frequency'] = {
                    'current': freq.current,
                    'min': freq.min,
                    'max': freq.max
                }
        except:
            pass
        
        return stats
    
    except Exception as e:
        logger.error(f"Failed to get CPU stats: {e}")
        return {'percent': 0, 'error': str(e)}


def get_memory_stats() -> Dict[str, Any]:
    """Get memory statistics."""
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            'total_gb': mem.total / (1024**3),
            'available_gb': mem.available / (1024**3),
            'used_gb': mem.used / (1024**3),
            'percent': mem.percent,
            'swap': {
                'total_gb': swap.total / (1024**3),
                'used_gb': swap.used / (1024**3),
                'free_gb': swap.free / (1024**3),
                'percent': swap.percent
            }
        }
    
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        return {'error': str(e)}


def get_disk_stats() -> List[Dict[str, Any]]:
    """Get disk statistics for all partitions."""
    try:
        disks = []
        
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                
                disks.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total_gb': usage.total / (1024**3),
                    'used_gb': usage.used / (1024**3),
                    'free_gb': usage.free / (1024**3),
                    'percent': usage.percent
                })
            except PermissionError:
                continue
            except Exception as e:
                logger.warning(f"Failed to get stats for {partition.mountpoint}: {e}")
                continue
        
        return disks
    
    except Exception as e:
        logger.error(f"Failed to get disk stats: {e}")
        return []


def get_temperatures() -> Dict[str, Optional[float]]:
    """Get temperature readings from sensors."""
    try:
        temps = {}
        
        if hasattr(psutil, 'sensors_temperatures'):
            sensors = psutil.sensors_temperatures()
            
            for name, entries in sensors.items():
                for entry in entries:
                    label = f"{name}_{entry.label}" if entry.label else name
                    temps[label] = entry.current
        
        return temps if temps else {'cpu': None}
    
    except Exception as e:
        logger.error(f"Failed to get temperatures: {e}")
        return {}


def get_network_stats() -> Dict[str, Any]:
    """Get network statistics."""
    try:
        net_io = psutil.net_io_counters(pernic=True)
        
        stats = {}
        
        for interface, io_counters in net_io.items():
            # Skip loopback
            if interface.startswith('lo'):
                continue
            
            stats[interface] = {
                'bytes_sent': io_counters.bytes_sent,
                'bytes_recv': io_counters.bytes_recv,
                'packets_sent': io_counters.packets_sent,
                'packets_recv': io_counters.packets_recv,
                'errors_in': io_counters.errin,
                'errors_out': io_counters.errout
            }

        return stats
    
    except Exception as e:
        logger.error(f"Failed to get network stats: {e}")
        return {}


def get_uptime() -> Dict[str, Any]:
    """Get system uptime."""
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = datetime.now().timestamp() - boot_time
        
        return {
            'boot_time': datetime.fromtimestamp(boot_time).isoformat(),
            'uptime_seconds': int(uptime_seconds)
        }
    
    except Exception as e:
        logger.error(f"Failed to get uptime: {e}")
        return {'error': str(e)}


def calculate_health_score() -> tuple[int, List[str]]:
    """
    Calculate overall system health score (0-100) and list issues.
    
    Returns:
        Tuple of (score, list of issues)
    """
    score = 100
    issues = []
    
    try:
        # Check CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > 90:
            score -= 20
            issues.append(f"High CPU usage: {cpu_percent:.1f}%")
        elif cpu_percent > 75:
            score -= 10
            issues.append(f"Elevated CPU usage: {cpu_percent:.1f}%")
        
        # Check Memory
        mem = psutil.virtual_memory()
        if mem.percent > 95:
            score -= 25
            issues.append(f"Critical memory usage: {mem.percent:.1f}%")
        elif mem.percent > 85:
            score -= 15
            issues.append(f"High memory usage: {mem.percent:.1f}%")
        
        # Check Disk
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                if usage.percent > 95:
                    score -= 20
                    issues.append(f"Critical disk space on {partition.mountpoint}: {usage.percent:.1f}%")
                elif usage.percent > 85:
                    score -= 10
                    issues.append(f"Low disk space on {partition.mountpoint}: {usage.percent:.1f}%")
            except:
                pass
        
        # Check Temperatures
        if hasattr(psutil, 'sensors_temperatures'):
            sensors = psutil.sensors_temperatures()
            for name, entries in sensors.items():
                if config.ignore_temperature_sensor_for_alerts(name):
                    continue
                for entry in entries:
                    if entry.current and entry.current > 80:
                        score -= 15
                        issues.append(f"High temperature {name}: {entry.current}°C")
                    elif entry.current and entry.current > 70:
                        score -= 5
                        issues.append(f"Elevated temperature {name}: {entry.current}°C")
        
        # Ensure score doesn't go negative
        score = max(0, score)
        
    except Exception as e:
        logger.error(f"Failed to calculate health score: {e}")
        score = 50
        issues.append("Unable to fully assess system health")
    
    return score, issues


def get_comprehensive_status() -> Dict[str, Any]:
    """Get comprehensive system status."""
    try:
        cpu_stats = get_cpu_stats()
        mem_stats = get_memory_stats()
        disk_stats = get_disk_stats()
        temps = get_temperatures()
        uptime = get_uptime()
        
        # Get primary temperature (first available)
        primary_temp = next((v for v in temps.values() if v is not None), None)
        
        # Get primary disk
        primary_disk = disk_stats[0] if disk_stats else {}
        
        status = {
            'cpu': cpu_stats,
            'memory': mem_stats,
            'disk': primary_disk,
            'temperature': primary_temp,
            'uptime': uptime.get('uptime_seconds', 0)
        }
        
        return status
    
    except Exception as e:
        logger.error(f"Failed to get comprehensive status: {e}")
        return {'error': str(e)}
