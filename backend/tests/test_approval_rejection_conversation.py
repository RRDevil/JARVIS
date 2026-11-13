"""Tests for Approval Rejection Conversation UX and Failure Scenarios (Phase 4)."""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.execution.approval import approval_manager
from app.execution.engine import execution_engine
from app.tools.base import RiskTier, ToolStatus
from app.tools.defaults import register_default_windows_tools

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_approvals_and_executions():
    mock_platform = MockPlatformAdapter()
    set_platform_adapter(mock_platform)
    register_default_windows_tools()
    approval_manager.clear()
    with execution_engine._lock:
        execution_engine._executions.clear()
    yield
    approval_manager.clear()
    with execution_engine._lock:
        execution_engine._executions.clear()
    set_platform_adapter(None)


class TestApprovalRejectionConversationUX:
    """Test suite verifying distinct natural language conversation outcomes for approval actions."""

    @pytest.mark.asyncio
    async def test_scenario_a_user_rejection_produces_distinct_conversation_message(self):
        """Scenario A: User rejects approval -> returns distinct cancellation message."""
        exec_model, approval = await execution_engine.propose(
            tool_name="windows_close_window",
            raw_parameters={"handle": 12345},
            session_id="session-rej-test",
        )
        assert approval is not None

        # User rejects
        resp = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": False},
        )
        assert resp.status_code == 200
        data = resp.json()

        # 1. Approval status rejected
        assert data["approval"]["status"] == "rejected"
        # 2. Execution rejected
        assert data["execution"]["status"] == "rejected"
        # 3. Dedicated conversation message returned
        assert "conversation_message" in data
        assert data["conversation_message"] == "Understood. I've cancelled that action as requested. Nothing was changed."
        # 4. Correct approval association
        assert data["approval"]["id"] == approval.id

    @pytest.mark.asyncio
    async def test_rejection_does_not_execute_action(self):
        """Verify rejecting an approval guarantees that the underlying tool is NEVER executed."""
        exec_model, approval = await execution_engine.propose(
            tool_name="windows_close_window",
            raw_parameters={"handle": 12345},
            session_id="session-no-exec",
        )

        resp = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": False},
        )
        assert resp.status_code == 200

        resolved_exec = execution_engine.get_execution(approval.toolExecutionId)
        assert resolved_exec.status == ToolStatus.REJECTED
        assert resolved_exec.result is None
        assert "rejected by user" in resolved_exec.error.lower()

    @pytest.mark.asyncio
    async def test_scenario_c_execution_failure_produces_failure_conversation_message(self):
        """Scenario C: User approves, but tool execution fails on Windows."""
        exec_model, approval = await execution_engine.propose(
            tool_name="windows_close_window",
            raw_parameters={"handle": 999999999},  # Invalid non-existent HWND
            session_id="session-fail-test",
        )

        resp = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": True},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["approval"]["status"] == "approved"
        assert "conversation_message" in data
        # Contains error detail explanation
        assert "attempted to perform the action" in data["conversation_message"] or "error" in data["conversation_message"].lower()

    @pytest.mark.asyncio
    async def test_scenario_d_expired_approval_produces_expiration_message(self):
        """Scenario D: Approval expires before authorization."""
        # Create expired approval request manually
        approval_req = approval_manager.create_request(
            execution_id="exec-exp-1",
            tool_name="windows_close_window",
            risk_tier=RiskTier.CONSEQUENTIAL,
            parameters={"handle": 12345},
            action_summary="Close target window",
            ttl_seconds=-10,  # Already expired in the past
        )

        # Attempting to respond returns 409 with distinct expiration message
        resp = client.post(
            f"/api/v1/approvals/{approval_req.id}/respond",
            json={"approved": True},
        )
        assert resp.status_code == 409
        assert "expired before it was authorized" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_exactly_once_message_creation_and_replay_protection(self):
        """Verify responding to an already resolved approval raises 409 conflict, preventing duplicate messages."""
        exec_model, approval = await execution_engine.propose(
            tool_name="windows_close_window",
            raw_parameters={"handle": 12345},
            session_id="session-dup-test",
        )

        # First rejection response
        resp1 = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": False},
        )
        assert resp1.status_code == 200

        # Second attempt with same ID (e.g. repeated click or duplicate event)
        resp2 = client.post(
            f"/api/v1/approvals/{approval.id}/respond",
            json={"approved": False},
        )
        # Blocked by replay protection
        assert resp2.status_code == 409
        assert "already resolved" in resp2.json()["detail"].lower()
