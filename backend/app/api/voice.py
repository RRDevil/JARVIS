"""
FastAPI router for J.A.R.V.I.S. Voice Interaction Subsystem (STT, TTS, Profiles & Providers).
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.security import verify_secret_token
from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TranscriptionResponse,
    VoiceStatusResponse,
    STTModelChangeRequest,
    TTSProviderInfo,
    VoiceProfile,
    VoiceProfileCreate,
    VoiceProfileUpdate,
    VoicePreviewRequest,
    VoicepackInfo,
    VoicepackImportResponse,
    ModelsStorageStatusResponse,
    ConfigureModelsPathRequest,
    ImportModelPathRequest,
)
from app.voice.service import voice_service

router = APIRouter(prefix="/v1/voice", tags=["Voice Interaction"])


class SetActiveProfileRequest(BaseModel):
    profile_id: str = Field(..., description="ID of the profile to activate.")


# --- Subsystem Telemetry & Discovery ---

@router.get(
    "/status",
    response_model=VoiceStatusResponse,
    summary="Get status and telemetry of voice subsystem",
)
def get_voice_status(
    _authorized: bool = Depends(verify_secret_token),
) -> VoiceStatusResponse:
    """Retrieve operational status, active STT/TTS providers, active profile, and voice count."""
    return voice_service.get_status()


@router.get(
    "/providers",
    response_model=List[TTSProviderInfo],
    summary="Enumerate registered TTS engines and their capabilities",
)
def list_providers(
    _authorized: bool = Depends(verify_secret_token),
) -> List[TTSProviderInfo]:
    """Retrieve all registered speech synthesis providers and readiness states."""
    return voice_service.list_providers()


@router.get(
    "/voices",
    response_model=List[VoiceInfo],
    summary="Enumerate available TTS voices across all engines",
)
def list_voices(
    _authorized: bool = Depends(verify_secret_token),
) -> List[VoiceInfo]:
    """Retrieve installed voices available for speech synthesis."""
    return voice_service.list_voices()


# --- Voice Profiles CRUD ---

@router.get(
    "/profiles",
    response_model=List[VoiceProfile],
    summary="List all persistent voice profiles",
)
def list_profiles(
    _authorized: bool = Depends(verify_secret_token),
) -> List[VoiceProfile]:
    """Retrieve all user and system voice profiles."""
    return voice_service.list_profiles()


@router.get(
    "/profiles/active",
    response_model=VoiceProfile,
    summary="Get currently active voice profile",
)
def get_active_profile(
    _authorized: bool = Depends(verify_secret_token),
) -> VoiceProfile:
    """Retrieve the voice profile currently applied to spoken responses."""
    return voice_service.get_active_profile()


@router.post(
    "/profiles/active",
    response_model=VoiceProfile,
    summary="Switch active voice profile",
)
def set_active_profile(
    request: SetActiveProfileRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> VoiceProfile:
    """Select the voice profile to use as active default."""
    try:
        return voice_service.set_active_profile(request.profile_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/profiles",
    response_model=VoiceProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new voice profile",
)
def create_profile(
    request: VoiceProfileCreate,
    _authorized: bool = Depends(verify_secret_token),
) -> VoiceProfile:
    """Create and persist a new custom voice profile."""
    try:
        return voice_service.create_profile(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/profiles/{profile_id}",
    response_model=VoiceProfile,
    summary="Update an existing voice profile",
)
def update_profile(
    profile_id: str,
    request: VoiceProfileUpdate,
    _authorized: bool = Depends(verify_secret_token),
) -> VoiceProfile:
    """Update name, rate, volume, pitch or parameters of an existing profile."""
    try:
        return voice_service.update_profile(profile_id, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.delete(
    "/profiles/{profile_id}",
    summary="Delete a voice profile",
)
def delete_profile(
    profile_id: str,
    _authorized: bool = Depends(verify_secret_token),
):
    """Delete a custom voice profile (fallback profile cannot be deleted)."""
    try:
        voice_service.delete_profile(profile_id)
        return {"status": "deleted", "profile_id": profile_id}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# --- Pretrained Voicepacks Management ---

@router.get(
    "/voicepacks",
    response_model=List[VoicepackInfo],
    summary="List all discovered and installed pretrained voicepacks",
)
def list_voicepacks(
    _authorized: bool = Depends(verify_secret_token),
) -> List[VoicepackInfo]:
    """Enumerate all ready-to-use voicepacks (e.g. Piper ONNX models) available on disk."""
    return voice_service.list_voicepacks()


@router.post(
    "/voicepacks/import",
    response_model=VoicepackImportResponse,
    summary="Import a local pretrained voicepack .zip archive",
)
async def import_voicepack(
    file: UploadFile = File(..., description="Voicepack .zip archive containing .onnx and .json"),
    _authorized: bool = Depends(verify_secret_token),
) -> VoicepackImportResponse:
    """
    Safely import, validate, and index a community or local voicepack archive.
    Extracts models safely and auto-registers a selectable voice profile.
    """
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid archive format. Only .zip voicepack archives are accepted.",
        )

    try:
        content = await file.read()
        res = voice_service.import_voicepack(content, filename=file.filename)
        if not res.success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=res.message,
            )
        return res
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Voicepack import failed: {str(exc)}",
        )


@router.delete(
    "/voicepacks/{voicepack_id}",
    summary="Safely remove an installed voicepack from disk",
)
def delete_voicepack(
    voicepack_id: str,
    _authorized: bool = Depends(verify_secret_token),
):
    """Remove voicepack files from disk and clean up associated voice profiles."""
    success, msg = voice_service.delete_voicepack(voicepack_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg,
        )
    return {"status": "deleted", "voicepack_id": voicepack_id, "message": msg}


# --- External Models Storage & Management ---

@router.get(
    "/models/status",
    response_model=ModelsStorageStatusResponse,
    summary="Get active models directory and external asset storage telemetry",
)
def get_models_storage_status(
    _authorized: bool = Depends(verify_secret_token),
) -> ModelsStorageStatusResponse:
    """Retrieve details on the active external voice models directory and detected model files."""
    return voice_service.get_models_status()


@router.post(
    "/models/configure-path",
    response_model=ModelsStorageStatusResponse,
    summary="Configure or switch the external voice models directory",
)
def configure_models_storage_path(
    request: ConfigureModelsPathRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> ModelsStorageStatusResponse:
    """Switch the external storage location for Whisper, Piper, and RVC models."""
    try:
        return voice_service.configure_models_dir(request.path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to configure models directory: {str(exc)}",
        )


@router.post(
    "/models/import-path",
    response_model=VoicepackImportResponse,
    summary="Import a voicepack or RVC model from a local file or folder path",
)
def import_model_from_path(
    request: ImportModelPathRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> VoicepackImportResponse:
    """Import and register a local voice model (.onnx, .pth, or folder) from anywhere on the PC."""
    res = voice_service.import_voicepack_from_path(request.source_path, target_name=request.target_name)
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.message,
        )
    return res


# --- Speech Synthesis & Previews ---

@router.post(
    "/preview",
    response_model=SpeechSynthesizeResponse,
    summary="Generate audio preview for a voice or profile",
)
async def preview_voice(
    request: VoicePreviewRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> SpeechSynthesizeResponse:
    """Generate a short audio preview phrase for a profile or voice token."""
    try:
        return await voice_service.generate_preview(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Preview generation failed: {str(exc)}",
        )


@router.post(
    "/synthesize",
    response_model=SpeechSynthesizeResponse,
    summary="Synthesize speech audio from text",
)
async def synthesize_speech(
    request: SpeechSynthesizeRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> SpeechSynthesizeResponse:
    """Synthesize text into speech audio bytes using active profile or overrides."""
    try:
        return await voice_service.synthesize(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech synthesis failed: {str(exc)}",
        )


# --- Speech-to-Text Endpoints ---

@router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    summary="Transcribe recorded speech audio to text",
)
async def transcribe_speech(
    file: UploadFile = File(...),
    _authorized: bool = Depends(verify_secret_token),
) -> TranscriptionResponse:
    """Transcribe user microphone audio to text completely on-device."""
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            return TranscriptionResponse(
                text="",
                confidence=0.0,
                language="en",
                duration_seconds=0.0,
                provider="faster-whisper",
            )

        return await voice_service.transcribe(audio_bytes, filename=file.filename or "audio.wav")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech recognition failed: {str(exc)}",
        )


@router.post(
    "/stt-model",
    summary="Switch active STT Whisper model size",
)
def set_stt_model(
    request: STTModelChangeRequest,
    _authorized: bool = Depends(verify_secret_token),
):
    """Dynamically switch between supported Whisper models (base.en, tiny.en, small.en)."""
    valid_models = ["base.en", "tiny.en", "small.en"]
    if request.model_size not in valid_models:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported model size '{request.model_size}'. Supported: {valid_models}",
        )
    voice_service.set_stt_model(request.model_size)
    return {"status": "ok", "model_size": request.model_size}


# --- Proactive Task Narration Endpoints ---

from app.voice.narration import task_narration_engine, TaskLifecycleEvent, NarrationSettings


class NarrationEventRequest(BaseModel):
    task_id: str
    event_type: str
    user_prompt: Optional[str] = None
    tool_name: Optional[str] = None
    parameters: Optional[dict] = None
    action_summary: Optional[str] = None
    approved: Optional[bool] = None
    error_message: Optional[str] = None
    has_pending_approval: Optional[bool] = False
    is_success: Optional[bool] = True


@router.get(
    "/narration/settings",
    response_model=NarrationSettings,
    summary="Get current voice narration settings",
)
def get_narration_settings(
    _authorized: bool = Depends(verify_secret_token),
) -> NarrationSettings:
    """Retrieve thresholds, flags, and interval configurations for task narration."""
    return task_narration_engine.settings


@router.post(
    "/narration/settings",
    response_model=NarrationSettings,
    summary="Update voice narration settings",
)
def update_narration_settings(
    settings_update: dict = Body(...),
    _authorized: bool = Depends(verify_secret_token),
) -> NarrationSettings:
    """Update progress narration frequency, acknowledgment flags, or enabled state."""
    return task_narration_engine.configure(settings_update)


@router.post(
    "/narration/event",
    response_model=Optional[TaskLifecycleEvent],
    summary="Evaluate and generate a spoken narration event",
)
def evaluate_narration_event(
    req: NarrationEventRequest,
    _authorized: bool = Depends(verify_secret_token),
) -> Optional[TaskLifecycleEvent]:
    """Evaluate task lifecycle transitions and formulate grounded speech text."""
    evt = req.event_type.upper()
    if evt in ("TASK_RECEIVED", "TASK_ACKNOWLEDGED") and req.user_prompt:
        return task_narration_engine.generate_acknowledgment(req.user_prompt, req.task_id)
    elif evt == "ACTION_STARTED" and req.tool_name:
        return task_narration_engine.generate_action_started(req.tool_name, req.parameters or {}, req.task_id)
    elif evt == "APPROVAL_REQUIRED" and req.action_summary:
        return task_narration_engine.generate_approval_required(
            action_summary=req.action_summary,
            risk_tier="CONSEQUENTIAL",
            capability=(req.parameters or {}).get("capability_id"),
            app_id=(req.parameters or {}).get("app_id"),
            task_id=req.task_id,
        )
    elif evt in ("APPROVAL_GRANTED", "APPROVAL_DENIED") and req.action_summary:
        return task_narration_engine.generate_approval_decision(
            approved=bool(req.approved),
            action_summary=req.action_summary,
            task_id=req.task_id,
        )
    elif evt in ("ACTION_FAILED", "RECOVERY_STARTED") and req.tool_name:
        return task_narration_engine.generate_error(
            tool_name=req.tool_name,
            error_message=req.error_message or "Unknown failure",
            task_id=req.task_id,
            recovery_attempted=(evt == "RECOVERY_STARTED"),
        )
    elif evt in ("TASK_COMPLETED", "TASK_FAILED", "TASK_CANCELLED"):
        return task_narration_engine.generate_completion(
            task_id=req.task_id,
            has_pending_approval=bool(req.has_pending_approval),
            is_success=(evt == "TASK_COMPLETED"),
            is_cancelled=(evt == "TASK_CANCELLED"),
        )
    return None
