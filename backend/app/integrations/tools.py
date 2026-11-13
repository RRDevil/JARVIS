"""Typed BaseTool Implementations for Application Integrations (Phase 5.2).

Exposes application discovery, capability inspection, and managed execution
through JARVIS Core ToolRegistry and central policy engine.
"""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.integrations.manager import application_manager
from app.integrations.models import AppCategory, ProviderType
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class AppDiscoverParams(BaseModel):
    category: Optional[str] = Field(
        default=None,
        description="Optional filter by category ('browser', 'office', 'messaging').",
    )
    refresh: bool = Field(
        default=False,
        description="Whether to perform a fresh filesystem and registry discovery scan.",
    )


class AppListCapabilitiesParams(BaseModel):
    app_id: str = Field(
        ...,
        description="Target application identifier (e.g. 'browser.opera_gx', 'office.word', 'messaging.discord').",
    )


class AppExecuteCapabilityParams(BaseModel):
    app_id: str = Field(
        ...,
        description="Target application identifier (e.g. 'browser.opera_gx', 'office.word', 'messaging.discord').",
    )
    capability_id: str = Field(
        ...,
        description="Capability to invoke (e.g. 'browser.navigate', 'word.read_document', 'excel.modify_cells').",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the application capability.",
    )
    preferred_provider: Optional[str] = Field(
        default=None,
        description="Optional preferred provider adapter ('desktop_ui', 'office_com', 'browser_automation').",
    )


class AppDiscoverTool(BaseTool):
    name = "app_discover"
    description = (
        "Discover installed and running desktop applications across browsers (Opera GX, Chrome), "
        "Microsoft Office (Word, Excel, PowerPoint, Outlook, OneNote, Access), and messaging (Discord, WhatsApp, Instagram)."
    )
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = AppDiscoverParams

    async def execute(self, params: AppDiscoverParams, context: ExecutionContext) -> ToolResult:
        try:
            cat = None
            if params.category:
                try:
                    cat = AppCategory(params.category.lower().strip())
                except ValueError:
                    pass

            if params.refresh:
                manifests = application_manager.refresh_discovery(refresh_installed=True)
            else:
                manifests = application_manager.list_applications(category=cat)

            data = [
                {
                    "app_id": m.app_id,
                    "display_name": m.display_name,
                    "category": m.category.value,
                    "is_installed": m.is_installed,
                    "installed_path": m.installed_path,
                    "is_running": m.is_running,
                    "running_window_count": len(m.running_window_handles),
                    "supported_providers": [p.value for p in m.supported_providers],
                    "capabilities": [c.id for c in m.capabilities],
                    "health_status": m.health_status.value,
                }
                for m in manifests
            ]

            return ToolResult(
                success=True,
                data={"total_discovered": len(data), "applications": data},
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Application discovery error: {str(exc)}",
                error_code="DISCOVERY_FAILED",
            )


class AppListCapabilitiesTool(BaseTool):
    name = "app_list_capabilities"
    description = "List all supported capabilities, permission tiers, and providers for an application."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = AppListCapabilitiesParams

    async def execute(self, params: AppListCapabilitiesParams, context: ExecutionContext) -> ToolResult:
        manifest = application_manager.get_application(params.app_id)
        if not manifest:
            return ToolResult(
                success=False,
                error=f"Application '{params.app_id}' not found.",
                error_code="APP_NOT_FOUND",
            )

        caps = [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "permission_level": c.permission_level.value,
                "risk_tier": c.risk_tier.value,
                "supported_providers": [p.value for p in c.supported_providers],
            }
            for c in manifest.capabilities
        ]

        return ToolResult(
            success=True,
            data={
                "app_id": manifest.app_id,
                "display_name": manifest.display_name,
                "is_installed": manifest.is_installed,
                "is_running": manifest.is_running,
                "capabilities": caps,
            },
            verified=True,
        )


class AppExecuteCapabilityTool(BaseTool):
    name = "app_execute_capability"
    description = (
        "Execute an authorized capability against an application integration (Opera GX, Chrome, Word, Excel, PowerPoint, Outlook, Discord). "
        "Automatically routes to the best available provider (Native COM, Browser Automation, Desktop UI)."
    )
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = AppExecuteCapabilityParams

    async def execute(self, params: AppExecuteCapabilityParams, context: ExecutionContext) -> ToolResult:
        pref = None
        if params.preferred_provider:
            try:
                pref = ProviderType(params.preferred_provider.lower().strip())
            except ValueError:
                pass

        resp = await application_manager.execute_capability(
            app_id=params.app_id,
            capability_id=params.capability_id,
            parameters=params.parameters,
            context=context,
            preferred_provider=pref,
            user_confirmed=True,  # ExecutionEngine passes this when confirmed
        )

        if resp.success:
            return ToolResult(
                success=True,
                data={
                    "app_id": resp.app_id,
                    "capability_id": resp.capability_id,
                    "provider_used": resp.provider_used.value,
                    "result": resp.result,
                },
                verified=True,
            )

        return ToolResult(
            success=False,
            error=resp.error or "Capability execution failed.",
            error_code=resp.error_code or "CAPABILITY_FAILED",
        )
