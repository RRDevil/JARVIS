"""Unit tests for GeminiProvider and AI provider abstraction."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.providers.base import ChatContextMessage, ProviderEvent
from app.providers.gemini import GeminiProvider


@pytest.mark.asyncio
async def test_gemini_unconfigured_yields_error():
    """Verify provider safely reports unconfigured state when API key is missing."""
    provider = GeminiProvider(api_key="")
    assert not provider.is_configured()

    events = []
    async for event in provider.stream_chat(
        messages=[ChatContextMessage(role="user", content="Hello")],
        session_id="test-sess",
        request_id="test-req",
    ):
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "error"
    assert events[0].error_code == "API_KEY_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_gemini_empty_conversation_yields_error():
    """Verify provider rejects empty messages context."""
    provider = GeminiProvider(api_key="valid-mock-key")
    assert provider.is_configured()

    events = []
    async for event in provider.stream_chat(
        messages=[],
        session_id="test-sess",
        request_id="test-req",
    ):
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "error"
    assert events[0].error_code == "EMPTY_CONVERSATION"


@pytest.mark.asyncio
async def test_gemini_streaming_success_with_mocked_sdk():
    """Verify successful streaming lifecycle: message_start -> text_delta -> usage -> message_complete."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-2.5-flash")

    # Mock chunk objects
    chunk1 = MagicMock()
    chunk1.text = "Hello! "
    chunk1.usage_metadata = None

    chunk2 = MagicMock()
    chunk2.text = "I am JARVIS."
    um_mock = MagicMock()
    um_mock.prompt_token_count = 12
    um_mock.candidates_token_count = 8
    um_mock.total_token_count = 20
    chunk2.usage_metadata = um_mock

    async def mock_stream_gen():
        yield chunk1
        yield chunk2

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    with patch.object(provider, "_get_client", return_value=mock_client):
        events = []
        async for ev in provider.stream_chat(
            messages=[
                ChatContextMessage(role="system", content="Be helpful."),
                ChatContextMessage(role="user", content="Introduce yourself."),
            ],
            session_id="sess-001",
            request_id="req-001",
        ):
            events.append(ev)

        event_types = [e.event_type for e in events]
        assert event_types == ["message_start", "text_delta", "text_delta", "usage", "message_complete"]

        assert events[0].model == "gemini-2.5-flash"
        assert events[1].delta == "Hello! "
        assert events[2].delta == "I am JARVIS."

        assert events[3].usage is not None
        assert events[3].usage.input_tokens == 12
        assert events[3].usage.output_tokens == 8
        assert events[3].usage.total_tokens == 20

        assert events[4].full_text == "Hello! I am JARVIS."
        assert events[4].duration_ms is not None
        assert events[4].duration_ms >= 0


@pytest.mark.asyncio
async def test_gemini_timeout_handling():
    """Verify upstream timeouts yield structured error events."""
    provider = GeminiProvider(api_key="test-api-key", timeout_seconds=0.01)

    async def slow_stream():
        import asyncio
        await asyncio.sleep(0.5)
        yield MagicMock(text="Delayed")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=slow_stream())

    with patch.object(provider, "_get_client", return_value=mock_client):
        events = []
        async for ev in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Ping")],
            session_id="sess-002",
            request_id="req-002",
        ):
            events.append(ev)

        assert any(e.event_type == "error" and e.error_code == "UPSTREAM_TIMEOUT" for e in events)


@pytest.mark.asyncio
async def test_gemini_error_redacts_api_key():
    """Verify error messages sanitize and never leak API key strings."""
    secret_key = "secret-key-xyz-12345"
    provider = GeminiProvider(api_key=secret_key)

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=RuntimeError(f"Failed with key {secret_key}")
    )

    with patch.object(provider, "_get_client", return_value=mock_client):
        events = []
        async for ev in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Ping")],
            session_id="sess-003",
            request_id="req-003",
        ):
            events.append(ev)

        err_event = [e for e in events if e.event_type == "error"][0]
        assert secret_key not in err_event.error_message
        assert "[REDACTED_API_KEY]" in err_event.error_message

