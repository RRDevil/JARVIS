"""Comprehensive Test Suite for Multi-Step Task Orchestration and Provider Resilience.

Tests:
1. Multi-step sequential tool calling loop across multiple turns.
2. Upstream 503 UNAVAILABLE handling, backoff retry, and graceful model failover.
3. Consequential tool gating, approval requirement event, and stage propagation.
4. Mid-execution tool failure handling and contextual recovery.
5. Stream cancellation resilience.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.providers.base import ChatContextMessage, ProviderEvent
from app.providers.gemini import GeminiProvider
from app.tools.base import RiskTier, ToolStatus
from app.execution.engine import ToolExecutionModel
from app.execution.approval import ApprovalRequestModel


@pytest.mark.asyncio
async def test_multi_step_sequential_tool_execution():
    """Verify GeminiProvider executes a multi-step task requiring at least three tool calls until completion."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")

    # Turn 0 Chunk: Tool Call 1 (Launch Notepad)
    call1 = MagicMock()
    call1.name = "windows_launch_app"
    call1.args = {"app_id": "notepad"}

    part1 = MagicMock()
    part1.function_call = call1
    part1.text = None
    part1.thought = None

    chunk0 = MagicMock()
    chunk0.text = ""
    chunk0.usage_metadata = None
    chunk0.function_calls = [call1]
    chunk0.candidates = [MagicMock(content=MagicMock(parts=[part1]))]

    # Turn 1 Chunk: Tool Call 2 (Read screen text)
    call2 = MagicMock()
    call2.name = "windows_read_screen_text"
    call2.args = {}

    part2 = MagicMock()
    part2.function_call = call2
    part2.text = None
    part2.thought = None

    chunk1 = MagicMock()
    chunk1.text = ""
    chunk1.usage_metadata = None
    chunk1.function_calls = [call2]
    chunk1.candidates = [MagicMock(content=MagicMock(parts=[part2]))]

    # Turn 2 Chunk: Tool Call 3 (List windows for verification)
    call3 = MagicMock()
    call3.name = "windows_list_windows"
    call3.args = {}

    part3 = MagicMock()
    part3.function_call = call3
    part3.text = None
    part3.thought = None

    chunk2 = MagicMock()
    chunk2.text = ""
    chunk2.usage_metadata = None
    chunk2.function_calls = [call3]
    chunk2.candidates = [MagicMock(content=MagicMock(parts=[part3]))]

    # Turn 3 Chunk: Final Natural Confirmation (No further tool calls)
    part_final = MagicMock()
    part_final.function_call = None
    part_final.text = "I have opened Notepad, verified the window on screen, and confirmed the active process."
    part_final.thought = None

    chunk3 = MagicMock()
    chunk3.text = "I have opened Notepad, verified the window on screen, and confirmed the active process."
    chunk3.function_calls = None
    chunk3.usage_metadata = MagicMock(prompt_token_count=60, candidates_token_count=40, total_token_count=100)
    chunk3.candidates = [MagicMock(content=MagicMock(parts=[part_final]))]

    async def stream_turn0():
        yield chunk0

    async def stream_turn1():
        yield chunk1

    async def stream_turn2():
        yield chunk2

    async def stream_turn3():
        yield chunk3

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[stream_turn0(), stream_turn1(), stream_turn2(), stream_turn3()]
    )

    # Mock execution engine proposals for 3 sequential actions
    exec_success1 = ToolExecutionModel(
        id="exec-1",
        toolName="windows_launch_app",
        riskTier=RiskTier.CONTROLLED,
        parameters={"app_id": "notepad"},
        status=ToolStatus.SUCCESS,
        requestedAt="2026-11-05T20:00:00Z",
        result={"pid": 1234},
    )

    exec_success2 = ToolExecutionModel(
        id="exec-2",
        toolName="windows_read_screen_text",
        riskTier=RiskTier.READ_ONLY,
        parameters={},
        status=ToolStatus.SUCCESS,
        requestedAt="2026-11-05T20:00:01Z",
        result={"text": "Untitled - Notepad"},
    )

    exec_success3 = ToolExecutionModel(
        id="exec-3",
        toolName="windows_list_windows",
        riskTier=RiskTier.READ_ONLY,
        parameters={},
        status=ToolStatus.SUCCESS,
        requestedAt="2026-11-05T20:00:02Z",
        result=[{"title": "Untitled - Notepad", "handle": 9876}],
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(side_effect=[(exec_success1, None), (exec_success2, None), (exec_success3, None)])):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Open notepad, check text, and verify window.")],
            session_id="multi-step-session",
            request_id="multi-step-req",
        ):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert "message_start" in event_types
        assert "tool_start" in event_types
        assert "tool_result" in event_types
        assert "message_complete" in event_types

        # Verify exactly 3 tool start and 3 tool result events in order
        tool_starts = [e for e in events if e.event_type == "tool_start"]
        assert len(tool_starts) == 3
        assert tool_starts[0].tool_name == "windows_launch_app"
        assert tool_starts[1].tool_name == "windows_read_screen_text"
        assert tool_starts[2].tool_name == "windows_list_windows"

        tool_results = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_results) == 3
        assert tool_results[0].tool_status == "success"
        assert tool_results[1].tool_status == "success"
        assert tool_results[2].tool_status == "success"

        # Verify exactly ONE terminal completion event
        complete_events = [e for e in events if e.event_type == "message_complete"]
        assert len(complete_events) == 1
        assert complete_events[0].stage == "COMPLETED"
        assert "I have opened Notepad, verified the window on screen" in complete_events[0].full_text


@pytest.mark.asyncio
async def test_consequential_tool_approval_gating():
    """Verify provider emits AWAITING_APPROVAL stage when a consequential tool is gated."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-2.5-flash")

    # Turn 0: Tool Call requiring approval
    call = MagicMock()
    call.name = "visual_click_element"
    call.args = {"query": "Submit"}

    part = MagicMock()
    part.function_call = call
    part.text = None
    part.thought = None

    chunk0 = MagicMock()
    chunk0.text = ""
    chunk0.usage_metadata = None
    chunk0.function_calls = [call]
    chunk0.candidates = [MagicMock(content=MagicMock(parts=[part]))]

    # Turn 1: Explains approval is needed
    part_expl = MagicMock()
    part_expl.function_call = None
    part_expl.text = "I require your authorization before clicking the 'Submit' button."
    part_expl.thought = None

    chunk1 = MagicMock()
    chunk1.text = "I require your authorization before clicking the 'Submit' button."
    chunk1.function_calls = None
    chunk1.usage_metadata = None
    chunk1.candidates = [MagicMock(content=MagicMock(parts=[part_expl]))]

    async def stream_turn0():
        yield chunk0

    async def stream_turn1():
        yield chunk1

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[stream_turn0(), stream_turn1()]
    )

    pending_exec = ToolExecutionModel(
        id="exec-gated-1",
        toolName="visual_click_element",
        riskTier=RiskTier.CONSEQUENTIAL,
        parameters={"query": "Submit"},
        status=ToolStatus.PENDING_APPROVAL,
        requestedAt="2026-11-05T20:00:00Z",
    )

    approval_req = ApprovalRequestModel(
        id="appr-123",
        toolExecutionId="exec-gated-1",
        actionSummary="Click visually grounded element 'Submit'",
        toolName="visual_click_element",
        riskTier=RiskTier.CONSEQUENTIAL,
        parameters={"query": "Submit"},
        requestedAt="2026-11-05T20:00:00Z",
        expiresAt="2026-11-05T20:05:00Z",
        status="pending",
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(return_value=(pending_exec, approval_req))):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Click the submit button")],
            session_id="approval-test-session",
            request_id="approval-test-req",
        ):
            events.append(event)

        tool_results = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0].stage == "AWAITING_APPROVAL"
        assert tool_results[0].tool_status == "requires_approval"

        complete_event = [e for e in events if e.event_type == "message_complete"][0]
        assert complete_event.stage == "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_503_retry_and_model_failover():
    """Verify that when a model experiences 503 UNAVAILABLE, failover succeeds."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")

    # Primary model fails with 503 UNAVAILABLE
    err_503 = Exception("503 UNAVAILABLE: This model is currently experiencing high demand.")

    # Fallback model succeeds
    chunk_ok = MagicMock()
    chunk_ok.text = "Hello from fallback model!"
    chunk_ok.usage_metadata = None
    chunk_ok.candidates = [
        MagicMock(content=MagicMock(parts=[MagicMock(function_call=None, text="Hello from fallback model!", thought=None)]))
    ]

    async def stream_ok():
        yield chunk_ok

    mock_client = MagicMock()
    # First 3 attempts (retries on primary) fail with 503, 4th attempt (fallback model) succeeds
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[err_503, err_503, err_503, stream_ok()]
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("asyncio.sleep", AsyncMock()):  # fast-forward sleep

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Hi")],
            session_id="failover-session",
            request_id="failover-req",
        ):
            events.append(event)

        text_deltas = [e.delta for e in events if e.event_type == "text_delta"]
        assert "Hello from fallback model!" in text_deltas
        complete = [e for e in events if e.event_type == "message_complete"][0]
        assert complete.full_text == "Hello from fallback model!"


@pytest.mark.asyncio
async def test_503_exhausted_conversational_fallback():
    """Verify that when all candidate models fail 503, an in-character degraded fallback is emitted."""
    from app.providers.gemini import GeminiProvider

    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")
    err_503 = Exception("503 UNAVAILABLE: This model is currently experiencing high demand. Spikes in demand are usually temporary.")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(side_effect=err_503)

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("asyncio.sleep", AsyncMock()):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Explain quantum computing")],
            session_id="spike-session",
            request_id="spike-req",
        ):
            events.append(event)

        # Must NOT emit an error event
        error_events = [e for e in events if e.event_type == "error"]
        assert len(error_events) == 0

        # Must emit text_delta and message_complete with COMPLETED stage
        deltas = [e for e in events if e.event_type == "text_delta"]
        assert len(deltas) > 0
        assert "acute demand spike" in deltas[0].delta or "503" in deltas[0].delta

        complete = [e for e in events if e.event_type == "message_complete"][0]
        assert complete.stage == "COMPLETED"
        assert "standby" in complete.full_text.lower()


@pytest.mark.asyncio
async def test_503_exhausted_local_desktop_execution_fallback():
    """Verify that when cloud 503 occurs but user requested a local desktop task, it executes locally."""
    from app.providers.gemini import GeminiProvider
    from app.execution.engine import ToolExecutionModel
    from app.tools.base import RiskTier, ToolStatus

    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")
    err_503 = Exception("503 UNAVAILABLE: This model is currently experiencing high demand.")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(side_effect=err_503)

    local_exec = ToolExecutionModel(
        id="exec-local-1",
        toolName="windows_launch_app",
        riskTier=RiskTier.READ_ONLY,
        parameters={"app_id": "notepad"},
        status=ToolStatus.SUCCESS,
        requestedAt="2026-11-05T20:00:00Z",
        result={"status": "success", "message": "Launched Notepad successfully."},
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(return_value=(local_exec, None))), \
         patch("asyncio.sleep", AsyncMock()):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Please open Notepad for me")],
            session_id="offline-session",
            request_id="offline-req",
        ):
            events.append(event)

        # Verifies offline tool execution was triggered
        tool_starts = [e for e in events if e.event_type == "tool_start"]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "windows_launch_app"

        tool_results = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0].tool_status == "success"

        complete = [e for e in events if e.event_type == "message_complete"][0]
        assert complete.stage == "COMPLETED"
        assert "offline automation" in complete.full_text or "Notepad" in complete.full_text


@pytest.mark.asyncio
async def test_503_exhausted_browser_navigation_fallback():
    """Verify that when 503 occurs during navigation request, offline capability execution routes to Opera GX."""
    from app.providers.gemini import GeminiProvider
    from app.execution.approval import ApprovalRequestModel
    from app.execution.engine import ToolExecutionModel
    from app.tools.base import RiskTier, ToolStatus

    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")
    err_503 = Exception("503 UNAVAILABLE: This model is currently experiencing high demand.")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(side_effect=err_503)

    pending_approval = ApprovalRequestModel(
        id="appr-nav-test",
        toolExecutionId="exec-nav-test",
        toolName="app_execute_capability",
        riskTier=RiskTier.CONSEQUENTIAL,
        actionSummary="Navigate to 'https://www.instagram.com' in Opera GX",
        requestedAt="2026-11-13T10:00:00Z",
        expiresAt="2026-11-13T10:05:00Z",
        parameters={"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}},
        status="pending",
    )
    pending_exec = ToolExecutionModel(
        id="exec-nav-test",
        toolName="app_execute_capability",
        riskTier=RiskTier.CONSEQUENTIAL,
        parameters={"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}},
        status=ToolStatus.PENDING_APPROVAL,
        requestedAt="2026-11-13T10:00:00Z",
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(return_value=(pending_exec, pending_approval))), \
         patch("asyncio.sleep", AsyncMock()):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Navigate to Instagram")],
            session_id="offline-nav-session",
            request_id="offline-nav-req",
        ):
            events.append(event)

        # Verifies offline tool execution was triggered for browser navigation
        tool_starts = [e for e in events if e.event_type == "tool_start"]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "app_execute_capability"

        tool_results = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0].stage == "AWAITING_APPROVAL"
        assert tool_results[0].tool_status == "requires_approval"

        complete = [e for e in events if e.event_type == "message_complete"][0]
        assert complete.stage == "AWAITING_APPROVAL"
        assert "authorize the action" in complete.full_text


def test_sanitize_error_message():
    """Verify error sanitization cleans raw JSON and python dicts."""
    from app.providers.gemini import sanitize_error_message

    raw_503 = "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand.'}}"
    sanitized = sanitize_error_message(raw_503)
    assert "{" not in sanitized
    assert "503 Service Unavailable" in sanitized

    raw_dict = "Internal error: {'details': 'bad status', 'code': 500}"
    sanitized2 = sanitize_error_message(raw_dict)
    assert "{" not in sanitized2
    assert "Internal error" in sanitized2


@pytest.mark.asyncio
async def test_tool_failure_midway_handling():
    """Verify that when a tool in step 1 fails, the failure is passed back to Gemini and gracefully reported."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-2.5-flash")

    # Turn 0: Gemini proposes a tool that fails
    call = MagicMock()
    call.name = "windows_launch_app"
    call.args = {"app_id": "invalid_app_id"}

    chunk0 = MagicMock()
    chunk0.text = ""
    chunk0.usage_metadata = None
    chunk0.function_calls = [call]
    chunk0.candidates = []

    # Turn 1: Gemini receives the failure and responds naturally with an apology/explanation
    chunk1 = MagicMock()
    chunk1.text = "I could not find or launch that application on your system."
    chunk1.function_calls = None
    chunk1.usage_metadata = None
    chunk1.candidates = []

    async def stream_turn0():
        yield chunk0

    async def stream_turn1():
        yield chunk1

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=[stream_turn0(), stream_turn1()]
    )

    failed_exec = ToolExecutionModel(
        id="exec-failed-1",
        toolName="windows_launch_app",
        riskTier=RiskTier.CONTROLLED,
        parameters={"app_id": "invalid_app_id"},
        status=ToolStatus.FAILED,
        requestedAt="2026-11-05T20:00:00Z",
        error="Application 'invalid_app_id' is not registered.",
    )

    with patch.object(provider, "_get_client", return_value=mock_client), \
         patch("app.execution.engine.execution_engine.propose", AsyncMock(return_value=(failed_exec, None))):

        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Launch non-existent app")],
            session_id="fail-recovery-session",
            request_id="fail-recovery-req",
        ):
            events.append(event)

        tool_results = [e for e in events if e.event_type == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0].tool_status == "failed"

        complete_event = [e for e in events if e.event_type == "message_complete"][0]
        assert complete_event.stage == "COMPLETED"
        assert "I could not find or launch" in complete_event.full_text


@pytest.mark.asyncio
async def test_stream_cancellation_midway():
    """Verify that breaking out of the generator (client cancellation) halts execution without errors."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-2.5-flash")

    chunk1 = MagicMock(text="Part 1... ", usage_metadata=None, function_calls=None, candidates=[])
    chunk2 = MagicMock(text="Part 2... ", usage_metadata=None, function_calls=None, candidates=[])

    async def infinite_chunks():
        yield chunk1
        yield chunk2
        # Client cancels here; subsequent chunk should not be consumed
        yield MagicMock(text="Should not arrive", usage_metadata=None, function_calls=None, candidates=[])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=infinite_chunks())

    with patch.object(provider, "_get_client", return_value=mock_client):
        received = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Stream forever")],
            session_id="cancel-session",
            request_id="cancel-req",
        ):
            received.append(event)
            if event.event_type == "text_delta" and "Part 2" in (event.delta or ""):
                # Simulate frontend AbortController breaking stream
                break

        assert any("Part 1" in (e.delta or "") for e in received if e.event_type == "text_delta")
        assert any("Part 2" in (e.delta or "") for e in received if e.event_type == "text_delta")
        assert not any("Should not arrive" in (e.delta or "") for e in received if e.event_type == "text_delta")


@pytest.mark.asyncio
async def test_sse_unexpected_connection_close():
    """Verify that unexpected connection disruptions emit clean error events without hanging."""
    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(
        side_effect=ConnectionResetError("Remote host closed active TCP connection.")
    )

    with patch.object(provider, "_get_client", return_value=mock_client):
        events = []
        async for event in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="Test connection drop")],
            session_id="drop-session",
            request_id="drop-req",
        ):
            events.append(event)

        assert len(events) == 2
        assert events[0].event_type == "message_start"
        assert events[1].event_type == "error"
        assert events[1].error_code == "UPSTREAM_PROVIDER_ERROR"
        assert "Remote host closed active TCP connection" in (events[1].error_message or "")


@pytest.mark.asyncio
async def test_multi_step_approval_continuation_preserves_session_and_proceeds():
    """Verify that when a tool requires approval, the session is preserved with native candidate parts,
    and upon operator approval continuation, the turn proceeds seamlessly to subsequent steps.
    """
    provider = GeminiProvider(api_key="test-api-key", model="gemini-3.5-flash-lite")
    session_id = "test-multi-step-continuation-session"

    # Turn 1: Model proposes a consequential tool requiring approval (e.g. app_execute_capability)
    call_nav = MagicMock()
    call_nav.name = "app_execute_capability"
    call_nav.args = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"query": "snakes of Nepal"}}

    part_nav = MagicMock()
    part_nav.function_call = call_nav
    part_nav.text = None

    chunk_turn1 = MagicMock()
    chunk_turn1.text = ""
    chunk_turn1.function_calls = [call_nav]
    chunk_turn1.usage_metadata = None
    chunk_turn1.candidates = [MagicMock(content=MagicMock(parts=[part_nav]))]

    # Turn 2 (after continuation): Model calls browser.read_page then finishes
    part_finish = MagicMock()
    part_finish.function_call = None
    part_finish.text = "Nepal is home to diverse snake species including the King Cobra and Himalayan Pit Viper."

    chunk_turn2 = MagicMock()
    chunk_turn2.text = "Nepal is home to diverse snake species including the King Cobra and Himalayan Pit Viper."
    chunk_turn2.function_calls = None
    chunk_turn2.usage_metadata = None
    chunk_turn2.candidates = [MagicMock(content=MagicMock(parts=[part_finish]))]

    async def stream_turn1():
        yield chunk_turn1

    async def stream_turn2():
        yield chunk_turn2

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(side_effect=[stream_turn1(), stream_turn2()])

    with patch.object(provider, "_get_client", return_value=mock_client):
        # 1. Execute Turn 1
        t1_events = []
        async for evt in provider.stream_chat(
            messages=[ChatContextMessage(role="user", content="can you open a new tab in opera and find me an article about species of snakes found in Nepal")],
            session_id=session_id,
            request_id="req-turn-1",
        ):
            t1_events.append(evt)

        # Verify Turn 1 ended in AWAITING_APPROVAL with non-empty text delta and stored session contents
        complete_evt = next(e for e in t1_events if e.event_type == "message_complete")
        assert complete_evt.stage == "AWAITING_APPROVAL"
        assert complete_evt.full_text is not None and len(complete_evt.full_text) > 0
        assert "authorization" in complete_evt.full_text.lower() or "action" in complete_evt.full_text.lower()
        assert session_id in provider._session_contents

        # 2. Operator approves: send continuation prompt
        continuation_prompt = (
            "[SYSTEM NOTIFICATION: The operator approved and executed 'Navigate in Opera GX'. "
            "Execution completed with status: SUCCESS. The desktop action has already been performed. "
            "Do NOT re-execute or re-propose 'app_execute_capability'. Proceed with the next step.]"
        )

        t2_events = []
        async for evt in provider.stream_chat(
            messages=[
                ChatContextMessage(role="user", content="can you open a new tab in opera and find me an article about species of snakes found in Nepal"),
                ChatContextMessage(role="user", content=continuation_prompt),
            ],
            session_id=session_id,
            request_id="req-turn-2",
        ):
            t2_events.append(evt)

        # Verify Turn 2 completed successfully and generated the final synthesized response
        t2_complete = next(e for e in t2_events if e.event_type == "message_complete")
        assert t2_complete.stage == "COMPLETED"
        assert "Nepal is home to diverse snake species" in t2_complete.full_text
        # Verify session contents were cleaned up on successful task completion
        assert session_id not in provider._session_contents



