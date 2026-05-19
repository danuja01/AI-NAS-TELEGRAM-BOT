"""
Database models and schema for the NAS Telegram AI Assistant.
Uses SQLite for storing conversations, commands, preferences, and alerts.
"""

import aiosqlite
import logging
from pathlib import Path
from datetime import datetime

import config

logger = logging.getLogger(__name__)

DATABASE_SCHEMA = """
-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    message TEXT NOT NULL,
    command_output TEXT,  -- Stores structured command outputs
    metadata TEXT  -- JSON metadata
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_timestamp ON conversations(timestamp);

-- Command history table
CREATE TABLE IF NOT EXISTS command_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    command TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    output_summary TEXT,
    success BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_command_history_user_id ON command_history(user_id);
CREATE INDEX IF NOT EXISTS idx_command_history_timestamp ON command_history(timestamp);

-- User preferences table
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_preferences_user_id ON preferences(user_id);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,  -- 'disk', 'cpu', 'temperature', 'docker', 'smart'
    severity TEXT NOT NULL,  -- 'info', 'warning', 'critical'
    message TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);

-- SMART sector history (for delta alerts)
CREATE TABLE IF NOT EXISTS smart_snapshots (
    device TEXT PRIMARY KEY,
    reallocated INTEGER DEFAULT 0,
    pending INTEGER DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Lightweight metric samples for digests
CREATE TABLE IF NOT EXISTS metric_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cpu_percent REAL,
    memory_percent REAL,
    temp_max REAL,
    disk_min_free_percent REAL,
    pending_updates_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_metric_samples_recorded ON metric_samples(recorded_at);

-- Periodic SMART samples for spin/load-cycle trend (see /hdddetail)
CREATE TABLE IF NOT EXISTS drive_spin_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device TEXT NOT NULL,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    start_stop INTEGER,
    load_cycle INTEGER,
    power_cycles INTEGER
);

CREATE INDEX IF NOT EXISTS idx_drive_spin_device_time ON drive_spin_history(device, recorded_at);

-- Docker storage scan snapshots (/dscan, weekly report)
CREATE TABLE IF NOT EXISTS storage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reclaimable_hint TEXT,
    disk_min_free_percent REAL,
    docker_df_excerpt TEXT
);

CREATE INDEX IF NOT EXISTS idx_storage_snapshots_recorded ON storage_snapshots(recorded_at);
"""


async def init_database():
    """Initialize the database with schema."""
    try:
        db_path = Path(config.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        db = await aiosqlite.connect(
            config.DATABASE_PATH,
            check_same_thread=False
        )
        await db.executescript(DATABASE_SCHEMA)
        await db.commit()
        await db.close()
        
        logger.info(f"Database initialized at {config.DATABASE_PATH}")
    
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


async def get_db():
    """
    Get a new database connection.
    Always returns a fresh connection with proper settings.
    Caller is responsible for closing the connection.
    """
    try:
        db = await aiosqlite.connect(
            config.DATABASE_PATH,
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None  # Enable autocommit mode for better concurrency
        )
        # Enable WAL mode for better concurrency
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
        return db
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        raise
