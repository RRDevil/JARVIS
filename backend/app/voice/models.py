"""
Pydantic contracts and data models for J.A.R.V.I.S. Voice Interaction & Voice Library Subsystem.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TTSProviderStatus(str, Enum):
    """Readiness and lifecycle state of a Text-to-Speech provider."""

    INSTALLED_READY = "installed_ready"
    NOT_INSTALLED = "not_installed"
    INITIALIZING = "initializing"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class VoicepackStatus(str, Enum):
    """Installation and validation status of an imported voicepack."""

    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    CORRUPTED = "corrupted"


class VoicepackInfo(BaseModel):
    """Metadata describing an installed or discovered pretrained voicepack."""

    id: str = Field(..., description="Unique voicepack identifier, e.g. en_US-lessac-medium.")
    name: str = Field(..., description="Human-readable voicepack display name.")
    provider_id: str = Field(default="piper", description="Compatible TTS provider ID (e.g. piper).")
    language: str = Field(default="en-US", description="Primary language or locale code.")
    model_path: str = Field(..., description="Absolute path to the neural model checkpoint/ONNX file.")
    config_path: str = Field(..., description="Absolute path to model configuration/manifest JSON.")
    sample_rate: int = Field(default=22050, description="Audio sample rate in Hz.")
    num_speakers: int = Field(default=1, description="Number of distinct speaker timbres in model.")
    speakers: List[str] = Field(default_factory=lambda: ["default"], description="List of speaker identifiers or names.")
    size_bytes: int = Field(default=0, description="Total size in bytes on disk.")
    status: VoicepackStatus = Field(default=VoicepackStatus.INSTALLED, description="Current health status.")
    license: Optional[str] = Field(None, description="Model license (e.g. MIT, CC-BY-4.0).")
    attribution: Optional[str] = Field(None, description="Creator or source attribution.")
    description: Optional[str] = Field(None, description="Optional description of voice timbre or characteristics.")
    is_builtin: bool = Field(default=False, description="Whether this voicepack is bundled with J.A.R.V.I.S.")


class VoicepackImportResponse(BaseModel):
    """Response returned upon importing a local voicepack archive."""

    success: bool = Field(..., description="Whether import and validation succeeded.")
    message: str = Field(..., description="Informative status or diagnostic error message.")
    voicepack: Optional[VoicepackInfo] = Field(None, description="Imported voicepack metadata if successful.")
    profile_created: Optional["VoiceProfile"] = Field(None, description="Associated voice profile if created.")


class TTSProviderInfo(BaseModel):
    """Metadata describing a TTS provider, its operational health and capabilities."""

    id: str = Field(..., description="Unique provider identifier, e.g. sapi5, piper, xtts-v2.")
    name: str = Field(..., description="Human-readable provider name.")
    status: TTSProviderStatus = Field(..., description="Current availability and readiness status.")
    description: str = Field(..., description="Description of provider capabilities and engine type.")
    is_local: bool = Field(True, description="Whether synthesis runs 100% locally on-device.")
    supports_custom_voices: bool = Field(False, description="Whether provider supports reference voice cloning.")
    supports_pitch: bool = Field(False, description="Whether provider supports dynamic pitch tuning.")
    supports_emotions: bool = Field(False, description="Whether provider supports expressive emotional styles.")
    error_message: Optional[str] = Field(None, description="Diagnostic error or installation instructions if unavailable.")
    voice_count: int = Field(default=0, description="Number of discovered voices for this provider.")


class VoiceInfo(BaseModel):
    """Metadata describing an available Text-to-Speech voice."""

    id: str = Field(..., description="Unique voice identifier or system token.")
    name: str = Field(..., description="Human-readable voice display name.")
    provider_id: str = Field(default="sapi5", description="ID of the provider offering this voice.")
    provider_name: str = Field(default="Windows SAPI 5", description="Display name of the provider.")
    gender: Optional[str] = Field(None, description="Reported voice gender (Male/Female/Neutral).")
    languages: List[str] = Field(default_factory=list, description="Supported BCP-47 language tags.")
    styles: List[str] = Field(default_factory=list, description="Available emotional or stylistic modes.")
    is_default: bool = Field(False, description="Whether this voice is the system or provider default.")


class VoiceProfile(BaseModel):
    """User-selectable voice profile combining provider, voice token, and acoustic parameters."""

    id: str = Field(..., description="Unique voice profile identifier, e.g. jarvis-default.")
    name: str = Field(..., description="Human-readable display name for this voice profile.")
    provider_id: str = Field(default="sapi5", description="Target TTS provider ID.")
    voice_id: str = Field(..., description="Provider-specific voice token or speaker ID.")
    language: str = Field(default="en-US", description="Language and locale code.")
    rate: int = Field(default=180, ge=80, le=300, description="Speaking rate in words per minute.")
    pitch: Optional[float] = Field(default=1.0, ge=0.5, le=2.0, description="Pitch multiplier (where supported).")
    volume: int = Field(default=100, ge=0, le=100, description="Volume percentage (0 to 100).")
    style: Optional[str] = Field(None, description="Active emotion or style name if supported.")
    is_favorite: bool = Field(default=False, description="Whether marked as favorite by the user.")
    is_default: bool = Field(default=False, description="Whether marked as the active default profile.")
    is_fallback: bool = Field(default=False, description="Whether this profile acts as universal fallback.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific configuration.")


class VoiceProfileCreate(BaseModel):
    """Request payload to create a new voice profile."""

    id: Optional[str] = Field(None, description="Custom unique profile ID (auto-generated if omitted).")
    name: str = Field(..., min_length=1, max_length=100, description="Display name for the profile.")
    provider_id: str = Field(default="sapi5", description="Target TTS provider ID.")
    voice_id: str = Field(..., min_length=1, description="Provider-specific voice token or speaker ID.")
    language: str = Field(default="en-US", description="Language and locale code.")
    rate: int = Field(default=180, ge=80, le=300, description="Speaking rate in words per minute.")
    pitch: Optional[float] = Field(default=1.0, ge=0.5, le=2.0, description="Pitch multiplier.")
    volume: int = Field(default=100, ge=0, le=100, description="Volume percentage (0 to 100).")
    style: Optional[str] = Field(None, description="Active emotion or style.")
    is_favorite: bool = Field(default=False, description="Whether marked as favorite.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional provider-specific settings.")


class VoiceProfileUpdate(BaseModel):
    """Request payload to update an existing voice profile."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    provider_id: Optional[str] = None
    voice_id: Optional[str] = None
    language: Optional[str] = None
    rate: Optional[int] = Field(None, ge=80, le=300)
    pitch: Optional[float] = Field(None, ge=0.5, le=2.0)
    volume: Optional[int] = Field(None, ge=0, le=100)
    style: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_default: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class VoicePreviewRequest(BaseModel):
    """Request payload to generate a short spoken audio preview."""

    profile_id: Optional[str] = Field(None, description="Profile ID to preview.")
    provider_id: Optional[str] = Field(None, description="Provider ID if previewing raw voice.")
    voice_id: Optional[str] = Field(None, description="Voice ID if previewing raw voice.")
    text: Optional[str] = Field(None, description="Custom preview text string (optional).")
    rate: Optional[int] = Field(None, ge=80, le=300, description="Speaking rate in WPM.")
    pitch: Optional[float] = Field(None, ge=0.5, le=2.0, description="Pitch multiplier.")
    volume: Optional[int] = Field(None, ge=0, le=100, description="Volume percentage.")


class SpeechSynthesizeRequest(BaseModel):
    """Request payload for text-to-speech synthesis."""

    text: str = Field(..., min_length=1, max_length=50000, description="Text string to speak.")
    profile_id: Optional[str] = Field(None, description="Specific voice profile ID to use.")
    voice_id: Optional[str] = Field(None, description="Specific voice identifier to use (legacy / direct override).")
    provider_id: Optional[str] = Field(None, description="Specific provider ID to use (optional override).")
    rate: int = Field(default=180, ge=80, le=300, description="Speaking rate in words per minute (80 to 300).")
    pitch: Optional[float] = Field(default=1.0, ge=0.5, le=2.0, description="Pitch multiplier (where supported).")
    volume: int = Field(default=100, ge=0, le=100, description="Volume percentage from 0 to 100.")
    format: str = Field(default="wav", description="Audio container format.")
    delivery_profile: Optional[str] = Field(None, description="Conversational delivery profile (relaxed, conversational, formal).")
    noise_scale: Optional[float] = Field(None, ge=0.0, le=2.0, description="Phoneme noise scale for prosody variation.")
    noise_w_scale: Optional[float] = Field(None, ge=0.0, le=2.0, description="Phoneme width noise scale.")
    length_scale: Optional[float] = Field(None, ge=0.1, le=5.0, description="Phoneme length scale multiplier.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific or profile metadata overrides.")


class SpeechSynthesizeResponse(BaseModel):
    """Synthesized audio response with base64 encoded audio bytes."""

    audio_base64: str = Field(..., description="Base64 encoded audio bytes.")
    mime_type: str = Field(default="audio/wav", description="MIME type of the audio data.")
    duration_seconds: Optional[float] = Field(None, description="Estimated duration in seconds.")
    voice_used: str = Field(..., description="Identifier of the voice used for synthesis.")
    provider_used: str = Field(default="sapi5", description="ID of the provider that performed synthesis.")
    fallback_applied: bool = Field(False, description="Whether fallback to default provider occurred.")
    fallback_reason: Optional[str] = Field(None, description="Explanation if fallback occurred.")


class TranscriptionResponse(BaseModel):
    """Recognized speech transcription output."""

    text: str = Field(..., description="Transcribed spoken text.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0.")
    language: str = Field(default="en", description="Detected language code.")
    duration_seconds: float = Field(default=0.0, description="Audio duration processed.")
    provider: str = Field(default="faster-whisper", description="STT provider that processed the audio.")


class VoiceStatusResponse(BaseModel):
    """Current telemetry and capability status of the Voice Subsystem."""

    stt_available: bool = Field(..., description="Whether speech recognition is functional.")
    tts_available: bool = Field(..., description="Whether speech synthesis is functional.")
    stt_provider: str = Field(..., description="Active STT provider name.")
    tts_provider: str = Field(..., description="Active TTS provider name.")
    stt_model_loaded: bool = Field(default=False, description="Whether the offline STT model is loaded in memory.")
    stt_model_size: str = Field(default="base.en", description="Active Whisper model size.")
    available_stt_models: List[str] = Field(default_factory=lambda: ["base.en", "tiny.en", "small.en"], description="Available STT models.")
    available_voices: List[VoiceInfo] = Field(default_factory=list, description="Installed TTS voices.")
    active_profile_id: Optional[str] = Field(None, description="Active voice profile ID.")
    active_profile_name: Optional[str] = Field(None, description="Active voice profile display name.")
    active_provider_id: Optional[str] = Field(None, description="Active TTS provider ID.")


class ModelsStorageStatusResponse(BaseModel):
    """Telemetry describing active models directory and external asset distribution."""

    active_models_dir: str = Field(..., description="Active directory path where models reside.")
    is_external: bool = Field(..., description="Whether models directory is outside the Git repo.")
    total_size_mb: float = Field(default=0.0, description="Total size of model weights in MB.")
    stt_models_count: int = Field(default=0, description="Number of detected Whisper model versions.")
    tts_voicepacks_count: int = Field(default=0, description="Number of detected Piper voicepacks.")
    rvc_models_count: int = Field(default=0, description="Number of detected RVC character models.")
    scan_directories: List[str] = Field(default_factory=list, description="All directories inspected for models.")


class ConfigureModelsPathRequest(BaseModel):
    """Request to update or switch the active external models directory."""

    path: str = Field(..., min_length=1, description="Absolute or relative path to models directory.")


class ImportModelPathRequest(BaseModel):
    """Request to import an on-disk model folder, .zip, or model weights file into the app."""

    source_path: str = Field(..., min_length=1, description="Local path to file or folder to import.")
    target_name: Optional[str] = Field(None, description="Optional custom name or identifier for the model.")

    providers: List[TTSProviderInfo] = Field(default_factory=list, description="Status of all registered TTS providers.")


class STTModelChangeRequest(BaseModel):
    """Request payload to change active STT model size."""

    model_size: str = Field(..., description="Whisper model size, e.g. base.en or tiny.en.")
