"""
Base abstract interface for Speech-to-Text (STT) providers.
"""

from abc import ABC, abstractmethod
from app.voice.models import TranscriptionResponse


class BaseSTTProvider(ABC):
    """Abstract Base Class for pluggable Speech Recognition engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the STT engine and its dependencies are operational."""
        pass

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptionResponse:
        """Transcribe an audio file/buffer into text."""
        pass

