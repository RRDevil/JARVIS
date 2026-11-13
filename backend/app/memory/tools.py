"""Typed BaseTools for Preference and Workflow Memory (Phase 7 Foundation)."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.memory.models import PreferenceCategory
from app.memory.service import preference_service
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class PreferenceQueryParams(BaseModel):
    person_name: Optional[str] = Field(None, description="Name of contact or person to check communication preference for.")
    website_domain: Optional[str] = Field(None, description="Website domain (e.g. 'instagram.com', 'youtube.com') to check browser preference for.")
    workflow_type: Optional[str] = Field(None, description="Workflow type (e.g. 'messaging', 'document', 'browse').")
    explicit_request: Optional[str] = Field(None, description="Explicit app or browser mentioned in user prompt.")


class PreferenceStoreParams(BaseModel):
    category: str = Field(..., description="Category: 'person_communications', 'website_browsers', 'global_defaults', 'workflow_preferences'.")
    key: str = Field(..., description="Normalized key: e.g. 'person:john_doe', 'domain:instagram.com', 'default:browser'.")
    app_id: Optional[str] = Field(None, description="Application ID (e.g. 'browser.opera_gx', 'messaging.whatsapp').")
    target_entity: Optional[str] = Field(None, description="Target person name, website, or entity.")
    browser_id: Optional[str] = Field(None, description="Browser ID if web-based (e.g. 'browser.opera_gx').")
    details: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary safe preference metadata (NO secrets).")


class PreferenceQueryTool(BaseTool):
    name = "preference_query"
    description = (
        "Query saved user preferences for a contact, website, or workflow. "
        "Returns the resolved application and browser according to user preference memory."
    )
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = PreferenceQueryParams

    async def execute(self, params: PreferenceQueryParams, context: ExecutionContext) -> ToolResult:
        try:
            res = preference_service.resolve_application(
                explicit_request=params.explicit_request,
                person_name=params.person_name,
                website_domain=params.website_domain,
                workflow_type=params.workflow_type,
            )
            return ToolResult(
                success=True,
                data={
                    "resolved_app_id": res.resolved_app_id,
                    "resolved_browser_id": res.resolved_browser_id,
                    "resolved_profile": res.resolved_profile,
                    "resolution_source": res.resolution_source,
                    "confidence": res.confidence,
                    "requires_confirmation": res.requires_confirmation,
                    "explanation": res.explanation,
                },
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Preference query failed: {str(exc)}",
                error_code="PREFERENCE_QUERY_FAILED",
            )


class PreferenceStoreTool(BaseTool):
    name = "preference_store"
    description = (
        "Save or update an explicit user preference across sessions (e.g. preferred browser for a website, "
        "or preferred messaging app for a contact). Never stores credentials or private messages."
    )
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = PreferenceStoreParams

    async def execute(self, params: PreferenceStoreParams, context: ExecutionContext) -> ToolResult:
        try:
            try:
                cat = PreferenceCategory(params.category.lower().strip())
            except ValueError:
                cat = PreferenceCategory.GLOBAL_DEFAULTS

            pref = preference_service.set_explicit_preference(
                category=cat,
                key=params.key,
                app_id=params.app_id,
                target_entity=params.target_entity,
                browser_id=params.browser_id,
                details=params.details,
            )
            return ToolResult(
                success=True,
                data={
                    "preference_id": pref.id,
                    "category": pref.category.value,
                    "preference_key": pref.preference_key,
                    "app_id": pref.app_id,
                    "browser_id": pref.browser_id,
                    "user_confirmed": pref.user_confirmed,
                },
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Preference store failed: {str(exc)}",
                error_code="PREFERENCE_STORE_FAILED",
            )
