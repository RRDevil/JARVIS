"""Opt-in live integration test with real Google Gemini API.

Note: This test runs ONLY when a real GEMINI_API_KEY is configured in the environment.
It communicates with Google's live API servers and may incur quota/token usage.
"""

import os
import pytest
from app.core.config import settings
from app.providers.base import ChatContextMessage
from app.providers.gemini import GeminiProvider

API_KEY = settings.GEMINI_API_KEY
IS_REAL_KEY = bool(API_KEY and API_KEY.strip() and API_KEY != "your_gemini_api_key_here")


@pytest.mark.skipif(not IS_REAL_KEY, reason="Live Gemini API test skipped: GEMINI_API_KEY not set in environment.")
@pytest.mark.asyncio
async def test_live_gemini_streaming_generation():
    """Verify live end-to-end streaming response from Google Gemini servers."""
    provider = GeminiProvider()
    assert provider.is_configured()

    events = []
    async for event in provider.stream_chat(
        messages=[
            ChatContextMessage(role="user", content="Hello JARVIS, please confirm system readiness in one sentence.")
        ],
        session_id="live-test-sess",
        request_id="live-test-req",
    ):
        print(f"EVENT: {event.event_type} | code={getattr(event, 'error_code', None)} | msg={getattr(event, 'error_message', None)}")
        events.append(event)

    types = [e.event_type for e in events]
    assert "message_start" in types
    assert "text_delta" in types
    assert "message_complete" in types

    complete_event = [e for e in events if e.event_type == "message_complete"][0]
    assert complete_event.full_text is not None
    assert len(complete_event.full_text) > 0

