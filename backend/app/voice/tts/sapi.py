"""
Local Windows SAPI 5 / OneCore Text-to-Speech Provider using pyttsx3.
Provides 100% offline, on-device speech synthesis with zero cloud dependencies.
"""

import asyncio
import base64
import logging
import os
import tempfile
import threading
from typing import List, Optional

import pyttsx3

from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TTSProviderInfo,
    TTSProviderStatus,
)
from app.voice.tts.base import BaseTTSProvider
from app.voice.utils import clean_text_for_speech

logger = logging.getLogger("jarvis.voice.tts.sapi")


class LocalSapiTTSProvider(BaseTTSProvider):
    """Windows SAPI 5 offline text-to-speech implementation."""

    def __init__(self):
        self._lock = threading.Lock()
        self._voices_cache: Optional[List[VoiceInfo]] = None

    @property
    def id(self) -> str:
        return "sapi5"

    @property
    def name(self) -> str:
        return "Windows SAPI 5"

    def get_status(self) -> TTSProviderStatus:
        return TTSProviderStatus.INSTALLED_READY

    def is_available(self) -> bool:
        """SAPI 5 is built into Windows and always operational."""
        return True

    def get_info(self) -> TTSProviderInfo:
        voices = self.list_voices()
        return TTSProviderInfo(
            id=self.id,
            name=self.name,
            status=self.get_status(),
            description="Native Windows Speech API (SAPI 5 / OneCore). Fast, lightweight, 100% offline.",
            is_local=True,
            supports_custom_voices=False,
            supports_pitch=False,
            supports_emotions=False,
            voice_count=len(voices),
        )

    def list_voices(self) -> List[VoiceInfo]:
        """List all voices installed in the Windows Speech subsystem."""
        if self._voices_cache is not None:
            return self._voices_cache

        with self._lock:
            try:
                engine = pyttsx3.init()
                sapi_voices = engine.getProperty("voices")
                voices: List[VoiceInfo] = []

                for i, v in enumerate(sapi_voices):
                    # Identify gender if available
                    gender = getattr(v, "gender", None)
                    if not gender:
                        if "zira" in v.name.lower() or "haruka" in v.name.lower() or "heami" in v.name.lower():
                            gender = "Female"
                        elif "david" in v.name.lower() or "mark" in v.name.lower():
                            gender = "Male"

                    langs = getattr(v, "languages", [])
                    if isinstance(langs, bytes):
                        langs = [langs.decode("utf-8", errors="ignore")]
                    elif isinstance(langs, (list, tuple)):
                        langs = [str(lang) for lang in langs]
                    else:
                        langs = ["en-US"]

                    voices.append(
                        VoiceInfo(
                            id=v.id,
                            name=v.name,
                            provider_id=self.id,
                            provider_name=self.name,
                            gender=gender,
                            languages=langs,
                            is_default=(i == 0),
                        )
                    )

                self._voices_cache = voices
                return voices
            except Exception as exc:
                logger.error(f"Failed to enumerate Windows SAPI voices: {exc}")
                return [
                    VoiceInfo(
                        id="default",
                        name="Default Windows Voice",
                        provider_id=self.id,
                        provider_name=self.name,
                        gender="Neutral",
                        languages=["en-US"],
                        is_default=True,
                    )
                ]

    async def synthesize(self, request: SpeechSynthesizeRequest) -> SpeechSynthesizeResponse:
        """Synthesize text into WAV speech audio bytes."""
        cleaned_text = clean_text_for_speech(request.text)
        if not cleaned_text:
            cleaned_text = "Ready."

        # Run synthesis in background thread to prevent blocking asyncio event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, request, cleaned_text)

    def _synthesize_sync(self, request: SpeechSynthesizeRequest, cleaned_text: str) -> SpeechSynthesizeResponse:
        with self._lock:
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name

                engine = pyttsx3.init()

                # 1. Configure voice
                voice_used = "Default Voice"
                if request.voice_id:
                    try:
                        engine.setProperty("voice", request.voice_id)
                        voice_used = request.voice_id
                    except Exception as e:
                        logger.warning(f"Failed to set requested voice {request.voice_id}: {e}")

                # 2. Configure speaking rate (canonical words per minute: 80 to 300)
                target_rate = int(max(80, min(300, request.rate)))
                engine.setProperty("rate", target_rate)

                # 3. Configure volume (percentage 0 to 100 converted to pyttsx3 0.0 to 1.0)
                target_volume = max(0.0, min(1.0, float(request.volume) / 100.0))
                engine.setProperty("volume", target_volume)

                # 4. Save to temporary WAV
                engine.save_to_file(cleaned_text, temp_path)
                engine.runAndWait()

                # 5. Read generated WAV bytes and encode to base64
                with open(temp_path, "rb") as f:
                    audio_bytes = f.read()

                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

                # Estimate duration from word count at given WPM
                word_count = len(cleaned_text.split())
                duration = round(max(0.1, word_count / (target_rate / 60.0)), 2)

                return SpeechSynthesizeResponse(
                    audio_base64=audio_base64,
                    mime_type="audio/wav",
                    duration_seconds=duration,
                    voice_used=voice_used,
                    provider_used=self.id,
                )
            except Exception as exc:
                logger.error(f"SAPI speech synthesis failed: {exc}")
                raise RuntimeError(f"Speech synthesis error: {str(exc)}") from exc
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
