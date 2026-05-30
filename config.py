"""
Configuration module for the NAS Telegram AI Assistant.
Loads environment variables and defines global settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER_IDS = [
    int(uid.strip()) 
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") 
    if uid.strip()
]

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
THINKING_MODEL = os.getenv("THINKING_MODEL", "o1-mini")
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "gpt-4o-mini")

# Search API Configuration
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Ollama Configuration (optional fallback)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# Document and File Paths
DOCUMENT_PATH = os.getenv("DOCUMENT_PATH", "")
ALLOWED_PATHS = [
    path.strip() 
    for path in os.getenv("ALLOWED_PATHS", "").split(",") 
    if path.strip()
]

# Folder Filtering Configuration
DISK_ROOT_PATH = '/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988'
VISIBLE_ROOT_FOLDERS = ['documents', 'loo', 'media', 'photos', 'tutorials']

# Conversation Settings
CONVERSATION_HISTORY_LENGTH = int(os.getenv("CONVERSATION_HISTORY_LENGTH", "10"))
# Max assistant↔tool round-trips for /chat, /analyze, and RAG /ask agent mode
AGENT_MAX_TOOL_ROUNDS = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "12"))


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# When True, expose nas_host_readonly_profile to /chat /analyze /ask agent (allowlisted host reads; see services/readonly).
AGENT_HOST_READONLY_TOOL = _env_bool("AGENT_HOST_READONLY_TOOL", False)

# When True, `get_network_stats()` runs `tailscale ip -4` (requires Tailscale CLI in the bot environment).
NETWORK_TAILSCALE_CLI = _env_bool("NETWORK_TAILSCALE_CLI", True)

# After startup: re-index RAG documents and message ALLOWED_USER_IDS (good after new deploy).
AUTO_INDEX_ON_START = _env_bool("AUTO_INDEX_ON_START", False)
# If true, clears the Chroma collection first (slower; use if embedding model changed).
AUTO_INDEX_FORCE_REINDEX = _env_bool("AUTO_INDEX_FORCE_REINDEX", False)

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "bot.db"))
CHROMA_PATH = os.getenv("CHROMA_PATH", str(DATA_DIR / "chroma_db"))

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", str(LOGS_DIR / "bot.log"))

# Rate Limiting
MAX_COMMANDS_PER_MINUTE = 10

# Alert Thresholds
ALERT_THRESHOLDS = {
    "disk_space_percent": 10,  # Alert if < 10% free
    "cpu_percent": 90,  # Alert if > 90%
    "temperature_celsius": 75,  # Alert if > 75°C
    "memory_percent": 95,  # Alert if > 95%
}

# psutil sensor keys (substring match, case-insensitive) excluded from temperature alerts,
# health-score temp penalties, and digest temp_max. Comma-separated env override; empty
# env clears the list. Default drops dell_smm (often bogus highs on Dell systems).
_temp_ignore_env = os.getenv("TEMPERATURE_ALERT_IGNORE")
if _temp_ignore_env is None:
    TEMPERATURE_ALERT_IGNORE_SUBSTRINGS: tuple[str, ...] = ("dell_smm",)
else:
    TEMPERATURE_ALERT_IGNORE_SUBSTRINGS = tuple(
        s.strip().lower() for s in _temp_ignore_env.split(",") if s.strip()
    )


def ignore_temperature_sensor_for_alerts(sensor_key: str) -> bool:
    """True if this sensor label/chip should not drive alerts or temp rollups."""
    if not sensor_key or not TEMPERATURE_ALERT_IGNORE_SUBSTRINGS:
        return False
    k = str(sensor_key).lower()
    return any(substr in k for substr in TEMPERATURE_ALERT_IGNORE_SUBSTRINGS)


# Health Check Interval (minutes)
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "5"))
# Max entries in in-memory alert deduplication cache
ALERT_DEDUP_CACHE_MAX = max(100, int(os.getenv("ALERT_DEDUP_CACHE_MAX", "500")))

# Autonomous troubleshooting (AI advisory reports on health alerts; no auto-remediation)
_AUTOTROUBLESHOOT_SEVERITIES = frozenset({"info", "warning", "critical"})
AUTOTROUBLESHOOT_ENABLED = _env_bool("AUTOTROUBLESHOOT_ENABLED", False)
_min_sev = os.getenv("AUTOTROUBLESHOOT_MIN_SEVERITY", "warning").strip().lower()
AUTOTROUBLESHOOT_MIN_SEVERITY = (
    _min_sev if _min_sev in _AUTOTROUBLESHOOT_SEVERITIES else "warning"
)
AUTOTROUBLESHOOT_COOLDOWN_MINUTES = int(os.getenv("AUTOTROUBLESHOOT_COOLDOWN_MINUTES", "120"))
AUTOTROUBLESHOOT_MAX_ALERTS_PER_RUN = int(os.getenv("AUTOTROUBLESHOOT_MAX_ALERTS_PER_RUN", "5"))
AUTOTROUBLESHOOT_USE_THINKING = _env_bool("AUTOTROUBLESHOOT_USE_THINKING", False)
AUTOTROUBLESHOOT_MODEL = os.getenv("AUTOTROUBLESHOOT_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
AUTOTROUBLESHOOT_MAX_TOKENS = int(os.getenv("AUTOTROUBLESHOOT_MAX_TOKENS", "2500"))
AUTOTROUBLESHOOT_EVIDENCE_MAX_CHARS = int(os.getenv("AUTOTROUBLESHOOT_EVIDENCE_MAX_CHARS", "12000"))
AUTOTROUBLESHOOT_ACK_ALERTS = _env_bool("AUTOTROUBLESHOOT_ACK_ALERTS", True)
AUTOTROUBLESHOOT_SCAN_UNACK = _env_bool("AUTOTROUBLESHOOT_SCAN_UNACK", True)
AUTOTROUBLESHOOT_UNACK_SCAN_HOURS = int(os.getenv("AUTOTROUBLESHOOT_UNACK_SCAN_HOURS", "6"))
AUTOTROUBLESHOOT_UNACK_MAX_AGE_HOURS = int(os.getenv("AUTOTROUBLESHOOT_UNACK_MAX_AGE_HOURS", "24"))

# Host command execution (OMV / apt on host from container)
# Use "nsenter" with docker pid: host + privileged, or "ssh" with HOST_SSH=user@nas
HOST_EXEC_MODE = os.getenv("HOST_EXEC_MODE", "nsenter").strip().lower()
HOST_NSENTER_PID = int(os.getenv("HOST_NSENTER_PID", "1"))
HOST_SSH = os.getenv("HOST_SSH", "").strip()
HOST_SSH_EXTRA_ARGS = [
    a.strip()
    for a in os.getenv("HOST_SSH_EXTRA_ARGS", "").split()
    if a.strip()
]
HOST_EXEC_TIMEOUT_SHORT = int(os.getenv("HOST_EXEC_TIMEOUT_SHORT", "300"))
HOST_EXEC_TIMEOUT_LONG = int(os.getenv("HOST_EXEC_TIMEOUT_LONG", "3600"))
# omv-upgrade only: seconds for subprocess wait, or 0 = no timeout (can run many hours).
# Default 2h — NAS upgrades often exceed 1h; killing the process corrupts dpkg.
HOST_OMV_UPGRADE_TIMEOUT = int(os.getenv("HOST_OMV_UPGRADE_TIMEOUT", "7200"))

# OpenMediaVault CLI RPC (`omv-rpc` on the NAS host). Used read-only for richer storage/SMART views.
OMV_RPC_USER = os.getenv("OMV_RPC_USER", "admin").strip() or "admin"
OMV_RPC_ENABLED = _env_bool("OMV_RPC_ENABLED", True)

MAINTENANCE_ALLOWED_USER_IDS = [
    int(x.strip())
    for x in os.getenv("MAINTENANCE_ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
]

# systemd units for host_runner + health (comma-separated)
MONITOR_SYSTEMD_UNITS = [
    u.strip()
    for u in os.getenv(
        "MONITOR_SYSTEMD_UNITS",
        "docker,smbd,nginx",
    ).split(",")
    if u.strip()
]

# When false (default): journal_tail + systemctl_is_active only accept MONITOR_SYSTEMD_UNITS entries.
# When true: accept any systemd unit string that passes strict syntax checks (still read-only profiles only;
# argv list invocation — no shell). Lets you tail ssh/sshd/nginx without listing every unit in MONITOR.
# Logs may contain secrets; only enable when you trust bot users + AI tooling.
HOST_READONLY_SYSTEMD_ANY_UNIT = _env_bool("HOST_READONLY_SYSTEMD_ANY_UNIT", False)

JOURNAL_TAIL_LINES = int(os.getenv("JOURNAL_TAIL_LINES", "20"))
JOURNAL_ALERT_COOLDOWN_SECONDS = int(os.getenv("JOURNAL_ALERT_COOLDOWN_SECONDS", "600"))

# Cron notify HTTP hook (127.0.0.1 inside container; use docker exec curl from host)
CRON_NOTIFY_SECRET = os.getenv("CRON_NOTIFY_SECRET", "").strip()
CRON_NOTIFY_BIND = os.getenv("CRON_NOTIFY_BIND", "127.0.0.1").strip()
CRON_NOTIFY_PORT = int(os.getenv("CRON_NOTIFY_PORT", "18765"))
CRON_NOTIFY_RATE_PER_MINUTE = max(1, int(os.getenv("CRON_NOTIFY_RATE_PER_MINUTE", "30")))

# Uptime Kuma-style monitor platform
UPTIME_MONITORING_ENABLED = _env_bool("UPTIME_MONITORING_ENABLED", True)
UPTIME_TICK_SECONDS = max(15, int(os.getenv("UPTIME_TICK_SECONDS", "30")))
UPTIME_HEARTBEAT_RETENTION_DAYS = max(1, int(os.getenv("UPTIME_HEARTBEAT_RETENTION_DAYS", "30")))
UPTIME_DEFAULT_INTERVAL = max(30, int(os.getenv("UPTIME_DEFAULT_INTERVAL", "60")))
UPTIME_WEEKLY_REPORT_ENABLED = _env_bool("UPTIME_WEEKLY_REPORT_ENABLED", True)
UPTIME_WEEKLY_REPORT_DAY = os.getenv("UPTIME_WEEKLY_REPORT_DAY", "sun").strip().lower()
# Auto-send AI analysis on new DOWN alerts (default off — use inline "AI assist" button)
UPTIME_AI_ON_INCIDENT = _env_bool("UPTIME_AI_ON_INCIDENT", False)
UPTIME_AI_BUTTON = _env_bool("UPTIME_AI_BUTTON", True)
UPTIME_AI_COOLDOWN_MINUTES = int(os.getenv("UPTIME_AI_COOLDOWN_MINUTES", "60"))
UPTIME_AUTO_DISCOVER_DOCKER = _env_bool("UPTIME_AUTO_DISCOVER_DOCKER", True)
UPTIME_DASHBOARD_ENABLED = _env_bool("UPTIME_DASHBOARD_ENABLED", False)
UPTIME_DASHBOARD_BIND = os.getenv("UPTIME_DASHBOARD_BIND", "127.0.0.1").strip()
# Listen address when started via bot (0.0.0.0 so Tailscale can reach the container/host)
UPTIME_DASHBOARD_LISTEN = os.getenv("UPTIME_DASHBOARD_LISTEN", "0.0.0.0").strip()
UPTIME_DASHBOARD_PORT = int(os.getenv("UPTIME_DASHBOARD_PORT", "18766"))
UPTIME_DASHBOARD_SECRET = os.getenv("UPTIME_DASHBOARD_SECRET", "").strip()
# Hostname/IP shown in Telegram links (your NAS Tailscale IP, e.g. 100.75.87.91)
UPTIME_DASHBOARD_PUBLIC_HOST = os.getenv("UPTIME_DASHBOARD_PUBLIC_HOST", "100.75.87.91").strip()
# Built-in connectivity monitors (internet, DNS, tailscale hint)
UPTIME_BUILTIN_INTERNET = _env_bool("UPTIME_BUILTIN_INTERNET", True)
UPTIME_BUILTIN_DNS_HOST = os.getenv("UPTIME_BUILTIN_DNS_HOST", "1.1.1.1").strip()
UPTIME_BUILTIN_HTTP_URL = os.getenv("UPTIME_BUILTIN_HTTP_URL", "https://1.1.1.1").strip()
# Self-healing (optional; requires explicit enable)
UPTIME_SELF_HEAL_ENABLED = _env_bool("UPTIME_SELF_HEAL_ENABLED", False)
UPTIME_SELF_HEAL_MAX_RESTARTS = max(1, int(os.getenv("UPTIME_SELF_HEAL_MAX_RESTARTS", "2")))
UPTIME_SELF_HEAL_COOLDOWN_MINUTES = max(5, int(os.getenv("UPTIME_SELF_HEAL_COOLDOWN_MINUTES", "30")))
# NAS reboot detection (psutil boot_time)
UPTIME_REBOOT_ALERT_ENABLED = _env_bool("UPTIME_REBOOT_ALERT_ENABLED", True)
# Built-in Tailscale / Cloudflare tunnel monitors
UPTIME_BUILTIN_TAILSCALE = _env_bool("UPTIME_BUILTIN_TAILSCALE", True)
# Tailscale probe: auto | cli | docker | container | interface
# auto = try CLI, then docker exec in UPTIME_TAILSCALE_CONTAINER / auto-find *tailscale* container
UPTIME_TAILSCALE_PROBE = os.getenv("UPTIME_TAILSCALE_PROBE", "auto").strip().lower()
UPTIME_TAILSCALE_CONTAINER = os.getenv("UPTIME_TAILSCALE_CONTAINER", "tailscale").strip()
UPTIME_TAILSCALE_SYNC_TARGET = _env_bool("UPTIME_TAILSCALE_SYNC_TARGET", True)
UPTIME_BUILTIN_CLOUDFLARED = _env_bool("UPTIME_BUILTIN_CLOUDFLARED", True)
# cloudflared target: empty=process, systemd, or tcp:127.0.0.1:7844
UPTIME_CLOUDFLARED_TARGET = os.getenv("UPTIME_CLOUDFLARED_TARGET", "process").strip()
# Docker image change alerts
UPTIME_DOCKER_IMAGE_ALERTS = _env_bool("UPTIME_DOCKER_IMAGE_ALERTS", True)
# Run image scan every N uptime engine ticks (30s tick → 120 ≈ 1h)
UPTIME_DOCKER_IMAGE_SCAN_TICKS = max(10, int(os.getenv("UPTIME_DOCKER_IMAGE_SCAN_TICKS", "120")))
# Escalation: send/re-escalate at these consecutive failure counts
_esc = os.getenv("UPTIME_ESCALATION_THRESHOLDS", "1,3,10")
UPTIME_ESCALATION_THRESHOLDS = tuple(
    sorted({max(1, int(x.strip())) for x in _esc.split(",") if x.strip().isdigit()}) or [1, 3, 10]
)

# Metrics samples + digest
METRICS_SAMPLE_INTERVAL_MINUTES = int(os.getenv("METRICS_SAMPLE_INTERVAL_MINUTES", "15"))
DIGEST_INTERVAL_HOURS = int(os.getenv("DIGEST_INTERVAL_HOURS", "24"))

# CrowdSec security assistant (read-only cscli via docker exec + optional LAPI)
CROWDSEC_MONITOR_ENABLED = _env_bool("CROWDSEC_MONITOR_ENABLED", False)
CROWDSEC_SECURITY_ASSISTANT_IN_CHAT = _env_bool("CROWDSEC_SECURITY_ASSISTANT_IN_CHAT", True)
CROWDSEC_CONTAINER = os.getenv("CROWDSEC_CONTAINER", "crowdsec").strip().lstrip("/")
CROWDSEC_API_URL = os.getenv("CROWDSEC_API_URL", "http://127.0.0.1:8082").strip()
CROWDSEC_POLL_MINUTES = max(2, int(os.getenv("CROWDSEC_POLL_MINUTES", "5")))
_crowdsec_min = os.getenv("CROWDSEC_ALERT_MIN_SEVERITY", "MEDIUM").strip().upper()
CROWDSEC_ALERT_MIN_SEVERITY = (
    _crowdsec_min if _crowdsec_min in ("LOW", "MEDIUM", "HIGH") else "MEDIUM"
)
CROWDSEC_ALERT_COOLDOWN_MINUTES = max(5, int(os.getenv("CROWDSEC_ALERT_COOLDOWN_MINUTES", "60")))
CROWDSEC_SPIKE_THRESHOLD = max(3, int(os.getenv("CROWDSEC_SPIKE_THRESHOLD", "8")))
CROWDSEC_SPIKE_WINDOW_MINUTES = max(5, int(os.getenv("CROWDSEC_SPIKE_WINDOW_MINUTES", "15")))
CROWDSEC_DAILY_REPORT_HOUR = min(23, max(0, int(os.getenv("CROWDSEC_DAILY_REPORT_HOUR", "8"))))

# Docker / storage management (/d* commands)
STORAGE_CMD_TIMEOUT = int(os.getenv("STORAGE_CMD_TIMEOUT", "120"))
STORAGE_SCAN_TIMEOUT = int(os.getenv("STORAGE_SCAN_TIMEOUT", "300"))
STORAGE_FIND_MIN_MB = int(os.getenv("STORAGE_FIND_MIN_MB", "500"))
STORAGE_LOG_MIN_MB = int(os.getenv("STORAGE_LOG_MIN_MB", "100"))
STORAGE_LOW_DISK_PERCENT = int(os.getenv("STORAGE_LOW_DISK_PERCENT", "90"))
STORAGE_WEEKLY_SCAN_ENABLED = _env_bool("STORAGE_WEEKLY_SCAN_ENABLED", False)
DOCKER_CLEAN_DRY_RUN_DEFAULT = _env_bool("DOCKER_CLEAN_DRY_RUN_DEFAULT", False)

# Docker health alerts: avoid noise from containers you stopped on purpose
MONITOR_DOCKER_IGNORE = frozenset(
    n.strip().lstrip("/").lower()
    for n in os.getenv("MONITOR_DOCKER_IGNORE", "").split(",")
    if n.strip()
)
_docker_alert_mode = os.getenv("MONITOR_DOCKER_ALERT_MODE", "unexpected_exit").strip().lower()
MONITOR_DOCKER_ALERT_MODE = (
    _docker_alert_mode
    if _docker_alert_mode in ("unexpected_exit", "all_exited")
    else "unexpected_exit"
)
# Skip exited containers with restart policy no / unless-stopped / successful one-shot (on-failure + exit 0)
MONITOR_DOCKER_SKIP_INTENTIONAL_STOP = _env_bool("MONITOR_DOCKER_SKIP_INTENTIONAL_STOP", True)

# Resource-aware container orchestrator (pause/stop low-priority containers under pressure)
RESOURCE_ORCHESTRATOR_ENABLED = _env_bool("RESOURCE_ORCHESTRATOR_ENABLED", False)
RESOURCE_RAM_HIGH_PERCENT = float(os.getenv("RESOURCE_RAM_HIGH_PERCENT", "85"))
RESOURCE_RAM_RECOVER_PERCENT = float(os.getenv("RESOURCE_RAM_RECOVER_PERCENT", "70"))
RESOURCE_CPU_HIGH_PERCENT = float(os.getenv("RESOURCE_CPU_HIGH_PERCENT", "85"))
RESOURCE_CPU_RECOVER_PERCENT = float(os.getenv("RESOURCE_CPU_RECOVER_PERCENT", "50"))
RESOURCE_RAM_STAGE2_PERCENT = float(os.getenv("RESOURCE_RAM_STAGE2_PERCENT", "90"))
RESOURCE_CPU_STAGE2_PERCENT = float(os.getenv("RESOURCE_CPU_STAGE2_PERCENT", "90"))
RESOURCE_RECOVERY_DELAY_MINUTES = max(1, int(os.getenv("RESOURCE_RECOVERY_DELAY_MINUTES", "5")))
RESOURCE_CHECK_INTERVAL_SECONDS = max(10, int(os.getenv("RESOURCE_CHECK_INTERVAL_SECONDS", "30")))
RESOURCE_STAGE2_DELAY_SECONDS = max(30, int(os.getenv("RESOURCE_STAGE2_DELAY_SECONDS", "60")))
RESOURCE_RESTORE_GAP_SECONDS = max(1, int(os.getenv("RESOURCE_RESTORE_GAP_SECONDS", "10")))
RESOURCE_ORCHESTRATOR_STATE_PATH = os.getenv(
    "RESOURCE_ORCHESTRATOR_STATE_PATH",
    str(DATA_DIR / "resource_orchestrator_state.json"),
)


def _parse_container_name_list(env_var: str, default_csv: str) -> tuple[str, ...]:
    """Comma-separated Docker container names (normalized to lowercase, no leading slash)."""
    raw = os.getenv(env_var, default_csv)
    seen: set[str] = set()
    out: list[str] = []
    for part in raw.split(","):
        name = part.strip().lstrip("/").lower()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return tuple(out)


_DEFAULT_RESOURCE_CRITICAL = "tailscale,cloudflared,adguardhome,nas-telegram-bot"
_DEFAULT_RESOURCE_PAUSE = "affine,homarr,filebrowser"
_DEFAULT_RESOURCE_STOP = (
    "jellyfin,sonarr,radarr,prowlarr,bazarr,jellyseerr,qbittorrent,flaresolverr"
)

RESOURCE_CRITICAL_CONTAINERS = frozenset(
    _parse_container_name_list("RESOURCE_CRITICAL_CONTAINERS", _DEFAULT_RESOURCE_CRITICAL)
)
_pause_raw = _parse_container_name_list("RESOURCE_PAUSE_CONTAINERS", _DEFAULT_RESOURCE_PAUSE)
_stop_raw = _parse_container_name_list("RESOURCE_STOP_CONTAINERS", _DEFAULT_RESOURCE_STOP)
RESOURCE_PAUSE_CONTAINERS = tuple(n for n in _pause_raw if n not in RESOURCE_CRITICAL_CONTAINERS)
RESOURCE_STOP_CONTAINERS = tuple(n for n in _stop_raw if n not in RESOURCE_CRITICAL_CONTAINERS)

RESOURCE_PROTECT_HEAVY_CONTAINERS = _env_bool("RESOURCE_PROTECT_HEAVY_CONTAINERS", True)
RESOURCE_HEAVY_RAM_PERCENT = float(os.getenv("RESOURCE_HEAVY_RAM_PERCENT", "8"))
RESOURCE_HEAVY_CPU_PERCENT = float(os.getenv("RESOURCE_HEAVY_CPU_PERCENT", "50"))
RESOURCE_HEAVY_MIN_MEMORY_MB = max(64, int(os.getenv("RESOURCE_HEAVY_MIN_MEMORY_MB", "256")))
RESOURCE_HEAVY_MAX_PROTECT = max(1, int(os.getenv("RESOURCE_HEAVY_MAX_PROTECT", "8")))


def docker_container_ignored_for_alerts(name: str) -> bool:
    """True if this container name is in MONITOR_DOCKER_IGNORE (exact, case-insensitive)."""
    if not name or not MONITOR_DOCKER_IGNORE:
        return False
    return name.lstrip("/").lower() in MONITOR_DOCKER_IGNORE


_default_scan_paths = "/var/lib/docker,/var/log"
if DOCUMENT_PATH:
    _default_scan_paths += f",{DOCUMENT_PATH}"
if DISK_ROOT_PATH:
    _default_scan_paths += f",{DISK_ROOT_PATH}"
STORAGE_SCAN_PATHS = [
    p.strip()
    for p in os.getenv("STORAGE_SCAN_PATHS", _default_scan_paths).split(",")
    if p.strip()
]

# Validation
def validate_config():
    """Validate required configuration."""
    errors = []
    
    if not TELEGRAM_TOKEN:
        errors.append("TELEGRAM_TOKEN is required")
    
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is required")
    
    if not ALLOWED_USER_IDS:
        print("⚠️  WARNING: No ALLOWED_USER_IDS set. Bot will be accessible to anyone!")
    
    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")


# Validate on import (skipped for CI/local import-only smoke tests)
if os.getenv("SMOKE_IMPORT_ONLY", "").strip().lower() not in ("1", "true", "yes"):
    validate_config()
