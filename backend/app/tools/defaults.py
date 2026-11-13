"""Registration of default system tools in tool registry."""

from app.tools.registry import ToolRegistry, tool_registry
from app.tools.perception import (
    WindowsCaptureScreenTool,
    WindowsReadScreenTextTool,
)
from app.tools.windows import (
    WindowsCloseWindowTool,
    WindowsFocusWindowTool,
    WindowsLaunchAppTool,
    WindowsListAppsTool,
    WindowsListWindowsTool,
    WindowsMinimizeWindowTool,
    WindowsOpenFolderTool,
)
from app.tools.ui import (
    UIClickControlTool,
    UIDesktopTypeTextTool,
    UIFindControlsTool,
    UIScrollTool,
    UISendShortcutTool,
    UISetTextTool,
)
from app.tools.grounded_interaction import (
    VisualClickElementTool,
    VisualLocateElementsTool,
    VisualScrollRegionTool,
    VisualTypeIntoElementTool,
)
from app.integrations.tools import (
    AppDiscoverTool,
    AppExecuteCapabilityTool,
    AppListCapabilitiesTool,
)


def register_default_windows_tools(registry: ToolRegistry = tool_registry) -> None:
    """Register all built-in Windows 11 desktop tools, UI automation tools, and perception tools."""
    tools = [
        # Desktop & Window Management
        WindowsListAppsTool(),
        WindowsLaunchAppTool(),
        WindowsListWindowsTool(),
        WindowsFocusWindowTool(),
        WindowsMinimizeWindowTool(),
        WindowsCloseWindowTool(),
        WindowsOpenFolderTool(),
        # Accessible UI Automation
        UIFindControlsTool(),
        UIClickControlTool(),
        UISetTextTool(),
        UIDesktopTypeTextTool(),
        UISendShortcutTool(),
        UIScrollTool(),
        # Screen Perception & Local OCR
        WindowsCaptureScreenTool(),
        WindowsReadScreenTextTool(),
        # Phase 5: Grounded Visual UI Interaction
        VisualLocateElementsTool(),
        VisualClickElementTool(),
        VisualTypeIntoElementTool(),
        VisualScrollRegionTool(),
        # Phase 5.2: Modular Application Integrations
        AppDiscoverTool(),
        AppListCapabilitiesTool(),
        AppExecuteCapabilityTool(),
    ]
    for tool in tools:
        if not registry.has_tool(tool.name):
            registry.register(tool)

