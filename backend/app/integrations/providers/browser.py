"""Browser Automation Integration Provider (Phase 5.2).

Provides dedicated, independent automation profiles for Opera GX and Google Chrome
with process awareness, URL navigation, tab management, and strict privacy boundaries.
"""

import asyncio
import logging
import subprocess
from typing import Any, Dict, Optional, Set

from app.automation.factory import get_platform_adapter
from app.integrations.models import (
    ApplicationManifest,
    CapabilitySpec,
    IntegrationHealth,
    ProviderType,
)
from app.integrations.providers.base import (
    BaseIntegrationProvider,
    IntegrationProviderError,
)
from app.perception.models import ScreenInspectRequest
from app.perception.service import screen_perception_service
from app.tools.base import ExecutionContext

logger = logging.getLogger("jarvis.integrations.providers.browser")


class BrowserAutomationProvider(BaseIntegrationProvider):
    """Services Chromium-based browsers (Opera GX, Google Chrome) with independent profiles."""

    def __init__(self):
        self._active_operations: Set[str] = set()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.BROWSER_AUTOMATION

    async def initialize(self) -> bool:
        return True

    async def health_check(self, manifest: Optional[ApplicationManifest] = None) -> IntegrationHealth:
        if manifest and not manifest.is_installed:
            return IntegrationHealth.NOT_INSTALLED
        return IntegrationHealth.HEALTHY

    def is_available_for(self, manifest: ApplicationManifest) -> bool:
        return ProviderType.BROWSER_AUTOMATION in manifest.supported_providers and manifest.is_installed

    async def execute_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute browser capability conforming to strict privacy and safety rules."""
        op_id = context.execution_id
        self._active_operations.add(op_id)
        adapter = get_platform_adapter()

        try:
            cap_id = capability.id.lower()

            # 1. Resolve Target Browser Window
            target_hwnd = parameters.get("window_handle")
            if not target_hwnd:
                windows = adapter.list_windows()
                for win in windows:
                    w_proc = (win.process_name or "").lower()
                    w_title = (win.title or "").lower()
                    if any(exe.lower() in w_proc for exe in manifest.process_rule.executable_names):
                        target_hwnd = win.handle
                        break
                    if any(pat.lower() in w_title for pat in manifest.process_rule.window_title_patterns):
                        target_hwnd = win.handle
                        break

            # --- Capability: browser.navigate ---
            if "navigate" in cap_id:
                url = parameters.get("url") or parameters.get("query")
                if not url:
                    raise IntegrationProviderError("Navigation requires 'url' or 'query' parameter.")

                # If query is plain search keywords, format search query
                if not url.startswith("http://") and not url.startswith("https://"):
                    if "." in url and " " not in url:
                        url = f"https://{url}"
                    else:
                        import urllib.parse
                        url = f"https://www.google.com/search?q={urllib.parse.quote(url)}"

                # Launch or open URL in target browser
                exe_path = manifest.installed_path or manifest.process_rule.executable_names[0]
                subprocess.Popen(
                    [exe_path, url],
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await asyncio.sleep(1.0)

                return {
                    "action": "browser_navigate",
                    "app_id": manifest.app_id,
                    "target_url": url,
                    "browser": manifest.display_name,
                    "status": "navigated",
                }

            # --- Capability: browser.read_page ---
            elif "read_page" in cap_id:
                if target_hwnd:
                    adapter.restore_and_focus_window(target_hwnd)
                    await asyncio.sleep(0.15)

                # Capture active page state with OCR
                inspect_resp = await screen_perception_service.inspect_screen(
                    ScreenInspectRequest(
                        active_window_only=bool(target_hwnd),
                        include_ocr=True,
                        authorize_gemini_vision=False,
                    )
                )

                page_title = inspect_resp.screen.active_window_title or manifest.display_name
                raw_text = inspect_resp.screen.ocr_result.full_text if inspect_resp.screen.ocr_result else ""

                # Wrap in explicit Untrusted Content envelope to protect against prompt injection
                return {
                    "action": "browser_read_page",
                    "app_id": manifest.app_id,
                    "page_title": page_title,
                    "browser": manifest.display_name,
                    "window_handle": target_hwnd,
                    "data_envelope": {
                        "data_type": "untrusted_content",
                        "source": f"browser_{manifest.app_id}",
                        "page_title": page_title,
                        "text": raw_text[:6000],  # Bounded page extract
                    },
                    "privacy_notice": "Passwords and session cookies were not inspected or extracted.",
                }

            # --- Capability: browser.manage_tabs ---
            elif "manage_tabs" in cap_id:
                action = parameters.get("action", "new_tab").lower()
                if not target_hwnd:
                    raise IntegrationProviderError(f"No active {manifest.display_name} window found to manage tabs.")

                adapter.restore_and_focus_window(target_hwnd)
                await asyncio.sleep(0.08)

                if action in ("new", "new_tab", "create"):
                    adapter.send_shortcut(target_hwnd, "ctrl+t")
                    msg = "Created new browser tab."
                elif action in ("close", "close_tab"):
                    adapter.send_shortcut(target_hwnd, "ctrl+w")
                    msg = "Closed active browser tab."
                elif action in ("next", "next_tab"):
                    adapter.send_shortcut(target_hwnd, "ctrl+tab")
                    msg = "Switched to next browser tab."
                elif action in ("previous", "prev", "prev_tab"):
                    adapter.send_shortcut(target_hwnd, "ctrl+shift+tab")
                    msg = "Switched to previous browser tab."
                else:
                    raise IntegrationProviderError(f"Unknown tab action '{action}'.")

                return {
                    "action": "browser_manage_tabs",
                    "app_id": manifest.app_id,
                    "tab_action": action,
                    "message": msg,
                    "window_handle": target_hwnd,
                }

            # --- Capability: browser.submit_form ---
            elif "submit_form" in cap_id:
                if not target_hwnd:
                    raise IntegrationProviderError(f"No active {manifest.display_name} window found to submit form.")

                adapter.restore_and_focus_window(target_hwnd)
                await asyncio.sleep(0.08)
                adapter.type_text(text="", target_hwnd=target_hwnd, press_enter=True)

                return {
                    "action": "browser_submit_form",
                    "app_id": manifest.app_id,
                    "status": "submitted",
                    "window_handle": target_hwnd,
                }

            raise IntegrationProviderError(f"Unsupported browser capability '{cap_id}'.")

        finally:
            self._active_operations.discard(op_id)

    async def cancel(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            self._active_operations.discard(operation_id)
            return True
        return False

    async def cleanup(self) -> None:
        self._active_operations.clear()
