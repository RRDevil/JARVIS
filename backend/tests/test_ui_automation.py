"""Hermetic unit tests for Controlled UI Automation (Phase 3.3)."""

import pytest
from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.tools.base import ExecutionContext, RiskTier
from app.tools.ui import (
    UIClickControlParams,
    UIClickControlTool,
    UIFindControlsParams,
    UIFindControlsTool,
    UIScrollParams,
    UIScrollTool,
    UISendShortcutParams,
    UISendShortcutTool,
    UISetTextParams,
    UISetTextTool,
)


@pytest.fixture(autouse=True)
def setup_mock_platform():
    mock = MockPlatformAdapter()
    set_platform_adapter(mock)
    yield mock
    set_platform_adapter(None)


@pytest.mark.asyncio
async def test_ui_find_controls(setup_mock_platform):
    tool = UIFindControlsTool()
    assert tool.risk_tier == RiskTier.READ_ONLY
    ctx = ExecutionContext(execution_id="test-ui-1")

    # Find all controls in Notepad window (1003)
    res = await tool.execute(UIFindControlsParams(window_handle=1003), ctx)
    assert res.success is True
    assert len(res.data) == 3

    # Filter by name "Save"
    res_filtered = await tool.execute(
        UIFindControlsParams(window_handle=1003, name="Save"), ctx
    )
    assert res_filtered.success is True
    assert len(res_filtered.data) == 1
    assert res_filtered.data[0]["name"] == "Save"

    # Filter by control_type "edit"
    res_edit = await tool.execute(
        UIFindControlsParams(window_handle=1003, control_type="edit"), ctx
    )
    assert res_edit.success is True
    assert len(res_edit.data) == 1
    assert res_edit.data[0]["control_id"] == "ctrl_edit_doc"


@pytest.mark.asyncio
async def test_ui_click_control(setup_mock_platform):
    mock = setup_mock_platform
    tool = UIClickControlTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL
    ctx = ExecutionContext(execution_id="test-ui-2")

    # Click the "Save" button
    res = await tool.execute(
        UIClickControlParams(window_handle=1003, control_id="ctrl_btn_save"), ctx
    )
    assert res.success is True
    assert len(mock.ui_actions_history) == 1
    assert mock.ui_actions_history[0]["action"] == "click"
    assert mock.ui_actions_history[0]["control_id"] == "ctrl_btn_save"

    # Click non-existent control
    res_bad = await tool.execute(
        UIClickControlParams(window_handle=1003, control_id="non_existent_ctrl"), ctx
    )
    assert res_bad.success is False
    assert res_bad.error_code == "CONTROL_CLICK_FAILED"


@pytest.mark.asyncio
async def test_ui_set_text(setup_mock_platform):
    mock = setup_mock_platform
    tool = UISetTextTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL
    ctx = ExecutionContext(execution_id="test-ui-3")

    # Set text on the document editor
    res = await tool.execute(
        UISetTextParams(
            window_handle=1003,
            control_id="ctrl_edit_doc",
            text="Hello JARVIS Autonomous Core",
        ),
        ctx,
    )
    assert res.success is True
    assert mock.controls[1003]["ctrl_edit_doc"].value == "Hello JARVIS Autonomous Core"
    assert len(mock.ui_actions_history) == 1
    assert mock.ui_actions_history[0]["action"] == "set_text"


@pytest.mark.asyncio
async def test_ui_send_shortcut_allowlist(setup_mock_platform):
    mock = setup_mock_platform
    tool = UISendShortcutTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL
    ctx = ExecutionContext(execution_id="test-ui-4")

    # Authorized shortcut: ctrl+s
    res = await tool.execute(
        UISendShortcutParams(window_handle=1003, shortcut="ctrl+s"), ctx
    )
    assert res.success is True
    assert len(mock.ui_actions_history) == 1
    assert mock.ui_actions_history[0]["shortcut"] == "ctrl+s"

    # Unauthorized/dangerous shortcut: ctrl+alt+delete
    res_danger = await tool.execute(
        UISendShortcutParams(window_handle=1003, shortcut="ctrl+alt+delete"), ctx
    )
    assert res_danger.success is False
    assert res_danger.error_code == "UNAUTHORIZED_SHORTCUT"


@pytest.mark.asyncio
async def test_ui_scroll(setup_mock_platform):
    mock = setup_mock_platform
    tool = UIScrollTool()
    assert tool.risk_tier == RiskTier.CONTROLLED
    ctx = ExecutionContext(execution_id="test-ui-5")

    res = await tool.execute(
        UIScrollParams(window_handle=1003, direction="down", amount=5), ctx
    )
    assert res.success is True
    assert len(mock.ui_actions_history) == 1
    assert mock.ui_actions_history[0]["action"] == "scroll"
    assert mock.ui_actions_history[0]["direction"] == "down"
    assert mock.ui_actions_history[0]["amount"] == 5

