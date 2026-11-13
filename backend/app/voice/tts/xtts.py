"""
Coqui XTTS-v2 Text-to-Speech Provider (Integration Point).

Provides neural voice cloning from reference audio recordings using Coqui XTTS-v2.
Licensing Notice:
    Coqui XTTS-v2 uses the Coqui Public Model License (CPML).
    Use of reference recordings must be strictly authorized by the voice owner.
    In Milestone 2.0, this provider serves as an extensible integration point
    and does not force-load heavy dependencies into the primary backend environment.
"""

import logging
from typing import List, Optional

from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TTSProviderInfo,
    TTSProviderStatus,
)
from app.voice.tts.base import BaseTTSProvider

logger = logging.getLogger("jarvis.voice.tts.xtts")


class XTTSv2TTSProvider(BaseTTSProvider):
    """Coqui XTTS-v2 neural voice cloning provider integration point."""

    def __init__(self):
        self._model = None
        self._is_initialized = False

    @property
    def id(self) -> str:
        return "xtts-v2"

    @property
    def name(self) -> str:
        return "Coqui XTTS-v2"

    def is_available(self) -> bool:
        """Checks whether deep learning dependencies (torch & TTS) are available."""
        try:
            import importlib.util
            return importlib.util.find_spec("TTS") is not None
        except Exception:
            return False

    def get_status(self) -> TTSProviderStatus:
        if self.is_available():
            return TTSProviderStatus.INSTALLED_READY if self._is_initialized else TTSProviderStatus.INSTALLED_READY
        return TTSProviderStatus.NOT_INSTALLED

    def get_info(self) -> TTSProviderInfo:
        status = self.get_status()
        msg = None
        if status == TTSProviderStatus.NOT_INSTALLED:
            msg = (
                "Coqui XTTS-v2 package ('TTS') is not installed. "
                "Install via 'pip install TTS' to enable local neural voice cloning from reference audio. "
                "Note: Coqui XTTS-v2 is subject to the Coqui Public Model License (CPML)."
            )

        return TTSProviderInfo(
            id=self.id,
            name=self.name,
            status=status,
            description="Deep learning neural voice cloning from short authorized reference audio clips.",
            is_local=True,
            supports_custom_voices=True,
            supports_pitch=False,
            supports_emotions=True,
            error_message=msg,
            voice_count=len(self.list_voices()),
        )

    def list_voices(self) -> List[VoiceInfo]:
        """Enumerate reference voice models or registered voice profiles for XTTS."""
        if not self.is_available():
            return []

        # Return registered reference voice samples if present
        return [
            VoiceInfo(
                id="xtts-reference-sample",
                name="XTTS Reference Voice (Custom)",
                provider_id=self.id,
                provider_name=self.name,
                gender="Neutral",
                languages=["en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh", "ja", "hu", "ko"],
                styles=["neutral", "expressive"],
                is_default=False,
            )
        ]

    async def synthesize(self, request: SpeechSynthesizeRequest) -> SpeechSynthesizeResponse:
        """Synthesize text using XTTS-v2 model."""
        if not self.is_available():
            raise RuntimeError(
                "Coqui XTTS-v2 provider is not installed. "
                "Please configure a valid SAPI profile or install TTS dependencies."
            )

        # Lazy model initialization hook for future milestone
        raise NotImplementedError("XTTS-v2 direct inference pipeline will be enabled in subsequent voice milestone.")

