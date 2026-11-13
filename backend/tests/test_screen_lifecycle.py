"""
test_screen_lifecycle.py - Phase 4.1 Perception Processing Lifecycle & State Synchronization
Validates request_id correlation, duration timings, stage propagation, and event transitions.
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import ProviderEvent, ChatContextMessage
from app.providers.gemini import GeminiProvider
from app.api.chat import format_sse


client = TestClient(app)


def test_inspect_screen_lifecycle_request_id_and_durations():
    """Verify request_id propagation and duration metrics in API response and headers."""
    req_id = "test-corr-12345"
    response = client.post(
        "/api/v1/screen/inspect",
        json={
            "request_id": req_id,
            "monitor_id": 1,
            "active_window_only": False,
            "include_ocr": True,
            "authorize_gemini_vision": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == req_id
    assert response.headers.get("X-Request-Id") == req_id
    assert "capture_duration_ms" in data
    assert "ocr_duration_ms" in data
    assert data["capture_duration_ms"] >= 0
    assert data["ocr_duration_ms"] >= 0
    assert data["stage"] == "COMPLETED"


def test_inspect_screen_auto_generates_request_id_if_omitted():
    """Verify request_id is automatically generated when not supplied by caller."""
    response = client.post(
        "/api/v1/screen/inspect",
        json={
            "monitor_id": 1,
            "active_window_only": True,
            "include_ocr": False,
            "authorize_gemini_vision": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] is not None
    assert data["request_id"].startswith("percept-")
    assert response.headers.get("X-Request-Id") == data["request_id"]


@pytest.mark.asyncio
async def test_provider_event_stage_propagation():
    """Verify ProviderEvent models support and transmit lifecycle stage identifiers."""
    event_start = ProviderEvent(
        event_type="message_start",
        request_id="req-stage-1",
        model="gemini-2.5-flash",
        stage="ANALYZING_VISION",
    )
    assert event_start.stage == "ANALYZING_VISION"
    dump_start = event_start.model_dump(exclude_none=True)
    assert dump_start["stage"] == "ANALYZING_VISION"
    sse_start = format_sse("message_start", dump_start)
    assert "event: message_start" in sse_start
    assert '"stage": "ANALYZING_VISION"' in sse_start

    event_delta = ProviderEvent(
        event_type="text_delta",
        request_id="req-stage-1",
        delta="Observing screen layout.",
        stage="GENERATING",
    )
    assert event_delta.stage == "GENERATING"
    dump_delta = event_delta.model_dump(exclude_none=True)
    assert dump_delta["stage"] == "GENERATING"

    event_done = ProviderEvent(
        event_type="message_complete",
        request_id="req-stage-1",
        full_text="Done.",
        stage="COMPLETED",
    )
    assert event_done.stage == "COMPLETED"
    dump_done = event_done.model_dump(exclude_none=True)
    assert dump_done["stage"] == "COMPLETED"


@pytest.mark.asyncio
async def test_gemini_provider_multimodal_lifecycle_stages():
    """Verify Gemini provider emits stage events during multimodal stream generation."""
    from unittest.mock import AsyncMock, patch
    provider = GeminiProvider(api_key="AIzaFakeKeyForLifecycleTest123")

    mock_chunk1 = MagicMock()
    mock_chunk1.text = "I observe an active "
    mock_chunk1.usage_metadata = None

    mock_chunk2 = MagicMock()
    mock_chunk2.text = "command prompt."
    mock_chunk2.usage_metadata = None

    async def mock_stream_gen():
        yield mock_chunk1
        yield mock_chunk2

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    events = []
    messages = [
        ChatContextMessage(
            role="user",
            content="What is on my screen?",
            image_data="fakebase64jpeg",
            image_mime_type="image/jpeg",
        )
    ]

    with patch.object(provider, "_get_client", return_value=mock_client):
        async for ev in provider.stream_chat(
            messages=messages, session_id="test-sess", request_id="req-test-stages"
        ):
            events.append(ev)

    stages = [ev.stage for ev in events if ev.stage is not None]
    # Should include ANALYZING_VISION on start, GENERATING on delta, and COMPLETED on complete
    assert "ANALYZING_VISION" in stages
    assert "GENERATING" in stages
    assert "COMPLETED" in stages
