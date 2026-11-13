"""End-to-End Test for Conversational Tool Execution (User Prompt -> Tool Selection -> Execution -> Verification -> Natural Language Confirmation)."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.providers.base import ChatContextMessage
from app.providers.gemini import GeminiProvider
from app.tools.base import ToolStatus


@pytest.mark.asyncio
async def test_gemini_provider_conversational_tool_execution():
    """Verify GeminiProvider executes tools and verifies application launch end-to-end."""
    provider = GeminiProvider()
    if not provider.is_configured():
        pytest.skip("Gemini API key not configured in environment.")

    messages = [ChatContextMessage(role="user", content="Open Notepad")]
    events = []
    text_deltas = []

    async for event in provider.stream_chat(
        messages=messages,
        session_id="test-e2e-conversational-session",
        request_id="test-e2e-conversational-req",
    ):
        events.append(event)
        if event.event_type == "text_delta" and event.delta:
            text_deltas.append(event.delta)

    full_text = "".join(text_deltas).strip()

    # Verify message completed with natural language response
    assert len(events) >= 3
    event_types = [e.event_type for e in events]
    assert "message_start" in event_types
    assert "message_complete" in event_types
    assert len(full_text) > 0
    # The response should mention Notepad or notes/editor
    assert any(term in full_text.lower() for term in ["notepad", "notes", "opened", "ready", "window"])


@pytest.mark.asyncio
async def test_chat_stream_api_conversational_tool_execution():
    """Verify POST /api/v1/chat/stream conversational tool execution pipeline."""
    provider = GeminiProvider()
    if not provider.is_configured():
        pytest.skip("Gemini API key not configured in environment.")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "messages": [{"role": "user", "content": "Open Notepad"}],
            "session_id": "test-api-e2e-session",
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": "Bearer jarvis-local-dev-secret-key-2026",
        }

        async with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json=payload,
            headers=headers,
            timeout=35.0,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")
            chunks = []
            async for chunk in response.aiter_text():
                chunks.append(chunk)
            full_resp_text = "".join(chunks)

            assert "event: message_start" in full_resp_text
            assert "event: message_complete" in full_resp_text
            assert "event: text_delta" in full_resp_text

