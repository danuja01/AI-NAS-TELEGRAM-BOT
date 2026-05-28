"""
CrowdSec read-only client: cscli via Docker SDK exec (or docker CLI fallback) + optional LAPI HTTP.
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

import config

logger = logging.getLogger(__name__)

_CSCLI_SUBCOMMANDS = {
    "alerts": ["alerts", "list", "-o", "json"],
    "decisions": ["decisions", "list", "-o", "json"],
    "metrics": ["metrics", "-o", "json"],
}


def crowdsec_available() -> bool:
    """True if cscli in the CrowdSec container appears reachable."""
    ok, _ = crowdsec_probe()
    return ok


def crowdsec_probe() -> Tuple[bool, str]:
    """Check cscli reachability; returns (ok, error_or_ok_message)."""
    ok, out = _run_cscli(["version"], timeout=8)
    if ok:
        first = (out or "").splitlines()[0][:120] if out else "ok"
        return True, first
    return False, out


def _container_name() -> str:
    return (getattr(config, "CROWDSEC_CONTAINER", None) or "crowdsec").strip().lstrip("/")


def _run_cscli_sdk(name: str, extra_argv: List[str]) -> Tuple[bool, str]:
    """Run cscli inside a container using the Docker Python SDK (no host docker CLI required)."""
    try:
        from docker.errors import NotFound

        from services.docker_service import get_docker_client

        client = get_docker_client()
        container = client.containers.get(name)
        status = (container.status or "").lower()
        if status != "running":
            return False, f"container {name!r} is not running (status: {status})"

        result = container.exec_run(["cscli", *extra_argv], demux=True)
        exit_code = getattr(result, "exit_code", 1)
        output = getattr(result, "output", None)
        if isinstance(output, tuple):
            stdout_b, stderr_b = output
            stdout = (stdout_b or b"").decode("utf-8", errors="replace")
            stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        elif isinstance(output, (bytes, bytearray)):
            stdout = bytes(output).decode("utf-8", errors="replace")
            stderr = ""
        else:
            stdout = str(output or "")
            stderr = ""

        if exit_code != 0:
            err = (stderr or stdout or "cscli failed").strip()[:800]
            return False, err
        return True, stdout.strip()
    except NotFound:
        return False, f"container {name!r} not found"
    except ImportError:
        return False, "Docker SDK not installed"
    except Exception as e:
        logger.debug("CrowdSec SDK exec failed: %s", e)
        return False, str(e)[:800]


def _run_cscli_cli(name: str, extra_argv: List[str], timeout: int) -> Tuple[bool, str]:
    """Fallback: host docker CLI subprocess."""
    cmd = ["docker", "exec", name, "cscli", *extra_argv]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "docker CLI not in PATH (bot image uses Docker SDK instead)"
    except subprocess.TimeoutExpired:
        return False, f"timeout running {' '.join(cmd[:6])}..."
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "cscli failed").strip()[:800]
        return False, err
    return True, (proc.stdout or "").strip()


def _run_cscli(extra_argv: List[str], timeout: int = 25) -> Tuple[bool, str]:
    name = _container_name()
    if not name:
        return False, "CROWDSEC_CONTAINER is empty"

    ok, out = _run_cscli_sdk(name, extra_argv)
    if ok:
        return True, out

    sdk_err = out
    ok_cli, out_cli = _run_cscli_cli(name, extra_argv, timeout)
    if ok_cli:
        return True, out_cli

    if "docker CLI not in PATH" in out_cli or "Docker SDK not installed" in sdk_err:
        return False, sdk_err
    return False, sdk_err or out_cli


def _parse_json_list(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("CrowdSec JSON parse failed: %s", e)
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("alerts", "decisions", "items", "data"):
            inner = data.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        return [data]
    return []


def fetch_alerts() -> Tuple[bool, List[Dict[str, Any]], str]:
    ok, raw = _run_cscli(_CSCLI_SUBCOMMANDS["alerts"])
    if not ok:
        return False, [], raw
    return True, _parse_json_list(raw), ""


def fetch_decisions() -> Tuple[bool, List[Dict[str, Any]], str]:
    ok, raw = _run_cscli(_CSCLI_SUBCOMMANDS["decisions"])
    if not ok:
        return False, [], raw
    return True, _parse_json_list(raw), ""


def fetch_metrics() -> Tuple[bool, Dict[str, Any], str]:
    ok, raw = _run_cscli(_CSCLI_SUBCOMMANDS["metrics"])
    if not ok:
        return False, {}, raw
    if not raw:
        return True, {}, ""
    try:
        data = json.loads(raw)
        return True, data if isinstance(data, dict) else {"raw": data}, ""
    except json.JSONDecodeError as e:
        return False, {}, str(e)


def fetch_lapi_health() -> Tuple[bool, str]:
    """Optional GET against CrowdSec LAPI (read-only health)."""
    base = (getattr(config, "CROWDSEC_API_URL", "") or "").strip().rstrip("/")
    if not base:
        return False, "CROWDSEC_API_URL not set"
    url = f"{base}/v1/heartbeat"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except urllib.error.URLError as e:
        return False, str(e)[:200]
    except Exception as e:
        return False, str(e)[:200]


def _alert_ip(alert: Dict[str, Any]) -> str:
    for key in ("source_ip", "value", "ip"):
        v = alert.get(key)
        if v:
            return str(v)
    src = alert.get("source") or {}
    if isinstance(src, dict):
        return str(src.get("ip") or src.get("value") or "")
    return ""


def _alert_scenario(alert: Dict[str, Any]) -> str:
    return str(
        alert.get("scenario")
        or alert.get("type")
        or (alert.get("labels") or {}).get("type")
        or "unknown"
    )


def _alert_country(alert: Dict[str, Any]) -> str:
    for key in ("country", "cn"):
        if alert.get(key):
            return str(alert[key])
    src = alert.get("source") or {}
    if isinstance(src, dict):
        loc = src.get("location") or src.get("cn") or src.get("country")
        if loc:
            return str(loc)
    labels = alert.get("labels") or {}
    if isinstance(labels, dict):
        for k in ("country", "IsoCode", "iso_code"):
            if labels.get(k):
                return str(labels[k])
    return "?"


def _decision_ip(dec: Dict[str, Any]) -> str:
    return str(dec.get("value") or dec.get("ip") or "")


def normalize_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten alert for monitor and AI tools."""
    scenario = _alert_scenario(alert)
    return {
        "id": alert.get("id") or alert.get("uuid"),
        "scenario": scenario,
        "source_ip": _alert_ip(alert),
        "country": _alert_country(alert),
        "target": infer_target_service(scenario, alert),
        "created_at": alert.get("created_at") or alert.get("start_at"),
        "events_count": len(alert.get("events") or []) if isinstance(alert.get("events"), list) else 0,
        "raw": alert,
    }


def normalize_decision(dec: Dict[str, Any]) -> Dict[str, Any]:
    scenario = str(dec.get("scenario") or dec.get("type") or "unknown")
    return {
        "id": dec.get("id"),
        "scenario": scenario,
        "source_ip": _decision_ip(dec),
        "origin": dec.get("origin") or "",
        "duration": dec.get("duration") or dec.get("until"),
        "target": infer_target_service(scenario, dec),
        "raw": dec,
    }


_PROTECTED = (
    ("ssh", "SSH"),
    ("filebrowser", "Filebrowser"),
    ("portainer", "Portainer"),
    ("jellyfin", "Jellyfin"),
    ("immich", "Immich"),
    ("qbittorrent", "qBittorrent"),
    ("sonarr", "Sonarr"),
    ("radarr", "Radarr"),
    ("bazarr", "Bazarr"),
    ("prowlarr", "Prowlarr"),
    ("homarr", "Homarr"),
    ("adguard", "AdGuard Home"),
    ("tailscale", "Tailscale"),
    ("docker", "Docker"),
    ("http", "HTTP"),
    ("https", "HTTP"),
)


def infer_target_service(scenario: str, item: Dict[str, Any]) -> str:
    """Map scenario/labels to a protected service name."""
    hay = scenario.lower()
    labels = item.get("labels") or {}
    if isinstance(labels, dict):
        for v in labels.values():
            hay += " " + str(v).lower()
    meta = item.get("meta") or item.get("machine_id") or ""
    hay += " " + str(meta).lower()
    for needle, name in _PROTECTED:
        if needle in hay:
            return name
    if "bruteforce" in hay or "brute" in hay:
        if "ssh" in hay:
            return "SSH"
        return "HTTP"
    if "scan" in hay or "crawl" in hay:
        return "HTTP"
    return "NAS"


def gather_crowdsec_snapshot() -> Dict[str, Any]:
    """Combined read-only snapshot for tools and commands."""
    out: Dict[str, Any] = {
        "ok": True,
        "container": _container_name(),
        "api_url": getattr(config, "CROWDSEC_API_URL", ""),
        "lapi": {},
        "alerts": [],
        "decisions": [],
        "metrics": {},
        "errors": [],
    }
    ok_a, alerts, err_a = fetch_alerts()
    if ok_a:
        out["alerts"] = [normalize_alert(a) for a in alerts[:80]]
    else:
        out["errors"].append(f"alerts: {err_a}")
        out["ok"] = False

    ok_d, decisions, err_d = fetch_decisions()
    if ok_d:
        out["decisions"] = [normalize_decision(d) for d in decisions[:120]]
    else:
        out["errors"].append(f"decisions: {err_d}")
        out["ok"] = False

    ok_m, metrics, err_m = fetch_metrics()
    if ok_m:
        out["metrics"] = metrics
    else:
        out["errors"].append(f"metrics: {err_m}")

    if getattr(config, "CROWDSEC_API_URL", ""):
        lapi_ok, lapi_msg = fetch_lapi_health()
        out["lapi"] = {"ok": lapi_ok, "message": lapi_msg}

    return out
