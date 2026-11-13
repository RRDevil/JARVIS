"""Unit tests for Platform Abstraction Layer and Cross-Platform Expansion (Milestone 6.1)."""

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import pytest

from app.core.platform import (
    PlatformType,
    get_cache_dir,
    get_current_platform,
    get_logs_dir,
    get_models_dir,
    get_user_data_dir,
    is_linux,
    is_macos,
    is_windows,
)
from app.automation.base import (
    ApprovedApp,
    AutomationError,
    FocusMismatchError,
    PlatformAdapter,
    UIControlInfo,
    WindowInfo,
)
from app.automation.factory import get_platform_adapter, set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.automation.windows_adapter import WindowsPlatformAdapter
from app.automation.macos_adapter import MacOSPlatformAdapter
from app.perception.base import OCREngineProvider, ScreenCaptureProvider
from app.perception.ocr_engine import LocalOCREngine
from app.perception.ocr_macos import MacOSVisionOCREngine
from app.perception.screen_capture import ScreenCaptureEngine, screen_capture_engine
from app.integrations.base import AppDiscoveryProvider, OfficeAutomationProvider
from app.integrations.discovery import ApplicationDiscoveryEngine
from app.integrations.providers.office_com import OfficeCOMProvider
from app.integrations.providers.office_macos import MacOSOfficeAppleScriptProvider


# ---------------------------------------------------------
# 1. Platform Detection & Path Resolution Tests
# ---------------------------------------------------------

def test_current_platform_matches_sys_platform():
    """Verify get_current_platform correctly identifies current OS."""
    plat = get_current_platform()
    if sys.platform == "win32":
        assert plat == PlatformType.WINDOWS
        assert is_windows() is True
        assert is_macos() is False
    elif sys.platform == "darwin":
        assert plat == PlatformType.MACOS
        assert is_macos() is True
        assert is_windows() is False
    elif sys.platform.startswith("linux"):
        assert plat == PlatformType.LINUX
        assert is_linux() is True


def test_platform_mocking_and_path_resolution():
    """Verify standard paths adhere to OS specifications (macOS vs Windows)."""
    # Test macOS paths
    with patch("sys.platform", "darwin"):
        assert get_current_platform() == PlatformType.MACOS
        assert is_macos() is True
        assert is_windows() is False

        mac_data = get_user_data_dir("JARVIS")
        assert "Library" in str(mac_data) and "Application Support" in str(mac_data)
        assert mac_data.name == "JARVIS"

        mac_logs = get_logs_dir("JARVIS")
        assert "Library" in str(mac_logs) and "Logs" in str(mac_logs)

        mac_cache = get_cache_dir("JARVIS")
        assert "Library" in str(mac_cache) and "Caches" in str(mac_cache)

    # Test Windows paths
    with patch("sys.platform", "win32"):
        assert get_current_platform() == PlatformType.WINDOWS
        assert is_windows() is True
        assert is_macos() is False

        with patch.dict(os.environ, {"LOCALAPPDATA": "C:\\Users\\Test\\AppData\\Local"}):
            win_data = get_user_data_dir("JARVIS")
            assert "AppData" in str(win_data)
            assert win_data.name == "JARVIS"


def test_models_dir_env_override():
    """Verify JARVIS_MODELS_DIR override takes precedence."""
    with patch.dict(os.environ, {"JARVIS_MODELS_DIR": "D:\\External\\Models"}):
        m_dir = get_models_dir("JARVIS")
        assert str(m_dir) == str(Path("D:\\External\\Models"))


# ---------------------------------------------------------
# 2. Automation Base and Factory Tests
# ---------------------------------------------------------

def test_automation_base_reexports():
    """Verify that automation/base.py cleanly re-exports all required types."""
    assert issubclass(WindowsPlatformAdapter, PlatformAdapter)
    assert issubclass(MacOSPlatformAdapter, PlatformAdapter)
    assert issubclass(MockPlatformAdapter, PlatformAdapter)
    assert issubclass(FocusMismatchError, AutomationError)


def test_factory_platform_routing():
    """Verify get_platform_adapter routes properly based on platform and environment."""
    set_platform_adapter(None)

    # 1. Mock override
    with patch.dict(os.environ, {"JARVIS_MOCK_PLATFORM": "1"}):
        adapter = get_platform_adapter()
        assert isinstance(adapter, MockPlatformAdapter)

    set_platform_adapter(None)

    # 2. Windows platform
    with patch.dict(os.environ, {"JARVIS_MOCK_PLATFORM": ""}, clear=True):
        with patch("sys.platform", "win32"):
            adapter = get_platform_adapter()
            assert isinstance(adapter, WindowsPlatformAdapter)

    set_platform_adapter(None)

    # 3. macOS platform
    with patch.dict(os.environ, {"JARVIS_MOCK_PLATFORM": ""}, clear=True):
        with patch("sys.platform", "darwin"):
            adapter = get_platform_adapter()
            assert isinstance(adapter, MacOSPlatformAdapter)

    # Clean up singleton
    set_platform_adapter(None)


def test_macos_platform_adapter_interface():
    """Verify MacOSPlatformAdapter fulfills the PlatformAdapter abstract contract."""
    adapter = MacOSPlatformAdapter()
    assert isinstance(adapter, PlatformAdapter)

    # Approved apps
    approved = adapter.get_approved_apps()
    assert len(approved) > 0
    app_ids = [a.app_id for a in approved]
    assert "calculator" in app_ids
    assert "safari" in app_ids
    assert "word" in app_ids

    # Permission check method exists and returns bool
    assert isinstance(adapter.is_permission_granted(), bool)

    # Virtual desktop bounds fallback
    bounds = adapter.get_virtual_desktop_bounds()
    assert len(bounds) == 4
    assert bounds[2] > 0 and bounds[3] > 0


# ---------------------------------------------------------
# 3. Perception Abstraction Tests
# ---------------------------------------------------------

def test_perception_provider_interfaces():
    """Verify ScreenCaptureEngine and OCR engines implement base provider interfaces."""
    assert issubclass(ScreenCaptureEngine, ScreenCaptureProvider)
    assert isinstance(screen_capture_engine, ScreenCaptureProvider)

    assert issubclass(LocalOCREngine, OCREngineProvider)
    assert issubclass(MacOSVisionOCREngine, OCREngineProvider)

    ocr = LocalOCREngine()
    assert isinstance(ocr, OCREngineProvider)
    assert isinstance(ocr.is_available, bool)

    mac_ocr = MacOSVisionOCREngine()
    assert isinstance(mac_ocr, OCREngineProvider)
    assert isinstance(mac_ocr.is_available, bool)


# ---------------------------------------------------------
# 4. Integrations Abstraction Tests
# ---------------------------------------------------------

def test_integrations_provider_interfaces():
    """Verify application discovery and office providers implement base interfaces."""
    assert issubclass(ApplicationDiscoveryEngine, AppDiscoveryProvider)
    discovery = ApplicationDiscoveryEngine()
    assert isinstance(discovery, AppDiscoveryProvider)

    assert issubclass(OfficeCOMProvider, OfficeAutomationProvider)
    assert issubclass(MacOSOfficeAppleScriptProvider, OfficeAutomationProvider)

    com_provider = OfficeCOMProvider()
    assert isinstance(com_provider, OfficeAutomationProvider)

    applescript_provider = MacOSOfficeAppleScriptProvider()
    assert isinstance(applescript_provider, OfficeAutomationProvider)
    assert applescript_provider.provider_type.value == "office_applescript"
