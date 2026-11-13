"""
TTS Provider Registry coordinating multi-engine Text-to-Speech discovery and execution.
"""

import logging
from typing import Dict, List, Optional

from app.voice.models import TTSProviderInfo, VoiceInfo
from app.voice.tts.base import BaseTTSProvider
from app.voice.tts.sapi import LocalSapiTTSProvider
from app.voice.tts.piper import PiperTTSProvider
from app.voice.tts.xtts import XTTSv2TTSProvider

logger = logging.getLogger("jarvis.voice.tts.registry")


class TTSProviderRegistry:
    """Central registry holding all pluggable Text-to-Speech engines."""

    def __init__(self):
        self._providers: Dict[str, BaseTTSProvider] = {}
        # Register foundation engines
        self.register(LocalSapiTTSProvider())
        self.register(PiperTTSProvider())
        self.register(XTTSv2TTSProvider())

    def register(self, provider: BaseTTSProvider) -> None:
        """Register a new TTS provider."""
        self._providers[provider.id] = provider
        logger.debug(f"Registered TTS provider '{provider.id}' ({provider.name})")

    def get_provider(self, provider_id: str) -> Optional[BaseTTSProvider]:
        """Retrieve provider instance by ID."""
        return self._providers.get(provider_id)

    def get_default_provider(self) -> BaseTTSProvider:
        """Return the default fallback provider (Windows SAPI 5)."""
        sapi = self.get_provider("sapi5")
        if sapi and sapi.is_available():
            return sapi
        # Fallback to first available provider
        for p in self._providers.values():
            if p.is_available():
                return p
        # If none available, return sapi5 instance regardless
        return sapi or next(iter(self._providers.values()))

    def list_providers(self) -> List[TTSProviderInfo]:
        """Return operational telemetry and capabilities for all registered engines."""
        return [p.get_info() for p in self._providers.values()]

    def list_all_voices(self) -> List[VoiceInfo]:
        """Enumerate all discovered voices across all available providers."""
        all_voices: List[VoiceInfo] = []
        for provider in self._providers.values():
            try:
                voices = provider.list_voices()
                all_voices.extend(voices)
            except Exception as exc:
                logger.warning(f"Error enumerating voices from provider '{provider.id}': {exc}")
        return all_voices


# Global singleton provider registry
tts_registry = TTSProviderRegistry()
