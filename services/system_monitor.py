"""
System monitoring service using psutil.
Provides comprehensive system statistics.
"""

import logging
import socket
import struct
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil

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


def _tailscale_ipv4() -> Optional[str]:
    if not getattr(config, "NETWORK_TAILSCALE_CLI", True):
        return None
    try:
        import subprocess

        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        logger.debug("tailscale ip -4 unavailable: %s", e)
    return None


def _outbound_local_ipv4() -> Optional[str]:
    """Local IPv4 chosen for outbound traffic (UDP trick; no packets are sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
            return addr if addr else None
        finally:
            s.close()
    except Exception:
        return None


def _linux_default_route() -> tuple[Optional[str], Optional[str]]:
    """(gateway_ipv4, interface) from /proc/net/route, or (None, None)."""
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            next(f)
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                iface, dest, gw_hex = parts[0], parts[1], parts[2]
                if dest != "00000000":
                    continue
                if not gw_hex or gw_hex == "00000000":
                    continue
                gw_int = int(gw_hex, 16)
                gw = socket.inet_ntoa(struct.pack("<L", gw_int))
                return gw, iface
    except Exception:
        pass
    return None, None


def _duplex_label(duplex: Any) -> str:
    if duplex is None:
        return "unknown"
    try:
        if duplex == psutil.NIC_DUPLEX_FULL:
            return "full"
        if duplex == psutil.NIC_DUPLEX_HALF:
            return "half"
    except Exception:
        pass
    return "unknown"


def get_network_stats() -> Dict[str, Any]:
    """
    Per-interface counters plus link state, MTU, addresses, default route, outbound local IP,
    and optional Tailscale IPv4 (see config.NETWORK_TAILSCALE_CLI).
    """
    try:
        try:
            net_io = psutil.net_io_counters(pernic=True) or {}
        except Exception:
            net_io = {}
        try:
            if_stats = psutil.net_if_stats() or {}
        except Exception:
            if_stats = {}
        try:
            if_addrs = psutil.net_if_addrs() or {}
        except Exception:
            if_addrs = {}

        names = set(net_io.keys()) | set(if_stats.keys()) | set(if_addrs.keys())
        stats: Dict[str, Any] = {}

        for interface in sorted(names):
            if interface.startswith("lo"):
                continue
            row: Dict[str, Any] = {}

            io = net_io.get(interface)
            if io is not None:
                row.update(
                    {
                        "bytes_sent": io.bytes_sent,
                        "bytes_recv": io.bytes_recv,
                        "packets_sent": io.packets_sent,
                        "packets_recv": io.packets_recv,
                        "errors_in": io.errin,
                        "errors_out": io.errout,
                    }
                )
            else:
                row.update(
                    {
                        "bytes_sent": 0,
                        "bytes_recv": 0,
                        "packets_sent": 0,
                        "packets_recv": 0,
                        "errors_in": 0,
                        "errors_out": 0,
                    }
                )

            st = if_stats.get(interface)
            if st is not None:
                row["isup"] = bool(st.isup)
                row["duplex"] = _duplex_label(getattr(st, "duplex", None))
                spd = int(getattr(st, "speed", 0) or 0)
                row["speed_mbps"] = spd if spd > 0 else None
                mtu = getattr(st, "mtu", None)
                row["mtu"] = int(mtu) if mtu is not None else None
            else:
                row["isup"] = None
                row["duplex"] = "unknown"
                row["speed_mbps"] = None
                row["mtu"] = None

            addr_rows: List[Dict[str, str]] = []
            for snic in if_addrs.get(interface, []):
                fam = snic.family
                if fam == socket.AF_INET:
                    fam_name = "ipv4"
                elif fam == getattr(socket, "AF_INET6", None):
                    fam_name = "ipv6"
                else:
                    fam_name = str(int(fam))
                addr_rows.append(
                    {
                        "family": fam_name,
                        "address": snic.address,
                        "netmask": snic.netmask or "",
                    }
                )
            row["addresses"] = addr_rows

            stats[interface] = row

        ts = _tailscale_ipv4()
        if ts:
            stats["tailscale_ip"] = ts

        outbound = _outbound_local_ipv4()
        if outbound:
            stats["outbound_local_ipv4"] = outbound
        gw, gw_if = _linux_default_route()
        if gw:
            stats["default_gateway_ipv4"] = gw
        if gw_if:
            stats["default_route_iface"] = gw_if

        return stats

    except Exception as e:
        logger.error("Failed to get network stats: %s", e)
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


def _primary_temperature_c(temps: Dict[str, Optional[float]]) -> Optional[float]:
    """Best-effort primary CPU/package temperature (°C), skipping alert-ignored sensors."""
    if not temps:
        return None
    preferred = []
    other = []
    for key, value in temps.items():
        if value is None:
            continue
        if config.ignore_temperature_sensor_for_alerts(key):
            continue
        k = str(key).lower()
        if "cpu" in k or "core" in k or "package" in k or "k10temp" in k:
            preferred.append(value)
        else:
            other.append(value)
    if preferred:
        return max(preferred)
    if other:
        return max(other)
    return next((v for v in temps.values() if v is not None), None)


def get_simple_stats() -> Dict[str, Any]:
    """
    Compact CPU/RAM/temp snapshot for HTTP /stats and external dashboards.
    Returns {"cpu": float, "ram": float, "temp": int | None}.
    """
    try:
        cpu_percent = round(psutil.cpu_percent(interval=1), 1)
        mem_percent = round(psutil.virtual_memory().percent, 1)
        primary_temp = _primary_temperature_c(get_temperatures())
        return {
            "cpu": cpu_percent,
            "ram": mem_percent,
            "temp": int(round(primary_temp)) if primary_temp is not None else None,
        }
    except Exception as e:
        logger.error("Failed to get simple stats: %s", e)
        return {"cpu": 0.0, "ram": 0.0, "temp": None, "error": str(e)}


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
