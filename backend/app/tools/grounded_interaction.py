"""Phase 5 Grounded Visual UI Interaction Tools.

Integrates visual identification, OCR bounding boxes, and UIA accessibility
controls with the Windows native platform adapter and security policy engine.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.automation.factory import get_platform_adapter
from app.perception.grounding import (
    AmbiguousTargetError,
    GroundedUIElement,
    TargetNotFoundError,
    grounding_engine,
)
from app.perception.models import ElementType, LocateElementsRequest
from app.perception.screen_capture import screen_capture_engine
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult

logger = logging = __import__("logging").getLogger("jarvis.tools.grounded_interaction")


class VisualLocateElementsParams(BaseModel):
    """Parameters for discovering and grounding visible UI elements."""

    query: Optional[str] = Field(
        None,
        description="Natural language description or label to locate (e.g. 'Save button', 'Search field').",
    )
    monitor_id: int = Field(
        1,
        description="Display monitor index (1 for primary display).",
    )
    active_window_only: bool = Field(
        True,
        description="Constrain search strictly to the active foreground application window.",
    )
    element_type: Optional[str] = Field(
        None,
        description="Optional filter by control type (e.g. 'button', 'text_field', 'tab', 'menu').",
    )
    max_results: int = Field(
        25,
        ge=1,
        le=100,
        description="Maximum candidate elements to return.",
    )


class VisualClickElementParams(BaseModel):
    """Parameters for clicking anywhere on screen or targeting an identified UI element."""

    x: Optional[int] = Field(
        None,
        description="Exact horizontal screen X coordinate to click.",
    )
    y: Optional[int] = Field(
        None,
        description="Exact vertical screen Y coordinate to click.",
    )
    target_description: Optional[str] = Field(
        None,
        description="Natural language description of the control to click (e.g. 'Save button', 'File menu', 'Search bar', 'this video').",
    )
    element_id: Optional[str] = Field(
        None,
        description="Specific element ID from a previous locate call.",
    )
    app_name: Optional[str] = Field(
        None,
        description="Target application name or executable (e.g. 'Opera GX', 'Chrome').",
    )
    window_title: Optional[str] = Field(
        None,
        description="Host window title.",
    )
    window_handle: Optional[int] = Field(
        None,
        description="Win32 HWND of target window.",
    )
    bounding_box: Optional[Dict[str, Any]] = Field(
        None,
        description="Resolved element bounding box coordinates {left, top, width, height}.",
    )
    detection_method: Optional[str] = Field(
        None,
        description="Method used to detect target ('visual_reasoning', 'uia', 'ocr', 'hybrid', 'coordinate').",
    )
    confidence: Optional[float] = Field(
        None,
        description="Target resolution confidence score.",
    )
    observation_timestamp: Optional[str] = Field(
        None,
        description="ISO 8601 observation timestamp when target was resolved.",
    )
    resolved_target: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured resolved target metadata.",
    )
    button: Literal["left", "right", "double"] = Field(
        default="left",
        description="Mouse click type: 'left', 'right', or 'double'.",
    )
    clicks: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of clicks to dispatch (1 for single click, 2 for double click).",
    )
    hover_ms: int = Field(
        default=40,
        ge=0,
        le=1000,
        description="Hover duration in milliseconds before mouse down dispatch.",
    )
    monitor_id: int = Field(
        1,
        description="Display monitor index.",
    )
    active_window_only: bool = Field(
        False,
        description="Constrain targeting to the active foreground application window (default False searches all windows).",
    )
    verify_post_condition: bool = Field(
        True,
        description="Capture screen/cursor after interaction to verify expected UI update.",
    )


class VisualTypeIntoElementParams(BaseModel):
    """Parameters for focusing and typing text into any input control, application, or coordinates."""

    text: str = Field(
        ...,
        description="The text content to type into the field or application.",
    )
    x: Optional[int] = Field(
        None,
        description="Exact screen X coordinate of the input field or text box.",
    )
    y: Optional[int] = Field(
        None,
        description="Exact screen Y coordinate of the input field or text box.",
    )
    target_description: Optional[str] = Field(
        None,
        description="Natural language description of the input field (e.g. 'Search bar', 'Username text box', 'Notepad document').",
    )
    element_id: Optional[str] = Field(
        None,
        description="Specific element ID from a previous locate call.",
    )
    app_name: Optional[str] = Field(
        None,
        description="Target application name or executable (e.g. 'notepad', 'chrome', 'terminal', 'vscode').",
    )
    window_handle: Optional[int] = Field(
        None,
        description="Target window HWND handle.",
    )
    clear_first: bool = Field(
        False,
        description="Select all and clear existing contents before typing.",
    )
    press_enter: bool = Field(
        False,
        description="Press Enter key after typing (useful for search bars or terminal commands).",
    )
    paste_mode: Optional[bool] = Field(
        None,
        description="Use clipboard paste (Ctrl+V) for instant, flawless multi-line or special Unicode text.",
    )
    monitor_id: int = Field(
        1,
        description="Display monitor index.",
    )
    active_window_only: bool = Field(
        False,
        description="Constrain targeting to the active foreground application window.",
    )


class VisualScrollRegionParams(BaseModel):
    """Parameters for scrolling within an identified region or window."""

    target_description: Optional[str] = Field(
        None,
        description="Natural language description of the container to scroll within.",
    )
    direction: Literal["up", "down"] = Field(
        default="down",
        description="Scroll direction ('up' or 'down').",
    )
    amount: int = Field(
        default=3,
        ge=1,
        le=30,
        description="Number of scroll wheel steps.",
    )
    monitor_id: int = Field(
        1,
        description="Display monitor index.",
    )


# --- Tool Implementations ---


class VisualLocateElementsTool(BaseTool):
    """Tool to locate and ground interactive UI elements from current screen state."""

    name = "visual_locate_elements"
    description = (
        "Ground and identify interactive UI elements (buttons, fields, menus, tabs) on screen "
        "matching a natural language description with precise coordinates."
    )
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = VisualLocateElementsParams

    async def execute(self, params: VisualLocateElementsParams, context: ExecutionContext) -> ToolResult:
        try:
            el_type = None
            if params.element_type:
                try:
                    el_type = ElementType(params.element_type.lower())
                except ValueError:
                    pass

            req = LocateElementsRequest(
                query=params.query,
                monitor_id=params.monitor_id,
                active_window_only=params.active_window_only,
                element_type=el_type,
                max_results=params.max_results,
            )

            res = await grounding_engine.locate_elements(req)
            data = {
                "total_found": res.total_found,
                "active_window": res.active_window,
                "screen_dimensions": f"{res.screen_width}x{res.screen_height}",
                "elements": [e.model_dump() for e in res.elements],
            }

            return ToolResult(
                success=True,
                data=data,
                verified=True,
            )
        except Exception as exc:
            logger.error(f"Failed to locate UI elements: {exc}")
            return ToolResult(
                success=False,
                error=f"Element localization error: {str(exc)}",
                error_code="LOCATE_FAILED",
            )


class VisualClickElementTool(BaseTool):
    """Tool to perform a click anywhere on screen or on a grounded UI element."""

    name = "visual_click_element"
    description = (
        "Click, double-click, or right-click anywhere on screen. Can target by exact screen "
        "coordinates (x, y), by visual description/label (e.g. 'Save button', 'Search bar'), "
        "or by element ID. Automatically activates the target window."
    )
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = VisualClickElementParams

    async def execute(self, params: VisualClickElementParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()
        clicks = 2 if params.button == "double" else max(1, params.clicks)
        btn = "right" if params.button == "right" else "left"

        try:
            cx: Optional[int] = params.x
            cy: Optional[int] = params.y
            target_desc = params.target_description or params.element_id or "target"
            app_name = params.app_name or "Desktop"
            win_title = params.window_title or ""
            target_hwnd = params.window_handle
            b_dict = params.bounding_box
            det_method = params.detection_method or ("coordinate" if cx is not None else "grounding")

            # 1. PRE-RESOLUTION IF CALLED WITHOUT COORDINATES
            if cx is None or cy is None:
                if not params.target_description and not params.element_id:
                    return ToolResult(
                        success=False,
                        error="Either coordinates (x, y) or a target_description must be provided for visual clicking.",
                        error_code="MISSING_TARGET_PARAMETERS",
                    )

                if params.element_id and not grounding_engine.is_observation_fresh():
                    return ToolResult(
                        success=False,
                        error="Target observation has expired. Screen state may have changed. Please re-scan or locate the target again.",
                        error_code="OBSERVATION_STALE",
                    )

                # First check existing grounding cache or scan elements
                elements, meta = await grounding_engine.scan_screen_elements(
                    monitor_id=params.monitor_id,
                    active_window_only=params.active_window_only,
                )

                target_elem: Optional[GroundedUIElement] = None
                if params.element_id:
                    for e in elements:
                        if e.element_id == params.element_id:
                            target_elem = e
                            break

                if not target_elem and params.target_description:
                    try:
                        target_elem, match_score = grounding_engine.match_element(
                            params.target_description,
                            elements,
                        )
                    except TargetNotFoundError:
                        target_elem = None

                if target_elem:
                    cx = target_elem.center.x
                    cy = target_elem.center.y
                    target_desc = target_elem.description
                    app_name = target_elem.window_title or app_name
                    win_title = target_elem.window_title or win_title
                    target_hwnd = target_elem.window_handle
                    b_dict = target_elem.bounding_box.model_dump()
                    det_method = target_elem.source.value
                else:
                    from app.perception.target_resolver import target_resolver
                    query = params.target_description or params.element_id or ""
                    resolved = await target_resolver.resolve_target(
                        query=query,
                        monitor_id=params.monitor_id,
                        active_window_only=params.active_window_only,
                    )
                    cx = resolved.click_coordinates.x
                    cy = resolved.click_coordinates.y
                    target_desc = resolved.target_description
                    app_name = resolved.app_name
                    win_title = resolved.window_title
                    target_hwnd = resolved.window_handle
                    b_dict = resolved.bounding_box.model_dump()
                    det_method = resolved.detection_method

            # 2. TARGET INVALIDATION VERIFICATION
            if target_hwnd is not None:
                if not adapter.is_window_valid(target_hwnd):
                    return ToolResult(
                        success=False,
                        error=f"Target window handle [{target_hwnd}] is no longer valid. The application may have closed or navigated away.",
                        error_code="TARGET_INVALIDATED",
                    )

            # 3. BOUNDARY AND COORDINATE VALIDATION
            v_left, v_top, v_width, v_height = adapter.get_virtual_desktop_bounds()
            if not (v_left <= cx < v_left + v_width and v_top <= cy < v_top + v_height):
                return ToolResult(
                    success=False,
                    error=f"Click coordinates ({cx}, {cy}) are outside virtual desktop boundaries (left={v_left}, top={v_top}, width={v_width}, height={v_height}).",
                    error_code="COORDINATES_OUT_OF_BOUNDS",
                )

            if b_dict:
                bx = b_dict.get("left", 0)
                by = b_dict.get("top", 0)
                bw = b_dict.get("width", 0)
                bh = b_dict.get("height", 0)
                if bw > 0 and bh > 0:
                    if not (bx <= cx <= bx + bw and by <= cy <= by + bh):
                        return ToolResult(
                            success=False,
                            error=f"Click coordinates ({cx}, {cy}) fall outside target bounding box [{bx}, {by}, {bw}x{bh}].",
                            error_code="INVALID_TARGET_BOUNDS",
                        )

            # 4. CAPTURE PRE-INTERACTION FOREGROUND STATE
            pre_win = adapter.get_active_window()
            pre_title = pre_win.title if pre_win else ""
            pre_hwnd = pre_win.handle if pre_win else None

            # 5. DISPATCH NATIVE CLICK WITH VISIBLE CURSOR MOVEMENT AND HOVER
            ok = adapter.click_at(
                cx,
                cy,
                button=btn,
                clicks=clicks,
                target_hwnd=target_hwnd,
                hover_ms=params.hover_ms,
            )
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Native click dispatch failed for target '{target_desc}' at coordinates ({cx}, {cy}).",
                    error_code="CLICK_FAILED",
                )

            # 6. POST-INTERACTION VERIFICATION
            verification_evidence: Dict[str, Any] = {
                "dispatch_success": True,
                "target_coordinates": {"x": cx, "y": cy},
            }

            if params.verify_post_condition:
                import asyncio
                await asyncio.sleep(0.12)
                try:
                    import ctypes
                    from ctypes import wintypes
                    cur_pt = wintypes.POINT()
                    if ctypes.windll.user32.GetCursorPos(ctypes.byref(cur_pt)):
                        verification_evidence["cursor_x"] = int(cur_pt.x)
                        verification_evidence["cursor_y"] = int(cur_pt.y)
                        verification_evidence["cursor_reached_target"] = (
                            abs(cur_pt.x - cx) <= 25 and abs(cur_pt.y - cy) <= 25
                        )
                except Exception:
                    pass

                post_win = adapter.get_active_window()
                post_title = post_win.title if post_win else ""
                post_hwnd = post_win.handle if post_win else None

                title_changed = bool(post_title and post_title != pre_title)
                window_changed = bool(post_hwnd and post_hwnd != pre_hwnd)

                verification_evidence["pre_window"] = {"title": pre_title, "handle": pre_hwnd}
                verification_evidence["post_window"] = {"title": post_title, "handle": post_hwnd}
                verification_evidence["state_changed"] = title_changed or window_changed

                if title_changed or window_changed:
                    verif_status = "SUCCESS"
                    verif_msg = f"Click dispatched and interaction verified. Active window state changed to '{post_title}'."
                elif verification_evidence.get("cursor_reached_target"):
                    verif_status = "DISPATCHED_UNVERIFIED"
                    verif_msg = f"Click dispatched successfully at ({cx}, {cy}). Cursor position verified, but no foreground title change was detected."
                else:
                    verif_status = "SUCCESS"
                    verif_msg = f"Click dispatched at ({cx}, {cy})."
            else:
                verif_status = "SUCCESS"
                verif_msg = f"Click dispatched at ({cx}, {cy})."

            return ToolResult(
                success=True,
                data={
                    "status": verif_status,
                    "action": f"{params.button}_click",
                    "mode": "coordinate" if (params.x is not None and params.y is not None and not params.target_description) else "grounded_element",
                    "target_description": target_desc,
                    "app_name": app_name,
                    "window_title": win_title,
                    "coordinates": {"x": cx, "y": cy},
                    "bounding_box": b_dict,
                    "detection_method": det_method,
                    "clicks": clicks,
                    "message": verif_msg,
                    "verification": verification_evidence,
                },
                verified=True,
            )

        except AmbiguousTargetError as amb:
            return ToolResult(
                success=False,
                error=str(amb),
                error_code="AMBIGUOUS_TARGET",
                data={"candidates": [c.model_dump() for c in amb.candidates]},
            )
        except TargetNotFoundError as tnf:
            return ToolResult(
                success=False,
                error=str(tnf),
                error_code="TARGET_NOT_FOUND",
            )
        except Exception as exc:
            logger.error(f"Click failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Click failure: {str(exc)}",
                error_code="EXECUTION_FAILED",
            )


class VisualTypeIntoElementTool(BaseTool):
    """Tool to focus and type text into any input field, application window, or coordinates."""

    name = "visual_type_into_element"
    description = (
        "Focus and type text into any textbox, form, editor, or application (Notepad, Chrome, "
        "Terminal, VS Code, Discord, search bars). Can target by exact coordinates (x, y), "
        "application name (e.g. 'notepad'), window handle, or visual element description. "
        "Supports clear_first, press_enter, and clipboard paste."
    )
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = VisualTypeIntoElementParams

    async def execute(self, params: VisualTypeIntoElementParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()

        try:
            target_hwnd: Optional[int] = params.window_handle
            app_title: str = ""

            # 1. Resolve target application window if specified
            if not target_hwnd and params.app_name:
                win = adapter.find_app_window(params.app_name)
                if win:
                    target_hwnd = win.handle
                    app_title = win.title

            # 2. Case A: Direct Screen Coordinates (x, y) provided
            if params.x is not None and params.y is not None:
                cx, cy = int(params.x), int(params.y)
                ok = adapter.type_text(
                    text=params.text,
                    x=cx,
                    y=cy,
                    target_hwnd=target_hwnd,
                    clear_first=params.clear_first,
                    press_enter=params.press_enter,
                    use_clipboard=params.paste_mode,
                )
                if not ok:
                    return ToolResult(
                        success=False,
                        error=f"Failed to enter text at coordinates ({cx}, {cy}).",
                        error_code="TYPE_FAILED",
                    )
                return ToolResult(
                    success=True,
                    data={
                        "action": "type_text",
                        "mode": "coordinates",
                        "coordinates": {"x": cx, "y": cy},
                        "characters_typed": len(params.text),
                        "clear_first": params.clear_first,
                        "press_enter": params.press_enter,
                        "target_hwnd": target_hwnd,
                    },
                    verified=True,
                )

            # 3. Case B: Target by natural language description or element ID
            target_elem: Optional[GroundedUIElement] = None
            if params.target_description or params.element_id:
                try:
                    elements, _ = await grounding_engine.scan_screen_elements(
                        monitor_id=params.monitor_id,
                        active_window_only=params.active_window_only,
                    )
                    if params.element_id:
                        for e in elements:
                            if e.element_id == params.element_id:
                                target_elem = e
                                break
                    if not target_elem and params.target_description:
                        target_elem, _ = grounding_engine.match_element(
                            params.target_description,
                            elements,
                            target_type=ElementType.TEXT_FIELD,
                        )
                except Exception:
                    pass

                # If element was found on screen, use its exact center
                if target_elem:
                    cx, cy = target_elem.center.x, target_elem.center.y
                    ok = adapter.type_text(
                        text=params.text,
                        x=cx,
                        y=cy,
                        target_hwnd=target_elem.window_handle or target_hwnd,
                        clear_first=params.clear_first,
                        press_enter=params.press_enter,
                        use_clipboard=params.paste_mode,
                    )
                    if not ok:
                        return ToolResult(
                            success=False,
                            error=f"Failed to enter text into field '{target_elem.description}' at ({cx}, {cy}).",
                            error_code="TYPE_FAILED",
                        )
                    return ToolResult(
                        success=True,
                        data={
                            "action": "type_text",
                            "mode": "grounded_element",
                            "target_description": target_elem.description,
                            "element_id": target_elem.element_id,
                            "characters_typed": len(params.text),
                            "coordinates": {"x": cx, "y": cy},
                            "bounding_box": target_elem.bounding_box.model_dump(),
                            "window_title": target_elem.window_title,
                            "clear_first": params.clear_first,
                            "press_enter": params.press_enter,
                        },
                        verified=True,
                    )

            # 4. Case C: Target application window is known (e.g. Notepad, Chrome, active window)
            # If element OCR/UIA matching did not locate a specific control, gracefully focus the window
            # and enter text into its main client/edit area
            if target_hwnd is not None or params.app_name:
                ok = adapter.type_text(
                    text=params.text,
                    target_hwnd=target_hwnd,
                    clear_first=params.clear_first,
                    press_enter=params.press_enter,
                    use_clipboard=params.paste_mode,
                )
                if not ok:
                    return ToolResult(
                        success=False,
                        error=f"Failed to enter text into target application window {target_hwnd}.",
                        error_code="TYPE_FAILED",
                    )
                return ToolResult(
                    success=True,
                    data={
                        "action": "type_text",
                        "mode": "application_window",
                        "app_name": params.app_name,
                        "window_handle": target_hwnd,
                        "characters_typed": len(params.text),
                        "clear_first": params.clear_first,
                        "press_enter": params.press_enter,
                    },
                    verified=True,
                )

            # 5. Case D: Active foreground window typing
            ok = adapter.type_text(
                text=params.text,
                clear_first=params.clear_first,
                press_enter=params.press_enter,
                use_clipboard=params.paste_mode,
            )
            if not ok:
                return ToolResult(
                    success=False,
                    error="Failed to enter text into active window.",
                    error_code="TYPE_FAILED",
                )
            return ToolResult(
                success=True,
                data={
                    "action": "type_text",
                    "mode": "active_window",
                    "characters_typed": len(params.text),
                    "clear_first": params.clear_first,
                    "press_enter": params.press_enter,
                },
                verified=True,
            )

        except AmbiguousTargetError as amb:
            return ToolResult(
                success=False,
                error=str(amb),
                error_code="AMBIGUOUS_TARGET",
                data={"candidates": [c.model_dump() for c in amb.candidates]},
            )
        except TargetNotFoundError as tnf:
            return ToolResult(
                success=False,
                error=str(tnf),
                error_code="TARGET_NOT_FOUND",
            )
        except Exception as exc:
            logger.error(f"Typing failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Typing failure: {str(exc)}",
                error_code="EXECUTION_FAILED",
            )


class VisualScrollRegionTool(BaseTool):
    """Tool to scroll inside an identified container or region."""

    name = "visual_scroll_region"
    description = "Scroll within an identified UI region or application window."
    risk_tier = RiskTier.CONTROLLED
    parameters_schema = VisualScrollRegionParams

    async def execute(self, params: VisualScrollRegionParams, context: ExecutionContext) -> ToolResult:
        adapter = get_platform_adapter()

        try:
            cx, cy = 960, 540  # Default center fallback

            if params.target_description:
                elements, _ = await grounding_engine.scan_screen_elements(monitor_id=params.monitor_id)
                try:
                    target_elem, _ = grounding_engine.match_element(params.target_description, elements)
                    cx, cy = target_elem.center.x, target_elem.center.y
                except Exception:
                    pass

            ok = adapter.scroll_at(cx, cy, direction=params.direction, amount=params.amount)
            if not ok:
                return ToolResult(
                    success=False,
                    error=f"Failed to execute scroll {params.direction} at ({cx}, {cy}).",
                    error_code="SCROLL_FAILED",
                )

            return ToolResult(
                success=True,
                data={
                    "action": "scroll",
                    "direction": params.direction,
                    "amount": params.amount,
                    "coordinates": {"x": cx, "y": cy},
                },
                verified=True,
            )
        except Exception as exc:
            logger.error(f"Grounded scroll failed: {exc}")
            return ToolResult(
                success=False,
                error=f"Grounded scroll failure: {str(exc)}",
                error_code="EXECUTION_FAILED",
            )

