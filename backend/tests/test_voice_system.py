"""
test_voice_system.py - Phase Voice Interaction Milestone 1.0
Validates Voice Models, Local SAPI TTS, Faster-Whisper STT, Text Sanitization, and API endpoints.
"""

import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.voice.models import SpeechSynthesizeRequest
from app.voice.service import voice_service
from app.voice.utils import clean_text_for_speech


client = TestClient(app)


def test_clean_text_for_speech_markdown_and_code():
    """Verify clean_text_for_speech filters code blocks, links, headers, and emojis."""
    raw_text = (
        "# J.A.R.V.I.S. Update\n\n"
        "Here is the result: **System Online**!\n"
        "```python\nprint('secret code')\n```\n"
        "Visit [Our Documentation](https://example.com/docs) for `config.json` details. > Notice\n"
        "- [x] Item 1\n- Item 2"
    )
    cleaned = clean_text_for_speech(raw_text)

    # Markdown headers, bold, code block, links, and bullets should be sanitized
    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "print('secret code')" not in cleaned
    assert "Code snippet omitted." in cleaned
    assert "Our Documentation" in cleaned
    assert "https://" not in cleaned
    assert "config.jason" in cleaned or "config.json" in cleaned


def test_voice_status_endpoint():
    """Verify GET /api/v1/voice/status returns telemetry and capability status."""
    response = client.get("/api/v1/voice/status")
    assert response.status_code == 200
    data = response.json()
    assert "stt_available" in data
    assert "tts_available" in data
    assert data["tts_available"] is True
    assert "faster-whisper" in data["stt_provider"]
    assert "Windows SAPI" in data["tts_provider"]


def test_list_voices_endpoint():
    """Verify GET /api/v1/voice/voices returns installed voices."""
    response = client.get("/api/v1/voice/voices")
    assert response.status_code == 200
    voices = response.json()
    assert isinstance(voices, list)
    assert len(voices) >= 1
    first_voice = voices[0]
    assert "id" in first_voice
    assert "name" in first_voice


@pytest.mark.asyncio
async def test_tts_synthesis_service():
    """Verify voice_service.synthesize produces valid base64 WAV speech."""
    req = SpeechSynthesizeRequest(
        text="Affirmative, Sir. System checks clear.",
        rate=180,
        volume=80,
    )
    res = await voice_service.synthesize(req)
    assert res.audio_base64 is not None
    assert res.mime_type == "audio/wav"

    decoded = base64.b64decode(res.audio_base64)
    # Valid RIFF WAV header begins with 'RIFF'
    assert decoded.startswith(b"RIFF")
    assert len(decoded) > 1000


def test_synthesize_api_endpoint():
    """Verify POST /api/v1/voice/synthesize produces valid response."""
    response = client.post(
        "/api/v1/voice/synthesize",
        json={
            "text": "Hello world from JARVIS.",
            "rate": 180,
            "volume": 90,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "audio_base64" in data
    assert data["mime_type"] == "audio/wav"
    assert "voice_used" in data


def test_stt_model_switching_endpoint():
    """Verify POST /api/v1/voice/stt-model allows switching between supported models."""
    response = client.post(
        "/api/v1/voice/stt-model",
        json={"model_size": "tiny.en"},
    )
    assert response.status_code == 200
    assert response.json()["model_size"] == "tiny.en"

    # Switch to small.en
    response_small = client.post(
        "/api/v1/voice/stt-model",
        json={"model_size": "small.en"},
    )
    assert response_small.status_code == 200
    assert response_small.json()["model_size"] == "small.en"

    # Switch back to base.en
    response2 = client.post(
        "/api/v1/voice/stt-model",
        json={"model_size": "base.en"},
    )
    assert response2.status_code == 200
    assert response2.json()["model_size"] == "base.en"

    # Invalid model returns 400
    response_invalid = client.post(
        "/api/v1/voice/stt-model",
        json={"model_size": "large-v3"},
    )
    assert response_invalid.status_code == 400



def test_transcribe_empty_file_returns_clean_empty():
    """Verify POST /api/v1/voice/transcribe with empty file returns empty transcription without error."""
    files = {"file": ("empty.wav", io.BytesIO(b""), "audio/wav")}
    response = client.post("/api/v1/voice/transcribe", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == ""
    assert data["provider"] == "faster-whisper"


def test_transcribe_with_mocked_stt_provider():
    """Verify STT transcription route coordinates correctly with underlying provider."""
    mock_transcription = MagicMock()
    mock_transcription.text = "Open Notepad"
    mock_transcription.confidence = 0.98
    mock_transcription.language = "en"
    mock_transcription.duration_seconds = 0.45
    mock_transcription.provider = "faster-whisper"

    with patch.object(voice_service, "transcribe", new=AsyncMock(return_value=mock_transcription)):
        fake_wav = b"RIFF" + b"\x00" * 200
        files = {"file": ("test.wav", io.BytesIO(fake_wav), "audio/wav")}
        response = client.post("/api/v1/voice/transcribe", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Open Notepad"
        assert data["confidence"] == 0.98

