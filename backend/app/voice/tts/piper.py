"""
Piper Neural Text-to-Speech Provider.
Provides high-speed, 100% offline neural speech synthesis using pretrained ONNX voicepacks.
"""

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from typing import List, Optional
import wave

from app.voice.models import (
    VoiceInfo,
    SpeechSynthesizeRequest,
    SpeechSynthesizeResponse,
    TTSProviderInfo,
    TTSProviderStatus,
)
from app.voice.tts.base import BaseTTSProvider
from app.voice.utils import clean_text_for_speech
from app.voice.voicepacks import voicepack_manager

logger = logging.getLogger("jarvis.voice.tts.piper")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
VOICE_PYTHON_EXE = (PROJECT_ROOT / ".venv_voice" / "Scripts" / "python.exe").resolve()
RUNNER_SCRIPT = (PROJECT_ROOT / "backend" / "app" / "voice" / "tts" / "piper_runner.py").resolve()


class PiperTTSProvider(BaseTTSProvider):
    """Local Piper ONNX Text-to-Speech provider with pretrained voicepack discovery."""

    def __init__(self):
        self._cached_voices: Optional[List[VoiceInfo]] = None

    @property
    def id(self) -> str:
        return "piper"

    @property
    def name(self) -> str:
        return "Piper Neural TTS"

    def _get_runner_python(self) -> Optional[str]:
        """Find Python executable with Piper support (.venv_voice or current sys.executable)."""
        if VOICE_PYTHON_EXE.exists():
            return str(VOICE_PYTHON_EXE)
        # Check current python environment
        try:
            import piper
            return "python"
        except ImportError:
            return None

    def is_available(self) -> bool:
        """Provider is available if a compatible Python environment and at least one voicepack exist."""
        has_python = self._get_runner_python() is not None
        has_voicepacks = len(voicepack_manager.list_voicepacks()) > 0
        return has_python and has_voicepacks

    def get_status(self) -> TTSProviderStatus:
        runner_py = self._get_runner_python()
        if not runner_py:
            return TTSProviderStatus.NOT_INSTALLED
        voicepacks = voicepack_manager.list_voicepacks()
        if not voicepacks:
            return TTSProviderStatus.UNAVAILABLE
        return TTSProviderStatus.INSTALLED_READY

    def get_info(self) -> TTSProviderInfo:
        status = self.get_status()
        msg = None
        if status == TTSProviderStatus.NOT_INSTALLED:
            msg = "Piper environment (.venv_voice) is not installed. Run voice setup to enable Piper Neural TTS."
        elif status == TTSProviderStatus.UNAVAILABLE:
            msg = "No pretrained Piper voicepacks (.onnx) found. Import a compatible voicepack to enable synthesis."

        voices = self.list_voices()
        return TTSProviderInfo(
            id=self.id,
            name=self.name,
            status=status,
            description="Ultra-fast local neural TTS using ONNX runtime and pretrained voicepacks with RVC character conversion.",
            is_local=True,
            supports_custom_voices=True,
            supports_pitch=False,
            supports_emotions=False,
            error_message=msg,
            voice_count=len(voices),
        )

    def list_voices(self) -> List[VoiceInfo]:
        """Enumerate installed voices from the VoicepackManager and discovered character models."""
        voicepacks = voicepack_manager.list_voicepacks()
        voices: List[VoiceInfo] = []

        for vp in voicepacks:
            if vp.status.value != "installed":
                continue

            # If multi-speaker voicepack, enumerate distinct speakers
            if vp.num_speakers > 1 and vp.speakers:
                for idx, spk in enumerate(vp.speakers):
                    voices.append(
                        VoiceInfo(
                            id=f"{vp.id}:{idx}",
                            name=f"{vp.name} — Speaker {spk}",
                            provider_id=self.id,
                            provider_name=self.name,
                            gender="Neutral",
                            languages=[vp.language],
                            styles=["neural"],
                            is_default=False,
                        )
                    )
            else:
                voices.append(
                    VoiceInfo(
                        id=vp.id,
                        name=vp.name,
                        provider_id=self.id,
                        provider_name=self.name,
                        gender="Neutral",
                        languages=[vp.language],
                        styles=["neural"],
                        is_default=(vp.id == "en_US-lessac-medium"),
                    )
                )

        # Discover all local RVC character models dynamically
        try:
            from app.voice.rvc_models import scan_rvc_models
            for rvc in scan_rvc_models():
                voices.append(
                    VoiceInfo(
                        id=f"piper-{rvc.id}",
                        name=rvc.name,
                        provider_id=self.id,
                        provider_name=self.name,
                        gender="Female",
                        languages=["en-US", "ja-JP"],
                        styles=["character", "rvc"],
                        is_default=False,
                    )
                )
        except Exception as exc:
            logger.warning(f"Error enumerating RVC voices: {exc}")

        return voices

    async def synthesize(self, request: SpeechSynthesizeRequest) -> SpeechSynthesizeResponse:
        """Synthesize text using Piper ONNX neural voicepack with optional RVC character conversion."""
        cleaned_text = clean_text_for_speech(request.text)
        if not cleaned_text:
            return SpeechSynthesizeResponse(
                audio_base64="",
                mime_type="audio/wav",
                duration_seconds=0.0,
                voice_used=request.voice_id or "piper-default",
                provider_used=self.id,
            )

        runner_py = self._get_runner_python()
        if not runner_py:
            raise RuntimeError("Piper TTS execution environment is not available.")

        # Identify requested voicepack and speaker
        voicepacks = voicepack_manager.list_voicepacks()
        if not voicepacks:
            raise RuntimeError("No installed Piper voicepacks available for speech synthesis.")

        target_vp = None
        target_speaker_idx = 0

        req_voice = request.voice_id or ""
        rvc_model = None
        rvc_index = None
        f0method = "pm"
        f0up_key = 0

        if request.metadata:
            rvc_model = request.metadata.get("rvc_model")
            rvc_index = request.metadata.get("rvc_index")
            f0method = request.metadata.get("f0method", "pm")
            f0up_key = int(request.metadata.get("f0up_key", 0))

        # Dynamic semitone calculation from request pitch multiplier
        if f0up_key == 0 and request.pitch is not None and request.pitch != 1.0:
            import math
            f0up_key = int(round(12.0 * math.log2(max(0.25, min(4.0, request.pitch)))))

        # Dynamic RVC character model lookup
        try:
            from app.voice.rvc_models import get_rvc_model
            if not rvc_model and req_voice:
                clean_req = req_voice.replace("piper-", "")
                matched = get_rvc_model(clean_req)
                if matched:
                    rvc_model = matched.model_path
                    rvc_index = matched.index_path
                    req_voice = "en_US-lessac-medium"

            # Fallback path self-healing if path moved or was renamed
            if rvc_model and not os.path.exists(rvc_model):
                stem = Path(rvc_model).stem
                matched = get_rvc_model(stem)
                if matched and os.path.exists(matched.model_path):
                    rvc_model = matched.model_path
                    rvc_index = matched.index_path or rvc_index
        except Exception as exc:
            logger.debug(f"RVC lookup fallback: {exc}")

        # Resolve paths if relative
        if rvc_model and not os.path.isabs(rvc_model):
            rvc_model = str((PROJECT_ROOT / rvc_model).resolve())
        if rvc_index and not os.path.isabs(rvc_index):
            rvc_index = str((PROJECT_ROOT / rvc_index).resolve())

        if rvc_model and not os.path.exists(rvc_model):
            logger.warning(f"RVC model file '{rvc_model}' not found, skipping RVC post-processing.")
            rvc_model = None
            rvc_index = None

        if ":" in req_voice:
            vp_id, spk_str = req_voice.split(":", 1)
            target_vp = voicepack_manager.get_voicepack(vp_id)
            try:
                target_speaker_idx = int(spk_str)
            except ValueError:
                target_speaker_idx = 0
        elif req_voice:
            target_vp = voicepack_manager.get_voicepack(req_voice)

        # Fallback to first installed voicepack if target not found
        if not target_vp:
            target_vp = voicepacks[0]

        # Calculate prosody parameters from delivery profile and speaking rate
        delivery_profile = request.delivery_profile or (request.metadata or {}).get("delivery_profile", "relaxed")
        profile_noise = 0.333
        profile_noise_w = 0.50
        profile_length = 1.06

        if delivery_profile == "conversational":
            profile_noise = 0.450
            profile_noise_w = 0.60
            profile_length = 1.00
        elif delivery_profile == "formal":
            profile_noise = 0.280
            profile_noise_w = 0.40
            profile_length = 1.12

        eff_noise = request.noise_scale if request.noise_scale is not None else profile_noise
        eff_noise_w = request.noise_w_scale if request.noise_w_scale is not None else profile_noise_w

        base_rate = 180.0
        req_rate = max(80, min(300, request.rate))
        rate_factor = base_rate / req_rate
        length_scale = round(profile_length * rate_factor, 3) if request.length_scale is None else request.length_scale

        volume_scale = max(0.0, min(1.0, request.volume / 100.0))

        # 1. Attempt ultra-low latency synthesis via warm persistent Piper worker
        b64_audio = ""
        duration_s = 0.0

        try:
            from app.voice.tts.piper_worker_client import piper_worker
            worker_resp = await piper_worker.synthesize(
                model_path=target_vp.model_path,
                config_path=target_vp.config_path,
                text=cleaned_text,
                speaker_id=target_speaker_idx,
                length_scale=length_scale,
                volume=volume_scale,
                noise_scale=eff_noise,
                noise_w_scale=eff_noise_w,
                rvc_model=rvc_model,
                rvc_index=rvc_index,
                f0method=f0method,
                f0up_key=f0up_key,
                runner_py=runner_py,
            )
            b64_audio = worker_resp.get("audio_base64", "")
            duration_s = float(worker_resp.get("duration_seconds", 0.0))
        except Exception as exc:
            logger.warning(f"Persistent Piper worker unavailable ({exc}), falling back to isolated runner subprocess.")
            loop = asyncio.get_running_loop()
            wav_bytes = await loop.run_in_executor(
                None,
                self._execute_synthesis,
                runner_py,
                target_vp.model_path,
                target_vp.config_path,
                cleaned_text,
                target_speaker_idx,
                length_scale,
                volume_scale,
                eff_noise,
                eff_noise_w,
                rvc_model,
                rvc_index,
                f0method,
                f0up_key,
            )
            b64_audio = base64.b64encode(wav_bytes).decode("ascii")
            try:
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    duration_s = round(wf.getnframes() / float(wf.getframerate()), 2)
            except Exception:
                pass

        voice_used_label = request.voice_id or (f"{target_vp.id}:{target_speaker_idx}" if target_vp.num_speakers > 1 else target_vp.id)
        if rvc_model:
            char_name = (request.metadata or {}).get("character_name") or Path(rvc_model).stem
            voice_used_label = char_name

        return SpeechSynthesizeResponse(
            audio_base64=b64_audio,
            mime_type="audio/wav",
            duration_seconds=duration_s,
            voice_used=voice_used_label,
            provider_used=self.id,
            fallback_applied=False,
        )

    def _execute_synthesis(
        self,
        runner_py: str,
        model_path: str,
        config_path: str,
        text: str,
        speaker_idx: int,
        length_scale: float,
        volume_scale: float,
        noise_scale: Optional[float] = None,
        noise_w_scale: Optional[float] = None,
        rvc_model: Optional[str] = None,
        rvc_index: Optional[str] = None,
        f0method: str = "pm",
        f0up_key: int = 0,
    ) -> bytes:
        """Synchronously invokes runner script in isolated Python environment and returns WAV bytes."""
        cmd = [
            runner_py,
            str(RUNNER_SCRIPT),
            "--model",
            model_path,
            "--config",
            config_path,
            "--text",
            text,
            "--speaker",
            str(speaker_idx),
            "--length-scale",
            str(length_scale),
            "--volume",
            str(volume_scale),
        ]

        if noise_scale is not None:
            cmd.extend(["--noise-scale", str(noise_scale)])
        if noise_w_scale is not None:
            cmd.extend(["--noise-w-scale", str(noise_w_scale)])
        if rvc_model and os.path.exists(rvc_model):
            cmd.extend(["--rvc-model", str(rvc_model)])
        if rvc_index and os.path.exists(rvc_index):
            cmd.extend(["--rvc-index", str(rvc_index)])
        if f0method:
            cmd.extend(["--f0method", str(f0method)])
        if f0up_key:
            cmd.extend(["--f0up-key", str(f0up_key)])

        base_timeout = 180.0 if rvc_model else 45.0
        char_timeout = (len(text) / 100.0) * (2.0 if rvc_model else 0.5)
        timeout_sec = max(base_timeout, base_timeout + char_timeout)

        # Use temporary file for reliable IPC on Windows
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd.extend(["--output", tmp_path])
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            if proc.returncode != 0:
                logger.error(f"Piper synthesis subprocess failed: {proc.stderr}")
                raise RuntimeError(f"Piper synthesis failed (code {proc.returncode}): {proc.stderr.strip()}")

            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
