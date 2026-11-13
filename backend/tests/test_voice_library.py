"""
Comprehensive Test Suite for J.A.R.V.I.S. Voice Library Foundation (Milestone 2.0).
Tests provider registry, voice profiles, fallback resolution, previews, and persistence.
"""

import base64
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.voice.models import (
    VoiceProfileCreate,
    VoiceProfileUpdate,
    VoicePreviewRequest,
    SpeechSynthesizeRequest,
    TTSProviderStatus,
)
from app.voice.profiles import VoiceProfileManager, profile_manager
from app.voice.service import voice_service
from app.voice.tts.registry import tts_registry

client = TestClient(app)


# --- 1. Provider Architecture & Registry Tests ---

def test_provider_registry_contains_foundation_providers():
    """Verify registry initializes with SAPI 5, Piper, and XTTS-v2 engines."""
    providers = tts_registry.list_providers()
    provider_ids = [p.id for p in providers]

    assert "sapi5" in provider_ids
    assert "piper" in provider_ids
    assert "xtts-v2" in provider_ids
    assert "voicevox" not in provider_ids


def test_sapi5_provider_health_and_discovery():
    """Verify Windows SAPI 5 is installed and operational with installed voices."""
    sapi = tts_registry.get_provider("sapi5")
    assert sapi is not None
    assert sapi.is_available() is True
    assert sapi.get_status() == TTSProviderStatus.INSTALLED_READY

    voices = sapi.list_voices()
    assert len(voices) >= 1
    # Check that voice metadata is properly enriched
    assert voices[0].provider_id == "sapi5"
    assert "Windows SAPI" in voices[0].provider_name


def test_xtts_provider_unavailable_state():
    """Verify XTTS-v2 reports not_installed gracefully without crashing."""
    xtts = tts_registry.get_provider("xtts-v2")
    assert xtts is not None
    info = xtts.get_info()
    assert info.id == "xtts-v2"
    assert info.supports_custom_voices is True

    # Unless full TTS is installed in dev, it should report not_installed
    if not xtts.is_available():
        assert info.status == TTSProviderStatus.NOT_INSTALLED
        assert "not installed" in info.error_message.lower()


def test_piper_provider_health_and_discovery():
    """Verify Piper Neural TTS reports installed and discovers pretrained voicepacks."""
    piper = tts_registry.get_provider("piper")
    assert piper is not None
    info = piper.get_info()
    assert info.id == "piper"
    assert info.is_local is True

    voices = piper.list_voices()
    assert len(voices) >= 1
    assert any("lessac" in v.id.lower() or "lessac" in v.name.lower() for v in voices)
    assert any("teto" in v.id.lower() or "teto" in v.name.lower() for v in voices)


def test_api_list_providers_endpoint():
    """Verify GET /api/v1/voice/providers returns clean provider telemetry."""
    resp = client.get("/api/v1/voice/providers")
    assert resp.status_code == 200
    providers = resp.json()
    assert isinstance(providers, list)
    ids = [p["id"] for p in providers]
    assert "sapi5" in ids
    assert "piper" in ids
    assert "xtts-v2" in ids
    assert "voicevox" not in ids


# --- 2. Voice Profiles CRUD & Persistence Tests ---

def test_default_profiles_seeded():
    """Verify baseline default profiles are seeded on initialization."""
    profiles = profile_manager.list_profiles()
    profile_ids = [p.id for p in profiles]

    assert "jarvis-default" in profile_ids
    assert "assistant-zira" in profile_ids
    assert "teto-character" in profile_ids

    teto_profile = profile_manager.get_profile("teto-character")
    assert teto_profile is not None
    assert teto_profile.provider_id == "piper"
    assert teto_profile.metadata.get("post_processor") == "rvc"

    fallback_profile = profile_manager.get_fallback_profile()
    assert fallback_profile is not None
    assert fallback_profile.provider_id == "sapi5"
    assert fallback_profile.is_fallback is True


def test_profile_creation_update_and_persistence():
    """Verify custom profile creation, modification, and persistence across restarts."""
    new_profile_data = VoiceProfileCreate(
        id="test-custom-profile",
        name="Test Tactical Officer",
        provider_id="sapi5",
        voice_id="HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0",
        language="en-US",
        rate=200,
        volume=90,
        is_favorite=True,
    )
    created = profile_manager.create_profile(new_profile_data)
    assert created.id == "test-custom-profile"
    assert created.rate == 200

    # Verify update
    updated = profile_manager.update_profile(
        "test-custom-profile",
        VoiceProfileUpdate(name="Test Tactical Officer v2", rate=220),
    )
    assert updated.name == "Test Tactical Officer v2"
    assert updated.rate == 220

    # Simulate application restart: instantiate a new manager from SQLite
    reloaded_manager = VoiceProfileManager()
    persisted = reloaded_manager.get_profile("test-custom-profile")
    assert persisted is not None
    assert persisted.name == "Test Tactical Officer v2"
    assert persisted.rate == 220

    # Clean up test profile
    profile_manager.delete_profile("test-custom-profile")
    assert profile_manager.get_profile("test-custom-profile") is None


def test_cannot_delete_fallback_profile():
    """Verify fallback profile is protected from accidental deletion."""
    fallback = profile_manager.get_fallback_profile()
    assert fallback is not None
    with pytest.raises(ValueError, match="Cannot delete designated fallback"):
        profile_manager.delete_profile(fallback.id)


def test_set_active_profile():
    """Verify switching active profile updates default flags."""
    # Switch to assistant-zira
    activated = profile_manager.set_active_profile("assistant-zira")
    assert activated.id == "assistant-zira"
    assert activated.is_default is True

    current_active = profile_manager.get_active_profile()
    assert current_active.id == "assistant-zira"

    # Switch back to jarvis-default
    profile_manager.set_active_profile("jarvis-default")
    assert profile_manager.get_active_profile().id == "jarvis-default"


# --- 3. Fallback Resolution & Synthesis Tests ---

@pytest.mark.asyncio
async def test_automatic_fallback_when_provider_unavailable():
    """Verify synthesis automatically falls back to SAPI when target engine is offline."""
    # Request synthesis with custom-xtts (uninstalled/offline local engine)
    req = SpeechSynthesizeRequest(
        text="Testing automated fallback protocol.",
        profile_id="custom-xtts",
    )
    res = await voice_service.synthesize(req)

    assert res.audio_base64 is not None
    # Verify fallback telemetry
    assert res.fallback_applied is True
    assert res.fallback_reason is not None
    assert "unavailable" in res.fallback_reason.lower()
    assert res.provider_used == "sapi5"

    decoded = base64.b64decode(res.audio_base64)
    assert decoded.startswith(b"RIFF")


@pytest.mark.asyncio
async def test_preview_generation():
    """Verify voice preview synthesis for a profile."""
    prev_req = VoicePreviewRequest(
        profile_id="jarvis-default",
        text="Previewing J.A.R.V.I.S. speech engine.",
    )
    res = await voice_service.generate_preview(prev_req)
    assert res.audio_base64 is not None
    assert res.mime_type == "audio/wav"

    decoded = base64.b64decode(res.audio_base64)
    assert decoded.startswith(b"RIFF")


# --- 4. API Endpoints Tests ---

def test_api_profiles_crud_endpoints():
    """Verify REST API endpoints for profiles."""
    # GET /profiles
    res_list = client.get("/api/v1/voice/profiles")
    assert res_list.status_code == 200
    profiles = res_list.json()
    assert len(profiles) >= 3

    # GET /profiles/active
    res_active = client.get("/api/v1/voice/profiles/active")
    assert res_active.status_code == 200
    assert "id" in res_active.json()

    # POST /profiles
    create_payload = {
        "id": "api-test-profile",
        "name": "API Test Voice",
        "provider_id": "sapi5",
        "voice_id": "default",
        "rate": 190,
        "volume": 85,
    }
    res_create = client.post("/api/v1/voice/profiles", json=create_payload)
    assert res_create.status_code == 201
    assert res_create.json()["id"] == "api-test-profile"

    # POST /profiles/active
    res_switch = client.post(
        "/api/v1/voice/profiles/active",
        json={"profile_id": "api-test-profile"},
    )
    assert res_switch.status_code == 200
    assert res_switch.json()["id"] == "api-test-profile"

    # Switch back to jarvis-default before deletion
    client.post(
        "/api/v1/voice/profiles/active",
        json={"profile_id": "jarvis-default"},
    )

    # DELETE /profiles/{id}
    res_del = client.delete("/api/v1/voice/profiles/api-test-profile")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "deleted"


def test_api_voice_preview_endpoint():
    """Verify POST /api/v1/voice/preview endpoint."""
    res = client.post(
        "/api/v1/voice/preview",
        json={"profile_id": "jarvis-default"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "audio_base64" in data
    assert data["mime_type"] == "audio/wav"

