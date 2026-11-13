"""Modular Application Integration Framework (Phase 5.2)."""

from app.integrations.models import (
    AppCategory,
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    PermissionLevel,
    ProcessRule,
    ProviderType,
)
from app.integrations.registry import ApplicationRegistry, application_registry
from app.integrations.discovery import ApplicationDiscoveryEngine, application_discovery_engine
from app.integrations.permissions import IntegrationPermissionManager, integration_permissions
from app.integrations.manager import ApplicationIntegrationManager, application_manager
from app.integrations.tools import (
    AppDiscoverTool,
    AppListCapabilitiesTool,
    AppExecuteCapabilityTool,
)

__all__ = [
    "AppCategory",
    "ApplicationManifest",
    "CapabilitySpec",
    "IntegrationHealth",
    "PermissionLevel",
    "ProcessRule",
    "ProviderType",
    "ApplicationRegistry",
    "application_registry",
    "ApplicationDiscoveryEngine",
    "application_discovery_engine",
    "IntegrationPermissionManager",
    "integration_permissions",
    "ApplicationIntegrationManager",
    "application_manager",
    "AppDiscoverTool",
    "AppListCapabilitiesTool",
    "AppExecuteCapabilityTool",
]
