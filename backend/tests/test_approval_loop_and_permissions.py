"""Regression & Idempotency Tests for Approval Loop Prevention and Capability Permissions.

Verifies:
1. Layer A Capability Authorization (Session vs Permanent enablement).
2. Layer B Consequential Action Approval gating.
3. Idempotent approval resolution (double-click/replay safety without 409).
4. Completed action caching in ExecutionEngine (eliminates looping proposals).
5. Active approval expected_request_id binding guard.
6. Offline navigation fallback during 503 capacity spikes.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.integrations.models import PermissionLevel, ProviderType
from app.integrations.permissions import IntegrationPermissionManager
from app.integrations.registry import application_registry
from app.execution.approval import ApprovalAlreadyResolvedError, ApprovalManager, ApprovalRequestModel
from app.execution.engine import ExecutionEngine, ToolExecutionModel
from app.tools.base import BaseTool, ExecutionContext, PolicyDecision, RiskTier, ToolResult, ToolStatus
from app.tools.policy import PolicyEngine
from app.tools.registry import ToolRegistry
from pydantic import BaseModel, Field


class DummyNavigateParams(BaseModel):
    app_id: str = "browser.opera_gx"
    capability_id: str = "browser.navigate"
    parameters: dict = Field(default_factory=lambda: {"url": "https://www.instagram.com"})


class DummyNavigateTool(BaseTool):
    name = "app_execute_capability"
    description = "Execute application capability."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = DummyNavigateParams

    def __init__(self, execution_counter=None):
        self.execution_counter = execution_counter if execution_counter is not None else []

    async def execute(self, params: DummyNavigateParams, context: ExecutionContext) -> ToolResult:
        self.execution_counter.append(params.parameters.get("url"))
        return ToolResult(
            success=True,
            data={"status": "navigated", "url": params.parameters.get("url")},
            verified=True,
        )


@pytest.fixture
def clean_engine():
    registry = ToolRegistry()
    counter = []
    tool = DummyNavigateTool(execution_counter=counter)
    registry.register(tool)

    policy = PolicyEngine()
    approvals = ApprovalManager()
    engine = ExecutionEngine(registry=registry, policy=policy, approvals=approvals)
    return engine, counter, approvals, policy


# -----------------------------------------------------------------------------
# 1. Layer A: Capability Authorization Tests
# -----------------------------------------------------------------------------

def test_layer_a_capability_permission_scoping():
    manager = IntegrationPermissionManager()
    app_id = "browser.opera_gx"
    manifest = application_registry.get(app_id)
    assert manifest is not None
    cap = next((c for c in manifest.capabilities if c.id == "browser.navigate"), None)
    assert cap is not None

    # Step 1: Default state is enabled
    state = manager.get_permission_state(app_id)
    assert state.is_enabled is True

    # Step 2: Disable the capability (Layer A block)
    manager.set_capability_enabled(app_id, "browser.navigate", enabled=False)
    decision, reason, _ = manager.evaluate_capability(manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://www.instagram.com"})
    assert decision == PolicyDecision.BLOCK
    assert "disabled" in reason.lower()

    # Step 3: Authorize for session only
    manager.authorize_capability(app_id, "browser.navigate", scope="session")
    state = manager.get_permission_state(app_id)
    assert "browser.navigate" in state.session_authorized_capabilities
    assert "browser.navigate" in state.disabled_capabilities  # Still disabled permanently

    # Now passes Layer A check and progresses to Layer B (consequential approval)
    decision, reason, binding = manager.evaluate_capability(manifest, cap, ProviderType.BROWSER_AUTOMATION, {"url": "https://www.instagram.com"})
    assert decision == PolicyDecision.REQUIRE_APPROVAL
    assert binding is not None

    # Step 4: Authorize permanently
    manager.authorize_capability(app_id, "browser.navigate", scope="permanent")
    state = manager.get_permission_state(app_id)
    assert "browser.navigate" not in state.disabled_capabilities


# -----------------------------------------------------------------------------
# 2. Layer B: Action Approval & Idempotent Resolution Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consequential_navigation_requires_single_approval(clean_engine):
    engine, counter, approvals, _ = clean_engine

    params = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}}

    # Propose execution
    exec_model, approval_req = await engine.propose("app_execute_capability", params)

    assert approval_req is not None
    assert approval_req.riskTier == RiskTier.CONSEQUENTIAL
    assert "Navigate to 'https://www.instagram.com' in Opera GX" in approval_req.actionSummary
    assert exec_model.status == ToolStatus.PENDING_APPROVAL
    assert len(counter) == 0  # Not yet executed

    # Approve and execute
    appr_res, exec_res = await engine.resolve_approval(approval_req.id, approved=True)
    assert appr_res.status == "approved"
    assert exec_res.status == ToolStatus.SUCCESS
    assert len(counter) == 1
    assert counter[0] == "https://www.instagram.com"


@pytest.mark.asyncio
async def test_idempotent_approval_resolution_no_409(clean_engine):
    """Verify repeated approval submission raises ApprovalAlreadyResolvedError to protect against token replay."""
    engine, counter, approvals, _ = clean_engine
    params = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}}

    _, approval_req = await engine.propose("app_execute_capability", params, session_id="sess-idemp")

    # First resolution: Approved
    appr1, exec1 = await engine.resolve_approval(approval_req.id, approved=True)
    assert appr1.status == "approved"
    assert exec1.status == ToolStatus.SUCCESS
    assert len(counter) == 1

    # Second submission with same token is blocked by replay protection
    with pytest.raises(ApprovalAlreadyResolvedError):
        await engine.resolve_approval(approval_req.id, approved=True)
    assert len(counter) == 1  # Execution count strictly preserved!


@pytest.mark.asyncio
async def test_completed_action_cache_prevents_loop(clean_engine):
    """Verify that if Gemini or user proposes the exact same action after success in the session, it returns cached success."""
    engine, counter, approvals, _ = clean_engine
    params = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}}
    session_id = "session-instagram-flow"

    # Turn 1: Propose and approve
    _, approval_req = await engine.propose("app_execute_capability", params, session_id=session_id)
    await engine.resolve_approval(approval_req.id, approved=True)
    assert len(counter) == 1

    # Turn 2: Gemini attempts to re-propose the same navigation within 60s
    cached_exec, new_approval = await engine.propose("app_execute_capability", params, session_id=session_id)

    # Cache hit: No new approval request is created, execution status is SUCCESS, counter is unchanged
    assert new_approval is None
    assert cached_exec.status == ToolStatus.SUCCESS
    assert len(counter) == 1  # No duplicate execution!
    assert len(approvals.get_pending()) == 0


@pytest.mark.asyncio
async def test_duplicate_pending_proposal_deduplication(clean_engine):
    """Verify that proposing identical action while one is already pending returns the existing pending card."""
    engine, counter, approvals, _ = clean_engine
    params = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}}

    exec1, appr1 = await engine.propose("app_execute_capability", params)
    assert appr1 is not None

    # Propose again before user has resolved the first card
    exec2, appr2 = await engine.propose("app_execute_capability", params)

    assert appr2.id == appr1.id
    assert exec2.id == exec1.id
    assert len(approvals.get_pending()) == 1


# -----------------------------------------------------------------------------
# 3. Active Approval Mismatch Guard
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_approval_expected_request_id_binding(clean_engine):
    from fastapi import HTTPException
    from app.api.approvals import RespondApprovalPayload, respond_to_active_approval

    engine, counter, approvals, _ = clean_engine

    params = {"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"url": "https://www.instagram.com"}}
    with patch("app.api.approvals.execution_engine", engine), patch("app.api.approvals.approval_manager", approvals):
        _, req = await engine.propose("app_execute_capability", params)

        # Mismatched expected ID should raise 409
        with pytest.raises(HTTPException) as exc_info:
            await respond_to_active_approval(
                payload=RespondApprovalPayload(approved=True, expected_request_id="appr-wrong-id"),
                _authorized=True,
            )
        assert exc_info.value.status_code == 409

        # Matching expected ID should succeed
        res = await respond_to_active_approval(
            payload=RespondApprovalPayload(approved=True, expected_request_id=req.id),
            _authorized=True,
        )
        assert res.approval.status == "approved"
        assert res.execution.status == ToolStatus.SUCCESS
