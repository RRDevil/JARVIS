"""Controlled UI Automation tools targeting accessible controls (Phase 3.3)."""

from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.automation.factory import get_platform_adapter
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class UIFindControlsParams(BaseModel):
    """Parameters for discovering accessible controls in a window."""

    window_handle: int = Field(
        ...,
        description="The integer HWND handle of the window to inspect.",
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional substring filter for control text/label.",
    )
    control_type: Optional[str] = Field(
        default=None,
        description="Optional control type filter (e.g. 'button', 'edit', 'menu_item', 'text').",
    )


class UIClickControlParams(BaseModel):
    """Parameters for clicking a verified accessible UI control."""

    window_handle: int = Field(
        ...,
        description="The integer HWND handle of the window containing the control.",
    )
    control_id: str = Field(
        ...,
        description="Unique identifier of the target control.",
    )
    control_name: Optional[str] = Field(
        default=None,
        description="Optional name of control for verification.",
    )


class UISetTextParams(BaseModel):
    """Parameters for setting text inside an editable control."""

    window_handle: int = Field(
        ...,
        description="The integer HWND handle of the window containing the control.",
    )
    control_id: str = Field(
        ...,
        description="Unique identifier of the target editable control.",
    )
    text: str = Field(
        ...,
        description="The text content to enter.",
    )


class UISendShortcutParams(BaseModel):
    """Parameters for sending an authorized keyboard shortcut."""

    window_handle: int = Field(
        ...,
        description="The integer HWND handle of the targeted window.",
    )
    shortcut: str = Field(
        ...,
        description="Authorized keyboard shortcut combination (e.g. 'ctrl+s', 'ctrl+c', 'enter', 'tab').",
    )
    expected_process_id: Optional[int] = Field(
        default=None,
        description="Optional process ID for verifying the target window has not been recycled.",
    )
    target_app_name: Optional[str] = Field(
        default=None,
        description="Optional display name of the target application (e.g. 'Notepad').",
    )
    window_title: Optional[str] = Field(
        default=None,
        description="Optional title of the targeted window.",
    )


class UIScrollParams(BaseModel):
    """Parameters for scrolling a window or scrollable container."""

    window_handle: int = Field(
        ...,
        description="The integer HWND handle of the targeted window.",
    )
    direction: Literal["up", "down"] = Field(
        default="down",
        description="Scroll direction ('up' or 'down').",
    )
    amount: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Number of scroll steps.",
    )


class UIDesktopTypeTextParams(BaseModel):
    """Parameters for typing text into any application window or text box."""

    text: str = Field(
        ...,
        description="The text content to type into the application or textbox.",
    )
    app_name: Optional[str] = Field(
        default=None,
        description="Name of the target application (e.g. 'notepad', 'chrome', 'terminal', 'vscode').",
    )
    window_handle: Optional[int] = Field(
        default=None,
        description="The integer HWND handle of the target window.",
    )
    x: Optional[int] = Field(
        default=None,
        description="Optional exact screen X coordinate of the input box.",
    )
    y: Optional[int] = Field(
        default=None,
        description="Optional exact screen Y coordinate of the input box.",
    )
    clear_first: bool = Field(
        default=False,
        description="Select all and clear existing contents before typing.",
    )
    press_enter: bool = Field(
        default=False,
        description="Press Enter key after typing (useful for search bars or terminal commands).",
    )
    paste_mode: Optional[bool] = Field(
        default=None,
        description="Use clipboard paste for instant, high-fidelity multi-line or special Unicode text.",
    )


# --- UI Tool Implementations ---


class UIFindControlsTool(BaseTool):
    name = "ui_find_controls"
    description = "Discover accessible UI controls (buttons, edits, labels) inside a target window."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = UIFindControlsParams

    async def execute(self, params: UIFindControlsParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        controls = adapter.find_controls(
            handle=params.window_handle,
            name=params.name,
            control_type=params.control_type,
        )
        return ToolResult(
            success=True,
            data=[c.model_dump() for c in controls],
            verified=True,
        )


class UIClickControlTool(BaseTool):
    name = "ui_click_control"
    description = "Click a specific accessible UI control within a desktop window. Consequential action."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = UIClickControlParams

    async def execute(self, params: UIClickControlParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        ok = adapter.click_control(handle=params.window_handle, control_id=params.control_id)
        if ok:
            return ToolResult(
                success=True,
                data={
                    "window_handle": params.window_handle,
                    "control_id": params.control_id,
                    "clicked": True,
                },
                verified=True,
            )
        return ToolResult(
            success=False,
            error=f"Control '{params.control_id}' in window {params.window_handle} could not be clicked or was disabled.",
            error_code="CONTROL_CLICK_FAILED",
        )


class UISetTextTool(BaseTool):
    name = "ui_set_text"
    description = "Enter text into an accessible editable control. Consequential action."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = UISetTextParams

    async def execute(self, params: UISetTextParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        ok = adapter.set_control_text(
            handle=params.window_handle,
            control_id=params.control_id,
            text=params.text,
        )
        if ok:
            return ToolResult(
                success=True,
                data={
                    "window_handle": params.window_handle,
                    "control_id": params.control_id,
                    "length": len(params.text),
                },
                verified=True,
            )
        return ToolResult(
            success=False,
            error=f"Unable to enter text into control '{params.control_id}' in window {params.window_handle}.",
            error_code="SET_TEXT_FAILED",
        )


class UISendShortcutTool(BaseTool):
    name = "ui_send_shortcut"
    description = "Send an authorized keyboard shortcut to the target window. Consequential action."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = UISendShortcutParams

    async def execute(self, params: UISendShortcutParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        try:
            from app.automation.platform_adapter import FocusMismatchError

            ok = adapter.send_shortcut(
                handle=params.window_handle,
                shortcut=params.shortcut,
                expected_pid=params.expected_process_id,
            )
            if ok:
                return ToolResult(
                    success=True,
                    data={
                        "window_handle": params.window_handle,
                        "shortcut": params.shortcut,
                        "target_app_name": params.target_app_name,
                        "window_title": params.window_title,
                    },
                    verified=True,
                )
            return ToolResult(
                success=False,
                error=f"Window {params.window_handle} could not receive shortcut.",
                error_code="SHORTCUT_DISPATCH_FAILED",
            )
        except FocusMismatchError as fme:
            return ToolResult(
                success=False,
                error=str(fme),
                error_code="FOCUS_MISMATCH",
            )
        except ValueError as err:
            return ToolResult(
                success=False,
                error=str(err),
                error_code="UNAUTHORIZED_SHORTCUT",
            )


class UIScrollTool(BaseTool):
    name = "ui_scroll"
    description = "Scroll a window up or down."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = UIScrollParams

    async def execute(self, params: UIScrollParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        try:
            ok = adapter.scroll_window(
                handle=params.window_handle,
                direction=params.direction,
                amount=params.amount,
            )
            if ok:
                return ToolResult(
                    success=True,
                    data={
                        "window_handle": params.window_handle,
                        "direction": params.direction,
                        "amount": params.amount,
                    },
                    verified=True,
                )
            return ToolResult(
                success=False,
                error=f"Window {params.window_handle} could not be scrolled.",
                error_code="SCROLL_FAILED",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=str(exc),
                error_code="SCROLL_FAILED",
            )


class UIDesktopTypeTextTool(BaseTool):
    name = "desktop_type_text"
    description = (
        "Type text into any application window or textbox on Windows (Notepad, Chrome, Terminal, "
        "VS Code, Discord, search fields, web inputs). Supports targeting by application name, "
        "window handle, or coordinates (x, y), with clear-first and press-enter options."
    )
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = UIDesktopTypeTextParams

    async def execute(self, params: UIDesktopTypeTextParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        try:
            target_hwnd = params.window_handle
            if not target_hwnd and params.app_name:
                win = adapter.find_app_window(params.app_name)
                if win:
                    target_hwnd = win.handle
                else:
                    return ToolResult(
                        success=False,
                        error=f"Target application '{params.app_name}' is not currently running. Please open it before typing.",
                        error_code="APPLICATION_NOT_RUNNING",
                    )

            ok = adapter.type_text(
                text=params.text,
                x=params.x,
                y=params.y,
                target_hwnd=target_hwnd,
                clear_first=params.clear_first,
                press_enter=params.press_enter,
                use_clipboard=params.paste_mode,
            )
            if ok:
                return ToolResult(
                    success=True,
                    data={
                        "action": "desktop_type_text",
                        "app_name": params.app_name,
                        "window_handle": target_hwnd,
                        "coordinates": {"x": params.x, "y": params.y} if params.x is not None and params.y is not None else None,
                        "characters_typed": len(params.text),
                        "clear_first": params.clear_first,
                        "press_enter": params.press_enter,
                    },
                    verified=True,
                )
            return ToolResult(
                success=False,
                error="Failed to enter text into the specified application or window.",
                error_code="TYPE_TEXT_FAILED",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Error executing desktop text input: {str(exc)}",
                error_code="TYPE_TEXT_FAILED",
            )

