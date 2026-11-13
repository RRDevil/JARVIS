"""Tests for configuration settings and security boundaries."""

from pathlib import Path
from app.core.config import Settings


def test_settings_default_values():
    """Verify default security and networking boundaries."""
    config = Settings()
    # Security invariants: loopback host by default
    assert config.JARVIS_HOST in ("127.0.0.1", "localhost")
    assert config.JARVIS_PORT == 8000
    assert isinstance(config.JARVIS_ALLOWED_ORIGINS, list)
    assert "tauri://localhost" in config.JARVIS_ALLOWED_ORIGINS


def test_workspace_directory_resolution(tmp_path):
    """Verify workspace path creation and canonical resolution."""
    custom_ws = tmp_path / "jarvis_custom_ws"
    config = Settings(JARVIS_WORKSPACE_ROOT=str(custom_ws))
    ws_path = config.workspace_path
    assert ws_path.exists()
    assert ws_path.is_dir()
    assert ws_path == custom_ws.resolve()

