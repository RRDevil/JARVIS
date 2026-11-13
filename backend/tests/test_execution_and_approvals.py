"""Integration and unit tests for Execution Engine, Approvals API, and Audit Trail (Phase 3.4)."""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.automation.factory import set_platform_adapter
from app.automation.mock_adapter import MockPlatformAdapter
from app.db.audit import audit_logger
from app.execution.approval import approval_manager
from app.execution.engine import execution_engine
from app.main import app
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult
from app.tools.defaults import register_default_windows_tools
from app.tools.registry import tool_registry


@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    """Setup hermetic test environment with MockPlatformAdapter and clean registries."""
    mock_platform = MockPlatformAdapter()
    set_platform_adapter(mock_platform)
    register_default_windows_tools()

    # Clear pending approvals for test isolation
    approval_manager.clear()

    yield mock_platform

    set_platform_adapter(None)


@pytest.fixture
def client():
    return TestClient(app)


def test_list_tools_endpoint(client):
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) >= 7
    tool_names = [t["name"] for t in tools]
    assert "windows_list_apps" in tool_names
    assert "windows_launch_app" in tool_names
    assert "windows_close_window" in tool_names
    assert "ui_find_controls" in tool_names
    assert "ui_click_control" in tool_names


def test_propose_read_only_tool_auto_executes(client):
    response = client.post(
        "/api/v1/tools/propose",
        json={"tool_name": "windows_list_apps", "parameters": {}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["execution"]["status"] == "success"
    assert data["approval_request"] is None
    assert isinstance(data["execution"]["result"], list)


def test_propose_consequential_tool_requires_approval(client):
    response = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    assert response.status_code == 200
    data = response.json()
    exec_data = data["execution"]
    appr_data = data["approval_request"]

    assert exec_data["status"] == "pending_approval"
    assert appr_data is not None
    assert appr_data["toolName"] == "windows_close_window"
    assert appr_data["riskTier"] == "CONSEQUENTIAL"
    assert appr_data["status"] == "pending"

    # Verify pending approvals listing endpoint
    pending_resp = client.get("/api/v1/approvals/pending")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()
    assert any(p["id"] == appr_data["id"] for p in pending_list)


def test_approval_rejection_workflow(client):
    # 1. Propose consequential tool
    prop_resp = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    appr_id = prop_resp.json()["approval_request"]["id"]
    exec_id = prop_resp.json()["execution"]["id"]

    # 2. Reject approval
    resp = client.post(
        f"/api/v1/approvals/{appr_id}/respond",
        json={"approved": False},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["approval"]["status"] == "rejected"
    assert res_data["execution"]["status"] == "rejected"

    # 3. Check execution status endpoint
    exec_check = client.get(f"/api/v1/tools/executions/{exec_id}")
    assert exec_check.status_code == 200
    assert exec_check.json()["status"] == "rejected"


def test_approval_grant_and_execution_workflow(client, setup_test_environment):
    mock = setup_test_environment
    assert 1002 in mock.windows

    # 1. Propose closing window 1002
    prop_resp = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    appr_id = prop_resp.json()["approval_request"]["id"]
    exec_id = prop_resp.json()["execution"]["id"]

    # 2. Approve request
    resp = client.post(
        f"/api/v1/approvals/{appr_id}/respond",
        json={"approved": True},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["approval"]["status"] == "approved"
    assert res_data["execution"]["status"] == "success"

    # 3. Verify mock window was closed
    assert 1002 not in mock.windows
    assert 1002 in mock.closed_windows


def test_approval_token_replay_protection(client):
    # Propose
    prop_resp = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    appr_id = prop_resp.json()["approval_request"]["id"]

    # First respond -> 200 OK
    resp1 = client.post(
        f"/api/v1/approvals/{appr_id}/respond",
        json={"approved": False},
    )
    assert resp1.status_code == 200

    # Second respond attempt with same token -> 409 Conflict
    resp2 = client.post(
        f"/api/v1/approvals/{appr_id}/respond",
        json={"approved": True},
    )
    assert resp2.status_code == 409
    assert "already resolved" in resp2.json()["detail"].lower()


def test_approval_token_expiration(client):
    # Propose
    prop_resp = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    appr_id = prop_resp.json()["approval_request"]["id"]

    # Manually expire the token
    req = approval_manager.get_request(appr_id)
    expired_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    req.expiresAt = expired_time

    # Attempt to respond to expired approval -> 409 Conflict
    resp = client.post(
        f"/api/v1/approvals/{appr_id}/respond",
        json={"approved": True},
    )
    assert resp.status_code == 409
    assert "expired" in resp.json()["detail"].lower()


def test_cancel_pending_execution(client):
    prop_resp = client.post(
        "/api/v1/tools/propose",
        json={
            "tool_name": "windows_close_window",
            "parameters": {"handle": 1002},
        },
    )
    exec_id = prop_resp.json()["execution"]["id"]

    # Cancel execution
    cancel_resp = client.post(f"/api/v1/tools/executions/{exec_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    # Status check
    check = client.get(f"/api/v1/tools/executions/{exec_id}")
    assert check.json()["status"] == "cancelled"


def test_audit_logs_query(client):
    # Run an action
    client.post(
        "/api/v1/tools/propose",
        json={"tool_name": "windows_list_apps", "parameters": {}},
    )

    # Query audit logs
    audit_resp = client.get("/api/v1/audit/logs?limit=10")
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    assert len(logs) > 0
    assert any("windows_list_apps" in l["action_name"].lower() for l in logs)


@pytest.mark.asyncio
async def test_execution_timeout_handling():
    """Verify engine enforces bounded timeouts on slow tools."""
    class SlowParams(BaseModel):
        duration: float = Field(default=2.0)

    class SlowTool(BaseTool):
        name = "slow_hanging_tool"
        description = "Simulates a tool hanging or timing out."
        risk_tier = RiskTier.READ_ONLY
        parameters_schema = SlowParams

        async def execute(self, params: SlowParams, context: ExecutionContext) -> ToolResult:
            await asyncio.sleep(params.duration)
            return ToolResult(success=True)

    tool_registry.register(SlowTool(), overwrite=True)

    # Instantiate engine with short 0.1s timeout limit
    from app.execution.engine import ExecutionEngine
    engine = ExecutionEngine(registry=tool_registry, default_timeout_seconds=0.1)

    exec_res, _ = await engine.propose("slow_hanging_tool", {"duration": 1.0})
    assert exec_res.status == "failed"
    assert "timed out" in exec_res.error.lower()

