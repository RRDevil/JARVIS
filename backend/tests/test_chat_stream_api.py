"""Automated integration tests for SSE streaming chat endpoint."""

import json
import pytest
from unittest.mock import AsyncMock
from app.providers.base import BaseAIProvider, ProviderEvent, UsageMetadata
from app.providers.factory import set_ai_provider_override


class MockTestProvider(BaseAIProvider):
    """Mock provider for deterministic SSE endpoint testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def is_configured(self) -> bool:
        return True

    def get_model_name(self) -> str:
        return "mock-gemini-test"

    async def stream_chat(self, messages, session_id, request_id):
        if self.should_fail:
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="MOCK_FAILURE",
                error_message="Simulated mock failure",
            )
            return

        yield ProviderEvent(
            event_type="message_start",
            request_id=request_id,
            session_id=session_id,
            model="mock-gemini-test",
        )
        yield ProviderEvent(
            event_type="text_delta",
            request_id=request_id,
            session_id=session_id,
            delta="Greetings, ",
        )
        yield ProviderEvent(
            event_type="text_delta",
            request_id=request_id,
            session_id=session_id,
            delta="Sir.",
        )
        yield ProviderEvent(
            event_type="usage",
            request_id=request_id,
            session_id=session_id,
            usage=UsageMetadata(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        yield ProviderEvent(
            event_type="message_complete",
            request_id=request_id,
            session_id=session_id,
            full_text="Greetings, Sir.",
            duration_ms=45.2,
        )


def parse_sse_stream(stream_text: str):
    """Parse raw SSE text into a list of (event_type, json_data) tuples."""
    events = []
    blocks = [b.strip() for b in stream_text.strip().split("\n\n") if b.strip()]

    for block in blocks:
        lines = block.split("\n")
        event_name = "message"
        data_str = ""

        for line in lines:
            if line.startswith("event:"):
                event_name = line.replace("event:", "").strip()
            elif line.startswith("data:"):
                data_str = line.replace("data:", "").strip()

        if data_str:
            events.append((event_name, json.loads(data_str)))

    return events


def test_chat_stream_endpoint_success(client):
    """Verify POST /api/v1/chat/stream returns valid SSE format and events."""
    mock_provider = MockTestProvider()
    set_ai_provider_override(mock_provider)

    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "messages": [
                    {"role": "user", "content": "Hello JARVIS"}
                ],
                "session_id": "test-session-42",
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert response.headers["X-Session-Id"] == "test-session-42"

        events = parse_sse_stream(response.text)
        assert len(events) == 5

        assert events[0][0] == "message_start"
        assert events[0][1]["model"] == "mock-gemini-test"

        assert events[1][0] == "text_delta"
        assert events[1][1]["delta"] == "Greetings, "

        assert events[2][0] == "text_delta"
        assert events[2][1]["delta"] == "Sir."

        assert events[3][0] == "usage"
        assert events[3][1]["usage"]["total_tokens"] == 15

        assert events[4][0] == "message_complete"
        assert events[4][1]["full_text"] == "Greetings, Sir."

    finally:
        set_ai_provider_override(None)


def test_chat_stream_input_validation(client):
    """Verify input validation rejecting invalid roles, empty messages, or excessive size."""
    # 1. Empty message list
    resp = client.post("/api/v1/chat/stream", json={"messages": []})
    assert resp.status_code == 422

    # 2. Last message must be from user
    resp = client.post(
        "/api/v1/chat/stream",
        json={
            "messages": [
                {"role": "user", "content": "Question"},
                {"role": "assistant", "content": "Answer"},
            ]
        },
    )
    assert resp.status_code == 422

    # 3. Excessive message count
    many_messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
        for i in range(25)
    ]
    resp = client.post("/api/v1/chat/stream", json={"messages": many_messages})
    assert resp.status_code == 422


def test_chat_stream_session_isolation(client):
    """Verify distinct session identifiers are respected in headers and event streams."""
    mock_provider = MockTestProvider()
    set_ai_provider_override(mock_provider)

    try:
        resp_a = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "User A"}], "session_id": "sess-alpha"},
        )
        resp_b = client.post(
            "/api/v1/chat/stream",
            json={"messages": [{"role": "user", "content": "User B"}], "session_id": "sess-beta"},
        )

        assert resp_a.headers["X-Session-Id"] == "sess-alpha"
        assert resp_b.headers["X-Session-Id"] == "sess-beta"

        events_a = parse_sse_stream(resp_a.text)
        events_b = parse_sse_stream(resp_b.text)

        assert events_a[0][1]["session_id"] == "sess-alpha"
        assert events_b[0][1]["session_id"] == "sess-beta"
    finally:
        set_ai_provider_override(None)

