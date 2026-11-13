"""J.A.R.V.I.S. Core Platform Detection and Unified Path Resolution Module.

Provides cross-platform operating system identification and standard filesystem
path resolution adhering to OS conventions (Windows AppData vs macOS Library vs Linux XDG).
"""

from enum import Enum
import os
from pathlib import Path
import sys
from typing import Optional


class PlatformType(str, Enum):
    """Supported desktop operating system platforms."""
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"
    UNKNOWN = "unknown"


def get_current_platform() -> PlatformType:
    """Return the current operating system as a PlatformType enum."""
    if sys.platform == "win32":
        return PlatformType.WINDOWS
    elif sys.platform == "darwin":
        return PlatformType.MACOS
    elif sys.platform.startswith("linux"):
        return PlatformType.LINUX
    return PlatformType.UNKNOWN


def is_windows() -> bool:
    """Check if the current host environment is Windows."""
    return sys.platform == "win32"


def is_macos() -> bool:
    """Check if the current host environment is macOS."""
    return sys.platform == "darwin"


def is_linux() -> bool:
    """Check if the current host environment is Linux."""
    return sys.platform.startswith("linux")


def get_user_data_dir(app_name: str = "JARVIS") -> Path:
    """Resolve the standardized persistent application data directory.

    Windows: %LOCALAPPDATA%/{app_name} or ~/.AppData/Local/{app_name}
    macOS: ~/Library/Application Support/{app_name}
    Linux: $XDG_DATA_HOME/{app_name} or ~/.local/share/{app_name}
    """
    home = Path.home()
    if is_windows():
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
    elif is_macos():
        base = home / "Library" / "Application Support"
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else home / ".local" / "share"

    data_dir = base / app_name
    return data_dir


def get_logs_dir(app_name: str = "JARVIS") -> Path:
    """Resolve the standardized application logs directory.

    Windows: %LOCALAPPDATA%/{app_name}/logs
    macOS: ~/Library/Logs/{app_name}
    Linux: $XDG_STATE_HOME/{app_name}/logs or ~/.local/state/{app_name}/logs
    """
    home = Path.home()
    if is_windows():
        base = get_user_data_dir(app_name) / "logs"
    elif is_macos():
        base = home / "Library" / "Logs" / app_name
    else:
        xdg_state = os.environ.get("XDG_STATE_HOME")
        base = (Path(xdg_state) if xdg_state else home / ".local" / "state") / app_name / "logs"

    return base


def get_cache_dir(app_name: str = "JARVIS") -> Path:
    """Resolve the standardized application cache directory.

    Windows: %LOCALAPPDATA%/{app_name}/cache
    macOS: ~/Library/Caches/{app_name}
    Linux: $XDG_CACHE_HOME/{app_name} or ~/.cache/{app_name}
    """
    home = Path.home()
    if is_windows():
        base = get_user_data_dir(app_name) / "cache"
    elif is_macos():
        base = home / "Library" / "Caches" / app_name
    else:
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        base = (Path(xdg_cache) if xdg_cache else home / ".cache") / app_name

    return base


def get_models_dir(app_name: str = "JARVIS") -> Path:
    """Resolve the directory for large external models (TTS, STT, ONNX, CTranslate2).

    If JARVIS_MODELS_DIR environment variable is defined, use it directly.
    Otherwise, default to a 'models' folder within the standardized user data directory.
    """
    env_models_dir = os.environ.get("JARVIS_MODELS_DIR")
    if env_models_dir and env_models_dir.strip():
        return Path(env_models_dir.strip()).expanduser()

    return get_user_data_dir(app_name) / "models"
