"""Centralized Permission & Capability Management Engine (Phase 5.2).

Enforces Level 1 to Level 4 authorization tiers, granular per-application and
per-capability overrides, and cryptographic approval binding for consequential actions.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.db.audit import audit_logger
from app.integrations.models import (
    ActionApprovalBinding,
    AppPermissionState,
    ApplicationManifest,
    CapabilitySpec,
    PermissionLevel,
    ProviderType,
)
from app.tools.base import PolicyDecision, RiskTier

logger = logging.getLogger("jarvis.integrations.permissions")


class IntegrationPermissionError(Exception):
    """Raised when an operation violates application integration permissions."""
    pass


class IntegrationPermissionManager:
    """Manages application capability permissions, approval bindings, and authorization checks."""

    def __init__(self):
        self._app_states: Dict[str, AppPermissionState] = {}
        self._approval_bindings: Dict[str, ActionApprovalBinding] = {}
        self._lock = threading.RLock()

    def get_permission_state(self, app_id: str) -> AppPermissionState:
        """Get or initialize permission state for an application."""
        with self._lock:
            app_clean = app_id.lower().strip()
            if app_clean not in self._app_states:
                self._app_states[app_clean] = AppPermissionState(app_id=app_clean)
            return self._app_states[app_clean]

    def set_app_enabled(self, app_id: str, enabled: bool) -> AppPermissionState:
        """Enable or disable entire integration for an application."""
        with self._lock:
            state = self.get_permission_state(app_id)
            state.is_enabled = enabled
            audit_logger.log(
                action_name=f"APP_PERMISSION_{'ENABLE' if enabled else 'DISABLE'}",
                risk_tier=RiskTier.CONTROLLED,
                status="SUCCESS",
                details={"app_id": app_id, "enabled": enabled},
            )
            return state

    def set_provider_enabled(self, app_id: str, provider: ProviderType, enabled: bool) -> AppPermissionState:
        """Enable or disable a specific integration provider for an application."""
        with self._lock:
            state = self.get_permission_state(app_id)
            if not enabled and provider not in state.disabled_providers:
                state.disabled_providers.append(provider)
            elif enabled and provider in state.disabled_providers:
                state.disabled_providers.remove(provider)
            return state

    def set_capability_enabled(self, app_id: str, capability_id: str, enabled: bool) -> AppPermissionState:
        """Enable or disable a specific capability for an application."""
        with self._lock:
            state = self.get_permission_state(app_id)
            cap_clean = capability_id.lower().strip()
            if not enabled and cap_clean not in state.disabled_capabilities:
                state.disabled_capabilities.append(cap_clean)
            elif enabled and cap_clean in state.disabled_capabilities:
                state.disabled_capabilities.remove(cap_clean)
            return state

    def authorize_capability(
        self,
        app_id: str,
        capability_id: str,
        scope: str = "session",
    ) -> AppPermissionState:
        """Authorize a capability either for the current session or permanently."""
        with self._lock:
            state = self.get_permission_state(app_id)
            cap_clean = capability_id.lower().strip()
            if scope == "permanent":
                if cap_clean in state.disabled_capabilities:
                    state.disabled_capabilities.remove(cap_clean)
                audit_logger.log(
                    action_name="APP_CAPABILITY_PERMANENT_AUTHORIZE",
                    risk_tier=RiskTier.CONTROLLED,
                    status="SUCCESS",
                    details={"app_id": app_id, "capability_id": capability_id},
                )
            else:
                if cap_clean not in state.session_authorized_capabilities:
                    state.session_authorized_capabilities.append(cap_clean)
                audit_logger.log(
                    action_name="APP_CAPABILITY_SESSION_AUTHORIZE",
                    risk_tier=RiskTier.CONTROLLED,
                    status="SUCCESS",
                    details={"app_id": app_id, "capability_id": capability_id},
                )
            return state

    def evaluate_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        provider: ProviderType,
        parameters: Dict[str, Any],
        user_confirmed: bool = False,
        approval_binding_id: Optional[str] = None,
    ) -> Tuple[PolicyDecision, str, Optional[ActionApprovalBinding]]:
        """Evaluate if an application capability is authorized to execute.

        Returns (PolicyDecision, reason, Optional[ActionApprovalBinding]).
        """
        with self._lock:
            app_id = manifest.app_id
            state = self.get_permission_state(app_id)

            # 1. Global Application Switch Check
            if not state.is_enabled or not manifest.is_enabled:
                return PolicyDecision.BLOCK, f"Application integration '{app_id}' is disabled by user policy.", None

            # 2. Provider Enablement Check
            if provider in state.disabled_providers:
                return PolicyDecision.BLOCK, f"Integration provider '{provider.value}' is disabled for '{app_id}'.", None

            # 3. Capability Enablement Check (Layer A: Capability Authorization)
            cap_id = capability.id.lower().strip()
            if cap_id in state.disabled_capabilities:
                if cap_id not in state.session_authorized_capabilities:
                    return PolicyDecision.BLOCK, f"Capability '{capability.id}' is disabled for '{app_id}'.", None

            # 4. Level 4 Restricted Actions Check: Permanently blocked from autonomous execution
            if capability.permission_level == PermissionLevel.RESTRICTED:
                return PolicyDecision.BLOCK, f"Capability '{capability.id}' is a Level 4 Restricted Action and is blocked by security policy.", None

            # 5. Level 1 Read-Only: Auto-allow
            if capability.permission_level == PermissionLevel.READ_ONLY:
                return PolicyDecision.ALLOW_AUTO, "Read-only application inspection permitted.", None

            # 6. Level 2 Controlled Interaction
            if capability.permission_level == PermissionLevel.CONTROLLED:
                # Check for explicit user override forcing approval
                if state.require_approval_overrides.get(capability.id, False):
                    binding = self.create_approval_binding(app_id, capability, parameters)
                    return PolicyDecision.REQUIRE_APPROVAL, f"Controlled action '{capability.name}' configured to require approval.", binding
                return PolicyDecision.ALLOW_AUTO, "Controlled interaction permitted.", None

            # 7. Level 3 Consequential Action
            if capability.permission_level == PermissionLevel.CONSEQUENTIAL:
                if user_confirmed:
                    # Validate that approval binding matches exact parameters
                    if approval_binding_id:
                        valid, reason = self.verify_approval_binding(approval_binding_id, parameters)
                        if not valid:
                            return PolicyDecision.BLOCK, f"Approval token invalidated: {reason}", None
                    return PolicyDecision.ALLOW_AUTO, "Consequential action authorized via validated approval token.", None

                binding = self.create_approval_binding(app_id, capability, parameters)
                return PolicyDecision.REQUIRE_APPROVAL, f"Consequential action '{capability.name}' requires explicit approval.", binding

            return PolicyDecision.BLOCK, f"Unknown permission level: {capability.permission_level}", None

    def create_approval_binding(
        self,
        app_id: str,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
    ) -> ActionApprovalBinding:
        """Create a cryptographic binding linking approval strictly to exact parameters."""
        with self._lock:
            # Normalize parameters to deterministic JSON string for hashing
            serialized = json.dumps(parameters, sort_keys=True, default=str)
            content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            binding_id = f"bind-{content_hash[:16]}"
            now_iso = datetime.now(timezone.utc).isoformat()

            # Formulate action-specific summary and target bindings
            recipient = parameters.get("recipient") or parameters.get("channel") or parameters.get("target")
            target_doc = parameters.get("document_path") or parameters.get("file_path") or parameters.get("target_path")
            target_domain = parameters.get("domain") or parameters.get("url")

            action_type = capability.id
            summary = f"[{manifest_category(app_id).upper()}] {capability.name} on {app_id}"
            if recipient:
                summary += f" to recipient '{recipient}'"
            if target_doc:
                summary += f" target: '{target_doc}'"
            if target_domain:
                summary += f" domain: '{target_domain}'"

            binding = ActionApprovalBinding(
                binding_id=binding_id,
                app_id=app_id,
                capability_id=capability.id,
                action_type=action_type,
                recipient=str(recipient) if recipient else None,
                target_document=str(target_doc) if target_doc else None,
                target_domain=str(target_domain) if target_domain else None,
                content_hash=content_hash,
                action_summary=summary,
                created_at=now_iso,
                is_valid=True,
            )
            self._approval_bindings[binding_id] = binding
            return binding

    def verify_approval_binding(
        self,
        binding_id: str,
        current_parameters: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Verify that current execution parameters have not been tampered with since approval."""
        with self._lock:
            binding = self._approval_bindings.get(binding_id)
            if not binding:
                return False, f"Approval binding '{binding_id}' not found."
            if not binding.is_valid:
                return False, "Approval binding has already been consumed or invalidated."

            serialized = json.dumps(current_parameters, sort_keys=True, default=str)
            current_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

            if current_hash != binding.content_hash:
                binding.is_valid = False
                return False, "Parameters have changed since approval was granted. Action invalidated."

            # Mark consumed to prevent replay attacks
            binding.is_valid = False
            return True, "Approval binding verified."


def manifest_category(app_id: str) -> str:
    """Extract category prefix from canonical application ID."""
    parts = app_id.split(".")
    return parts[0] if len(parts) > 1 else "app"


# Global singleton instance
integration_permissions = IntegrationPermissionManager()
