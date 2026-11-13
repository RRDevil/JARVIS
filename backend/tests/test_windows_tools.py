"""Hermetic unit tests for Windows desktop tools (Phase 3.2)."""

import pytest
from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.automation.platform_adapter import WindowInfo
from app.tools.base import ExecutionContext, RiskTier
from app.tools.windows import (
    EmptyParams,
    LaunchAppParams,
    ListWindowsParams,
    OpenFolderParams,
    WindowCloseParams,
    WindowHandleParams,
    WindowsCloseWindowTool,
    WindowsFocusWindowTool,
    WindowsLaunchAppTool,
    WindowsListAppsTool,
    WindowsListWindowsTool,
    WindowsMinimizeWindowTool,
    WindowsOpenFolderTool,
)


@pytest.fixture(autouse=True)
def setup_mock_platform():
    """Ensure every test runs against a fresh hermetic MockPlatformAdapter."""
    mock = MockPlatformAdapter()
    set_platform_adapter(mock)
    yield mock
    set_platform_adapter(None)


@pytest.mark.asyncio
async def test_list_approved_apps(setup_mock_platform):
    tool = WindowsListAppsTool()
    assert tool.risk_tier == RiskTier.READ_ONLY
    ctx = ExecutionContext(execution_id="test-exec-1")

    result = await tool.execute(EmptyParams(), ctx)
    assert result.success is True
    assert isinstance(result.data, list)
    app_ids = [a["app_id"] for a in result.data]
    assert "notepad" in app_ids
    assert "calculator" in app_ids
    assert "vscode" in app_ids


@pytest.mark.asyncio
async def test_launch_approved_app(setup_mock_platform):
    mock = setup_mock_platform
    tool = WindowsLaunchAppTool()
    assert tool.risk_tier == RiskTier.CONTROLLED
    ctx = ExecutionContext(execution_id="test-exec-2")

    # Launch allowlisted app
    result = await tool.execute(LaunchAppParams(app_id="notepad"), ctx)
    assert result.success is True
    assert result.data["app_id"] == "notepad"
    assert len(mock.launch_history) == 1

    # Launch non-allowlisted app
    fail_res = await tool.execute(LaunchAppParams(app_id="arbitrary_virus.exe"), ctx)
    assert fail_res.success is False
    assert "allowlist" in fail_res.error.lower()


@pytest.mark.asyncio
async def test_list_windows(setup_mock_platform):
    tool = WindowsListWindowsTool()
    ctx = ExecutionContext(execution_id="test-exec-3")

    # Include minimized
    res_all = await tool.execute(ListWindowsParams(include_minimized=True), ctx)
    assert res_all.success is True
    assert len(res_all.data) == 3

    # Exclude minimized
    res_unminimized = await tool.execute(ListWindowsParams(include_minimized=False), ctx)
    assert res_unminimized.success is True
    assert len(res_unminimized.data) == 2


@pytest.mark.asyncio
async def test_focus_and_minimize_window(setup_mock_platform):
    mock = setup_mock_platform
    focus_tool = WindowsFocusWindowTool()
    min_tool = WindowsMinimizeWindowTool()
    ctx = ExecutionContext(execution_id="test-exec-4")

    # Target window 1003 is currently minimized
    assert mock.windows[1003].is_minimized is True

    # Focus it -> should restore and set active
    f_res = await focus_tool.execute(WindowHandleParams(handle=1003), ctx)
    assert f_res.success is True
    assert mock.windows[1003].is_minimized is False
    assert mock.active_window_handle == 1003

    # Minimize window 1001
    m_res = await min_tool.execute(WindowHandleParams(handle=1001), ctx)
    assert m_res.success is True
    assert mock.windows[1001].is_minimized is True

    # Invalid handle
    bad_res = await focus_tool.execute(WindowHandleParams(handle=99999), ctx)
    assert bad_res.success is False
    assert bad_res.error_code == "WINDOW_NOT_FOUND"


@pytest.mark.asyncio
async def test_close_window(setup_mock_platform):
    mock = setup_mock_platform
    tool = WindowsCloseWindowTool()
    assert tool.risk_tier == RiskTier.CONSEQUENTIAL
    ctx = ExecutionContext(execution_id="test-exec-5")

    # Close window 1002
    assert 1002 in mock.windows
    res = await tool.execute(WindowCloseParams(handle=1002), ctx)
    assert res.success is True
    assert 1002 not in mock.windows
    assert 1002 in mock.closed_windows


@pytest.mark.asyncio
async def test_open_folder(setup_mock_platform):
    mock = setup_mock_platform
    tool = WindowsOpenFolderTool()
    assert tool.risk_tier == RiskTier.CONTROLLED
    ctx = ExecutionContext(execution_id="test-exec-6")

    res = await tool.execute(OpenFolderParams(folder_path="C:\\mock\\folder"), ctx)
    assert res.success is True
    assert "C:\\mock\\folder" in mock.opened_folders


def test_windows_adapter_single_window_enforcement_and_focus():
    from app.automation.windows_adapter import WindowsPlatformAdapter
    from unittest.mock import MagicMock, patch

    adapter = WindowsPlatformAdapter()

    # 1. When an actual visible window exists, launch_app focuses existing window
    mock_win = MagicMock(handle=9999, process_id=1234, title="Untitled - Notepad", process_name="notepad.exe")
    with patch.object(adapter, "find_app_window", return_value=mock_win):
        with patch.object(adapter, "focus_window", return_value=True) as focus_mock:
            res = adapter.launch_app("notepad")
            assert res["action"] == "focused_existing_window"
            assert res["window_handle"] == 9999
            focus_mock.assert_called_once_with(9999)

    # 2. When no visible window exists even if a background process was running, it terminates zombie and spawns new instance
    with patch.object(adapter, "find_app_window", return_value=None):
        with patch.object(adapter, "find_running_process", return_value=5555):
            with patch("subprocess.run") as run_mock:
                with patch("subprocess.Popen") as popen_mock:
                    popen_mock.return_value = MagicMock(pid=7777)
                    res = adapter.launch_app("notepad")
                    assert res["action"] == "launched_new_instance"
                    # Verified taskkill was called to remove headless zombie
                    assert run_mock.called


