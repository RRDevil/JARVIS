"""Base definitions for OS Automation.

Re-exports core platform automation contracts from platform_adapter for unified import semantics.
"""

from app.automation.platform_adapter import (
    ApprovedApp,
    AutomationError,
    FocusMismatchError,
    PlatformAdapter,
    UIControlInfo,
    WindowInfo,
)

__all__ = [
    "ApprovedApp",
    "AutomationError",
    "FocusMismatchError",
    "PlatformAdapter",
    "UIControlInfo",
    "WindowInfo",
]
