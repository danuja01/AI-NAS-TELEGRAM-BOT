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

# Root Access Password (bcrypt hash recommended: python scripts/hash_root_password.py 'secret')
ROOT_PASSWORD = os.getenv("ROOT_PASSWORD", "")
ROOT_LOGIN_MAX_ATTEMPTS = int(os.getenv("ROOT_LOGIN_MAX_ATTEMPTS", "5"))
ROOT_LOGIN_LOCKOUT_MINUTES = int(os.getenv("ROOT_LOGIN_LOCKOUT_MINUTES", "15"))
ROOT_LOGIN_RATE_PER_MINUTE = int(os.getenv("ROOT_LOGIN_RATE_PER_MINUTE", "3"))

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

# Metrics samples + digest
METRICS_SAMPLE_INTERVAL_MINUTES = int(os.getenv("METRICS_SAMPLE_INTERVAL_MINUTES", "15"))
DIGEST_INTERVAL_HOURS = int(os.getenv("DIGEST_INTERVAL_HOURS", "24"))

# Docker / storage management (/d* commands)
STORAGE_CMD_TIMEOUT = int(os.getenv("STORAGE_CMD_TIMEOUT", "120"))
STORAGE_SCAN_TIMEOUT = int(os.getenv("STORAGE_SCAN_TIMEOUT", "300"))
STORAGE_FIND_MIN_MB = int(os.getenv("STORAGE_FIND_MIN_MB", "500"))
STORAGE_LOG_MIN_MB = int(os.getenv("STORAGE_LOG_MIN_MB", "100"))
STORAGE_LOW_DISK_PERCENT = int(os.getenv("STORAGE_LOW_DISK_PERCENT", "90"))
STORAGE_WEEKLY_SCAN_ENABLED = _env_bool("STORAGE_WEEKLY_SCAN_ENABLED", False)
DOCKER_CLEAN_DRY_RUN_DEFAULT = _env_bool("DOCKER_CLEAN_DRY_RUN_DEFAULT", False)

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
