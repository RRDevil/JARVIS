"""Unit and Integration Tests for J.A.R.V.I.S. Task Narration Subsystem (Phase 5.3).

Verifies:
1. Immediate task acknowledgment across user intents.
2. Suppression of acknowledgments for internal system/approval continuation prompts.
3. Grounded action started progress narration.
4. Throttling of rapid/repetitive progress events.
5. Consequential approval request narration and friendly domain extraction.
6. Approval granted / denied speech.
7. Error and recovery announcements with trace sanitization.
8. Accurate task completion announcement gating (suppressed if approval pending or cancelled).
9. Narration REST API endpoints (/api/v1/voice/narration/*).
"""

import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.voice.narration import (
    NarrationPriority,
    NarrationSettings,
    TaskLifecycleEventType,
    TaskNarrationEngine,
    task_narration_engine,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def clean_engine():
    engine = TaskNarrationEngine(
        settings=NarrationSettings(
            enabled=True,
            progress_interval_seconds=2.0,  # 2s for fast testing
            acknowledge_tasks=True,
            announce_approvals=True,
            announce_errors=True,
            announce_progress=True,
            announce_completion=True,
        )
    )
    return engine


class TestTaskNarrationEngine:
    """Core logic testing for TaskNarrationEngine."""

    def test_immediate_acknowledgment_formulations(self, clean_engine):
        task_id = "task-test-ack"

        # 1. Instagram / Browser
        ev1 = clean_engine.generate_acknowledgment("Open Opera GX and go to Instagram", task_id)
        assert ev1 is not None
        assert ev1.event_type == TaskLifecycleEventType.TASK_ACKNOWLEDGED
        assert ev1.priority == NarrationPriority.ACKNOWLEDGMENT
        assert "Instagram" in ev1.narration_text

        # 2. YouTube
        ev2 = clean_engine.generate_acknowledgment("Play music on YouTube", task_id)
        assert "YouTube" in ev2.narration_text

        # 3. Desktop Application
        ev3 = clean_engine.generate_acknowledgment("Launch Notepad please", task_id)
        assert "Notepad" in ev3.narration_text

        # 4. Grounded Clicking
        ev4 = clean_engine.generate_acknowledgment("Click the blue button in the center", task_id)
        assert "Locating" in ev4.narration_text

        # 5. Document Preparation
        ev5 = clean_engine.generate_acknowledgment("Write a report in Word document", task_id)
        assert "Word" in ev5.narration_text or "workspace" in ev5.narration_text

        # 6. General query
        ev6 = clean_engine.generate_acknowledgment("What time is it in Tokyo?", task_id)
        assert "Understood" in ev6.narration_text

    def test_suppression_of_internal_prompts(self, clean_engine):
        task_id = "task-sys-prompt"

        # Internal continuation prompt following user approval must NOT trigger acknowledgment
        ev1 = clean_engine.generate_acknowledgment(
            "[SYSTEM]: The consequential action 'app_execute_capability' was approved by the operator.",
            task_id,
        )
        assert ev1 is None

        ev2 = clean_engine.generate_acknowledgment("[APPROVAL_DECISION]: Approved", task_id)
        assert ev2 is None

    def test_grounded_action_narration(self, clean_engine):
        task_id = "task-action-started"

        # Browser navigation
        ev1 = clean_engine.generate_action_started(
            tool_name="app_execute_capability",
            parameters={
                "app_id": "browser.opera_gx",
                "capability_id": "browser.navigate",
                "parameters": {"url": "https://www.instagram.com/direct"},
            },
            task_id=task_id,
        )
        assert ev1 is not None
        assert ev1.event_type == TaskLifecycleEventType.ACTION_STARTED
        assert "Instagram" in ev1.narration_text
        assert ev1.priority == NarrationPriority.PROGRESS

        # Launching desktop app
        clean_engine.settings.progress_interval_seconds = 0.0  # bypass throttle for distinct test
        ev2 = clean_engine.generate_action_started(
            tool_name="windows_launch_app",
            parameters={"app_name": "notepad.exe"},
            task_id=task_id,
        )
        assert ev2 is not None
        assert "Notepad" in ev2.narration_text

    def test_progress_narration_throttling(self, clean_engine):
        task_id = "task-throttling"
        clean_engine.settings.progress_interval_seconds = 5.0

        # Action 1: Navigation started
        ev1 = clean_engine.generate_action_started(
            tool_name="app_execute_capability",
            parameters={
                "app_id": "browser.opera_gx",
                "capability_id": "browser.navigate",
                "parameters": {"url": "https://www.instagram.com"},
            },
            task_id=task_id,
        )
        assert ev1 is not None

        # Action 2: Rapid repetition within throttle window is suppressed
        ev2 = clean_engine.generate_action_started(
            tool_name="app_execute_capability",
            parameters={
                "app_id": "browser.opera_gx",
                "capability_id": "browser.navigate",
                "parameters": {"url": "https://www.instagram.com"},
            },
            task_id=task_id,
        )
        assert ev2 is None  # Throttled!

    def test_approval_required_narration(self, clean_engine):
        task_id = "task-appr"
        ev = clean_engine.generate_approval_required(
            action_summary="Navigate to 'https://www.instagram.com' in Opera GX",
            risk_tier="CONSEQUENTIAL",
            capability="browser.navigate",
            app_id="browser.opera_gx",
            task_id=task_id,
        )
        assert ev is not None
        assert ev.event_type == TaskLifecycleEventType.APPROVAL_REQUIRED
        assert ev.priority == NarrationPriority.APPROVAL
        assert "permission" in ev.narration_text.lower()
        assert "Instagram" in ev.narration_text

    def test_approval_granted_and_denied_narration(self, clean_engine):
        task_id = "task-dec"

        # Granted
        ev_grant = clean_engine.generate_approval_decision(
            approved=True,
            action_summary="Navigate to Instagram",
            task_id=task_id,
        )
        assert ev_grant.event_type == TaskLifecycleEventType.APPROVAL_GRANTED
        assert "Authorization received" in ev_grant.narration_text

        # Denied
        ev_deny = clean_engine.generate_approval_decision(
            approved=False,
            action_summary="Navigate to Instagram",
            task_id=task_id,
        )
        assert ev_deny.event_type == TaskLifecycleEventType.APPROVAL_DENIED
        assert "will not perform" in ev_deny.narration_text

    def test_error_sanitization_for_speech(self, clean_engine):
        task_id = "task-err"

        # Cloud 503 error
        ev1 = clean_engine.generate_error(
            tool_name="gemini_stream",
            error_message="503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}",
            task_id=task_id,
            recovery_attempted=True,
        )
        assert ev1.event_type == TaskLifecycleEventType.RECOVERY_STARTED
        assert "503" not in ev1.narration_text  # Cleaned of raw code!
        assert "attempt to recover" in ev1.narration_text

        # Fatal error without recovery
        ev2 = clean_engine.generate_error(
            tool_name="browser_automation",
            error_message="Target application window 'Opera GX' not found.",
            task_id=task_id,
            recovery_attempted=False,
        )
        assert ev2.event_type == TaskLifecycleEventType.ACTION_FAILED
        assert "could not be found" in ev2.narration_text

    def test_completion_narration_gating(self, clean_engine):
        task_id = "task-comp"

        # 1. While approval is pending, completion MUST NOT be announced
        ev_blocked = clean_engine.generate_completion(
            task_id=task_id,
            has_pending_approval=True,
            is_success=True,
        )
        assert ev_blocked is None

        # 2. When conversational response is already present, redundant "That's done" is suppressed
        ev_conv = clean_engine.generate_completion(
            task_id=task_id,
            has_pending_approval=False,
            is_success=True,
            conversational_text_present=True,
        )
        assert ev_conv is None

        # 3. Pure tool execution without conversational delta announces completion
        ev_done = clean_engine.generate_completion(
            task_id=task_id,
            has_pending_approval=False,
            is_success=True,
            conversational_text_present=False,
        )
        assert ev_done is not None
        assert ev_done.event_type == TaskLifecycleEventType.TASK_COMPLETED
        assert "That's done, sir." in ev_done.narration_text

        # 4. Cancelled task
        ev_cancel = clean_engine.generate_completion(
            task_id="task-cancel",
            has_pending_approval=False,
            is_cancelled=True,
        )
        assert ev_cancel.event_type == TaskLifecycleEventType.TASK_CANCELLED
        assert "cancelled" in ev_cancel.narration_text.lower()


class TestTaskNarrationRestApi:
    """Verify REST API endpoints for narration."""

    def test_get_and_update_narration_settings(self, client):
        res = client.get("/api/v1/voice/narration/settings")
        assert res.status_code == 200
        data = res.json()
        assert "progress_interval_seconds" in data
        assert "acknowledge_tasks" in data

        update_res = client.post(
            "/api/v1/voice/narration/settings",
            json={"progress_interval_seconds": 12.0, "acknowledge_tasks": True},
        )
        assert update_res.status_code == 200
        updated = update_res.json()
        assert updated["progress_interval_seconds"] == 12.0

        # Reset
        client.post(
            "/api/v1/voice/narration/settings",
            json={"progress_interval_seconds": 8.0},
        )

    def test_evaluate_narration_event_endpoint(self, client):
        res = client.post(
            "/api/v1/voice/narration/event",
            json={
                "task_id": "api-task-1",
                "event_type": "TASK_RECEIVED",
                "user_prompt": "Open Opera GX and search for flights",
            },
        )
        assert res.status_code == 200
        event = res.json()
        assert event["event_type"] == "TASK_ACKNOWLEDGED"
        assert "Opera GX" in event["narration_text"] or "browser" in event["narration_text"]
