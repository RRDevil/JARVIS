"""
Unified Voice Service coordinating STT speech recognition, TTS provider registry,
voice profiles, and automatic fallback resolution.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TranscriptionResponse,
    VoiceStatusResponse,
    TTSProviderInfo,
    VoiceProfile,
    VoiceProfileCreate,
    VoiceProfileUpdate,
    VoicePreviewRequest,
    VoicepackInfo,
    VoicepackImportResponse,
    ModelsStorageStatusResponse,
)
from app.voice.paths import (
    get_base_models_dir,
    get_all_model_scan_dirs,
    set_runtime_models_dir,
    get_stt_models_dir,
    get_tts_piper_dir,
    get_rvc_models_dir,
    PROJECT_ROOT,
)
from app.voice.profiles import profile_manager
from app.voice.stt.base import BaseSTTProvider
from app.voice.stt.whisper import FasterWhisperSTTProvider
from app.voice.tts.registry import tts_registry
from app.voice.voicepacks import voicepack_manager

logger = logging.getLogger("jarvis.voice.service")


class VoiceService:
    """Coordinates speech synthesis, transcription engines, and persistent voice profiles."""

    def __init__(self, stt_provider: Optional[BaseSTTProvider] = None):
        self.stt_provider = stt_provider or FasterWhisperSTTProvider()
        self.tts_registry = tts_registry
        self.profile_manager = profile_manager
        self.voicepack_manager = voicepack_manager

    def get_status(self) -> VoiceStatusResponse:
        """Query active status, providers, profiles, and capabilities of the speech subsystem."""
        stt_avail = self.stt_provider.is_available()
        stt_loaded = getattr(self.stt_provider, "is_model_loaded", lambda: False)()
        model_size = getattr(self.stt_provider, "model_size", "base.en")
        voices = self.list_voices()
        providers = self.list_providers()
        active_profile = self.profile_manager.get_active_profile()
        active_provider = self.tts_registry.get_provider(active_profile.provider_id)
        provider_display = f"{active_provider.name} (local)" if active_provider else active_profile.provider_id

        return VoiceStatusResponse(
            stt_available=stt_avail,
            tts_available=any(p.status.value == "installed_ready" for p in providers),
            stt_provider="faster-whisper (local)",
            tts_provider=provider_display,
            stt_model_loaded=stt_loaded,
            stt_model_size=model_size,
            available_stt_models=["base.en", "tiny.en", "small.en"],
            available_voices=voices,
            active_profile_id=active_profile.id,
            active_profile_name=active_profile.name,
            active_provider_id=active_profile.provider_id,
            providers=providers,
        )

    def set_stt_model(self, model_size: str) -> None:
        """Switch active STT model size."""
        if hasattr(self.stt_provider, "set_model"):
            self.stt_provider.set_model(model_size)

    def list_providers(self) -> List[TTSProviderInfo]:
        """List operational capabilities and health for all registered TTS engines."""
        return self.tts_registry.list_providers()

    def list_voices(self) -> List[VoiceInfo]:
        """List all discovered TTS voices across all engines."""
        return self.tts_registry.list_all_voices()

    def list_profiles(self) -> List[VoiceProfile]:
        """List all configured persistent voice profiles."""
        return self.profile_manager.list_profiles()

    def get_active_profile(self) -> VoiceProfile:
        """Retrieve the currently active voice profile."""
        return self.profile_manager.get_active_profile()

    def set_active_profile(self, profile_id: str) -> VoiceProfile:
        """Set the active voice profile."""
        return self.profile_manager.set_active_profile(profile_id)

    def create_profile(self, create_data: VoiceProfileCreate) -> VoiceProfile:
        """Create and persist a new voice profile."""
        return self.profile_manager.create_profile(create_data)

    def update_profile(self, profile_id: str, update_data: VoiceProfileUpdate) -> VoiceProfile:
        """Update an existing voice profile."""
        return self.profile_manager.update_profile(profile_id, update_data)

    def delete_profile(self, profile_id: str) -> None:
        """Delete an existing voice profile."""
        self.profile_manager.delete_profile(profile_id)

    # --- Pretrained Voicepack Management ---

    def list_voicepacks(self) -> List[VoicepackInfo]:
        """List all discovered and installed pretrained voicepacks."""
        return self.voicepack_manager.list_voicepacks()

    def get_voicepack(self, voicepack_id: str) -> Optional[VoicepackInfo]:
        """Retrieve voicepack metadata by ID."""
        return self.voicepack_manager.get_voicepack(voicepack_id)

    def import_voicepack(self, archive_bytes: bytes, filename: Optional[str] = None) -> VoicepackImportResponse:
        """Import, validate, and extract a local voicepack .zip file."""
        target_name = Path(filename).stem if filename else None
        success, msg, vp = self.voicepack_manager.import_from_zip(archive_bytes, target_name=target_name)
        profile = None
        if success and vp:
            profile = self.profile_manager.create_or_update_profile_for_voicepack(vp)
        return VoicepackImportResponse(
            success=success,
            message=msg,
            voicepack=vp,
            profile_created=profile,
        )

    def delete_voicepack(self, voicepack_id: str) -> Tuple[bool, str]:
        """Safely delete an installed voicepack from disk and purge associated profiles."""
        self.profile_manager.remove_profiles_for_voicepack(voicepack_id)
        return self.voicepack_manager.delete_voicepack(voicepack_id)

    def import_voicepack_from_path(
        self, source_path: str, target_name: Optional[str] = None
    ) -> VoicepackImportResponse:
        """Import a voice model from an uncompressed directory or .zip archive path on disk."""
        path_obj = Path(source_path).resolve()
        if not path_obj.exists():
            return VoicepackImportResponse(
                success=False,
                message=f"Path '{source_path}' does not exist on disk.",
                voicepack=None,
                profile_created=None,
            )

        if path_obj.is_file() and path_obj.suffix.lower() == ".zip":
            success, msg, vp = self.voicepack_manager.import_from_zip(path_obj, target_name=target_name)
        else:
            success, msg, vp = self.voicepack_manager.import_from_folder(path_obj, target_name=target_name)

        profile = None
        if success and vp:
            profile = self.profile_manager.create_or_update_profile_for_voicepack(vp)
        return VoicepackImportResponse(
            success=success,
            message=msg,
            voicepack=vp,
            profile_created=profile,
        )

    def get_models_status(self) -> ModelsStorageStatusResponse:
        """Inspect storage directory and return telemetry regarding model asset distribution."""
        base_dir = get_base_models_dir()
        is_external = not (base_dir.resolve() == (PROJECT_ROOT / "data" / "models").resolve() or PROJECT_ROOT in base_dir.resolve().parents)

        total_bytes = 0
        stt_count = 0
        if base_dir.exists():
            for f in base_dir.rglob("*"):
                if f.is_file():
                    try:
                        total_bytes += f.stat().st_size
                    except Exception:
                        pass

        # Count STT models
        stt_dir = get_stt_models_dir()
        if stt_dir.exists():
            stt_count = len([d for d in stt_dir.iterdir() if d.is_dir() and "whisper" in d.name.lower()])

        tts_count = len(self.voicepack_manager.list_voicepacks())

        from app.voice.rvc_models import scan_rvc_models
        rvc_count = len(scan_rvc_models())

        scan_dirs = [str(p) for p in get_all_model_scan_dirs()]

        return ModelsStorageStatusResponse(
            active_models_dir=str(base_dir),
            is_external=is_external,
            total_size_mb=round(total_bytes / (1024 * 1024), 2),
            stt_models_count=stt_count,
            tts_voicepacks_count=tts_count,
            rvc_models_count=rvc_count,
            scan_directories=scan_dirs,
        )

    def configure_models_dir(self, new_path: str) -> ModelsStorageStatusResponse:
        """Switch or update the active external models directory."""
        target = set_runtime_models_dir(new_path)
        self.voicepack_manager.base_dir = get_tts_piper_dir()
        self.voicepack_manager.rescan()
        self.profile_manager.rescan_rvc_models()
        logger.info(f"Updated models directory to: {target}")
        return self.get_models_status()

    async def synthesize(self, request: SpeechSynthesizeRequest) -> SpeechSynthesizeResponse:
        """
        Synthesize text into speech audio bytes.
        Automatically resolves profile defaults and applies graceful fallback
        if the profile's engine is offline or unavailable.
        """
        # Resolve target profile and provider
        profile, provider, fallback_applied, fallback_reason = (
            self.profile_manager.resolve_profile_for_synthesis(request.profile_id)
        )

        # Allow explicit provider_id override if supplied and available
        if request.provider_id:
            override_provider = self.tts_registry.get_provider(request.provider_id)
            if override_provider and override_provider.is_available():
                provider = override_provider
                fallback_applied = False
                fallback_reason = None
        elif request.voice_id:
            # Auto-detect matching provider from voice_id identifier
            detected_id = None
            if request.voice_id.startswith("piper") or self.voicepack_manager.get_voicepack(request.voice_id.split(":")[0]):
                detected_id = "piper"
            elif "HKEY_LOCAL_MACHINE" in request.voice_id or request.voice_id == "default":
                detected_id = "sapi5"
            elif "xtts" in request.voice_id.lower():
                detected_id = "xtts-v2"

            if detected_id:
                cand = self.tts_registry.get_provider(detected_id)
                if cand and cand.is_available():
                    provider = cand
                    fallback_applied = False
                    fallback_reason = None

        # Merge request overrides with profile parameters
        effective_voice_id = request.voice_id or profile.voice_id
        effective_rate = request.rate if request.rate != 180 else profile.rate
        effective_volume = request.volume if request.volume != 100 else profile.volume
        effective_pitch = request.pitch if request.pitch != 1.0 else (profile.pitch or 1.0)

        effective_metadata = dict(profile.metadata or {})
        if request.metadata:
            effective_metadata.update(request.metadata)

        synth_req = SpeechSynthesizeRequest(
            text=request.text,
            profile_id=profile.id,
            voice_id=effective_voice_id,
            provider_id=provider.id,
            rate=effective_rate,
            pitch=effective_pitch,
            volume=effective_volume,
            format=request.format,
            delivery_profile=request.delivery_profile,
            noise_scale=request.noise_scale,
            noise_w_scale=request.noise_w_scale,
            length_scale=request.length_scale,
            metadata=effective_metadata,
        )

        response = await provider.synthesize(synth_req)
        response.provider_used = provider.id
        response.fallback_applied = fallback_applied
        response.fallback_reason = fallback_reason

        return response

    async def generate_preview(self, request: VoicePreviewRequest) -> SpeechSynthesizeResponse:
        """Generate a short audio preview phrase for a profile or voice."""
        preview_text = request.text or "J.A.R.V.I.S. voice synthesis online."

        if request.profile_id:
            profile = self.profile_manager.get_profile(request.profile_id)
            if not profile:
                raise ValueError(f"Voice profile '{request.profile_id}' not found.")
            provider = self.tts_registry.get_provider(profile.provider_id)
            if not provider or not provider.is_available():
                # Provide fallback preview with clear telemetry
                provider = self.tts_registry.get_default_provider()
                fallback_applied = True
                fallback_reason = f"Provider '{profile.provider_id}' is unavailable; previewing on fallback engine."
            else:
                fallback_applied = False
                fallback_reason = None

            effective_metadata = dict(profile.metadata or {})
            synth_req = SpeechSynthesizeRequest(
                text=preview_text,
                profile_id=profile.id,
                voice_id=profile.voice_id,
                provider_id=provider.id,
                rate=request.rate or profile.rate,
                pitch=request.pitch or (profile.pitch or 1.0),
                volume=request.volume or profile.volume,
                metadata=effective_metadata,
            )
            res = await provider.synthesize(synth_req)
            res.provider_used = provider.id
            res.fallback_applied = fallback_applied
            res.fallback_reason = fallback_reason
            return res

        # Raw provider/voice preview
        provider_id = request.provider_id or "sapi5"
        provider = self.tts_registry.get_provider(provider_id)
        if not provider or not provider.is_available():
            provider = self.tts_registry.get_default_provider()

        synth_req = SpeechSynthesizeRequest(
            text=preview_text,
            voice_id=request.voice_id,
            provider_id=provider.id,
            rate=request.rate or 180,
            pitch=request.pitch or 1.0,
            volume=request.volume or 100,
        )
        return await provider.synthesize(synth_req)

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptionResponse:
        """Transcribe user audio stream into text."""
        return await self.stt_provider.transcribe(audio_bytes, filename)


# Global singleton instance
voice_service = VoiceService()
