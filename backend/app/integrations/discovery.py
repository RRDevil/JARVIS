"""Safe Desktop Application Discovery Engine (Phase 5.2).

Discovers installed software and currently running processes/windows via the
Windows Registry (App Paths, Uninstall), filesystem conventions, and native Win32 APIs.
"""

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import psutil
import sys

from app.automation.factory import get_platform_adapter
from app.integrations.base import AppDiscoveryProvider
from app.integrations.models import (
    ApplicationManifest,
    IntegrationHealth,
)
from app.integrations.registry import application_registry

logger = logging.getLogger("jarvis.integrations.discovery")

# Optional winreg import for Windows host environments
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    winreg = None
    HAS_WINREG = False


class ApplicationDiscoveryEngine(AppDiscoveryProvider):
    """Safe, non-invasive discovery of installed and running applications across platforms."""

    def __init__(self, registry=application_registry):
        self.registry = registry
        self._lock = threading.RLock()
        self._cached_app_paths: Dict[str, str] = {}
        self._last_scan_time: Optional[float] = None

    def _query_registry_app_paths(self) -> Dict[str, str]:
        """Query HKLM and HKCU App Paths for registered application binaries."""
        if not HAS_WINREG:
            return {}

        paths: Dict[str, str] = {}

        # 1. Scan HKEY_LOCAL_MACHINE App Paths (64-bit and 32-bit views)
        for access_flag in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ | winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                    0,
                    access_flag,
                ) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        sub_key_name = winreg.EnumKey(key, i)
                        try:
                            with winreg.OpenKey(key, sub_key_name) as sub_key:
                                raw_val, _ = winreg.QueryValueEx(sub_key, "")
                                if raw_val and isinstance(raw_val, str):
                                    cleaned = raw_val.strip(' \t\r\n"')
                                    if cleaned and Path(cleaned).exists():
                                        paths[sub_key_name.lower()] = str(Path(cleaned).resolve())
                        except Exception:
                            continue
            except Exception:
                pass

        # 2. Scan HKEY_CURRENT_USER App Paths
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                0,
                winreg.KEY_READ,
            ) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    sub_key_name = winreg.EnumKey(key, i)
                    try:
                        with winreg.OpenKey(key, sub_key_name) as sub_key:
                            raw_val, _ = winreg.QueryValueEx(sub_key, "")
                            if raw_val and isinstance(raw_val, str):
                                cleaned = raw_val.strip(' \t\r\n"')
                                if cleaned and Path(cleaned).exists():
                                    paths[sub_key_name.lower()] = str(Path(cleaned).resolve())
                    except Exception:
                        continue
        except Exception:
            pass

        return paths

    def _scan_macos_applications(self) -> Dict[str, str]:
        """Scan macOS application directories for .app bundles."""
        paths: Dict[str, str] = {}
        for search_dir in ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]:
            p = Path(search_dir)
            if not p.exists():
                continue
            try:
                for item in p.glob("*.app"):
                    name = item.stem.lower()
                    paths[name] = str(item.resolve())
            except Exception:
                continue
        return paths

    def scan_installed_applications(self) -> Dict[str, str]:
        """Fulfill AppDiscoveryProvider contract."""
        if sys.platform == "darwin":
            return self._scan_macos_applications()
        return self._query_registry_app_paths()

    def resolve_app_path(self, app_name: str) -> Optional[str]:
        """Resolve application executable or bundle path."""
        lower_name = app_name.lower()
        if sys.platform == "darwin":
            mac_paths = self._scan_macos_applications()
            if lower_name in mac_paths:
                return mac_paths[lower_name]
            for name, path in mac_paths.items():
                if lower_name in name:
                    return path
            return None

        # Windows
        if not self._cached_app_paths:
            self._cached_app_paths = self._query_registry_app_paths()
        for key, path in self._cached_app_paths.items():
            if lower_name in key:
                return path
        return None

    def _resolve_executable_path(self, manifest: ApplicationManifest, app_paths: Dict[str, str]) -> Optional[str]:
        """Locate verified physical binary on the host filesystem."""
        rule = manifest.process_rule

        # Check macOS bundle matching
        if sys.platform == "darwin":
            for name, bundle_path in app_paths.items():
                if manifest.app_id.lower() in name or manifest.display_name.lower() in name:
                    return bundle_path

        # Check App Paths registry keys first
        for key_name in rule.registry_app_paths_keys:
            val = app_paths.get(key_name.lower())
            if val and Path(val).exists():
                return val

        # Check common filesystem installation locations
        for common in rule.common_install_paths:
            expanded = os.path.expandvars(common)
            if Path(expanded).exists():
                return str(Path(expanded).resolve())

        # Check system PATH via shutil.which
        for exe in rule.executable_names:
            resolved = shutil.which(exe)
            if resolved and Path(resolved).exists():
                return str(Path(resolved).resolve())

        return None

    def scan_installed(self) -> List[ApplicationManifest]:
        """Scan system registries and filesystem to detect installed applications."""
        with self._lock:
            if sys.platform == "darwin":
                app_paths = self._scan_macos_applications()
            else:
                app_paths = self._query_registry_app_paths()
            self._cached_app_paths = app_paths
            manifests = self.registry.list_all()

            for manifest in manifests:
                exe_path = self._resolve_executable_path(manifest, app_paths)
                if exe_path:
                    manifest.is_installed = True
                    manifest.installed_path = exe_path
                    manifest.health_status = IntegrationHealth.HEALTHY
                else:
                    manifest.is_installed = False
                    manifest.installed_path = None
                    manifest.health_status = IntegrationHealth.NOT_INSTALLED

                self.registry.register(manifest)

            return manifests

    def scan_running(self) -> List[ApplicationManifest]:
        """Detect active processes and desktop window handles belonging to registered apps."""
        with self._lock:
            manifests = self.registry.list_all()

            # 1. Enumerate active desktop windows via platform adapter
            adapter = get_platform_adapter()
            visible_windows = adapter.list_windows() if adapter else []

            # 2. Enumerate running processes via psutil safely
            running_processes: List[Tuple[int, str]] = []
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        p_name = proc.info["name"]
                        if p_name:
                            running_processes.append((proc.info["pid"], p_name.lower()))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception as exc:
                logger.debug(f"Process iteration note: {exc}")

            # 3. Match running processes and windows to manifests
            for manifest in manifests:
                rule = manifest.process_rule
                target_exes = {e.lower() for e in rule.executable_names}
                title_patterns = [p.lower() for p in rule.window_title_patterns]

                matched_pids: Set[int] = set()
                matched_hwnds: Set[int] = set()

                # Process matching
                for pid, p_name in running_processes:
                    if p_name in target_exes or any(exe in p_name for exe in target_exes):
                        matched_pids.add(pid)

                # Window matching
                for win in visible_windows:
                    win_proc = (win.process_name or "").lower()
                    win_title = (win.title or "").lower()

                    matches_exe = any(exe in win_proc for exe in target_exes) if win_proc else False
                    matches_title = any(pat in win_title for pat in title_patterns) if title_patterns else False

                    if matches_exe or matches_title:
                        matched_hwnds.add(win.handle)
                        if win.process_id:
                            matched_pids.add(win.process_id)

                manifest.running_pids = sorted(list(matched_pids))
                manifest.running_window_handles = sorted(list(matched_hwnds))
                manifest.is_running = len(matched_pids) > 0 or len(matched_hwnds) > 0

                # Health state adjustment
                if manifest.is_running:
                    manifest.health_status = IntegrationHealth.HEALTHY
                elif manifest.is_installed:
                    manifest.health_status = IntegrationHealth.HEALTHY

                self.registry.register(manifest)

            return manifests

    def discover_all(self, refresh_installed: bool = True) -> List[ApplicationManifest]:
        """Perform comprehensive application discovery (installed + running)."""
        with self._lock:
            if refresh_installed or not self._cached_app_paths:
                self.scan_installed()
            return self.scan_running()


# Global singleton instance
application_discovery_engine = ApplicationDiscoveryEngine()
