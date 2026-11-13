"""Base Contracts for Application Discovery and Productivity Integrations.

Provides platform-neutral interfaces for application discovery and office suite automation.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.integrations.models import ApplicationManifest, CapabilitySpec, IntegrationHealth
from app.tools.base import ExecutionContext


class AppDiscoveryProvider(ABC):
    """Abstract interface defining operating system application discovery."""

    @abstractmethod
    def scan_installed_applications(self) -> Dict[str, str]:
        """Scan system and return map of {app_id_or_name: executable_or_bundle_path}."""
        pass

    @abstractmethod
    def resolve_app_path(self, app_name: str) -> Optional[str]:
        """Resolve a common application name (e.g., 'chrome', 'word') to full launch target."""
        pass


class OfficeAutomationProvider(ABC):
    """Abstract interface for native office application automation (Word, Excel, PowerPoint)."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if native office automation is supported on this host platform."""
        pass

    @abstractmethod
    async def execute_office_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute structured office automation capability."""
        pass
