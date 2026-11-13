"""User Preference and Workflow Memory REST API Router."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.memory.models import (
    MemorySettings,
    PreferenceCategory,
    PreferenceResolution,
    UserPreference,
)
from app.memory.service import preference_service
from app.memory.store import preference_memory_store

router = APIRouter(prefix="/v1/preferences", tags=["preferences"])


class PreferenceCreateRequest(BaseModel):
    category: str
    key: str
    app_id: Optional[str] = None
    target_entity: Optional[str] = None
    browser_id: Optional[str] = None
    profile_name: Optional[str] = None
    workflow_type: Optional[str] = None
    details: Dict[str, Any] = {}


class MemorySettingsUpdateRequest(BaseModel):
    memory_enabled: Optional[bool] = None
    learning_enabled: Optional[bool] = None


@router.get("", response_model=List[UserPreference])
def list_preferences(
    category: Optional[str] = Query(None, description="Filter by category"),
    only_confirmed: bool = Query(False, description="Filter only confirmed preferences"),
):
    """List stored user preferences."""
    cat = None
    if category:
        try:
            cat = PreferenceCategory(category.lower().strip())
        except ValueError:
            pass
    return preference_memory_store.list_preferences(category=cat, only_confirmed=only_confirmed)


@router.post("", response_model=UserPreference)
def create_preference(req: PreferenceCreateRequest):
    """Create or update an explicit user preference."""
    try:
        cat = PreferenceCategory(req.category.lower().strip())
    except ValueError:
        cat = PreferenceCategory.GLOBAL_DEFAULTS

    return preference_service.set_explicit_preference(
        category=cat,
        key=req.key,
        app_id=req.app_id,
        target_entity=req.target_entity,
        browser_id=req.browser_id,
        profile_name=req.profile_name,
        workflow_type=req.workflow_type,
        details=req.details,
    )


@router.get("/resolve", response_model=PreferenceResolution)
def resolve_preference(
    explicit_request: Optional[str] = Query(None),
    person_name: Optional[str] = Query(None),
    website_domain: Optional[str] = Query(None),
    workflow_type: Optional[str] = Query(None),
):
    """Resolve preferred application and browser according to priority hierarchy."""
    return preference_service.resolve_application(
        explicit_request=explicit_request,
        person_name=person_name,
        website_domain=website_domain,
        workflow_type=workflow_type,
    )


@router.delete("/{preference_id}")
def delete_preference(preference_id: str):
    """Delete a user preference record."""
    deleted = preference_memory_store.delete_preference(preference_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Preference not found.")
    return {"status": "deleted", "preference_id": preference_id}


@router.post("/clear")
def clear_all_preferences():
    """Clear all preference records and observations."""
    preference_memory_store.clear_all()
    return {"status": "cleared"}


@router.get("/settings", response_model=MemorySettings)
def get_memory_settings():
    """Retrieve memory and learning configuration."""
    return preference_service.settings


@router.post("/settings", response_model=MemorySettings)
def update_memory_settings(req: MemorySettingsUpdateRequest):
    """Update memory and learning preferences."""
    if req.memory_enabled is not None:
        preference_service.set_memory_enabled(req.memory_enabled)
    if req.learning_enabled is not None:
        preference_service.set_learning_enabled(req.learning_enabled)
    return preference_service.settings
