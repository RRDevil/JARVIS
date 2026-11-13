"""JARVIS Desktop Assistant - Automation Framework Package."""

from app.automation.platform_adapter import ApprovedApp, PlatformAdapter, WindowInfo
from app.automation.windows_adapter import WindowsPlatformAdapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.automation.factory import get_platform_adapter, set_platform_adapter

__all__ = [
    "ApprovedApp",
    "PlatformAdapter",
    "WindowInfo",
    "WindowsPlatformAdapter",
    "MockPlatformAdapter",
    "get_platform_adapter",
    "set_platform_adapter",
]

