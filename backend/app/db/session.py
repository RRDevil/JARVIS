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

