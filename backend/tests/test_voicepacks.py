"""
Test Suite for Pretrained Voicepack Management & Security.
Tests safe zip extraction, path traversal defense, file whitelisting,
metadata parsing, profile auto-generation, and deletion.
"""

from io import BytesIO
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import zipfile

from app.main import app
from app.voice.models import VoicepackStatus, SpeechSynthesizeRequest
from app.voice.voicepacks import voicepack_manager
from app.voice.profiles import profile_manager
from app.voice.service import voice_service

client = TestClient(app)


def create_dummy_voicepack_zip(
    voice_name: str = "test-voice",
    has_onnx: bool = True,
    has_json: bool = True,
    illegal_files: dict = None,
    malicious_paths: dict = None,
) -> bytes:
    """Helper to synthesize a test zip archive with specified file payloads."""
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if has_onnx:
            zf.writestr(f"{voice_name}.onnx", b"FAKE_ONNX_MODEL_TENSORS")
        if has_json:
            config = {
                "audio": {"sample_rate": 22050},
                "num_speakers": 1,
                "espeak": {"voice": "en-US"},
                "dataset": "Test Synthetic Dataset",
                "license": "MIT",
                "attribution": "Unit Tester",
            }
            zf.writestr(f"{voice_name}.onnx.json", json.dumps(config))
        if illegal_files:
            for fname, content in illegal_files.items():
                zf.writestr(fname, content)
        if malicious_paths:
            for fname, content in malicious_paths.items():
                zf.writestr(fname, content)

    return buffer.getvalue()


def test_voicepack_discovery_baseline():
    """Verify built-in or default installed voicepack is discovered."""
    voicepacks = voicepack_manager.list_voicepacks()
    assert len(voicepacks) >= 1
    lessac = next((vp for vp in voicepacks if "lessac" in vp.id.lower()), None)
    assert lessac is not None
    assert lessac.sample_rate == 22050
    assert lessac.status == VoicepackStatus.INSTALLED


def test_safe_voicepack_import_and_profile_generation():
    """Verify importing a valid voicepack zip extracts safely and generates a profile."""
    zip_bytes = create_dummy_voicepack_zip(voice_name="unit-test-voice")
    
    res = voice_service.import_voicepack(zip_bytes, filename="unit-test-voice.zip")
    assert res.success is True
    assert res.voicepack is not None
    assert res.voicepack.id == "unit-test-voice"
    assert res.profile_created is not None
    assert res.profile_created.id == "piper-unit-test-voice"

    # Verify indexed in manager
    indexed = voicepack_manager.get_voicepack("unit-test-voice")
    assert indexed is not None

    # Verify voice profile persists
    prof = profile_manager.get_profile("piper-unit-test-voice")
    assert prof is not None
    assert prof.voice_id == "unit-test-voice"

    # Clean up
    del_ok, _ = voice_service.delete_voicepack("unit-test-voice")
    assert del_ok is True
    assert voicepack_manager.get_voicepack("unit-test-voice") is None
    assert profile_manager.get_profile("piper-unit-test-voice") is None


def test_security_path_traversal_rejection():
    """Verify archive containing path traversal (zip-slip) is blocked."""
    zip_bytes = create_dummy_voicepack_zip(
        voice_name="traversal-test",
        malicious_paths={"../../evil.txt": b"Malicious payload"},
    )
    success, msg, vp = voicepack_manager.import_from_zip(zip_bytes)
    assert success is False
    assert "security violation" in msg.lower() or "traversal" in msg.lower()
    assert vp is None


def test_security_prohibited_extension_rejection():
    """Verify archive containing executable or forbidden files is blocked."""
    zip_bytes = create_dummy_voicepack_zip(
        voice_name="bad-ext-test",
        illegal_files={"payload.exe": b"MZ\x90\x00Binary"},
    )
    success, msg, vp = voicepack_manager.import_from_zip(zip_bytes)
    assert success is False
    assert "prohibited file extension" in msg.lower() or "security violation" in msg.lower()
    assert vp is None


def test_missing_onnx_rejection():
    """Verify archive missing .onnx model is rejected."""
    zip_bytes = create_dummy_voicepack_zip(voice_name="no-onnx", has_onnx=False)
    success, msg, vp = voicepack_manager.import_from_zip(zip_bytes)
    assert success is False
    assert "no .onnx" in msg.lower()


def test_api_voicepacks_endpoints():
    """Verify GET, POST import, and DELETE endpoints via FastAPI."""
    # 1. GET /api/v1/voice/voicepacks
    resp = client.get("/api/v1/voice/voicepacks")
    assert resp.status_code == 200
    packs = resp.json()
    assert isinstance(packs, list)

    # 2. POST /api/v1/voice/voicepacks/import
    zip_bytes = create_dummy_voicepack_zip(voice_name="api-test-voice")
    upload_resp = client.post(
        "/api/v1/voice/voicepacks/import",
        files={"file": ("api-test-voice.zip", zip_bytes, "application/zip")},
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["success"] is True
    assert data["voicepack"]["id"] == "api-test-voice"

    # 3. DELETE /api/v1/voice/voicepacks/{id}
    del_resp = client.delete("/api/v1/voice/voicepacks/api-test-voice")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_piper_actual_synthesis():
    """Verify actual speech synthesis through Piper provider."""
    req = SpeechSynthesizeRequest(
        text="Testing universal Piper synthesis pipeline.",
        provider_id="piper",
        voice_id="en_US-lessac-medium",
        rate=180,
        volume=100,
    )
    res = await voice_service.synthesize(req)
    assert res.audio_base64 is not None
    assert len(res.audio_base64) > 500
    assert res.provider_used == "piper"
    assert res.fallback_applied is False
