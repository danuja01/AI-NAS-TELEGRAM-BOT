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

# ATA SMART attribute IDs useful for mechanical drive / power behavior
_ATTR_ID_START_STOP = 4
_ATTR_ID_POWER_CYCLE = 12
_ATTR_ID_LOAD_CYCLE = 193
_ATTR_ID_POWEROFF_RETRACT = 192  # often "Emergency Retract Cycle Count" / head parks
_ATTR_ID_GSENSE = 191


def _ata_attr_raw_int(table: List[dict], attr_id: int) -> Optional[int]:
    """Read integer raw value from smartctl JSON ata_smart_attributes.table entry."""
    for attr in table or []:
        if attr.get("id") != attr_id:
            continue
        raw = attr.get("raw") or {}
        val = raw.get("value")
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
        s = raw.get("string")
        if s:
            m = re.search(r"(-?\d+)", str(s).replace(",", ""))
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    pass
    return None


def _extract_nvme_cycle_info(data: dict) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    nv = data.get("nvme_smart_health_information") or data.get(
        "nvme_smart_health_information_log"
    )
    if not isinstance(nv, dict):
        return out
    pc = nv.get("power_cycles")
    poh = nv.get("power_on_hours")
    if pc is not None:
        try:
            out["power_cycle_count"] = int(pc)
        except (TypeError, ValueError):
            pass
    if poh is not None:
        try:
            # NVMe often reports hours as int; keep power_on_hours for display
            h = int(poh)
            out["power_on_hours"] = h
        except (TypeError, ValueError):
            pass
    return out


def get_hdparm_power_state(device: str) -> Optional[str]:
    """
    Current ATA power mode from hdparm -C (active/idle, standby, sleeping, unknown).
    None if hdparm missing or unsupported (e.g. NVMe, permission).
    """
    try:
        result = subprocess.run(
            ["hdparm", "-C", device],
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = (result.stdout or "") + (result.stderr or "")
        m = re.search(r"drive state is:\s*(\S+(?:/\S+)?)", text, re.I)
        if m:
            return m.group(1).strip().rstrip(",")
        if "SSD" in text or "not supported" in text.lower():
            return "n/a (ssd/nvme)"
    except FileNotFoundError:
        logger.debug("hdparm not installed")
    except Exception as e:
        logger.debug("hdparm -C failed for %s: %s", device, e)
    return None


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
            ["smartctl", "-a", "-j", device],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode not in [0, 4]:  # 4 means some SMART commands failed but data available
            logger.warning("smartctl returned code %s for %s", result.returncode, device)

        data = json.loads(result.stdout)

        smart_status = data.get("smart_status") or {}
        passed = smart_status.get("passed")
        health: Any = "UNKNOWN"
        if passed is True:
            health = "PASSED"
        elif passed is False:
            health = "FAILED"

        smart_info: Dict[str, Any] = {
            "device": device,
            "model": data.get("model_name", "Unknown"),
            "serial": data.get("serial_number", "Unknown"),
            "health": health,
        }

        # Get temperature
        if "temperature" in data:
            smart_info["temperature"] = data["temperature"].get("current", None)

        # Get power-on hours (ATA name field)
        if "power_on_time" in data:
            smart_info["power_on_hours"] = data["power_on_time"].get("hours", 0)

        rot = data.get("device", {})
        if isinstance(rot, dict):
            if rot.get("type") == "nvme":
                smart_info["device_type"] = "nvme"
            elif rot.get("type") == "scsi":
                smart_info["device_type"] = "scsi"

        nvme_extra = _extract_nvme_cycle_info(data)
        smart_info.update(nvme_extra)

        if "ata_smart_attributes" in data:
            table = data["ata_smart_attributes"].get("table", [])
            for attr in table:
                if attr.get("id") == 5:
                    smart_info["reallocated_sectors"] = attr.get("raw", {}).get("value", 0)
                elif attr.get("id") == 197:
                    smart_info["pending_sectors"] = attr.get("raw", {}).get("value", 0)

            v = _ata_attr_raw_int(table, _ATTR_ID_START_STOP)
            if v is not None:
                smart_info["start_stop_count"] = v
            v = _ata_attr_raw_int(table, _ATTR_ID_POWER_CYCLE)
            if v is not None:
                smart_info["power_cycle_count"] = v
            v = _ata_attr_raw_int(table, _ATTR_ID_LOAD_CYCLE)
            if v is not None:
                smart_info["load_cycle_count"] = v
            v = _ata_attr_raw_int(table, _ATTR_ID_POWEROFF_RETRACT)
            if v is not None:
                smart_info["poweroff_retract_count"] = v
            v = _ata_attr_raw_int(table, _ATTR_ID_GSENSE)
            if v is not None:
                smart_info["g_sense_error_rate"] = v

        if smart_info.get("device_type") != "nvme" and smart_info.get("power_cycle_count") is None:
            # Some JSON variants expose power cycle elsewhere
            pcs = data.get("power_cycle_count")
            if pcs is not None:
                try:
                    smart_info["power_cycle_count"] = int(pcs)
                except (TypeError, ValueError):
                    pass

        return smart_info

    except subprocess.TimeoutExpired:
        logger.error("smartctl timed out for %s", device)
        return None
    except json.JSONDecodeError:
        logger.error("Failed to parse smartctl JSON output for %s", device)
        # Try fallback text parsing
        return _parse_smart_text(device)
    except FileNotFoundError:
        logger.error("smartctl not found. Install smartmontools: sudo apt install smartmontools")
        return None
    except Exception as e:
        logger.error("Failed to get SMART data for %s: %s", device, e)
        return None


def _parse_smart_text(device: str) -> Optional[Dict[str, Any]]:
    """Fallback text parsing for smartctl output."""
    try:
        result = subprocess.run(
            ["smartctl", "-a", device],
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = result.stdout

        smart_info: Dict[str, Any] = {
            "device": device,
            "model": "Unknown",
            "health": "UNKNOWN",
        }

        # Parse model
        model_match = re.search(r"Device Model:\s+(.+)", output)
        if model_match:
            smart_info["model"] = model_match.group(1).strip()

        # Parse health status
        if "PASSED" in output:
            smart_info["health"] = "PASSED"
        elif "FAILED" in output:
            smart_info["health"] = "FAILED"

        # Parse temperature
        temp_match = re.search(r"Temperature_Celsius.*?(\d+)", output)
        if temp_match:
            smart_info["temperature"] = int(temp_match.group(1))

        return smart_info

    except Exception as e:
        logger.error("Failed to parse SMART text for %s: %s", device, e)
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
            ["smartctl", "--scan"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.warning("Failed to scan for drives with smartctl")
            # Fallback to common device paths
            common_devices = [f"/dev/sd{chr(i)}" for i in range(ord("a"), ord("z") + 1)]
            common_devices.extend([f"/dev/nvme{i}n1" for i in range(10)])
        else:
            # Parse scan output
            common_devices = []
            for line in result.stdout.split("\n"):
                if line.strip():
                    device = line.split()[0]
                    common_devices.append(device)

        # Scan can succeed but list nothing inside minimal containers; probe common nodes.
        if not common_devices:
            common_devices = [f"/dev/sd{chr(i)}" for i in range(ord("a"), ord("z") + 1)]
            common_devices.extend([f"/dev/nvme{i}n1" for i in range(10)])

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
        logger.error("Failed to get all drives: %s", e)
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
        device = drive.get("device", "Unknown")

        # Check health status
        h = drive.get("health")
        if h == "FAILED" or h is False:
            warnings.append(f"🔴 CRITICAL: {device} SMART health check FAILED!")
        elif h not in ["PASSED", True] and h is not None:
            warnings.append(f"⚠️ {device} health status unknown")

        # Check temperature
        temp = drive.get("temperature")
        if temp and temp > 60:
            warnings.append(f"🔥 {device} temperature high: {temp}°C")

        # Check reallocated sectors
        reallocated = drive.get("reallocated_sectors", 0)
        if reallocated and int(reallocated) > 0:
            warnings.append(f"⚠️ {device} has {reallocated} reallocated sectors")

        # Check pending sectors
        pending = drive.get("pending_sectors", 0)
        if pending and int(pending) > 0:
            warnings.append(f"⚠️ {device} has {pending} pending sectors")

    return warnings
