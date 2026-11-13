"""Platform Adapter Factory and Dependency Injection."""

import os
import sys
from typing import Optional
from app.automation.platform_adapter import PlatformAdapter
from app.automation.windows_adapter import WindowsPlatformAdapter
from app.automation.mock_adapter import MockPlatformAdapter

_current_adapter: Optional[PlatformAdapter] = None


def get_platform_adapter() -> PlatformAdapter:
    """Retrieve the active platform adapter singleton."""
    global _current_adapter
    if _current_adapter is not None:
        return _current_adapter

    # Check for test/mock override
    if os.environ.get("JARVIS_MOCK_PLATFORM") == "1" or sys.platform != "win32":
        _current_adapter = MockPlatformAdapter()
    else:
        _current_adapter = WindowsPlatformAdapter()

    return _current_adapter


def set_platform_adapter(adapter: Optional[PlatformAdapter]) -> None:
    """Inject a custom platform adapter (useful for hermetic test suites)."""
    global _current_adapter
    _current_adapter = adapter

