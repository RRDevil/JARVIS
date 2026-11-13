"""Registered tools for Windows screen perception and local OCR (Phase 4)."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.perception.models import ScreenInspectRequest
from app.perception.service import screen_perception_service
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class ScreenCaptureParams(BaseModel):
    """Parameters for capturing on-demand desktop or window state."""

    monitor_id: int = Field(
        1,
        description="Monitor index to capture (0 for virtual all-monitors desktop, 1 for primary display).",
    )
    active_window_only: bool = Field(
        False,
        description="If True, captures only the currently focused active application window.",
    )


class WindowsCaptureScreenTool(BaseTool):
    """Tool to capture screen state on demand to inspect open desktop applications."""

    name = "windows_capture_screen"
    description = "Capture screen state or active window on demand to inspect open applications and visible UI."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = ScreenCaptureParams

    async def execute(self, params: ScreenCaptureParams, context: ExecutionContext) -> ToolResult:
        try:
            req = ScreenInspectRequest(
                monitor_id=params.monitor_id,
                active_window_only=params.active_window_only,
                include_ocr=True,
                authorize_gemini_vision=False,  # Kept strictly local unless user explicit multimodal request
            )
            response = await screen_perception_service.inspect_screen(req)
            data = {
                "monitor_id": response.screen.monitor_id,
                "width": response.screen.width,
                "height": response.screen.height,
                "captured_at": response.screen.captured_at,
                "active_window_title": response.screen.active_window_title,
                "crop_region": response.screen.crop_region.model_dump() if response.screen.crop_region else None,
                "text_detected": response.screen.ocr_result.full_text if response.screen.ocr_result else "",
                "word_count": response.screen.ocr_result.word_count if response.screen.ocr_result else 0,
            }
            return ToolResult(
                success=True,
                data=data,
                verified=bool(data["width"] > 0),
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Screen capture failed: {str(exc)}",
                error_code="CAPTURE_FAILED",
                verified=False,
            )

    async def verify(self, params: ScreenCaptureParams, result: ToolResult, context: ExecutionContext) -> bool:
        return result.success and bool(result.data and result.data.get("width", 0) > 0)


class WindowsReadScreenTextTool(BaseTool):
    """Tool to read visible text on screen using local Windows OCR without cloud uploads."""

    name = "windows_read_screen_text"
    description = "Read and extract all visible text on the user's screen or active window using local on-device OCR."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = ScreenCaptureParams

    async def execute(self, params: ScreenCaptureParams, context: ExecutionContext) -> ToolResult:
        try:
            req = ScreenInspectRequest(
                monitor_id=params.monitor_id,
                active_window_only=params.active_window_only,
                include_ocr=True,
                authorize_gemini_vision=False,
            )
            response = await screen_perception_service.inspect_screen(req)
            ocr = response.screen.ocr_result
            data = {
                "active_window": response.screen.active_window_title,
                "monitor_id": response.screen.monitor_id,
                "full_text": ocr.full_text if ocr else "",
                "lines_count": ocr.line_count if ocr else 0,
                "words_count": ocr.word_count if ocr else 0,
                "ocr_duration_ms": ocr.duration_ms if ocr else 0.0,
            }
            return ToolResult(
                success=True,
                data=data,
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Local OCR text extraction failed: {str(exc)}",
                error_code="OCR_FAILED",
                verified=False,
            )

    async def verify(self, params: ScreenCaptureParams, result: ToolResult, context: ExecutionContext) -> bool:
        return result.success
