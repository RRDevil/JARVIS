"""
Local Faster-Whisper Speech Recognition Provider.
Transcribes audio completely on-device using local CTranslate2 Whisper models.
"""

import asyncio
import io
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.voice.models import TranscriptionResponse
from app.voice.paths import get_stt_models_dir, get_base_models_dir
from app.voice.stt.base import BaseSTTProvider

logger = logging.getLogger("jarvis.voice.stt.whisper")

# Compatibility fix: PyAV 14+ removed 'metadata_errors' from av.open()
# faster-whisper calls av.open(..., metadata_errors="ignore") which throws TypeError
try:
    import av
    if hasattr(av, "open"):
        _orig_av_open = av.open

        def _compat_av_open(*args, **kwargs):
            kwargs.pop("metadata_errors", None)
            return _orig_av_open(*args, **kwargs)

        av.open = _compat_av_open
except Exception as _patch_exc:
    logger.debug(f"PyAV patch notice: {_patch_exc}")


# Neutral domain vocabulary prompt to guide Whisper token decoding for technical terms
# without biasing the model to hallucinate actionable imperative commands on low audio/silence
DOMAIN_VOCABULARY_PROMPT = (
    "JARVIS, desktop assistant, Windows, system settings, diagnostics, "
    "PowerShell, terminal, browser, visual studio code, Python, "
    "FastAPI, Pydantic, SAPI 5, speech recognition, display, screen."
)


class FasterWhisperSTTProvider(BaseSTTProvider):
    """Local offline speech recognition using faster-whisper."""

    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._model = None
        self._lock = threading.Lock()
        self._is_loading = False

    @property
    def _model_dir(self) -> Path:
        """Dynamically resolve external/configured STT models directory."""
        return get_stt_models_dir()

    def is_available(self) -> bool:
        """Check if faster_whisper module is importable."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def is_model_loaded(self) -> bool:
        return self._model is not None

    def set_model(self, model_size: str):
        """Switch active model size lazily."""
        with self._lock:
            if model_size != self.model_size:
                logger.info(f"Switching STT model from '{self.model_size}' to '{model_size}'")
                self.model_size = model_size
                self._model = None  # Reload on next transcription request

    def _ensure_model(self):
        """Lazily initialize and download/load Whisper model."""
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            try:
                from faster_whisper import WhisperModel

                target_dir = self._model_dir
                target_dir.mkdir(parents=True, exist_ok=True)
                download_dir = target_dir

                # Check if model snapshot is present in target_dir or in local fallback
                local_fallback = Path(__file__).resolve().parents[4] / "data" / "models" / "stt"
                if not any(target_dir.glob(f"*{self.model_size}*")) and local_fallback.exists() and any(local_fallback.glob(f"*{self.model_size}*")):
                    download_dir = local_fallback

                logger.info(f"Loading faster-whisper model '{self.model_size}' from {download_dir}...")
                
                # CPU int8 quantization for minimal memory footprint and fast inference
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=str(download_dir),
                )
                logger.info("Faster-whisper model loaded successfully.")
                return self._model
            except Exception as exc:
                logger.error(f"Failed to initialize faster-whisper model: {exc}")
                raise RuntimeError(f"STT engine initialization failure: {str(exc)}") from exc

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.wav") -> TranscriptionResponse:
        """Transcribe audio bytes to text asynchronously without blocking the event loop."""
        if not audio_bytes or len(audio_bytes) < 100:
            return TranscriptionResponse(
                text="",
                confidence=0.0,
                language="en",
                duration_seconds=0.0,
                provider="faster-whisper",
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio_bytes, filename)

    def _transcribe_sync(self, audio_bytes: bytes, filename: str) -> TranscriptionResponse:
        start_time = time.perf_counter()
        model = self._ensure_model()

        temp_path = None
        try:
            suffix = Path(filename).suffix if Path(filename).suffix else ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_bytes)
                temp_path = f.name

            # Run transcription with beam_size=2 for robust hypothesis evaluation with minimal CPU overhead
            # Use natural conversational prompt, condition_on_previous_text=False to eliminate hallucination loops,
            # and tuned VAD with lower threshold and 400ms speech padding to prevent clipping soft word starts/ends
            segments, info = model.transcribe(
                temp_path,
                beam_size=2,
                best_of=2,
                language="en",
                initial_prompt=DOMAIN_VOCABULARY_PROMPT,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.35,
                    min_speech_duration_ms=150,
                    min_silence_duration_ms=800,
                    speech_pad_ms=400,
                ),
            )

            # Accumulate segment text
            full_text_parts = []
            for seg in segments:
                text_clean = seg.text.strip()
                if text_clean:
                    full_text_parts.append(text_clean)

            recognized_text = " ".join(full_text_parts).strip()
            elapsed = time.perf_counter() - start_time

            return TranscriptionResponse(
                text=recognized_text,
                confidence=round(getattr(info, "language_probability", 1.0), 3),
                language=getattr(info, "language", "en"),
                duration_seconds=round(elapsed, 3),
                provider="faster-whisper",
            )
        except Exception as exc:
            logger.error(f"Faster-whisper transcription error: {exc}")
            # Gracefully handle corrupt or unreadable audio format
            return TranscriptionResponse(
                text="",
                confidence=0.0,
                language="en",
                duration_seconds=round(time.perf_counter() - start_time, 3),
                provider="faster-whisper",
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

