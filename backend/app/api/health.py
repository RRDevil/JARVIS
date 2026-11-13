"""JARVIS System Health & Diagnostics API."""

import sys
import time
import platform
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.session import check_db_health

router = APIRouter(tags=["Health & Telemetry"])

# Record service launch timestamp
START_TIME = time.time()


class SubsystemStatus(BaseModel):
    status: str
    details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    uptime_seconds: float
    system: Dict[str, str]
    subsystems: Dict[str, SubsystemStatus]
    capabilities: List[str]


@router.get("/health", response_model=HealthResponse)
def get_system_health() -> HealthResponse:
    """Return comprehensive diagnostics on the JARVIS assistant backend."""
    current_time = time.time()
    uptime = round(current_time - START_TIME, 2)
    now_iso = datetime.now(timezone.utc).isoformat()

    db_health = check_db_health()
    db_status = "operational" if db_health.get("status") == "healthy" else "degraded"

    ai_configured = bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY != "your_gemini_api_key_here")

    return HealthResponse(
        status="operational",
        service="JARVIS Assistant Core",
        version=settings.VERSION,
        timestamp=now_iso,
        uptime_seconds=uptime,
        system={
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "python": sys.version.split()[0],
            "host": settings.JARVIS_HOST,
            "port": str(settings.JARVIS_PORT),
        },
        subsystems={
            "database": SubsystemStatus(
                status=db_status,
                details=db_health,
            ),
            "ai_provider": SubsystemStatus(
                status="configured" if ai_configured else "ready_for_key",
                details={
                    "provider": "Google Gemini",
                    "default_model": settings.GEMINI_DEFAULT_MODEL,
                    "has_key": ai_configured,
                },
            ),
            "security": SubsystemStatus(
                status="enforced",
                details={
                    "loopback_only": settings.JARVIS_HOST in ("127.0.0.1", "localhost"),
                    "cors_origins": settings.JARVIS_ALLOWED_ORIGINS,
                    "workspace_root": str(settings.workspace_path),
                },
            ),
            "automation": SubsystemStatus(
                status="ready",
                details={
                    "platform": "Windows",
                    "uia_available": platform.system() == "Windows",
                },
            ),
        },
        capabilities=[
            "diagnostics_monitoring",
            "sqlite_persistence",
            "cors_security_enforcement",
            "gemini_provider_scaffolding",
            "windows_automation_ready",
        ],
    )


@router.get("/info")
def get_system_info() -> Dict[str, Any]:
    """Lightweight metadata endpoint for quick handshake."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "online",
        "api_prefix": settings.API_V1_STR,
    }

