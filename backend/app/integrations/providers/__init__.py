"""Integration Providers Subsystem (Phase 5.2)."""

from app.integrations.providers.base import BaseIntegrationProvider, IntegrationProviderError
from app.integrations.providers.desktop_ui import DesktopUIProvider
from app.integrations.providers.office_com import OfficeCOMProvider
from app.integrations.providers.browser import BrowserAutomationProvider

__all__ = [
    "BaseIntegrationProvider",
    "IntegrationProviderError",
    "DesktopUIProvider",
    "OfficeCOMProvider",
    "BrowserAutomationProvider",
]
