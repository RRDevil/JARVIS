"""Phase 5.1 Comprehensive Tests: Grounded Clicking & Focus-Aware Keyboard Approval."""

import pytest
import time
from fastapi.testclient import TestClient

from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.automation.platform_adapter import WindowInfo
from app.perception.models import (
    ElementBoundingBox,
    ElementSource,
    ElementType,
    GroundedUIElement,
    PointCoordinate,
)
from app.perception.grounding import grounding_engine
from app.tools.base import ExecutionContext
from app.tools.defaults import register_default_windows_tools
from app.tools.grounded_interaction import VisualClickElementTool, VisualClickElementParams
from app.tools.ui import UISendShortcutTool, UISendShortcutParams
from app.execution.approval import approval_manager
from app.main import app


@pytest.fixture(autouse=True)
def setup_env():
    mock = MockPlatformAdapter()
    set_platform_adapter(mock)
    register_default_windows_tools()
    approval_manager.clear()
    yield mock
    set_platform_adapter(None)


@pytest.fixture
def test_client():
    return TestClient(app)


# --- 1. Multi-Monitor Coordinate & Virtual Screen Bounds ---

@pytest.mark.asyncio
async def test_grounded_click_multi_monitor_negative_coordinates():
    """Verify that secondary monitors with negative coordinates (e.g. left of primary) are accepted."""
    mock_adapter = MockPlatformAdapter()
    set_platform_adapter(mock_adapter)
    # Secondary monitor placed to the left: -1920 to 1920
    mock_adapter.virtual_desktop_bounds = (-1920, 0, 3840, 1080)

    elem = GroundedUIElement(
        element_id="elem-sec-1",
        description="Secondary Monitor Save",
        text="Save",
        element_type=ElementType.BUTTON,
        bounding_box=ElementBoundingBox(left=-500, top=200, width=100, height=50),
        center=PointCoordinate(x=-450, y=225),
        confidence=0.95,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp="2026-11-05T00:00:00Z",
        window_handle=12345,
    )
    grounding_engine._last_observation_time = time.time()  # Fresh
    grounding_engine._last_elements_cache = [elem]

    tool = VisualClickElementTool()
    ctx = ExecutionContext(execution_id="test-exec-sec-1")
    result = await tool.execute(VisualClickElementParams(element_id="elem-sec-1", target_description="Save"), ctx)

    assert result.success is True
    assert result.data["coordinates"] == {"x": -450, "y": 225}
    assert any(a.get("action") == "click_at" and a.get("x") == -450 and a.get("y") == 225 for a in mock_adapter.ui_actions_history)


@pytest.mark.asyncio
async def test_grounded_click_rejects_coordinates_outside_virtual_bounds():
    """Verify coordinates outside the virtual screen bounding rectangle are safely rejected."""
    mock_adapter = MockPlatformAdapter()
    set_platform_adapter(mock_adapter)
    mock_adapter.virtual_desktop_bounds = (0, 0, 1920, 1080)

    elem = GroundedUIElement(
        element_id="elem-oob",
        description="Offscreen Button",
        text="Offscreen",
        element_type=ElementType.BUTTON,
        bounding_box=ElementBoundingBox(left=5000, top=5000, width=100, height=50),
        center=PointCoordinate(x=5050, y=5025),
        confidence=0.95,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp="2026-11-05T00:00:00Z",
    )
    grounding_engine._last_observation_time = time.time()
    grounding_engine._last_elements_cache = [elem]

    tool = VisualClickElementTool()
    ctx = ExecutionContext(execution_id="test-exec-oob")
    result = await tool.execute(VisualClickElementParams(element_id="elem-oob", target_description="Offscreen"), ctx)

    assert result.success is False
    assert result.error_code == "COORDINATES_OUT_OF_BOUNDS"


# --- 2. Stale Observation Rejection ---

@pytest.mark.asyncio
async def test_grounded_click_rejects_stale_observation():
    """Verify that interaction fails safely when visual observation has expired."""
    mock_adapter = MockPlatformAdapter()
    set_platform_adapter(mock_adapter)

    # Observation from 30 seconds ago (max_age is 20.0 seconds)
    elem = GroundedUIElement(
        element_id="elem-stale",
        description="Stale Button",
        text="Stale",
        element_type=ElementType.BUTTON,
        bounding_box=ElementBoundingBox(left=100, top=100, width=50, height=50),
        center=PointCoordinate(x=125, y=125),
        confidence=0.9,
        is_interactable=True,
        source=ElementSource.UIA,
        timestamp="2026-11-05T00:00:00Z",
    )
    grounding_engine._last_observation_time = time.time() - 30.0
    grounding_engine._last_elements_cache = [elem]

    tool = VisualClickElementTool()
    ctx = ExecutionContext(execution_id="test-exec-stale")
    result = await tool.execute(VisualClickElementParams(element_id="elem-stale", target_description="Stale"), ctx)

    assert result.success is False
    assert result.error_code == "OBSERVATION_STALE"


# --- 3. Focus Mismatch & Keyboard Shortcut Safeguards ---

@pytest.mark.asyncio
async def test_ui_send_shortcut_focus_mismatch_fails_safely():
    """Verify that sending a shortcut fails cleanly with FOCUS_MISMATCH if target window cannot be activated."""
    mock_adapter = MockPlatformAdapter()
    set_platform_adapter(mock_adapter)
    # Target window focus is prevented
    mock_adapter.prevent_focus = True

    tool = UISendShortcutTool()
    params = UISendShortcutParams(
        window_handle=12345,
        shortcut="ctrl+s",
        target_app_name="Notepad",
        window_title="Untitled - Notepad",
    )
    ctx = ExecutionContext(execution_id="test-exec-mismatch")

    result = await tool.execute(params, ctx)
    assert result.success is False
    assert result.error_code == "FOCUS_MISMATCH"
    assert "Focus mismatch" in result.error or "could not be activated" in result.error


@pytest.mark.asyncio
async def test_ui_send_shortcut_focus_success_executes():
    """Verify shortcut executes when target window is properly focused."""
    mock_adapter = MockPlatformAdapter()
    set_platform_adapter(mock_adapter)
    mock_adapter.windows[12345] = WindowInfo(
        handle=12345,
        title="Untitled - Notepad",
        process_id=5432,
        process_name="notepad.exe",
        is_visible=True,
        is_minimized=False,
    )
    mock_adapter.active_window_handle = 12345

    tool = UISendShortcutTool()
    params = UISendShortcutParams(
        window_handle=12345,
        shortcut="ctrl+s",
        target_app_name="Notepad",
    )
    ctx = ExecutionContext(execution_id="test-exec-focus-ok")

    result = await tool.execute(params, ctx)
    assert result.success is True
    assert any(a.get("action") == "send_shortcut" and a.get("handle") == 12345 for a in mock_adapter.ui_actions_history)


# --- 4. Active Approval Endpoints (Global Shortcut Resolution) ---

def test_active_approval_get_and_respond_endpoints(test_client):
    """Verify GET /api/v1/approvals/active and POST /api/v1/approvals/active/respond."""
    # 1. Clear any pending approvals -> 404
    approval_manager.clear()
    r = test_client.get("/api/v1/approvals/active")
    assert r.status_code == 404

    # 2. Stage a consequential tool execution requiring approval
    prop_resp = test_client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    assert prop_resp.status_code == 200
    appr_data = prop_resp.json()["approval_request"]
    assert appr_data is not None

    # 3. GET /active returns the staged pending approval
    r_get = test_client.get("/api/v1/approvals/active")
    assert r_get.status_code == 200
    assert r_get.json()["id"] == appr_data["id"]
    assert r_get.json()["actionSummary"] == appr_data["actionSummary"]

    # 4. POST /active/respond approves the active request via global shortcut
    r_post = test_client.post("/api/v1/approvals/active/respond", json={"approved": True})
    assert r_post.status_code == 200
    assert r_post.json()["approval"]["status"] == "approved"
    assert r_post.json()["approval"]["id"] == appr_data["id"]

    # 5. Pending list is now empty
    assert len(approval_manager.get_pending()) == 0
