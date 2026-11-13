"""Live host smoke tests for WindowsPlatformAdapter on Windows 11."""

import os
import sys
import pytest

from app.automation.windows_adapter import WindowsPlatformAdapter


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows host")
def test_live_windows_approved_apps_catalog():
    """Verify approved apps catalog loads valid configurations on Windows."""
    adapter = WindowsPlatformAdapter()
    apps = adapter.get_approved_apps()
    assert len(apps) >= 5
    app_ids = [a.app_id for a in apps]
    assert "notepad" in app_ids
    assert "calculator" in app_ids
    assert "vscode" in app_ids


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows host")
def test_live_windows_enumeration():
    """Verify EnumWindows successfully enumerates real running host windows."""
    adapter = WindowsPlatformAdapter()
    windows = adapter.list_windows()

    # On an active Windows session, there is always at least one visible top-level window
    assert isinstance(windows, list)
    assert len(windows) > 0

    first = windows[0]
    assert isinstance(first.handle, int)
    assert first.handle > 0
    assert isinstance(first.title, str)
    assert len(first.title) > 0
    assert isinstance(first.process_id, int)
    assert first.process_id > 0
    assert isinstance(first.process_name, str)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows host")
def test_live_ui_controls_inspection_non_destructive():
    """Verify EnumChildWindows safely inspects child controls without mutation."""
    adapter = WindowsPlatformAdapter()
    windows = adapter.list_windows()
    assert len(windows) > 0

    # Pick the first window and query its child controls
    target_handle = windows[0].handle
    controls = adapter.find_controls(target_handle)
    assert isinstance(controls, list)
    # The call should succeed without throwing exceptions even if controls list is empty

