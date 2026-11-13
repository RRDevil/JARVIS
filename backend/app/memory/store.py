"""SQLite Persistence Store for User Preferences and Workflow Memory."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.session import get_db_path, init_db
from app.memory.models import (
    MemorySettings,
    PreferenceCategory,
    PreferenceSource,
    PreferenceType,
    UserPreference,
)

logger = logging.getLogger("jarvis.memory.store")

# Blacklisted sensitive keys and values to ensure privacy protection
SENSITIVE_KEY_SUBSTRINGS = (
    "password", "secret", "token", "auth", "credential", "cookie",
    "bearer", "session_id", "private_key", "credit_card", "ssn"
)


class MemoryPrivacyViolation(Exception):
    """Raised when an attempt is made to persist sensitive or private communication contents."""
    pass


def _sanitize_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect and strip or reject prohibited sensitive credentials."""
    sanitized = {}
    for k, v in details.items():
        k_lower = str(k).lower()
        if any(bad in k_lower for bad in SENSITIVE_KEY_SUBSTRINGS):
            raise MemoryPrivacyViolation(
                f"Refusing to persist preference containing sensitive key: '{k}'."
            )
        # Check string values for obvious tokens or passwords
        if isinstance(v, str):
            v_lower = v.lower()
            if any(bad in v_lower for bad in ("bearer ", "eyj", "ghp_", "sk-", "xoxb-")):
                raise MemoryPrivacyViolation(
                    f"Refusing to persist preference containing potential secret token in field '{k}'."
                )
        sanitized[k] = v
    return sanitized


class PreferenceMemoryStore:
    """Thread-safe SQLite store for user preferences and workflow memory."""

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or get_db_path()
        self._init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        init_db()
        conn = self._get_connection()
        cursor = conn.cursor()

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
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_cat_key ON user_preferences (category, preference_key);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pref_target ON user_preferences (target_entity);")

        # Inferred observation frequency tracker for confirmation thresholding
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
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_obs_key ON preference_observations (preference_key);")

        conn.commit()
        conn.close()

    def save_preference(self, pref: UserPreference) -> UserPreference:
        """Insert or update a user preference record with privacy verification."""
        clean_details = _sanitize_details(pref.details)
        details_json = json.dumps(clean_details)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO user_preferences (
                id, category, preference_key, app_id, target_entity, browser_id,
                profile_name, workflow_type, preference_type, confidence, source,
                is_enabled, user_confirmed, details, created_at, updated_at, last_confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                category = excluded.category,
                preference_key = excluded.preference_key,
                app_id = excluded.app_id,
                target_entity = excluded.target_entity,
                browser_id = excluded.browser_id,
                profile_name = excluded.profile_name,
                workflow_type = excluded.workflow_type,
                preference_type = excluded.preference_type,
                confidence = excluded.confidence,
                source = excluded.source,
                is_enabled = excluded.is_enabled,
                user_confirmed = excluded.user_confirmed,
                details = excluded.details,
                updated_at = excluded.updated_at,
                last_confirmed_at = excluded.last_confirmed_at;
        """, (
            pref.id,
            pref.category.value if isinstance(pref.category, PreferenceCategory) else pref.category,
            pref.preference_key,
            pref.app_id,
            pref.target_entity,
            pref.browser_id,
            pref.profile_name,
            pref.workflow_type,
            pref.preference_type.value if isinstance(pref.preference_type, PreferenceType) else pref.preference_type,
            pref.confidence,
            pref.source.value if isinstance(pref.source, PreferenceSource) else pref.source,
            1 if pref.is_enabled else 0,
            1 if pref.user_confirmed else 0,
            details_json,
            pref.created_at,
            pref.updated_at,
            pref.last_confirmed_at,
        ))

        conn.commit()
        conn.close()
        return pref

    def get_preference(self, preference_id: str) -> Optional[UserPreference]:
        """Fetch preference by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM user_preferences WHERE id = ?", (preference_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_preference(row)

    def get_by_key(self, preference_key: str, category: Optional[PreferenceCategory] = None) -> Optional[UserPreference]:
        """Fetch preference by normalized key and optional category."""
        conn = self._get_connection()
        cursor = conn.cursor()
        if category:
            cat_str = category.value if isinstance(category, PreferenceCategory) else str(category)
            cursor.execute(
                "SELECT * FROM user_preferences WHERE preference_key = ? AND category = ? AND is_enabled = 1 ORDER BY confidence DESC LIMIT 1",
                (preference_key, cat_str)
            )
        else:
            cursor.execute(
                "SELECT * FROM user_preferences WHERE preference_key = ? AND is_enabled = 1 ORDER BY confidence DESC LIMIT 1",
                (preference_key,)
            )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_preference(row)

    def find_by_entity(self, target_entity: str, category: Optional[PreferenceCategory] = None) -> List[UserPreference]:
        """Find active preferences matching a target entity (e.g. contact name or website domain)."""
        clean_entity = target_entity.lower().strip()
        conn = self._get_connection()
        cursor = conn.cursor()
        if category:
            cat_str = category.value if isinstance(category, PreferenceCategory) else str(category)
            cursor.execute(
                "SELECT * FROM user_preferences WHERE LOWER(target_entity) = ? AND category = ? AND is_enabled = 1",
                (clean_entity, cat_str)
            )
        else:
            cursor.execute(
                "SELECT * FROM user_preferences WHERE LOWER(target_entity) = ? AND is_enabled = 1",
                (clean_entity,)
            )
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_preference(r) for r in rows]

    def list_preferences(
        self,
        category: Optional[PreferenceCategory] = None,
        only_confirmed: bool = False,
    ) -> List[UserPreference]:
        """List preferences with optional category filter."""
        conn = self._get_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM user_preferences WHERE 1=1"
        params: List[Any] = []

        if category:
            cat_str = category.value if isinstance(category, PreferenceCategory) else str(category)
            query += " AND category = ?"
            params.append(cat_str)

        if only_confirmed:
            query += " AND user_confirmed = 1"

        query += " ORDER BY updated_at DESC"
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_preference(r) for r in rows]

    def delete_preference(self, preference_id: str) -> bool:
        """Delete a preference record by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_preferences WHERE id = ?", (preference_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def clear_all(self) -> None:
        """Clear all preference and observation records."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_preferences;")
        cursor.execute("DELETE FROM preference_observations;")
        conn.commit()
        conn.close()

    def record_observation(
        self,
        preference_key: str,
        category: PreferenceCategory,
        app_id: Optional[str] = None,
        target_entity: Optional[str] = None,
        browser_id: Optional[str] = None,
    ) -> int:
        """Track frequency of an observed action pattern to determine learning threshold."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO preference_observations (
                preference_key, category, app_id, target_entity, browser_id, count, first_observed, last_observed
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(preference_key) DO UPDATE SET
                count = count + 1,
                last_observed = excluded.last_observed,
                app_id = COALESCE(excluded.app_id, app_id),
                browser_id = COALESCE(excluded.browser_id, browser_id);
        """, (
            preference_key,
            category.value if isinstance(category, PreferenceCategory) else category,
            app_id,
            target_entity,
            browser_id,
            now,
            now,
        ))
        cursor.execute("SELECT count FROM preference_observations WHERE preference_key = ?", (preference_key,))
        count_row = cursor.fetchone()
        new_count = count_row[0] if count_row else 1
        conn.commit()
        conn.close()
        return new_count

    def _row_to_preference(self, row: sqlite3.Row) -> UserPreference:
        raw_details = row["details"]
        details_dict = json.loads(raw_details) if raw_details else {}
        return UserPreference(
            id=row["id"],
            category=PreferenceCategory(row["category"]),
            preference_key=row["preference_key"],
            app_id=row["app_id"],
            target_entity=row["target_entity"],
            browser_id=row["browser_id"],
            profile_name=row["profile_name"],
            workflow_type=row["workflow_type"],
            preference_type=PreferenceType(row["preference_type"]),
            confidence=float(row["confidence"]),
            source=PreferenceSource(row["source"]),
            is_enabled=bool(row["is_enabled"]),
            user_confirmed=bool(row["user_confirmed"]),
            details=details_dict,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_confirmed_at=row["last_confirmed_at"],
        )


# Global singleton instance
preference_memory_store = PreferenceMemoryStore()
