"""JARVIS Database Connection and Persistence Initialization."""

import sqlite3
from pathlib import Path
from typing import Dict, Any
from app.core.config import settings


def get_db_path() -> Path:
    """Resolve the SQLite database path from database URL."""
    db_url = settings.JARVIS_DATABASE_URL
    if db_url.startswith("sqlite:///"):
        rel_or_abs = db_url.replace("sqlite:///", "")
        path = Path(rel_or_abs).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return Path("./data/jarvis.db").resolve()


def init_db() -> None:
    """Initialize SQLite database tables for settings, memory, and audit trails."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create baseline audit log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action_name TEXT NOT NULL,
            risk_tier TEXT NOT NULL,
            status TEXT NOT NULL,
            details TEXT
        )
    """)

    # Create system key-value settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Create persistent user preferences table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            app_id TEXT,
            target_entity TEXT,
            browser_id TEXT,
            profile_name TEXT,
            workflow_type TEXT,
            preference_type TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            source TEXT NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            user_confirmed INTEGER NOT NULL DEFAULT 1,
            details TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_confirmed_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_cat_key ON user_preferences (category, preference_key);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_target ON user_preferences (target_entity);")

    # Create preference observation frequency tracker
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preference_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preference_key TEXT NOT NULL,
            category TEXT NOT NULL,
            app_id TEXT,
            target_entity TEXT,
            browser_id TEXT,
            count INTEGER NOT NULL DEFAULT 1,
            first_observed TEXT NOT NULL,
            last_observed TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_key ON preference_observations (preference_key);")

    # Create task plans table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_plans (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            original_objective TEXT NOT NULL,
            interpreted_goal TEXT NOT NULL,
            required_outcome TEXT NOT NULL,
            status TEXT NOT NULL,
            assumptions TEXT,
            constraints TEXT,
            steps TEXT NOT NULL,
            current_step_index INTEGER NOT NULL DEFAULT 0,
            recovery_strategy TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_plans_session ON task_plans (session_id);")

    conn.commit()
    conn.close()


def check_db_health() -> Dict[str, Any]:
    """Test connectivity and table state in SQLite database."""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return {
            "status": "healthy",
            "database_path": str(db_path),
            "tables": tables,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }

