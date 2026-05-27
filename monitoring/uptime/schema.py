"""SQLite schema for configurable uptime monitors."""

UPTIME_SCHEMA = """
-- Configurable monitors (Uptime Kuma-style)
CREATE TABLE IF NOT EXISTS uptime_monitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    target TEXT NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 60,
    enabled INTEGER NOT NULL DEFAULT 1,
    maintenance_mode INTEGER NOT NULL DEFAULT 0,
    expected_status INTEGER,
    keyword TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 10,
    retries INTEGER NOT NULL DEFAULT 1,
    tags TEXT,
    notify_route TEXT DEFAULT 'default',
    escalation_stage INTEGER NOT NULL DEFAULT 0,
    parent_monitor_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_check DATETIME,
    last_status TEXT DEFAULT 'unknown',
    uptime_percentage REAL DEFAULT 100.0,
    response_time_ms REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (parent_monitor_id) REFERENCES uptime_monitors(id)
);

CREATE INDEX IF NOT EXISTS idx_uptime_monitors_enabled ON uptime_monitors(enabled);
CREATE INDEX IF NOT EXISTS idx_uptime_monitors_type ON uptime_monitors(type);

-- Per-check heartbeats (retained ~30 days)
CREATE TABLE IF NOT EXISTS uptime_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id INTEGER NOT NULL,
    checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    success INTEGER NOT NULL,
    latency_ms REAL,
    status_code INTEGER,
    error_message TEXT,
    FOREIGN KEY (monitor_id) REFERENCES uptime_monitors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uptime_heartbeats_monitor ON uptime_heartbeats(monitor_id, checked_at);

-- Open/closed incidents
CREATE TABLE IF NOT EXISTS uptime_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id INTEGER NOT NULL,
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at DATETIME,
    duration_seconds INTEGER,
    root_cause TEXT,
    ai_summary TEXT,
    suppressed INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (monitor_id) REFERENCES uptime_monitors(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_uptime_incidents_monitor ON uptime_incidents(monitor_id, started_at);

-- Service dependency: when parent is down, suppress child alerts
CREATE TABLE IF NOT EXISTS uptime_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_monitor_id INTEGER NOT NULL,
    child_monitor_id INTEGER NOT NULL,
    UNIQUE(parent_monitor_id, child_monitor_id),
    FOREIGN KEY (parent_monitor_id) REFERENCES uptime_monitors(id) ON DELETE CASCADE,
    FOREIGN KEY (child_monitor_id) REFERENCES uptime_monitors(id) ON DELETE CASCADE
);

-- Alert silence windows (per monitor or global tag)
CREATE TABLE IF NOT EXISTS uptime_silences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id INTEGER,
    tag TEXT,
    until_at DATETIME NOT NULL,
    reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Push monitor last-seen (heartbeat token -> monitor_id)
CREATE TABLE IF NOT EXISTS uptime_push_tokens (
    token TEXT PRIMARY KEY,
    monitor_id INTEGER NOT NULL UNIQUE,
    last_seen DATETIME,
    FOREIGN KEY (monitor_id) REFERENCES uptime_monitors(id) ON DELETE CASCADE
);
"""
