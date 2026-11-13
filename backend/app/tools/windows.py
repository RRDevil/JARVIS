"""Concrete Windows desktop tools (Phase 3.2)."""

import asyncio
import ctypes
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from app.automation.factory import get_platform_adapter
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class EmptyParams(BaseModel):
    """Empty parameter schema for parameter-less queries."""
    pass


class LaunchAppParams(BaseModel):
    """Parameters for launching an authorized desktop application."""

    app_id: str = Field(
        ...,
        description="Identifier of the allowlisted application (e.g. 'notepad', 'calculator', 'vscode', 'terminal', 'explorer', 'paint').",
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Optional command-line arguments to pass to the application.",
    )


class ListWindowsParams(BaseModel):
    """Parameters for querying desktop windows."""

    include_minimized: bool = Field(
        default=True,
        description="Whether to include minimized windows in the query.",
    )


class WindowHandleParams(BaseModel):
    """Parameters targeting a specific window by handle."""

    handle: int = Field(
        ...,
        description="The integer window handle (HWND) of the target window.",
    )


class WindowCloseParams(BaseModel):
    """Parameters for closing a desktop window."""

    handle: int = Field(
        ...,
        description="The integer window handle (HWND) of the window to close.",
    )
    window_title: Optional[str] = Field(
        default=None,
        description="Optional title string for safety confirmation.",
    )


class OpenFolderParams(BaseModel):
    """Parameters for opening an authorized folder in File Explorer."""

    folder_path: str = Field(
        ...,
        description="Absolute or relative path to an authorized directory.",
    )


# --- Tool Implementations ---


class WindowsListAppsTool(BaseTool):
    name = "windows_list_apps"
    description = "List all applications pre-authorized for JARVIS to launch."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = EmptyParams

    async def execute(self, params: EmptyParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        apps = adapter.get_approved_apps()
        return ToolResult(
            success=True,
            data=[app.model_dump() for app in apps],
            verified=True,
        )


class WindowsLaunchAppTool(BaseTool):
    name = "windows_launch_app"
    description = "Launch an authorized desktop application by its app ID."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = LaunchAppParams

    @staticmethod
    def _is_process_active(pid: int) -> bool:
        """Verify whether the process handle is alive and active."""
        try:
            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION (0x1000) | SYNCHRONIZE (0x00100000)
            h = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)
            if not h:
                return False
            exit_code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            kernel32.CloseHandle(h)
            # STILL_ACTIVE is 259
            return exit_code.value == 259
        except Exception:
            return False

    async def execute(self, params: LaunchAppParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        try:
            res = adapter.launch_app(params.app_id, params.args)
            pid = res.get("pid")
            verified = False
            verification_note = "Process started."

            # Verify process or window is active
            if res.get("window_handle"):
                verified = True
                verification_note = f"Window '{res.get('window_title', params.app_id)}' verified open and brought to front on Windows desktop."
            elif pid:
                for _ in range(5):
                    if self._is_process_active(pid):
                        verified = True
                        verification_note = f"Application process {pid} confirmed active on Windows."
                        break
                    await asyncio.sleep(0.2)

            # Check if any window handle associated with the app is available (poll up to 1.5s for desktop UI registration)
            if not res.get("window_handle"):
                for _ in range(6):
                    try:
                        windows = adapter.list_windows()
                        matching_win = next(
                            (
                                w for w in windows
                                if params.app_id.lower() in w.title.lower()
                                or params.app_id.lower() in w.process_name.lower()
                                or (pid and w.process_id == pid)
                            ),
                            None,
                        )
                        if matching_win:
                            res["window_title"] = matching_win.title
                            res["window_handle"] = matching_win.handle
                            verified = True
                            verification_note = f"Window '{matching_win.title}' verified open on Windows desktop."
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.25)

            res["verified"] = verified
            res["verification_note"] = verification_note

            return ToolResult(
                success=True,
                data=res,
                verified=verified,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                error_code="LAUNCH_FAILED",
                verified=False,
            )


class WindowsListWindowsTool(BaseTool):
    name = "windows_list_windows"
    description = "Enumerate currently visible and minimized desktop windows."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = ListWindowsParams

    async def execute(self, params: ListWindowsParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        all_windows = adapter.list_windows()
        filtered = [
            w.model_dump()
            for w in all_windows
            if params.include_minimized or not w.is_minimized
        ]
        return ToolResult(
            success=True,
            data=filtered,
            verified=True,
        )


class WindowsFocusWindowTool(BaseTool):
    name = "windows_focus_window"
    description = "Bring a target desktop window to the foreground."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = WindowHandleParams

    async def execute(self, params: WindowHandleParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        ok = adapter.focus_window(params.handle)
        if ok:
            return ToolResult(
                success=True,
                data={"handle": params.handle, "focused": True},
                verified=True,
            )
        return ToolResult(
            success=False,
            error=f"Window handle {params.handle} not found or could not be focused.",
            error_code="WINDOW_NOT_FOUND",
        )


class WindowsMinimizeWindowTool(BaseTool):
    name = "windows_minimize_window"
    description = "Minimize a target desktop window to the taskbar."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = WindowHandleParams

    async def execute(self, params: WindowHandleParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        ok = adapter.minimize_window(params.handle)
        if ok:
            return ToolResult(
                success=True,
                data={"handle": params.handle, "minimized": True},
                verified=True,
            )
        return ToolResult(
            success=False,
            error=f"Window handle {params.handle} not found or could not be minimized.",
            error_code="WINDOW_NOT_FOUND",
        )


class WindowsCloseWindowTool(BaseTool):
    name = "windows_close_window"
    description = "Gracefully close a desktop window. Consequential action requiring confirmation."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = WindowCloseParams

    async def execute(self, params: WindowCloseParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        ok = adapter.close_window(params.handle)
        if ok:
            return ToolResult(
                success=True,
                data={"handle": params.handle, "closed": True},
                verified=True,
            )
        return ToolResult(
            success=False,
            error=f"Window handle {params.handle} not found or could not be closed.",
            error_code="WINDOW_NOT_FOUND",
        )


class WindowsOpenFolderTool(BaseTool):
    name = "windows_open_folder"
    description = "Open an authorized directory in Windows File Explorer."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = OpenFolderParams

    async def execute(self, params: OpenFolderParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        try:
            adapter.open_folder(params.folder_path)
            return ToolResult(
                success=True,
                data={"folder_path": params.folder_path, "opened": True},
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                error_code="FOLDER_OPEN_FAILED",
            )

