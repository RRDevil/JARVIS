"""API endpoints for Windows Screen Perception, Local OCR, and Multi-Monitor Management."""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.security import verify_secret_token
from app.perception.grounding import grounding_engine
from app.perception.models import (
    LocateElementsRequest,
    LocateElementsResponse,
    MonitorInfo,
    OCRResult,
    RecordingClipInfo,
    RecordingStartRequest,
    RecordingStatus,
    ScreenInspectRequest,
    ScreenInspectResponse,
)
from app.perception.recording import screen_recording_service
from app.perception.screen_capture import MonitorNotFoundError, ScreenCaptureError, screen_capture_engine
from app.perception.service import screen_perception_service

router = APIRouter(prefix="/v1/screen", tags=["Screen Perception & Vision"])


@router.get(
    "/monitors",
    response_model=List[MonitorInfo],
    summary="List available desktop display monitors",
)
def list_monitors(
    _authorized: bool = Depends(verify_secret_token),
) -> List[MonitorInfo]:
    """Enumerate connected physical displays and the combined virtual desktop."""
    try:
        return screen_capture_engine.list_monitors()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enumerate system monitors: {str(exc)}",
        )


@router.post(
    "/inspect",
    response_model=ScreenInspectResponse,
    summary="Perform authorized on-demand screen inspection",
)
async def inspect_screen(
    payload: ScreenInspectRequest,
    request: Request,
    response: Response,
    _authorized: bool = Depends(verify_secret_token),
) -> ScreenInspectResponse:
    """Capture screen or active window on-demand with local OCR and optional Gemini visual context.
    
    Privacy Enforcement:
    - Never runs in the background.
    - Local OCR is executed on-device.
    - Image base64 encoding only occurs if `authorize_gemini_vision` is explicitly True.
    """
    req_id = payload.request_id or request.headers.get("X-Request-Id") or f"percept-{uuid.uuid4().hex[:8]}"
    payload.request_id = req_id

    try:
        res = await screen_perception_service.inspect_screen(payload)
        response.headers["X-Request-Id"] = req_id
        return res
    except MonitorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except ScreenCaptureError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Screen perception error: {str(exc)}",
        )


@router.post(
    "/ocr",
    response_model=OCRResult,
    summary="Run local OCR directly on screen or active window",
)
async def run_screen_ocr(
    payload: ScreenInspectRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> OCRResult:
    """Run local on-device OCR without external cloud transmission."""
    try:
        payload.include_ocr = True
        payload.authorize_gemini_vision = False  # Strictly local
        response = await screen_perception_service.inspect_screen(payload)
        return response.screen.ocr_result or OCRResult()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Local OCR failed: {str(exc)}",
        )


# --- Phase 5: UI Element Grounding & Bounded Recording Endpoints ---

@router.post(
    "/elements/locate",
    response_model=LocateElementsResponse,
    summary="Locate and ground interactive UI elements on the screen",
)
async def locate_elements(
    payload: LocateElementsRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> LocateElementsResponse:
    """Discover, ground, and filter interactive UI elements from current desktop state."""
    try:
        return await grounding_engine.locate_elements(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Element localization fault: {str(exc)}",
        )


@router.post(
    "/record/start",
    response_model=RecordingStatus,
    summary="Start a bounded debugging screen recording clip",
)
async def start_screen_recording(
    payload: RecordingStartRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> RecordingStatus:
    """Begin bounded local screen recording (max 30s) without cloud uploads."""
    try:
        return await screen_recording_service.start_recording(payload)
    except RuntimeError as rerr:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(rerr),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start screen recording: {str(exc)}",
        )


@router.post(
    "/record/stop",
    response_model=Optional[RecordingClipInfo],
    summary="Halt screen recording and export local debugging clip",
)
async def stop_screen_recording(
    _authorized: bool = Depends(verify_secret_token),
) -> Optional[RecordingClipInfo]:
    """Halt active recording and export animated GIF clip."""
    try:
        return await screen_recording_service.stop_recording()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to finalize screen recording: {str(exc)}",
        )


@router.get(
    "/record/status",
    response_model=RecordingStatus,
    summary="Check current screen recorder status",
)
def get_screen_recording_status(
    _authorized: bool = Depends(verify_secret_token),
) -> RecordingStatus:
    """Get active recording status, frames, and elapsed time."""
    return screen_recording_service.get_status()


@router.get(
    "/record/clips",
    response_model=List[RecordingClipInfo],
    summary="List exported local debugging clips",
)
def list_screen_recording_clips(
    _authorized: bool = Depends(verify_secret_token),
) -> List[RecordingClipInfo]:
    """List previously exported debugging clips on disk."""
    return screen_recording_service.list_clips()


