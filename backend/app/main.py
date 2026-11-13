"""JARVIS Desktop Assistant - FastAPI Backend Entrypoint."""

from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import init_db
from app.tools.defaults import register_default_windows_tools
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.tools import router as tools_router
from app.api.approvals import router as approvals_router
from app.api.system import router as system_router
from app.api.screen import router as screen_router
from app.api.voice import router as voice_router
from app.api.integrations import router as integrations_router
from app.api.preferences import router as preferences_router
from app.api.plans import router as plans_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle management."""
    # Ensure database tables and workspace directory exist
    init_db()
    settings.workspace_path.mkdir(parents=True, exist_ok=True)
    # Register built-in Windows 11 desktop and UI automation tools
    register_default_windows_tools()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend service for JARVIS Windows Desktop AI Assistant",
    lifespan=lifespan,
    docs_url="/docs" if settings.JARVIS_DEBUG else None,
    redoc_url="/redoc" if settings.JARVIS_DEBUG else None,
)

# Configure Cross-Origin Resource Sharing (CORS) strictly for desktop client
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.JARVIS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(health_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(approvals_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(screen_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(preferences_router, prefix="/api")
app.include_router(plans_router, prefix="/api")

# Serve built production HUD assets if present
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if frontend_dist.exists() and (frontend_dist / "assets").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")


@app.get("/")
def root(request: Request):
    """Serve HUD web interface for browsers or JSON telemetry banner for API callers."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept and frontend_dist.exists() and (frontend_dist / "index.html").exists():
        from fastapi.responses import FileResponse
        return FileResponse(str(frontend_dist / "index.html"))

    return {
        "message": "JARVIS Assistant Core Online",
        "version": settings.VERSION,
        "docs": "/docs" if settings.JARVIS_DEBUG else "disabled",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.JARVIS_HOST,
        port=settings.JARVIS_PORT,
        reload=settings.JARVIS_DEBUG,
    )

