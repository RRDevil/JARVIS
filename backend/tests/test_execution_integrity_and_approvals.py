"""Backend Test Suite for Task Execution Integrity, Cryptographic Approval Binding, and Event Synchronization."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.execution.approval import (
    ApprovalIntegrityError,
    ApprovalManager,
    ApprovalRequestModel,
    compute_action_payload_hash,
)
from app.execution.engine import ExecutionEngine
from app.providers.base import ChatContextMessage
from app.providers.gemini import GeminiProvider
from app.tools.base import RiskTier, ToolStatus
from app.tools.policy import PolicyEngine
from app.tools.registry import ToolRegistry, tool_registry
from app.tools.ui import UIDesktopTypeTextParams, UIDesktopTypeTextTool
from app.voice.narration import TaskLifecycleEventType, TaskNarrationEngine


@pytest.fixture
def clean_engine():
    """Create an isolated ExecutionEngine with in-memory state."""
    from app.tools.defaults import register_default_windows_tools
    register_default_windows_tools()
    approvals = ApprovalManager(default_ttl_seconds=60)
    engine = ExecutionEngine(registry=tool_registry, approvals=approvals)
    engine.clear()
    approvals.clear()
    return engine, approvals


@pytest.mark.asyncio
async def test_exact_action_payload_hash_binding(clean_engine):
    """Verify that an approval binds cryptographically to the exact action payload, preventing tampering."""
    engine, approvals = clean_engine

    target_text = "Hello JARVIS. This is a test."
    tool_name = "desktop_type_text"
    raw_params = {
        "text": target_text,
        "app_name": "notepad",
        "clear_first": True,
        "press_enter": False,
    }

    # Propose action requiring approval
    exec_model, approval = await engine.propose(
        tool_name=tool_name,
        raw_parameters=raw_params,
        session_id="test-session-1",
    )

    assert approval is not None
    assert approval.payloadHash is not None
    expected_hash = compute_action_payload_hash(tool_name, approval.parameters)
    assert approval.payloadHash == expected_hash

    # Tamper with the parameters in the execution model
    exec_model.parameters["text"] = "Random nonsensical text injected by race condition"

    # Attempting to resolve approval with tampered payload must fail
    res_appr, res_exec = await engine.resolve_approval(approval.id, approved=True)

    assert res_exec.status == ToolStatus.FAILED
    assert "Approval payload integrity failure" in str(res_exec.error)


@pytest.mark.asyncio
async def test_exact_text_entry_approval_summary():
    """Verify that policy engine generates an explicit action summary showing the verbatim text."""
    policy = PolicyEngine()
    tool = UIDesktopTypeTextTool()
    text = "Secret test payload 12345"

    eval_result = policy.evaluate(tool, {"text": text, "app_name": "notepad"})
    assert f'"{text}"' in eval_result.action_summary
    assert "notepad" in eval_result.action_summary


@pytest.mark.asyncio
async def test_typing_aborts_when_target_app_not_running():
    """Verify that desktop_type_text aborts with APPLICATION_NOT_RUNNING if app is not running."""
    tool = UIDesktopTypeTextTool()
    params = UIDesktopTypeTextParams(
        text="Sample text",
        app_name="nonexistent_virtual_app",
    )

    mock_adapter = MagicMock()
    mock_adapter.find_app_window.return_value = None

    with patch("app.tools.ui.get_platform_adapter", return_value=mock_adapter):
        result = await tool.execute(params, MagicMock())
        assert result.success is False
        assert result.error_code == "APPLICATION_NOT_RUNNING"
        mock_adapter.type_text.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_orchestration_loop_stops_on_pending_approval():
    """Verify that GeminiProvider immediately breaks its orchestration loop when a tool requires approval."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-flash-lite-latest")

    # Mock chunk proposing consequential tool
    chunk_call = MagicMock()
    chunk_call.text = "I will type text for you."
    chunk_call.usage_metadata = None

    fc_mock = MagicMock()
    fc_mock.name = "desktop_type_text"
    fc_mock.args = {"text": "Test input", "app_name": "notepad"}
    chunk_call.function_calls = [fc_mock]
    chunk_call.candidates = []

    async def mock_stream_gen():
        yield chunk_call

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    # Mock engine propose returning an approval request
    fake_approval = ApprovalRequestModel(
        id="appr-test-123",
        toolExecutionId="exec-001",
        actionSummary='Type "Test input" into notepad',
        toolName="desktop_type_text",
        riskTier=RiskTier.CONSEQUENTIAL,
        parameters={"text": "Test input", "app_name": "notepad"},
        requestedAt="2026-11-13T00:00:00Z",
        expiresAt="2026-11-13T00:05:00Z",
        status="pending",
    )
    fake_exec = MagicMock()
    fake_exec.status = ToolStatus.PENDING_APPROVAL

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(return_value=(fake_exec, fake_approval))):

        events = []
        async for ev in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Type Test input in notepad")],
            session_id="sess-loop-test",
            request_id="req-loop-test",
        ):
            events.append(ev)

        # Gemini generate_content_stream should have been called exactly once for Turn 0
        # It must NOT have continued to Turn 1 while approval is pending
        assert mock_client.aio.models.generate_content_stream.call_count == 1

        event_types = [e.event_type for e in events]
        assert "tool_start" in event_types
        assert "tool_result" in event_types
        assert "message_complete" in event_types

        complete_event = next(e for e in events if e.event_type == "message_complete")
        assert complete_event.stage == "AWAITING_APPROVAL"


def test_approval_narration_includes_approval_id_and_stable_event_id():
    """Verify that TaskNarrationEngine binds approval_id and produces a deterministic stable event_id."""
    engine = TaskNarrationEngine()

    event = engine.generate_approval_required(
        action_summary='Type "Hello" into notepad',
        risk_tier="CONSEQUENTIAL",
        capability=None,
        app_id="notepad",
        task_id="task-001",
        approval_id="appr-abc-123",
    )

    assert event.approval_id == "appr-abc-123"
    assert event.event_id == "approval:appr-abc-123:required"
    assert event.priority == 2  # NarrationPriority.APPROVAL

    dec_event = engine.generate_approval_decision(
        approved=True,
        action_summary='Type "Hello" into notepad',
        task_id="task-001",
        approval_id="appr-abc-123",
    )

    assert dec_event.approval_id == "appr-abc-123"
    assert dec_event.event_id == "approval:appr-abc-123:decision"
    assert dec_event.event_type == TaskLifecycleEventType.APPROVAL_GRANTED
