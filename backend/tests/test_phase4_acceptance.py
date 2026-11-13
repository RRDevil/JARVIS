"""Phase 4 Acceptance Test Verification Suite.

Validates:
- Test A: Screen understanding with explicit user authorization and multimodal vision.
- Test B: Local OCR without cloud upload.
- Test C: Privacy (ordinary chat does not capture screen or upload images).
- Test D: Approval rejection producing a distinct conversation cancellation message.
- Test E: Multi-monitor capture and metadata verification.
"""

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image

from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.execution.approval import approval_manager
from app.execution.engine import execution_engine
from app.main import app
from app.perception.models import ScreenInspectRequest
from app.perception.screen_capture import screen_capture_engine
from app.perception.service import screen_perception_service
from app.providers.base import ChatContextMessage
from app.providers.gemini import GeminiProvider
from app.tools.base import ToolStatus
from app.tools.defaults import register_default_windows_tools

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_acceptance_env():
    mock_platform = MockPlatformAdapter()
    set_platform_adapter(mock_platform)
    register_default_windows_tools()
    approval_manager.clear()
    with execution_engine._lock:
        execution_engine._executions.clear()
    yield mock_platform
    approval_manager.clear()
    with execution_engine._lock:
        execution_engine._executions.clear()
    set_platform_adapter(None)


class TestPhase4Acceptance:
    """Rigorous acceptance test suite matching Phase 4 requirements."""

    # -----------------------------------------------------------------------
    # Test A: Screen Understanding with Consent and Multimodal Reasoning
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_acceptance_a_screen_understanding(self):
        """User: 'What is on my screen?'
        
        Workflow:
        1. User authorizes external processing.
        2. Screen captured.
        3. Local OCR runs.
        4. Gemini receives authorized multimodal visual context.
        5. Natural language response returned.
        """
        # Step 1 & 2 & 3: Screen capture and local OCR executed under explicit consent
        req = ScreenInspectRequest(
            monitor_id=1,
            active_window_only=False,
            include_ocr=True,
            authorize_gemini_vision=True,  # Explicit user consent
        )
        resp = await screen_perception_service.inspect_screen(req)

        assert resp.gemini_vision_authorized is True
        assert resp.screen.image_base64 is not None
        assert resp.screen.width > 0
        assert resp.screen.ocr_result is not None

        # Step 4 & 5: Gemini Multimodal Vision Reasoning
        provider = GeminiProvider(api_key="test-key")
        messages = [
            ChatContextMessage(
                role="user",
                content="What is on my screen?",
                image_data=resp.screen.image_base64,
                image_mime_type="image/jpeg",
            )
        ]

        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "You are currently viewing a web browser and an active terminal window, sir."
            mock_chunk.function_calls = []
            mock_chunk.candidates = []
            mock_chunk.usage_metadata = None

            async def mock_stream():
                yield mock_chunk

            mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream())
            mock_get_client.return_value = mock_client

            streamed_text = ""
            async for evt in provider.stream_chat(messages, session_id="test-session", request_id="req-a"):
                if evt.event_type == "text_delta" and evt.delta:
                    streamed_text += evt.delta

            # Step 6: Verified natural language explanation produced
            assert "terminal window" in streamed_text or "browser" in streamed_text

    # -----------------------------------------------------------------------
    # Test B: Local OCR Without Cloud Upload
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_acceptance_b_local_ocr_purely_on_device(self):
        """User: 'Read the text on my screen.'
        
        Expected:
        - OCR runs locally on device.
        - Extracted text is returned.
        - No screenshot is uploaded or encoded for external transmission.
        """
        req = ScreenInspectRequest(
            monitor_id=1,
            active_window_only=True,
            include_ocr=True,
            authorize_gemini_vision=False,  # Cloud upload disabled
        )
        resp = await screen_perception_service.inspect_screen(req)

        # Image is strictly NOT encoded for transmission
        assert resp.gemini_vision_authorized is False
        assert resp.screen.image_base64 is None
        assert resp.screen.ocr_result is not None
        assert isinstance(resp.screen.ocr_result.full_text, str)
        assert "local ocr only" in resp.message.lower()

    # -----------------------------------------------------------------------
    # Test C: Privacy — Ordinary Chat Does Not Capture Screen
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_acceptance_c_privacy_ordinary_chat_does_not_capture(self):
        """User asks an ordinary question.
        
        Expected:
        - No screenshot is captured.
        - No image is uploaded.
        """
        provider = GeminiProvider(api_key="test-key")
        messages = [
            ChatContextMessage(
                role="user",
                content="What is the distance to the moon?",
                image_data=None,  # No visual context
            )
        ]

        with patch.object(provider, "_get_client") as mock_get_client, \
             patch.object(screen_capture_engine, "capture") as mock_capture:

            mock_client = MagicMock()
            mock_chunk = MagicMock()
            mock_chunk.text = "The average distance to the Moon is approximately 384,400 kilometers, sir."
            mock_chunk.function_calls = []
            mock_chunk.candidates = []
            mock_chunk.usage_metadata = None

            async def mock_stream():
                yield mock_chunk

            mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream())
            mock_get_client.return_value = mock_client

            async for _ in provider.stream_chat(messages, session_id="test-session", request_id="req-c"):
                pass

            # Verify screen capture engine was NEVER invoked during ordinary conversation
            mock_capture.assert_not_called()

            # Verify payload contained only text, NO image part
            args, kwargs = mock_client.aio.models.generate_content_stream.call_args
            contents = kwargs["contents"]
            assert len(contents[0].parts) == 1
            assert contents[0].parts[0].text == "What is the distance to the moon?"

    # -----------------------------------------------------------------------
    # Test D: Approval Rejection Produces Separate Conversation Message
    # -----------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_acceptance_d_approval_rejection_message(self):
        """User rejects a pending consequential action.
        
        Expected:
        - The backend rejects the action.
        - No execution occurs.
        - A separate distinct JARVIS message appears in the conversation.
        - The message clearly explains that the action was cancelled.
        """
        exec_model, approval = await execution_engine.propose(
            tool_name="windows_close_window",
            raw_parameters={"handle": 1002},
            session_id="session-acc-d",
        )
        assert approval is not None

        # Rejection API call
        resp = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": False},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Outcome checks
        assert data["approval"]["status"] == "rejected"
        assert data["execution"]["status"] == "rejected"
        assert data["conversation_message"] == "Understood. I've cancelled that action as requested. Nothing was changed."

        # Confirm tool was not executed
        assert execution_engine.get_execution(approval.toolExecutionId).status == ToolStatus.REJECTED

    # -----------------------------------------------------------------------
    # Test E: Multiple Monitors Enumeration & Capture
    # -----------------------------------------------------------------------
    def test_acceptance_e_multiple_monitors(self):
        """Capture each available monitor and verify correct images and metadata."""
        monitors = screen_capture_engine.list_monitors()
        assert len(monitors) >= 1

        for mon in monitors:
            img, info = screen_capture_engine.capture_monitor(mon.monitor_id)
            assert isinstance(img, Image.Image)
            assert img.width == mon.width
            assert img.height == mon.height
            assert info.monitor_id == mon.monitor_id
