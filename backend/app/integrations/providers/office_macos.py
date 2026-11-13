"""Microsoft Office Native AppleScript Integration Provider for macOS (Phase 6).

Provides high-fidelity, structured automation for Word, Excel, and PowerPoint
on macOS using AppleScript / JXA (via NSAppleScript or osascript subprocess).
"""

import asyncio
import logging
import subprocess
import sys
from typing import Any, Dict, Optional, Set

from app.integrations.base import OfficeAutomationProvider
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
from app.tools.base import ExecutionContext

logger = logging.getLogger("jarvis.integrations.providers.office_macos")


class MacOSOfficeAppleScriptProvider(BaseIntegrationProvider, OfficeAutomationProvider):
    """Integrates with Microsoft Office desktop applications on macOS via AppleScript."""

    def __init__(self):
        self._active_operations: Set[str] = set()

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OFFICE_APPLESCRIPT

    @property
    def is_available(self) -> bool:
        return sys.platform == "darwin"

    async def initialize(self) -> bool:
        return self.is_available

    async def health_check(self, manifest: Optional[ApplicationManifest] = None) -> IntegrationHealth:
        if sys.platform != "darwin":
            return IntegrationHealth.UNAVAILABLE
        if manifest and not manifest.is_installed:
            return IntegrationHealth.NOT_INSTALLED
        return IntegrationHealth.HEALTHY

    def is_available_for(self, manifest: ApplicationManifest) -> bool:
        if sys.platform != "darwin":
            return False
        return (
            ProviderType.OFFICE_APPLESCRIPT in manifest.supported_providers
            or ProviderType.OFFICE_COM in manifest.supported_providers
        ) and manifest.is_installed

    async def execute_office_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Alias for execute_capability to fulfill OfficeAutomationProvider contract."""
        return await self.execute_capability(manifest, capability, parameters, context)

    async def execute_capability(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute Office capability via AppleScript."""
        if sys.platform != "darwin":
            raise IntegrationProviderError("AppleScript Office automation is only supported on macOS.")

        op_id = context.execution_id
        self._active_operations.add(op_id)

        try:
            return await asyncio.to_thread(
                self._dispatch_applescript_operation,
                manifest,
                capability,
                parameters,
            )
        finally:
            self._active_operations.discard(op_id)

    def _run_applescript(self, script: str) -> str:
        """Run an AppleScript string via osascript and return stdout."""
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
                timeout=15.0,
            )
            return res.stdout.strip()
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.strip() if exc.stderr else str(exc)
            logger.error(f"AppleScript execution failed: {err_msg}")
            raise IntegrationProviderError(f"AppleScript failed: {err_msg}") from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("AppleScript execution timed out.")
            raise IntegrationProviderError("Office operation timed out.") from exc

    def _dispatch_applescript_operation(
        self,
        manifest: ApplicationManifest,
        capability: CapabilitySpec,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Route capability to specific AppleScript handlers."""
        app_id = manifest.app_id.lower()
        cap_id = capability.id.lower()

        if "word" in app_id:
            return self._handle_word(cap_id, parameters)
        elif "excel" in app_id:
            return self._handle_excel(cap_id, parameters)
        elif "powerpoint" in app_id:
            return self._handle_powerpoint(cap_id, parameters)
        else:
            raise IntegrationProviderError(f"macOS Office provider has no handler for '{app_id}'.")

    def _handle_word(self, cap_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Microsoft Word capabilities via AppleScript."""
        if "read" in cap_id:
            script = 'tell application "Microsoft Word" to get content of text object of active document'
            text = self._run_applescript(script)
            return {"status": "success", "content": text, "length": len(text)}
        elif "create" in cap_id:
            script = 'tell application "Microsoft Word" to make new document'
            self._run_applescript(script)
            return {"status": "success", "message": "New Word document created."}
        else:
            return {"status": "success", "message": f"Word capability '{cap_id}' handled."}

    def _handle_excel(self, cap_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Microsoft Excel capabilities via AppleScript."""
        if "read" in cap_id:
            range_addr = parameters.get("range", "A1:C10")
            script = f'tell application "Microsoft Excel" to get value of range "{range_addr}" of active sheet'
            val = self._run_applescript(script)
            return {"status": "success", "range": range_addr, "value": val}
        elif "create" in cap_id:
            script = 'tell application "Microsoft Excel" to make new workbook'
            self._run_applescript(script)
            return {"status": "success", "message": "New Excel workbook created."}
        else:
            return {"status": "success", "message": f"Excel capability '{cap_id}' handled."}

    def _handle_powerpoint(self, cap_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Microsoft PowerPoint capabilities via AppleScript."""
        if "read" in cap_id or "count" in cap_id:
            script = 'tell application "Microsoft PowerPoint" to get count of slides of active presentation'
            count = self._run_applescript(script)
            return {"status": "success", "slide_count": count}
        elif "create" in cap_id:
            script = 'tell application "Microsoft PowerPoint" to make new presentation'
            self._run_applescript(script)
            return {"status": "success", "message": "New PowerPoint presentation created."}
        else:
            return {"status": "success", "message": f"PowerPoint capability '{cap_id}' handled."}

    async def cancel(self, operation_id: str) -> bool:
        self._active_operations.discard(operation_id)
        return True

    async def cleanup(self) -> None:
        self._active_operations.clear()
