"""Base Integration Provider Interface (Phase 5.2).

Defines lifecycle, availability probing, execution, and cancellation contracts
for all modular application integration adapters.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.integrations.models import (
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    ProviderType,
)
from app.tools.base import ExecutionContext


class IntegrationProviderError(Exception):
    """Base exception for application provider execution errors."""
    pass


class BaseIntegrationProvider(ABC):
    """Abstract lifecycle and execution interface for application integration providers."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """The distinct integration provider category."""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize provider subsystem, connection pools, or COM apartments."""
        pass

    @abstractmethod
    async def health_check(self, manifest: Optional[ApplicationManifest] = None) -> IntegrationHealth:
        """Probe provider operational health and dependency availability."""
        pass

    @abstractmethod
    def is_available_for(self, manifest: ApplicationManifest) -> bool:
        """Determine if this provider can service the specified application manifest."""
        pass

    @abstractmethod
    async def execute_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute a supported capability against the target application."""
        pass

    @abstractmethod
    async def cancel(self, operation_id: str) -> bool:
        """Signal cooperative cancellation to any active operations in progress."""
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Release automation handles, close owned child processes, and clean up resources."""
        pass
