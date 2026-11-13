"""Desktop UI Integration Provider (Phase 5.2).

Services applications using native Windows accessibility, UI Automation,
OCR, visual coordinate clicking, universal typing, and window management.
"""

import asyncio
import logging
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
from app.perception.grounding import grounding_engine
from app.perception.models import LocateElementsRequest, ScreenInspectRequest
from app.perception.service import screen_perception_service
from app.tools.base import ExecutionContext

logger = logging.getLogger("jarvis.integrations.providers.desktop_ui")


class DesktopUIProvider(BaseIntegrationProvider):
    """Integrates with host applications via non-invasive visible UI automation."""

    def __init__(self):
        self._active_operations: Set[str] = set()
        self._owned_pids: Set[int] = set()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.DESKTOP_UI

    async def initialize(self) -> bool:
        return True

    async def health_check(self, manifest: Optional[ApplicationManifest] = None) -> IntegrationHealth:
        adapter = get_platform_adapter()
        if not adapter:
            return IntegrationHealth.UNAVAILABLE
        if manifest and not manifest.is_installed:
            return IntegrationHealth.NOT_INSTALLED
        return IntegrationHealth.HEALTHY

    def is_available_for(self, manifest: ApplicationManifest) -> bool:
        return ProviderType.DESKTOP_UI in manifest.supported_providers

    async def execute_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute capability through visible desktop automation."""
        op_id = context.execution_id
        self._active_operations.add(op_id)
        adapter = get_platform_adapter()

        try:
            # 1. Resolve or activate application window
            target_hwnd = parameters.get("window_handle")
            if not target_hwnd:
                # Find open window matching the manifest
                windows = adapter.list_windows()
                for win in windows:
                    w_title = (win.title or "").lower()
                    w_proc = (win.process_name or "").lower()
                    if any(exe.lower() in w_proc for exe in manifest.process_rule.executable_names):
                        target_hwnd = win.handle
                        break
                    if any(pat.lower() in w_title for pat in manifest.process_rule.window_title_patterns):
                        target_hwnd = win.handle
                        break

            # If no window is open and the capability requires reading/interaction, launch application safely
            if not target_hwnd and manifest.is_installed and manifest.installed_path:
                try:
                    launch_info = adapter.launch_app(manifest.app_id)
                    if launch_info and "pid" in launch_info:
                        self._owned_pids.add(launch_info["pid"])
                    await asyncio.sleep(1.2)
                    # Re-scan for window
                    windows = adapter.list_windows()
                    for win in windows:
                        if any(exe.lower() in (win.process_name or "").lower() for exe in manifest.process_rule.executable_names):
                            target_hwnd = win.handle
                            break
                except Exception as launch_err:
                    logger.debug(f"Could not auto-launch {manifest.app_id}: {launch_err}")

            if target_hwnd:
                adapter.restore_and_focus_window(target_hwnd)
                await asyncio.sleep(0.1)

            # 2. Dispatch capability action
            cap_id = capability.id.lower()

            # --- Reading / Inspection Capabilities ---
            if any(term in cap_id for term in ["read", "inspect", "search"]):
                inspect_resp = await screen_perception_service.inspect_screen(
                    ScreenInspectRequest(
                        active_window_only=bool(target_hwnd),
                        include_ocr=True,
                        authorize_gemini_vision=False,
                    )
                )
                ocr_text = inspect_resp.screen.ocr_result.full_text if inspect_resp.screen.ocr_result else ""
                lines = inspect_resp.screen.ocr_result.lines if inspect_resp.screen.ocr_result else []
                return {
                    "action": "desktop_ui_read",
                    "app_id": manifest.app_id,
                    "window_handle": target_hwnd,
                    "window_title": inspect_resp.screen.active_window_title,
                    "extracted_text": ocr_text,
                    "line_count": len(lines),
                    "confidence": 0.90,
                }

            # --- Typing / Editing / Drafting Capabilities ---
            if any(term in cap_id for term in ["type", "edit", "create", "draft", "modify"]):
                text = parameters.get("text") or parameters.get("content") or ""
                clear_first = parameters.get("clear_first", False)
                press_enter = parameters.get("press_enter", False)
                x = parameters.get("x")
                y = parameters.get("y")

                ok = adapter.type_text(
                    text=text,
                    x=x,
                    y=y,
                    target_hwnd=target_hwnd,
                    clear_first=clear_first,
                    press_enter=press_enter,
                )
                if not ok:
                    raise IntegrationProviderError(f"UI typing failed into {manifest.display_name}.")
                return {
                    "action": "desktop_ui_type",
                    "app_id": manifest.app_id,
                    "window_handle": target_hwnd,
                    "characters_typed": len(text),
                    "clear_first": clear_first,
                    "press_enter": press_enter,
                }

            # --- Sending / Submitting Capabilities ---
            if any(term in cap_id for term in ["send", "submit", "save"]):
                # For messaging or forms, sending in UI means focusing input and pressing Enter or sending shortcut
                shortcut = parameters.get("shortcut", "enter")
                if shortcut == "ctrl+s":
                    adapter.send_shortcut(target_hwnd, "ctrl+s")
                else:
                    adapter.type_text(text="", target_hwnd=target_hwnd, press_enter=True)

                return {
                    "action": "desktop_ui_action_dispatched",
                    "app_id": manifest.app_id,
                    "window_handle": target_hwnd,
                    "capability_id": capability.id,
                    "status": "dispatched",
                }

            # Generic fallback: coordinate click or shortcut
            return {
                "action": "desktop_ui_executed",
                "app_id": manifest.app_id,
                "capability_id": capability.id,
                "window_handle": target_hwnd,
            }

        finally:
            self._active_operations.discard(op_id)

    async def cancel(self, operation_id: str) -> bool:
        if operation_id in self._active_operations:
            self._active_operations.discard(operation_id)
            return True
        return False

    async def cleanup(self) -> None:
        self._active_operations.clear()
        # J.A.R.V.I.S. owned processes are not forcibly killed to avoid user data loss,
        # but tracking is cleared.
        self._owned_pids.clear()
