"""Screen Perception Service coordinating capture, OCR, and privacy-first visual context."""

import logging
import time
import uuid
from typing import Optional, Tuple
from PIL import Image

from app.db.audit import audit_logger
from app.perception.models import (
    CapturedScreen,
    OCRResult,
    ScreenInspectRequest,
    ScreenInspectResponse,
)
from app.perception.ocr_engine import local_ocr_engine
from app.perception.screen_capture import screen_capture_engine
from app.tools.base import RiskTier

logger = logging.getLogger("jarvis.perception.service")


class ScreenPerceptionService:
    """Coordinates on-demand screen perception, OCR, and privacy boundaries."""

    def __init__(self):
        self.capture_engine = screen_capture_engine
        self.ocr_engine = local_ocr_engine

    async def inspect_screen(
        self,
        request: ScreenInspectRequest,
    ) -> ScreenInspectResponse:
        """Perform authorized on-demand screen perception.
        
        Strict Privacy Constraints:
        1. Capture is purely on-demand, never continuous.
        2. Local OCR is run entirely on-device.
        3. Image data is only encoded if user explicitly authorized external visual processing.
        4. No screen content is logged to persistent storage or audit logs.
        """
        request_id = request.request_id or f"percept-{uuid.uuid4().hex[:8]}"
        target_desc = "active window" if request.active_window_only else f"Monitor {request.monitor_id}"
        logger.info(f"[{request_id}] Starting perception inspection for {target_desc} (gemini_vision={request.authorize_gemini_vision})")

        # 1. On-Demand Capture
        t0 = time.perf_counter()
        img, screen_model = self.capture_engine.capture(
            monitor_id=request.monitor_id,
            active_window_only=request.active_window_only,
            encode_base64=request.authorize_gemini_vision,
        )
        capture_duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(f"[{request_id}] Capture completed in {capture_duration_ms:.1f}ms ({screen_model.width}x{screen_model.height})")

        # 2. Local On-Device OCR
        ocr_result: Optional[OCRResult] = None
        ocr_duration_ms = 0.0
        if request.include_ocr:
            t_ocr = time.perf_counter()
            ocr_result = await self.ocr_engine.recognize(img)
            ocr_duration_ms = round((time.perf_counter() - t_ocr) * 1000, 2)
            screen_model.ocr_result = ocr_result
            logger.info(f"[{request_id}] Local OCR completed in {ocr_duration_ms:.1f}ms ({ocr_result.word_count} words detected)")

        # Audit log the perception event with metadata only (NO pixel data or sensitive text in audit log)
        audit_logger.log(
            action_name="SCREEN_PERCEPTION_INSPECT",
            risk_tier=RiskTier.CONTROLLED if request.authorize_gemini_vision else RiskTier.READ_ONLY,
            status="SUCCESS",
            details={
                "request_id": request_id,
                "monitor_id": request.monitor_id,
                "active_window_only": request.active_window_only,
                "dimensions": f"{screen_model.width}x{screen_model.height}",
                "active_window": screen_model.active_window_title,
                "words_detected": ocr_result.word_count if ocr_result else 0,
                "capture_duration_ms": capture_duration_ms,
                "ocr_duration_ms": ocr_duration_ms,
                "gemini_vision_authorized": request.authorize_gemini_vision,
            },
        )

        message = (
            f"Screen perception completed for {screen_model.active_window_title or f'Monitor {request.monitor_id}'}. "
            f"Extracted {ocr_result.word_count if ocr_result else 0} words locally."
        )
        if request.authorize_gemini_vision:
            message += " Visual context authorized for Gemini multimodal analysis."
        else:
            message += " Image kept private on device (local OCR only)."

        return ScreenInspectResponse(
            request_id=request_id,
            screen=screen_model,
            gemini_vision_authorized=request.authorize_gemini_vision,
            message=message,
            capture_duration_ms=capture_duration_ms,
            ocr_duration_ms=ocr_duration_ms,
            stage="COMPLETED",
        )


# Singleton perception service
screen_perception_service = ScreenPerceptionService()

