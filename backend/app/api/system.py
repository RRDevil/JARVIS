"""JARVIS System Lifecycle API."""

import os
import time
import asyncio
from typing import Dict
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.db.session import get_db_path
import sqlite3

router = APIRouter(prefix="/v1/system", tags=["System Lifecycle"])


class ShutdownResponse(BaseModel):
    status: str
    message: str


def _record_shutdown_audit():
    try:
        conn = sqlite3.connect(str(get_db_path()))
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO audit_logs (timestamp, action_name, risk_tier, status, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "system_shutdown",
                "CONTROLLED",
                "COMPLETED",
                "Shutdown requested via user interface",
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _execute_process_shutdown():
    """Terminate the backend process after a short delay so HTTP response delivers."""
    time.sleep(0.35)
    _record_shutdown_audit()
    os._exit(0)


@router.post("/shutdown", response_model=ShutdownResponse)
async def shutdown_system(background_tasks: BackgroundTasks) -> ShutdownResponse:
    """Trigger graceful shutdown of JARVIS services."""
    background_tasks.add_task(_execute_process_shutdown)
    return ShutdownResponse(
        status="shutting_down",
        message="JARVIS shutdown sequence initiated. All services halting.",
    )

