"""Tests for Visual Target Resolution & Reliable Clicking Pipeline.

Verifies:
1. Pre-approval target resolution (textual, semantic visual, and coordinate).
2. Unresolvable target failure BEFORE approval creation (no approval requests generated for vague/missing targets).
3. Concrete coordinate, window, and bounding box binding in approval requests and cryptographic tokens.
4. Target invalidation protection (closed or destroyed windows reject execution).
5. Native mouse movement, hover settling, and post-click verification.
"""

import asyncio
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.automation.factory import get_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.execution.engine import execution_engine
from app.perception.grounding import GroundedUIElement, TargetNotFoundError
from app.perception.models import (
    CapturedScreen,
    ElementBoundingBox,
    ElementSource,
    ElementType,
    PointCoordinate,
)
from app.perception.target_resolver import ResolvedVisualTarget, target_resolver
from app.tools.defaults import register_default_windows_tools
from app.tools.base import RiskTier, ToolStatus
from app.tools.grounded_interaction import VisualClickElementParams, VisualClickElementTool


@pytest.fixture(autouse=True)
def ensure_mock_adapter():
    """Ensure platform adapter is MockPlatformAdapter and tools are registered during test runs."""
    register_default_windows_tools(execution_engine.registry)
    from app.automation.factory import set_platform_adapter
    mock_adapter = MockPlatformAdapter()
    mock_adapter.ui_actions_history.clear()
    mock_adapter.virtual_desktop_bounds = (0, 0, 1920, 1080)
    set_platform_adapter(mock_adapter)
    yield
    set_platform_adapter(None)


@pytest.mark.asyncio
async def test_resolve_target_textual_high_confidence():
    """Textual query matching an on-screen UIA/OCR control resolves immediately to concrete coordinates."""
    mock_element = GroundedUIElement(
        element_id="elem-test-search",
        description="'Search Bar' (search_bar)",
        text="Search",
        element_type=ElementType.SEARCH_BAR,
        bounding_box=ElementBoundingBox(left=200, top=50, width=400, height=36),
        center=PointCoordinate(x=400, y=68),
        confidence=0.95,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp=datetime.now(timezone.utc).isoformat(),
        window_title="Opera GX",
        window_handle=1001,
    )

    adapter = get_platform_adapter()
    if isinstance(adapter, MockPlatformAdapter):
        from app.automation.platform_adapter import WindowInfo
        adapter.windows[2001] = WindowInfo(
            handle=2001,
            title="Opera GX",
            process_id=5000,
            process_name="opera.exe",
            is_visible=True,
            is_minimized=False,
        )

    with patch("app.perception.grounding.grounding_engine.scan_screen_elements", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = ([mock_element], {"active_window": "Opera GX", "screen_width": 1920, "screen_height": 1080})

        resolved = await target_resolver.resolve_target("Search", monitor_id=1, active_window_only=False)

        assert isinstance(resolved, ResolvedVisualTarget)
        assert resolved.click_coordinates.x == 400
        assert resolved.click_coordinates.y == 68
        assert resolved.bounding_box.left == 200
        assert resolved.detection_method in ("uia", "hybrid", "ocr")
        assert resolved.confidence >= 0.85
        assert resolved.is_actionable is True


@pytest.mark.asyncio
async def test_resolve_target_semantic_video_heuristic():
    """Semantic query 'this video' or 'second video' identifies video element container and concrete coordinates."""
    video1 = GroundedUIElement(
        element_id="elem-video-1",
        description="First Video",
        text="How To Build A Desktop AI Assistant in Python - 12:45 - 50K views",
        element_type=ElementType.GENERIC_CLICKABLE,
        bounding_box=ElementBoundingBox(left=100, top=200, width=320, height=180),
        center=PointCoordinate(x=260, y=290),
        confidence=0.90,
        is_interactable=True,
        source=ElementSource.OCR,
        timestamp=datetime.now(timezone.utc).isoformat(),
        window_title="YouTube - Opera GX",
        window_handle=1002,
    )
    video2 = GroundedUIElement(
        element_id="elem-video-2",
        description="Second Video",
        text="Advanced Multimodal Vision with Gemini 2.5 - 24:10 - 120K views",
        element_type=ElementType.GENERIC_CLICKABLE,
        bounding_box=ElementBoundingBox(left=450, top=200, width=320, height=180),
        center=PointCoordinate(x=610, y=290),
        confidence=0.90,
        is_interactable=True,
        source=ElementSource.OCR,
        timestamp=datetime.now(timezone.utc).isoformat(),
        window_title="YouTube - Opera GX",
        window_handle=1002,
    )

    adapter = get_platform_adapter()
    if isinstance(adapter, MockPlatformAdapter):
        from app.automation.platform_adapter import WindowInfo
        adapter.windows[2001] = WindowInfo(
            handle=2001,
            title="Opera GX",
            process_id=5000,
            process_name="opera.exe",
            is_visible=True,
            is_minimized=False,
        )

    with patch("app.perception.grounding.grounding_engine.scan_screen_elements", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = ([video1, video2], {"active_window": "YouTube - Opera GX", "screen_width": 1920, "screen_height": 1080})

        # Test first video
        resolved_first = await target_resolver.resolve_target("click on this video", monitor_id=1)
        assert resolved_first.click_coordinates.x == 260
        assert resolved_first.click_coordinates.y == 290
        assert "Video" in resolved_first.target_description

        # Test second video
        resolved_second = await target_resolver.resolve_target("open the second video", monitor_id=1)
        assert resolved_second.click_coordinates.x == 610
        assert resolved_second.click_coordinates.y == 290


@pytest.mark.asyncio
async def test_unresolvable_target_fails_safely_without_approval():
    """When a target description cannot be resolved, execution fails immediately and NO approval request is created."""
    adapter = get_platform_adapter()
    if isinstance(adapter, MockPlatformAdapter):
        from app.automation.platform_adapter import WindowInfo
        adapter.windows[2001] = WindowInfo(
            handle=2001,
            title="Opera GX",
            process_id=5000,
            process_name="opera.exe",
            is_visible=True,
            is_minimized=False,
        )

    with patch("app.perception.grounding.grounding_engine.scan_screen_elements", new_callable=AsyncMock) as mock_scan:
        # Screen contains unrelated elements
        mock_scan.return_value = ([], {"active_window": "Desktop", "screen_width": 1920, "screen_height": 1080})

        exec_model, approval = await execution_engine.propose(
            tool_name="visual_click_element",
            raw_parameters={"target_description": "nonexistent play button in imaginary app"},
            session_id="test-unresolvable",
        )

        # Verification: Approval must NOT be generated!
        assert approval is None
        assert exec_model.status == ToolStatus.FAILED
        assert "target resolution failed" in exec_model.error.lower()


@pytest.mark.asyncio
async def test_approval_parameters_bound_to_concrete_coordinates():
    """Target resolution enriches proposed parameters so the approval request displays concrete target, window, and coords."""
    mock_element = GroundedUIElement(
        element_id="elem-settings",
        description="Settings button",
        text="Settings",
        element_type=ElementType.BUTTON,
        bounding_box=ElementBoundingBox(left=1800, top=30, width=40, height=40),
        center=PointCoordinate(x=1820, y=50),
        confidence=0.98,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp=datetime.now(timezone.utc).isoformat(),
        window_title="Opera GX",
        window_handle=2001,
    )

    adapter = get_platform_adapter()
    if isinstance(adapter, MockPlatformAdapter):
        from app.automation.platform_adapter import WindowInfo
        adapter.windows[2001] = WindowInfo(
            handle=2001,
            title="Opera GX",
            process_id=5000,
            process_name="opera.exe",
            is_visible=True,
            is_minimized=False,
        )

    with patch("app.perception.grounding.grounding_engine.scan_screen_elements", new_callable=AsyncMock) as mock_scan:
        mock_scan.return_value = ([mock_element], {"active_window": "Opera GX", "screen_width": 1920, "screen_height": 1080})

        exec_model, approval = await execution_engine.propose(
            tool_name="visual_click_element",
            raw_parameters={"target_description": "Settings"},
            session_id="test-approval-binding",
        )

        assert approval is not None
        assert exec_model.status == ToolStatus.PENDING_APPROVAL

        # Verification of concrete parameter binding
        params = approval.parameters
        assert params["x"] == 1820
        assert params["y"] == 50
        assert params["target_description"] == "Settings"
        assert params["bounding_box"] == {"left": 1800, "top": 30, "width": 40, "height": 40}
        assert params["detection_method"] in ("uia", "hybrid", "ocr")

        # Verification of human-readable action summary
        assert "(1820, 50)" in approval.actionSummary
        assert "Settings" in approval.actionSummary

        # Verification that approval can be granted and executed with the resolved parameters
        assert approval.id is not None
        appr_req, executed = await execution_engine.resolve_approval(approval.id, approved=True)
        assert appr_req.status == "approved"
        assert executed.status in (ToolStatus.SUCCESS, "success")
        assert executed.parameters["x"] == 1820
        assert executed.parameters["y"] == 50


@pytest.mark.asyncio
async def test_target_invalidation_rejected_safely():
    """If target window handle is destroyed/closed before execution, execution fails safely with TARGET_INVALIDATED."""
    tool = VisualClickElementTool()
    adapter = get_platform_adapter()

    # Pass an invalid window handle (99999999)
    with patch("ctypes.windll.user32.IsWindow", return_value=0):
        result = await tool.execute(
            VisualClickElementParams(
                x=500,
                y=500,
                target_description="Closed Window Target",
                window_handle=99999999,
                window_title="Old Window",
            ),
            context=MagicMock(),
        )

        assert result.success is False
        assert result.error_code == "TARGET_INVALIDATED"


@pytest.mark.asyncio
async def test_click_execution_and_verification():
    """Click execution moves cursor, dispatches SendInput, and verifies interaction state."""
    tool = VisualClickElementTool()
    adapter = get_platform_adapter()

    params = VisualClickElementParams(
        x=750,
        y=420,
        target_description="Test Button",
        bounding_box={"left": 700, "top": 400, "width": 100, "height": 40},
        hover_ms=30,
        verify_post_condition=True,
    )

    result = await tool.execute(params, context=MagicMock())

    assert result.success is True
    assert result.data["coordinates"] == {"x": 750, "y": 420}
    assert result.data["status"] in ("SUCCESS", "DISPATCHED_UNVERIFIED")

    # Verify adapter action record
    if isinstance(adapter, MockPlatformAdapter):
        assert len(adapter.ui_actions_history) >= 1
        last_action = adapter.ui_actions_history[-1]
        assert last_action["action"] == "click_at"
        assert last_action["x"] == 750
        assert last_action["y"] == 420
        assert last_action["hover_ms"] == 30
