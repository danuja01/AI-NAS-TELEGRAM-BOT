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

# Root Access Password
ROOT_PASSWORD = os.getenv("ROOT_PASSWORD", "")

# Conversation Settings
CONVERSATION_HISTORY_LENGTH = int(os.getenv("CONVERSATION_HISTORY_LENGTH", "10"))

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

# Health Check Interval (minutes)
HEALTH_CHECK_INTERVAL = 5

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

# Validate on import
validate_config()
