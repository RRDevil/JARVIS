"""
Base abstract interface for Text-to-Speech (TTS) providers.
Defines a standard lifecycle, discovery, and synthesis contract for all voice engines.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TTSProviderInfo,
    TTSProviderStatus,
)


class BaseTTSProvider(ABC):
    """Abstract Base Class for pluggable TTS engines."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique provider identifier (e.g. 'sapi5', 'piper', 'xtts-v2')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider display name."""
        pass

    @abstractmethod
    def get_info(self) -> TTSProviderInfo:
        """Retrieve operational health, availability status, and capabilities."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this provider is currently available and ready for synthesis."""
        pass

    @abstractmethod
    def get_status(self) -> TTSProviderStatus:
        """Get current provider status enum."""
        pass

    @abstractmethod
    def list_voices(self) -> List[VoiceInfo]:
        """List all voices discovered for this provider."""
        pass

    @abstractmethod
    async def synthesize(self, request: SpeechSynthesizeRequest) -> SpeechSynthesizeResponse:
        """Synthesize text into speech audio bytes encoded in base64."""
        pass

    async def generate_preview(
        self,
        voice_id: Optional[str] = None,
        text: Optional[str] = None,
        rate: int = 180,
        pitch: float = 1.0,
        volume: int = 100,
    ) -> SpeechSynthesizeResponse:
        """Generate a short audio preview phrase for a voice or parameter set."""
        preview_text = text or "J.A.R.V.I.S. voice synthesis online."
        req = SpeechSynthesizeRequest(
            text=preview_text,
            voice_id=voice_id,
            provider_id=self.id,
            rate=rate,
            pitch=pitch,
            volume=volume,
        )
        return await self.synthesize(req)

    def initialize(self) -> None:
        """Optional provider initialization hook."""
        pass

    def shutdown(self) -> None:
        """Optional provider shutdown and resource release hook."""
        pass
