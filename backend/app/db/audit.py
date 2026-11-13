"""Database Audit Logging Service for JARVIS Tool Execution."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.db.session import get_db_path
from app.tools.base import RiskTier


class AuditRecord(BaseModel):
    """Normalized audit log event record."""

    id: Optional[int] = None
    timestamp: str
    action_name: str
    risk_tier: RiskTier
    status: str
    details: Dict[str, Any]


class AuditLogger:
    """Manages persistent audit trail records in the SQLite database."""

    def __init__(self, db_path_override: Optional[str] = None):
        self._db_path_override = db_path_override

    def _get_connection(self) -> sqlite3.Connection:
        if self._db_path_override:
            return sqlite3.connect(self._db_path_override)
        return sqlite3.connect(str(get_db_path()))

    def log(
        self,
        action_name: str,
        risk_tier: RiskTier,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> int:
        """Insert an audit log entry and return the newly assigned record ID."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        details_str = json.dumps(details or {}, default=str)

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_logs (timestamp, action_name, risk_tier, status, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ts, action_name, risk_tier.value if isinstance(risk_tier, RiskTier) else str(risk_tier), status, details_str),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def get_recent(self, limit: int = 50) -> List[AuditRecord]:
        """Fetch the most recent audit records in descending chronological order."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, timestamp, action_name, risk_tier, status, details
                FROM audit_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            results: List[AuditRecord] = []
            for row in rows:
                rec_id, ts, action, risk, stat, det_str = row
                try:
                    det = json.loads(det_str) if det_str else {}
                except Exception:
                    det = {"raw": det_str}
                results.append(
                    AuditRecord(
                        id=rec_id,
                        timestamp=ts,
                        action_name=action,
                        risk_tier=RiskTier(risk) if risk in RiskTier._value2member_map_ else RiskTier.READ_ONLY,
                        status=stat,
                        details=det,
                    )
                )
            return results
        finally:
            conn.close()


# Singleton audit logger
audit_logger = AuditLogger()

