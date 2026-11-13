"""Data models and schemas for the Modular Application Integration Framework (Phase 5.2)."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tools.base import RiskTier


class AppCategory(str, Enum):
    BROWSER = "browser"
    OFFICE = "office"
    MESSAGING = "messaging"
    DEVELOPMENT = "development"
    UTILITY = "utility"
    SYSTEM = "system"


class ProviderType(str, Enum):
    DESKTOP_UI = "desktop_ui"
    OFFICE_COM = "office_com"
    OFFICE_APPLESCRIPT = "office_applescript"
    BROWSER_AUTOMATION = "browser_automation"
    NATIVE_API = "native_api"


class PermissionLevel(str, Enum):
    """Hierarchical permission tiers conforming to Phase 5.2 security specifications."""
    READ_ONLY = "read_only"                    # Level 1: Read/inspect content, list windows, parse state
    CONTROLLED = "controlled"                  # Level 2: Tab navigation, search, draft messages, cell edits
    CONSEQUENTIAL = "consequential"            # Level 3: Send message, send email, overwrite file, submit form
    RESTRICTED = "restricted"                  # Level 4: Financial, passwords, destructive DB, account recovery


class IntegrationHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NOT_INSTALLED = "not_installed"
    UNKNOWN = "unknown"


class CapabilitySpec(BaseModel):
    """Specification of a capability supported by an application integration."""
    id: str = Field(..., description="Unique capability identifier (e.g. 'browser.navigate', 'word.read_document').")
    name: str = Field(..., description="Human-readable capability name.")
    description: str = Field(..., description="Detailed description of what this capability does.")
    permission_level: PermissionLevel = Field(..., description="Level 1 to Level 4 authorization classification.")
    risk_tier: RiskTier = Field(..., description="Underlying core tool risk tier.")
    supported_providers: List[ProviderType] = Field(..., description="Integration providers capable of fulfilling this action.")
    parameters_schema: Optional[Dict[str, Any]] = Field(default=None, description="Expected parameter schema for capability invocation.")


class ProcessRule(BaseModel):
    """Rules for identifying application processes and visible desktop windows."""
    executable_names: List[str] = Field(..., description="Possible executable image names (case-insensitive).")
    window_title_patterns: List[str] = Field(default_factory=list, description="Substrings or regex patterns in window title.")
    window_class_names: Optional[List[str]] = Field(default=None, description="Optional Win32 window class names.")
    registry_app_paths_keys: List[str] = Field(default_factory=list, description="Registry App Paths keys to scan (e.g. 'opera.exe').")
    common_install_paths: List[str] = Field(default_factory=list, description="Well-known filesystem locations.")


class ApplicationManifest(BaseModel):
    """Structured metadata manifest describing an application integration."""
    app_id: str = Field(..., description="Canonical stable application identifier (e.g. 'browser.opera_gx').")
    display_name: str = Field(..., description="Human-readable application display name.")
    vendor: str = Field(..., description="Application publisher or software vendor.")
    category: AppCategory = Field(..., description="High-level application category.")
    description: str = Field(..., description="Purpose and scope of this application integration.")
    process_rule: ProcessRule = Field(..., description="Process and window identification heuristics.")
    supported_providers: List[ProviderType] = Field(..., description="Available integration provider adapters.")
    capabilities: List[CapabilitySpec] = Field(default_factory=list, description="Catalog of supported capabilities.")
    is_enabled: bool = Field(default=True, description="Whether this integration is enabled by user policy.")
    is_installed: bool = Field(default=False, description="Whether the application is detected as installed on host OS.")
    installed_path: Optional[str] = Field(default=None, description="Resolved absolute executable path if found.")
    is_running: bool = Field(default=False, description="Whether active processes or windows are currently running.")
    running_pids: List[int] = Field(default_factory=list, description="PIDs of active application instances.")
    running_window_handles: List[int] = Field(default_factory=list, description="HWND handles of visible application windows.")
    health_status: IntegrationHealth = Field(default=IntegrationHealth.UNKNOWN, description="Current operational health status.")
    version: Optional[str] = Field(default=None, description="Detected application or integration version.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Extensible application-specific metadata.")


class ActionApprovalBinding(BaseModel):
    """Security binding ensuring user approval is tied to exact parameters with tamper protection."""
    binding_id: str
    app_id: str
    capability_id: str
    action_type: str
    recipient: Optional[str] = None
    target_document: Optional[str] = None
    target_domain: Optional[str] = None
    content_hash: str
    action_summary: str
    created_at: str
    is_valid: bool = True


class AppPermissionState(BaseModel):
    """User-configured permission state for an application and its capabilities."""
    app_id: str
    is_enabled: bool = True
    disabled_providers: List[ProviderType] = Field(default_factory=list)
    disabled_capabilities: List[str] = Field(default_factory=list)
    session_authorized_capabilities: List[str] = Field(default_factory=list)
    require_approval_overrides: Dict[str, bool] = Field(default_factory=dict)


class AppExecuteCapabilityRequest(BaseModel):
    app_id: str
    capability_id: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    preferred_provider: Optional[ProviderType] = None
    session_id: Optional[str] = None


class AppExecuteCapabilityResponse(BaseModel):
    success: bool
    app_id: str
    capability_id: str
    provider_used: ProviderType
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    approval_required: bool = False
    approval_id: Optional[str] = None
    action_summary: Optional[str] = None
