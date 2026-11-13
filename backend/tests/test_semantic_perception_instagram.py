"""Automated Test Suite for Semantic Perception & Instagram Conversation Extraction (Phase 5/5.2)."""

from typing import Any, List
import pytest

from app.perception.models import BoundingBox, OCRLine, OCRWord
from app.perception.semantic.classifier import semantic_perception_engine
from app.perception.semantic.instagram import instagram_semantic_classifier
from app.perception.semantic.tools import (
    SemanticReadConversationsParams,
    SemanticReadConversationsTool,
)
from app.tools.base import ExecutionContext


def _make_mock_ocr_line(text: str, x: int, y: int, width: int, height: int) -> OCRLine:
    """Helper to generate realistic OCRLine with bounding box and word models."""
    words = []
    word_tokens = text.split()
    if word_tokens:
        w_width = max(1, width // len(word_tokens))
        for i, token in enumerate(word_tokens):
            words.append(
                OCRWord(
                    text=token,
                    bounding_box=BoundingBox(
                        x=x + i * w_width,
                        y=y,
                        width=w_width,
                        height=height,
                    ),
                    confidence=0.98,
                )
            )
    return OCRLine(
        text=text,
        words=words,
    )


def test_instagram_semantic_perception_isolates_notes_and_authors():
    """Verify Instagram perception strictly separates Notes from genuine conversation rows.

    Screen Layout Simulation:
    - Left Nav: Home, Messages, Profile (X: 10 - 70)
    - Inbox Column (X: 90 - 420):
      * Notes Tray (Y: 70 - 180):
        - Note bubble: "Coffee vibes ☕" (X: 110, Y: 80)
        - Note author: "sarah_99" (X: 110, Y: 130)
        - Note bubble: "Study mode 📚" (X: 200, Y: 80)
        - Note author: "alex_dev" (X: 200, Y: 130)
      * Search Bar (Y: 210 - 240): "Search"
      * Filter Tabs (Y: 250 - 270): "Primary", "General", "Requests"
      * Genuine Conversation 1 (Y: 290 - 330):
        - Name: "David Miller" (X: 140, Y: 295)
        - Preview: "Active 2h ago" (X: 140, Y: 315)
      * Genuine Conversation 2 (Y: 350 - 390):
        - Name: "Tech Community" (X: 140, Y: 355)
        - Preview: "You: Checked the PR · 1d" (X: 140, Y: 375)
      * Genuine Conversation 3 (Y: 410 - 450):
        - Name: "Emma Watson" (X: 140, Y: 415)
        - Preview: "Sent a reel • 4h" (X: 140, Y: 435)
    - Right Pane (X: 480 - 1200):
      * Header (Y: 80 - 120): "David Miller", "Audio Call", "Video Call"
    """
    ocr_lines = [
        # Left Nav
        _make_mock_ocr_line("Messages", 15, 100, 50, 20),
        _make_mock_ocr_line("Profile", 15, 200, 50, 20),

        # Top Notes Tray
        _make_mock_ocr_line("Coffee vibes ☕", 110, 80, 80, 20),
        _make_mock_ocr_line("sarah_99", 110, 130, 70, 18),
        _make_mock_ocr_line("Study mode 📚", 200, 80, 80, 20),
        _make_mock_ocr_line("alex_dev", 200, 130, 70, 18),

        # Search & Tabs
        _make_mock_ocr_line("Search", 120, 215, 60, 20),
        _make_mock_ocr_line("Primary", 120, 255, 50, 16),
        _make_mock_ocr_line("General", 190, 255, 50, 16),

        # Real Conversation 1
        _make_mock_ocr_line("David Miller", 140, 295, 90, 20),
        _make_mock_ocr_line("Active 2h ago", 140, 318, 80, 16),

        # Real Conversation 2
        _make_mock_ocr_line("Tech Community", 140, 355, 110, 20),
        _make_mock_ocr_line("You: Checked the PR · 1d", 140, 378, 140, 16),

        # Real Conversation 3
        _make_mock_ocr_line("Emma Watson", 140, 415, 95, 20),
        _make_mock_ocr_line("Sent a reel • 4h", 140, 438, 100, 16),

        # Active Chat Header in Right Pane
        _make_mock_ocr_line("David Miller", 500, 85, 100, 24),
        _make_mock_ocr_line("Audio Call", 700, 85, 60, 20),
    ]

    res = instagram_semantic_classifier.classify_screen(
        ocr_lines=ocr_lines,
        screen_width=1280,
        screen_height=800,
        window_title="Instagram Direct • Opera GX",
    )

    # 1. Verification of Notes Isolation (Zero False Positives)
    # Neither 'sarah_99' nor 'alex_dev' nor their note contents should appear in conversations!
    verified_names = [c.contact_name for c in res.verified_conversations]
    assert "sarah_99" not in verified_names, "Instagram note author must NOT be classified as a conversation"
    assert "alex_dev" not in verified_names, "Instagram note author must NOT be classified as a conversation"
    assert "Coffee vibes ☕" not in verified_names
    assert "Study mode 📚" not in verified_names

    # Check that Notes are cleanly isolated in detected_notes
    assert len(res.detected_notes) >= 2
    note_texts = [n.note_text for n in res.detected_notes]
    assert any("Coffee vibes" in t for t in note_texts)
    assert any("Study mode" in t for t in note_texts)

    # 2. Verification of Genuine Conversations (High Precision & Recall)
    assert len(res.verified_conversations) == 3
    assert "David Miller" in verified_names
    assert "Tech Community" in verified_names
    assert "Emma Watson" in verified_names

    # Check previews and unread indicators
    david_conv = next(c for c in res.verified_conversations if c.contact_name == "David Miller")
    assert "Active 2h ago" in (david_conv.last_message_preview or "")
    assert david_conv.confidence_level == "HIGH"

    emma_conv = next(c for c in res.verified_conversations if c.contact_name == "Emma Watson")
    assert emma_conv.is_unread is True

    # 3. Verification of Active Open Conversation in Right Pane
    assert res.open_conversation is not None
    assert res.open_conversation.contact_name == "David Miller"
    assert res.open_conversation.is_currently_open is True


def test_semantic_perception_engine_dispatcher():
    """Verify SemanticPerceptionEngine routes properly by application name."""
    ocr_lines = [
        _make_mock_ocr_line("Chats", 50, 50, 50, 20),
        _make_mock_ocr_line("Alice Cooper", 50, 100, 90, 20),
        _make_mock_ocr_line("See you at 5", 50, 125, 80, 16),
    ]

    # Test generic WhatsApp dispatch
    res = semantic_perception_engine.analyze_screen(
        app_name="WhatsApp",
        ocr_lines=ocr_lines,
        screen_width=1000,
        screen_height=700,
    )
    assert res.application_name == "WhatsApp"
    assert len(res.verified_conversations) == 1
    assert res.verified_conversations[0].contact_name == "Alice Cooper"


@pytest.mark.asyncio
async def test_semantic_read_conversations_tool(monkeypatch):
    """Verify SemanticReadConversationsTool returns structured JSON."""
    from app.perception.models import CapturedScreen, OCRResult, ScreenInspectResponse
    from app.perception.service import screen_perception_service

    mock_lines = [
        _make_mock_ocr_line("Search", 120, 100, 50, 20),
        _make_mock_ocr_line("Bob Jones", 120, 150, 80, 20),
        _make_mock_ocr_line("Can you call me?", 120, 175, 100, 16),
    ]
    mock_resp = ScreenInspectResponse(
        screen=CapturedScreen(
            monitor_id=1,
            width=1280,
            height=720,
            captured_at="2026-11-13T12:00:00Z",
            active_window_title="Instagram • Google Chrome",
            ocr_result=OCRResult(
                full_text="Bob Jones Can you call me?",
                lines=mock_lines,
                language="en",
            ),
        )
    )

    async def mock_inspect(req):
        return mock_resp

    monkeypatch.setattr(screen_perception_service, "inspect_screen", mock_inspect)

    tool = SemanticReadConversationsTool()
    ctx = ExecutionContext(execution_id="test-sem-exec")

    res = await tool.execute(
        SemanticReadConversationsParams(app_name="Instagram"),
        ctx,
    )

    assert res.success is True
    assert res.data["application"] == "Instagram"
    assert res.data["total_conversations_found"] == 1
    assert res.data["verified_conversations"][0]["contact_name"] == "Bob Jones"
