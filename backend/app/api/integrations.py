"""REST API Endpoints for Modular Application Integrations (Phase 5.2)."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.integrations.manager import application_manager
from app.integrations.models import (
    AppCategory,
    AppExecuteCapabilityRequest,
    AppExecuteCapabilityResponse,
    ApplicationManifest,
    AppPermissionState,
    ProviderType,
)
from app.integrations.permissions import integration_permissions

router = APIRouter(prefix="/v1/integrations", tags=["Application Integrations"])


class PermissionUpdatePayload(BaseModel):
    app_id: str
    is_enabled: Optional[bool] = None
    disabled_providers: Optional[List[str]] = None
    disabled_capabilities: Optional[List[str]] = None


class AuthorizeCapabilityPayload(BaseModel):
    app_id: str
    capability_id: str
    scope: str = Field(default="session", description="'session' or 'permanent'")


@router.get("/applications", response_model=List[ApplicationManifest])
def list_applications(category: Optional[str] = Query(None, description="Filter by category ('browser', 'office', 'messaging')")):
    """List all registered desktop applications with current discovery status."""
    cat = None
    if category:
        try:
            cat = AppCategory(category.lower().strip())
        except ValueError:
            pass
    return application_manager.list_applications(category=cat)


@router.get("/applications/{app_id}", response_model=ApplicationManifest)
def get_application(app_id: str):
    """Get detailed manifest, capabilities, and health for a specific application."""
    manifest = application_manager.get_application(app_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found.")
    return manifest


@router.post("/discover", response_model=List[ApplicationManifest])
def trigger_discovery(refresh_installed: bool = Query(True, description="Perform deep scan of Windows Registry and filesystem")):
    """Trigger safe discovery of installed and running applications."""
    return application_manager.refresh_discovery(refresh_installed=refresh_installed)


@router.get("/permissions/{app_id}", response_model=AppPermissionState)
def get_app_permissions(app_id: str):
    """Retrieve user permission configuration for an application."""
    manifest = application_manager.get_application(app_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Application '{app_id}' not found.")
    return integration_permissions.get_permission_state(app_id)


@router.post("/permissions", response_model=AppPermissionState)
def update_app_permissions(payload: PermissionUpdatePayload):
    """Configure permissions: enable/disable app, providers, or specific capabilities."""
    manifest = application_manager.get_application(payload.app_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Application '{payload.app_id}' not found.")

    if payload.is_enabled is not None:
        integration_permissions.set_app_enabled(payload.app_id, payload.is_enabled)

    if payload.disabled_providers is not None:
        state = integration_permissions.get_permission_state(payload.app_id)
        parsed_providers = []
        for p in payload.disabled_providers:
            try:
                parsed_providers.append(ProviderType(p.lower().strip()))
            except ValueError:
                pass
        state.disabled_providers = parsed_providers

    if payload.disabled_capabilities is not None:
        state = integration_permissions.get_permission_state(payload.app_id)
        state.disabled_capabilities = [c.lower().strip() for c in payload.disabled_capabilities]

    return integration_permissions.get_permission_state(payload.app_id)


@router.post("/permissions/authorize-capability", response_model=AppPermissionState)
def authorize_app_capability(payload: AuthorizeCapabilityPayload):
    """Authorize a disabled capability for the current session or permanently."""
    manifest = application_manager.get_application(payload.app_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Application '{payload.app_id}' not found.")
    return integration_permissions.authorize_capability(payload.app_id, payload.capability_id, scope=payload.scope)


@router.get("/activity")
def get_recent_activity(limit: int = Query(25, ge=1, le=100)):
    """Retrieve recent application action history and provider telemetry."""
    return {
        "total": len(application_manager.get_recent_activity(limit=limit)),
        "activity": application_manager.get_recent_activity(limit=limit),
    }


@router.post("/execute", response_model=AppExecuteCapabilityResponse)
async def execute_application_capability(payload: AppExecuteCapabilityRequest):
    """Execute an application integration capability."""
    return await application_manager.execute_capability(
        app_id=payload.app_id,
        capability_id=payload.capability_id,
        parameters=payload.parameters,
        preferred_provider=payload.preferred_provider,
        user_confirmed=False,
    )
