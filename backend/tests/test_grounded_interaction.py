"""Tests for Phase 5 Grounded UI Interaction Tools and Policy Authorization."""

import time
import pytest
from app.automation.factory import get_platform_adapter, set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.perception.grounding import grounding_engine
from app.perception.models import (
    ElementBoundingBox,
    ElementSource,
    ElementType,
    GroundedUIElement,
    PointCoordinate,
)
from app.tools.base import ExecutionContext, PolicyDecision, RiskTier
from app.tools.grounded_interaction import (
    VisualClickElementParams,
    VisualClickElementTool,
    VisualLocateElementsParams,
    VisualLocateElementsTool,
    VisualScrollRegionParams,
    VisualScrollRegionTool,
    VisualTypeIntoElementParams,
    VisualTypeIntoElementTool,
)
from app.tools.policy import PolicyEngine


@pytest.fixture(autouse=True)
def setup_mock():
    mock = MockPlatformAdapter()
    set_platform_adapter(mock)

    # Seed mock grounded elements in grounding engine cache
    now_iso = "2026-11-05T00:00:00Z"
    grounding_engine._last_observation_time = time.time()  # Fresh
    grounding_engine._last_elements_cache = [
        GroundedUIElement(
            element_id="elem-save-1",
            description="Save Button (button)",
            text="Save",
            element_type=ElementType.BUTTON,
            bounding_box=ElementBoundingBox(left=120, top=150, width=80, height=30),
            center=PointCoordinate(x=160, y=165),
            confidence=0.95,
            is_interactable=True,
            source=ElementSource.UIA,
            timestamp=now_iso,
            window_title="Untitled - Notepad",
        ),
        GroundedUIElement(
            element_id="elem-edit-1",
            description="Document Text Editor (text_field)",
            text="Text Editor",
            element_type=ElementType.TEXT_FIELD,
            bounding_box=ElementBoundingBox(left=50, top=80, width=500, height=300),
            center=PointCoordinate(x=300, y=230),
            confidence=0.95,
            is_interactable=True,
            source=ElementSource.UIA,
            timestamp=now_iso,
            window_title="Untitled - Notepad",
        ),
    ]

    yield mock
    set_platform_adapter(None)


@pytest.mark.asyncio
async def test_visual_locate_elements_tool():
    tool = VisualLocateElementsTool()
    assert tool.risk_tier == RiskTier.READ_ONLY

    params = VisualLocateElementsParams(query="Save")
    ctx = ExecutionContext(execution_id="test-exec-1")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["total_found"] >= 1
    found = res.data["elements"][0]
    assert found["text"] == "Save"
    assert found["center"]["x"] == 160


@pytest.mark.asyncio
async def test_visual_click_element_tool_success(setup_mock):
    tool = VisualClickElementTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL

    params = VisualClickElementParams(target_description="Save", button="left")
    ctx = ExecutionContext(execution_id="test-exec-2")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["action"] == "left_click"
    assert res.data["coordinates"]["x"] == 160
    assert res.data["coordinates"]["y"] == 165

    # Verify mock platform adapter recorded click_at
    mock_history = setup_mock.ui_actions_history
    assert any(a.get("action") == "click_at" and a.get("x") == 160 and a.get("y") == 165 for a in mock_history)


@pytest.mark.asyncio
async def test_visual_click_element_by_id(setup_mock):
    tool = VisualClickElementTool()
    params = VisualClickElementParams(element_id="elem-save-1", button="double")
    ctx = ExecutionContext(execution_id="test-exec-3")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["action"] == "double_click"


@pytest.mark.asyncio
async def test_visual_type_into_element_tool(setup_mock):
    tool = VisualTypeIntoElementTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL

    params = VisualTypeIntoElementParams(
        target_description="Document Text Editor",
        text="Hello J.A.R.V.I.S.",
        clear_first=True,
    )
    ctx = ExecutionContext(execution_id="test-exec-4")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["characters_typed"] == 18
    assert res.data["coordinates"]["x"] == 300

    # Verify mock platform adapter recorded type_text_at
    mock_history = setup_mock.ui_actions_history
    assert any(a.get("action") == "type_text_at" and a.get("text") == "Hello J.A.R.V.I.S." for a in mock_history)


@pytest.mark.asyncio
async def test_visual_scroll_region_tool(setup_mock):
    tool = VisualScrollRegionTool()
    assert tool.risk_tier == RiskTier.CONTROLLED

    params = VisualScrollRegionParams(target_description="Save", direction="down", amount=5)
    ctx = ExecutionContext(execution_id="test-exec-5")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["direction"] == "down"
    assert res.data["amount"] == 5

    mock_history = setup_mock.ui_actions_history
    assert any(a.get("action") == "scroll_at" and a.get("amount") == 5 for a in mock_history)


def test_grounded_interaction_policy_evaluation():
    policy = PolicyEngine(auto_approve_controlled=True)

    locate_tool = VisualLocateElementsTool()
    eval_locate = policy.evaluate(locate_tool, {"query": "Search"})
    assert eval_locate.decision == PolicyDecision.ALLOW_AUTO
    assert eval_locate.requires_approval is False

    click_tool = VisualClickElementTool()
    eval_click = policy.evaluate(click_tool, {"target_description": "Submit Order", "button": "left"})
    assert eval_click.decision == PolicyDecision.REQUIRE_APPROVAL
    assert eval_click.requires_approval is True
    assert "Perform left-click on grounded element 'Submit Order'" in eval_click.action_summary

    # When user confirms via approval token
    eval_click_confirmed = policy.evaluate(
        click_tool,
        {"target_description": "Submit Order", "button": "left"},
        user_confirmed=True,
    )
    assert eval_click_confirmed.decision == PolicyDecision.ALLOW_AUTO
    assert eval_click_confirmed.requires_approval is False


@pytest.mark.asyncio
async def test_visual_click_element_by_coordinates(setup_mock):
    """Verify clicking anywhere on screen by exact coordinates (x, y)."""
    tool = VisualClickElementTool()
    params = VisualClickElementParams(x=640, y=480, button="left")
    ctx = ExecutionContext(execution_id="test-exec-coord-click")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["mode"] == "coordinate"
    assert res.data["coordinates"]["x"] == 640
    assert res.data["coordinates"]["y"] == 480

    mock_history = setup_mock.ui_actions_history
    assert any(
        a.get("action") == "click_at" and a.get("x") == 640 and a.get("y") == 480
        for a in mock_history
    )


@pytest.mark.asyncio
async def test_visual_type_into_element_by_coordinates(setup_mock):
    """Verify typing into any textbox by coordinates (x, y) with press_enter and clear_first."""
    tool = VisualTypeIntoElementTool()
    params = VisualTypeIntoElementParams(
        x=500,
        y=300,
        text="Search Query\n",
        clear_first=True,
        press_enter=True,
    )
    ctx = ExecutionContext(execution_id="test-exec-coord-type")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["mode"] == "coordinates"
    assert res.data["coordinates"]["x"] == 500
    assert res.data["characters_typed"] == len("Search Query\n")

    mock_history = setup_mock.ui_actions_history
    assert any(
        a.get("action") == "type_text"
        and a.get("x") == 500
        and a.get("y") == 300
        and a.get("clear_first") is True
        and a.get("press_enter") is True
        for a in mock_history
    )


@pytest.mark.asyncio
async def test_visual_type_into_element_app_fallback(setup_mock):
    """Verify typing into an application like Notepad when text box control is blank or ungrounded."""
    setup_mock.create_window(handle=101, title="Untitled - Notepad", process_name="notepad.exe")

    tool = VisualTypeIntoElementTool()
    params = VisualTypeIntoElementParams(
        app_name="notepad",
        text="Automated document text",
    )
    ctx = ExecutionContext(execution_id="test-exec-app-type")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["mode"] == "application_window"
    assert res.data["app_name"] == "notepad"
    assert res.data["window_handle"] in (101, 1003)

    mock_history = setup_mock.ui_actions_history
    assert any(
        a.get("action") == "type_text"
        and a.get("target_hwnd") in (101, 1003)
        and a.get("text") == "Automated document text"
        for a in mock_history
    )


@pytest.mark.asyncio
async def test_desktop_type_text_tool(setup_mock):
    """Verify universal desktop_type_text tool works for any application."""
    from app.tools.ui import UIDesktopTypeTextParams, UIDesktopTypeTextTool

    tool = UIDesktopTypeTextTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL

    setup_mock.create_window(handle=202, title="Google Chrome", process_name="chrome.exe")

    params = UIDesktopTypeTextParams(
        app_name="chrome",
        text="https://news.ycombinator.com",
        press_enter=True,
    )
    ctx = ExecutionContext(execution_id="test-exec-desktop-type")

    res = await tool.execute(params, ctx)
    assert res.success is True
    assert res.data["app_name"] == "chrome"
    assert res.data["window_handle"] in (202, 1001)
    assert res.data["press_enter"] is True

    mock_history = setup_mock.ui_actions_history
    assert any(
        a.get("action") == "type_text"
        and a.get("target_hwnd") in (202, 1001)
        and a.get("press_enter") is True
        for a in mock_history
    )


def test_coordinate_click_and_desktop_typing_policy_evaluation():
    """Verify security policy properly evaluates coordinate clicks and universal typing."""
    from app.tools.ui import UIDesktopTypeTextTool

    policy = PolicyEngine()
    click_tool = VisualClickElementTool()

    # Direct coordinate click summary
    eval_click = policy.evaluate(click_tool, {"x": 500, "y": 250, "button": "left"})
    assert eval_click.decision == PolicyDecision.REQUIRE_APPROVAL
    assert "Perform left-click at screen coordinates (500, 250)" in eval_click.action_summary

    # Desktop type text summary
    type_tool = UIDesktopTypeTextTool()
    eval_type = policy.evaluate(type_tool, {"app_name": "notepad", "text": "Testing 123"})
    assert eval_type.decision == PolicyDecision.REQUIRE_APPROVAL
    assert 'Type "Testing 123" into notepad' in eval_type.action_summary
