"""Tests for Screen Perception, Multi-Monitor Capture, Local OCR, and Multimodal Vision (Phase 4)."""

import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image, ImageDraw

from app.perception.models import (
    BoundingBox,
    CaptureRegion,
    CapturedScreen,
    MonitorInfo,
    OCRLine,
    OCRResult,
    OCRWord,
    ScreenInspectRequest,
)
from app.perception.ocr_engine import LocalOCREngine, OCRError
from app.perception.screen_capture import (
    MonitorNotFoundError,
    ScreenCaptureEngine,
    ScreenCaptureError,
)
from app.perception.service import ScreenPerceptionService
from app.providers.base import ChatContextMessage


# ---------------------------------------------------------------------------
# 1. Screen Capture Unit Tests
# ---------------------------------------------------------------------------

class TestScreenCaptureEngine:
    """Test suite for MSS-based on-demand screen capture engine."""

    def test_list_monitors_enumeration(self):
        engine = ScreenCaptureEngine()
        monitors = engine.list_monitors()

        assert len(monitors) >= 1
        assert monitors[0].monitor_id == 0  # Virtual desktop
        assert monitors[0].width > 0
        assert monitors[0].height > 0
        if len(monitors) > 1:
            assert monitors[1].monitor_id == 1
            assert monitors[1].is_primary is True

    def test_capture_single_primary_monitor(self):
        engine = ScreenCaptureEngine()
        img, mon_info = engine.capture_monitor(1)

        assert isinstance(img, Image.Image)
        assert img.width > 0
        assert img.height > 0
        assert mon_info.monitor_id == 1

    def test_capture_multi_monitor_virtual_desktop(self):
        engine = ScreenCaptureEngine()
        img, mon_info = engine.capture_monitor(0)

        assert isinstance(img, Image.Image)
        assert img.width >= 100
        assert img.height >= 100
        assert mon_info.monitor_id == 0

    def test_invalid_monitor_selection_raises_error(self):
        engine = ScreenCaptureEngine()
        with pytest.raises(MonitorNotFoundError) as exc_info:
            engine.capture_monitor(999)
        assert "unavailable" in str(exc_info.value).lower()

    def test_screenshot_capture_failure_handling(self):
        engine = ScreenCaptureEngine()
        with patch("mss.MSS") as mock_mss:
            mock_inst = MagicMock()
            mock_inst.monitors = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
            mock_inst.grab.side_effect = RuntimeError("GDI display device hardware error")
            mock_mss.return_value.__enter__.return_value = mock_inst

            with pytest.raises(ScreenCaptureError) as exc_info:
                engine.capture_monitor(0)
            assert "failed" in str(exc_info.value).lower()

    def test_unified_capture_with_base64_encoding(self):
        engine = ScreenCaptureEngine()
        img, captured = engine.capture(monitor_id=1, encode_base64=True)

        assert captured.image_base64 is not None
        decoded = base64.b64decode(captured.image_base64)
        assert len(decoded) > 100  # Valid JPEG bytes
        assert captured.width == img.width
        assert captured.height == img.height


# ---------------------------------------------------------------------------
# 2. Local OCR Unit Tests
# ---------------------------------------------------------------------------

class TestLocalOCREngine:
    """Test suite for local on-device OCR engine."""

    @pytest.mark.asyncio
    async def test_ocr_text_and_bounding_box_extraction(self):
        engine = LocalOCREngine()

        # Create synthetic image with rendered text
        img = Image.new("RGB", (320, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((15, 25), "JARVIS OCR TEST 123", fill=(0, 0, 0))

        result = await engine.recognize(img)
        assert isinstance(result, OCRResult)
        assert result.duration_ms >= 0

        # If native Windows OCR is available on this runner, text is extracted with boxes
        if engine.is_available:
            assert "JARVIS" in result.full_text or "OCR" in result.full_text or result.word_count > 0
            if result.lines:
                first_line = result.lines[0]
                assert len(first_line.text) > 0
                if first_line.words:
                    word = first_line.words[0]
                    assert isinstance(word.bounding_box, BoundingBox)
                    assert word.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_ocr_empty_blank_image(self):
        engine = LocalOCREngine()
        # Pure white blank image
        blank = Image.new("RGB", (200, 200), color=(255, 255, 255))
        result = await engine.recognize(blank)

        assert isinstance(result, OCRResult)
        assert result.full_text == ""
        assert result.line_count == 0
        assert result.word_count == 0

    @pytest.mark.asyncio
    async def test_ocr_none_image_raises_error(self):
        engine = LocalOCREngine()
        with pytest.raises(OCRError):
            await engine.recognize(None)

    @pytest.mark.asyncio
    async def test_ocr_mocked_deterministic_pipeline(self):
        """Deterministic verification of bounding boxes and reading order formatting."""
        engine = LocalOCREngine()

        mock_ocr_result = MagicMock()
        mock_ocr_result.text = "Hello Iron Man"
        
        mock_word1 = MagicMock()
        mock_word1.text = "Hello"
        mock_word1.bounding_rect = MagicMock(x=10, y=15, width=40, height=20)
        
        mock_word2 = MagicMock()
        mock_word2.text = "Iron"
        mock_word2.bounding_rect = MagicMock(x=55, y=15, width=35, height=20)

        mock_line = MagicMock()
        mock_line.text = "Hello Iron"
        mock_line.words = [mock_word1, mock_word2]

        mock_ocr_result.lines = [mock_line]

        with patch("winocr.recognize_pil", new=AsyncMock(return_value=mock_ocr_result)):
            img = Image.new("RGB", (100, 50))
            engine._winocr_available = True
            res = await engine.recognize(img)

            assert res.full_text == "Hello Iron Man"
            assert res.line_count == 1
            assert res.word_count == 2
            assert res.lines[0].words[0].bounding_box.x == 10.0
            assert res.lines[0].words[1].text == "Iron"


# ---------------------------------------------------------------------------
# 3. Privacy, Consent & Visual Context Pipeline
# ---------------------------------------------------------------------------

class TestScreenPerceptionServiceAndPrivacy:
    """Test suite ensuring strict privacy and consent guarantees."""

    @pytest.mark.asyncio
    async def test_local_ocr_does_not_generate_base64_or_upload_image(self):
        service = ScreenPerceptionService()
        req = ScreenInspectRequest(
            monitor_id=1,
            include_ocr=True,
            authorize_gemini_vision=False,  # User did not authorize cloud vision
        )
        resp = await service.inspect_screen(req)

        assert resp.gemini_vision_authorized is False
        assert resp.screen.image_base64 is None  # Image NOT encoded for cloud transmission
        assert "local ocr only" in resp.message.lower()

    @pytest.mark.asyncio
    async def test_explicit_consent_enables_base64_multimodal_context(self):
        service = ScreenPerceptionService()
        req = ScreenInspectRequest(
            monitor_id=1,
            include_ocr=True,
            authorize_gemini_vision=True,  # Explicit user consent
        )
        resp = await service.inspect_screen(req)

        assert resp.gemini_vision_authorized is True
        assert resp.screen.image_base64 is not None
        assert len(resp.screen.image_base64) > 100
        assert "gemini multimodal" in resp.message.lower()

    @pytest.mark.asyncio
    async def test_gemini_provider_multimodal_message_handling(self):
        from app.providers.gemini import GeminiProvider

        provider = GeminiProvider(api_key="test-api-key")

        # Create dummy image data
        buf = io.BytesIO()
        Image.new("RGB", (50, 50), color=(0, 255, 255)).save(buf, format="PNG")
        b64_image = base64.b64encode(buf.getvalue()).decode("utf-8")

        messages = [
            ChatContextMessage(
                role="user",
                content="What is on my screen?",
                image_data=b64_image,
                image_mime_type="image/png",
            )
        ]

        # Verify that Gemini provider successfully decodes and processes multimodal image parts
        with patch.object(provider, "_get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_stream = AsyncMock()
            
            # Simulated response chunk
            mock_chunk = MagicMock()
            mock_chunk.text = "I observe your desktop screen with an active browser window, sir."
            mock_chunk.function_calls = []
            mock_chunk.candidates = []
            mock_chunk.usage_metadata = None

            async def gen():
                yield mock_chunk

            mock_client.aio.models.generate_content_stream.return_value = gen()
            mock_get_client.return_value = mock_client

            events = []
            async for evt in provider.stream_chat(messages, session_id="test-session", request_id="req-123"):
                events.append(evt)

            # Confirm call passed contents with Part containing image
            args, kwargs = mock_client.aio.models.generate_content_stream.call_args
            contents = kwargs["contents"]
            assert len(contents) == 1
            user_content = contents[0]
            assert len(user_content.parts) == 2  # Text part + Image part
            assert user_content.parts[0].text == "What is on my screen?"
            assert user_content.parts[1].inline_data is not None or hasattr(user_content.parts[1], "data")

