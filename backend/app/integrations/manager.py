"""Central Application Integration Manager (Phase 5.2).

Single entry point for application discovery, capability resolution, provider routing,
central permission enforcement, execution lifecycle, and health diagnostics.
"""

from datetime import datetime, timezone
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.db.audit import audit_logger
from app.integrations.discovery import application_discovery_engine
from app.integrations.models import (
    AppCategory,
    AppExecuteCapabilityResponse,
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    PermissionLevel,
    ProviderType,
)
from app.integrations.permissions import integration_permissions
from app.integrations.providers.base import BaseIntegrationProvider, IntegrationProviderError
from app.integrations.providers.browser import BrowserAutomationProvider
from app.integrations.providers.desktop_ui import DesktopUIProvider
from app.integrations.providers.office_com import OfficeCOMProvider
from app.integrations.registry import application_registry
from app.tools.base import ExecutionContext, PolicyDecision, RiskTier

logger = logging.getLogger("jarvis.integrations.manager")


class ApplicationIntegrationManager:
    """Orchestrates modular application integrations across browsers, Office, and messaging."""

    def __init__(self):
        self.registry = application_registry
        self.discovery = application_discovery_engine
        self.permissions = integration_permissions
        self._providers: Dict[ProviderType, BaseIntegrationProvider] = {}
        self._activity_history: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._init_providers()

    def _init_providers(self):
        """Register built-in integration provider adapters."""
        self._providers[ProviderType.DESKTOP_UI] = DesktopUIProvider()
        self._providers[ProviderType.OFFICE_COM] = OfficeCOMProvider()
        self._providers[ProviderType.BROWSER_AUTOMATION] = BrowserAutomationProvider()

    def get_provider(self, provider_type: ProviderType) -> Optional[BaseIntegrationProvider]:
        """Fetch provider adapter by type."""
        with self._lock:
            return self._providers.get(provider_type)

    def register_provider(self, provider: BaseIntegrationProvider) -> None:
        """Register a custom or future integration provider."""
        with self._lock:
            self._providers[provider.provider_type] = provider

    def list_applications(self, category: Optional[AppCategory] = None) -> List[ApplicationManifest]:
        """List registered applications with current installation and running states."""
        return self.registry.list_all(category=category)

    def get_application(self, app_id: str) -> Optional[ApplicationManifest]:
        """Fetch application manifest by ID."""
        return self.registry.get(app_id)

    def refresh_discovery(self, refresh_installed: bool = True) -> List[ApplicationManifest]:
        """Perform on-demand application discovery scanning."""
        return self.discovery.discover_all(refresh_installed=refresh_installed)

    def select_provider(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        preferred_provider: Optional[ProviderType] = None,
    ) -> Optional[BaseIntegrationProvider]:
        """Select the best available, authorized provider for an application capability."""
        with self._lock:
            # 1. If preferred provider requested and supported, check availability
            if preferred_provider and preferred_provider in capability.supported_providers:
                p = self._providers.get(preferred_provider)
                if p and p.is_available_for(manifest):
                    return p

            # 2. Priority order: Official/Native API / COM -> Browser Automation -> Desktop UI
            priority_order = [
                ProviderType.OFFICE_COM,
                ProviderType.BROWSER_AUTOMATION,
                ProviderType.NATIVE_API,
                ProviderType.DESKTOP_UI,
            ]

            for p_type in priority_order:
                if p_type in capability.supported_providers:
                    p = self._providers.get(p_type)
                    if p and p.is_available_for(manifest):
                        return p

            return None

    async def execute_capability(
        self,
        app_id: str,
        capability_id: str,
        parameters: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
        preferred_provider: Optional[ProviderType] = None,
        user_confirmed: bool = False,
        approval_binding_id: Optional[str] = None,
    ) -> AppExecuteCapabilityResponse:
        """Central execution pipeline with permission check, provider routing, and auditing."""
        ctx = context or ExecutionContext(execution_id=f"app-exec-{datetime.now(timezone.utc).timestamp()}")
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Resolve manifest
        manifest = self.registry.get(app_id)
        if not manifest:
            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=ProviderType.DESKTOP_UI,
                error=f"Application '{app_id}' is not registered in the integration catalog.",
                error_code="APPLICATION_NOT_REGISTERED",
            )

        # 2. Resolve capability
        capability: Optional[CapabilitySpec] = None
        for cap in manifest.capabilities:
            if cap.id.lower() == capability_id.lower():
                capability = cap
                break

        if not capability:
            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=ProviderType.DESKTOP_UI,
                error=f"Capability '{capability_id}' is not supported by '{manifest.display_name}'.",
                error_code="CAPABILITY_NOT_FOUND",
            )

        # 3. Select provider
        provider = self.select_provider(manifest, capability, preferred_provider)
        if not provider:
            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=preferred_provider or ProviderType.DESKTOP_UI,
                error=f"No available integration provider found for '{capability.name}' on {manifest.display_name}.",
                error_code="PROVIDER_UNAVAILABLE",
            )

        # 4. Central permission evaluation
        decision, reason, binding = self.permissions.evaluate_capability(
            manifest=manifest,
            capability=capability,
            provider=provider.provider_type,
            parameters=parameters,
            user_confirmed=user_confirmed,
            approval_binding_id=approval_binding_id,
        )

        if decision == PolicyDecision.BLOCK:
            audit_logger.log(
                action_name=f"APP_BLOCK_{capability.id}",
                risk_tier=capability.risk_tier,
                status="POLICY_BLOCKED",
                details={"app_id": app_id, "reason": reason, "params": parameters},
            )
            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=provider.provider_type,
                error=reason,
                error_code="PERMISSION_DENIED",
            )

        if decision == PolicyDecision.REQUIRE_APPROVAL:
            # Bind approval strictly to exact action parameters
            binding_id = binding.binding_id if binding else None
            summary = binding.action_summary if binding else f"Execute {capability.name} on {manifest.display_name}"

            audit_logger.log(
                action_name=f"APP_APPROVAL_REQUIRED_{capability.id}",
                risk_tier=capability.risk_tier,
                status="AWAITING_APPROVAL",
                details={
                    "app_id": app_id,
                    "binding_id": binding_id,
                    "summary": summary,
                    "params": parameters,
                },
            )
            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=provider.provider_type,
                approval_required=True,
                approval_id=binding_id,
                action_summary=summary,
                error="Action requires explicit user approval.",
                error_code="APPROVAL_REQUIRED",
            )

        # 5. Execute capability via selected provider
        activity_record = {
            "execution_id": ctx.execution_id,
            "timestamp": now_iso,
            "app_id": app_id,
            "display_name": manifest.display_name,
            "capability_id": capability.id,
            "provider": provider.provider_type.value,
            "status": "executing",
        }
        with self._lock:
            self._activity_history.append(activity_record)

        try:
            result = await provider.execute_capability(manifest, capability, parameters, ctx)
            activity_record["status"] = "success"

            audit_logger.log(
                action_name=f"APP_EXECUTE_{capability.id}",
                risk_tier=capability.risk_tier,
                status="SUCCESS",
                details={"app_id": app_id, "provider": provider.provider_type.value, "result": result},
            )

            return AppExecuteCapabilityResponse(
                success=True,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=provider.provider_type,
                result=result,
            )

        except Exception as exc:
            logger.error(f"Execution error on {manifest.display_name} via {provider.provider_type.value}: {exc}")
            activity_record["status"] = "failed"
            activity_record["error"] = str(exc)

            # Safe Fallback: only for read-only or safe idempotent operations, never for consequential actions
            if capability.permission_level in (PermissionLevel.READ_ONLY, PermissionLevel.CONTROLLED):
                if provider.provider_type != ProviderType.DESKTOP_UI:
                    fallback_provider = self._providers.get(ProviderType.DESKTOP_UI)
                    if fallback_provider and fallback_provider.is_available_for(manifest):
                        logger.info(f"Attempting safe fallback to DesktopUIProvider for {capability.id}...")
                        try:
                            fb_result = await fallback_provider.execute_capability(manifest, capability, parameters, ctx)
                            activity_record["status"] = "success_via_fallback"
                            activity_record["provider_fallback"] = ProviderType.DESKTOP_UI.value
                            return AppExecuteCapabilityResponse(
                                success=True,
                                app_id=app_id,
                                capability_id=capability_id,
                                provider_used=ProviderType.DESKTOP_UI,
                                result=fb_result,
                            )
                        except Exception as fb_exc:
                            logger.error(f"Fallback also failed: {fb_exc}")

            audit_logger.log(
                action_name=f"APP_FAILED_{capability.id}",
                risk_tier=capability.risk_tier,
                status="FAILED",
                details={"app_id": app_id, "error": str(exc)},
            )

            return AppExecuteCapabilityResponse(
                success=False,
                app_id=app_id,
                capability_id=capability_id,
                provider_used=provider.provider_type,
                error=f"Execution failed on {manifest.display_name}: {str(exc)}",
                error_code="EXECUTION_FAILED",
            )

    def get_recent_activity(self, limit: int = 25) -> List[Dict[str, Any]]:
        """Return recent application integration activity records."""
        with self._lock:
            return list(reversed(self._activity_history[-limit:]))


# Global singleton instance
application_manager = ApplicationIntegrationManager()
