"""Unit tests for JARVIS Tool Registry and Policy Engine (Phase 3.1)."""

import pytest
from pydantic import BaseModel, Field

from app.tools.base import (
    BaseTool,
    ExecutionContext,
    PolicyDecision,
    RiskTier,
    ToolResult,
)
from app.tools.policy import PolicyEngine
from app.tools.registry import (
    ToolNotFoundError,
    ToolRegistry,
    ToolValidationError,
)


class DummyEchoParams(BaseModel):
    message: str = Field(..., min_length=1)
    repeat: int = Field(default=1, ge=1, le=10)


class DummyEchoTool(BaseTool):
    name = "dummy_echo"
    description = "A dummy tool that echoes back a message."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = DummyEchoParams

    async def execute(self, params: DummyEchoParams, context: ExecutionContext) -> ToolResult:
        return ToolResult(
            success=True,
            data={"echo": params.message * params.repeat},
            verified=True,
        )


class DummyConsequentialParams(BaseModel):
    target: str = Field(...)


class DummyConsequentialTool(BaseTool):
    name = "dummy_consequential"
    description = "A simulated mutating operation."
    risk_tier = RiskTier.CONSEQUENTIAL
    parameters_schema = DummyConsequentialParams

    async def execute(self, params: DummyConsequentialParams, context: ExecutionContext) -> ToolResult:
        return ToolResult(success=True, data={"applied": params.target})


class DummyCriticalTool(BaseTool):
    name = "dummy_critical"
    description = "A prohibited critical tool."
    risk_tier = RiskTier.CRITICAL
    parameters_schema = DummyConsequentialParams

    async def execute(self, params: DummyConsequentialParams, context: ExecutionContext) -> ToolResult:
        return ToolResult(success=False, error="Should never execute")


class DummyFileParams(BaseModel):
    folder_path: str = Field(...)


class DummyFileTool(BaseTool):
    name = "dummy_folder_inspect"
    description = "Inspect an authorized folder."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = DummyFileParams

    async def execute(self, params: DummyFileParams, context: ExecutionContext) -> ToolResult:
        return ToolResult(success=True, data={"folder": params.folder_path})


def test_registry_registration_and_lookup():
    reg = ToolRegistry()
    tool = DummyEchoTool()
    reg.register(tool)

    assert reg.has_tool("dummy_echo")
    retrieved = reg.get("dummy_echo")
    assert retrieved.name == "dummy_echo"
    assert retrieved.risk_tier == RiskTier.READ_ONLY


def test_registry_duplicate_registration_rejected():
    reg = ToolRegistry()
    tool = DummyEchoTool()
    reg.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(tool)


def test_registry_missing_tool_raises():
    reg = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        reg.get("non_existent_tool")


def test_registry_invalid_name_rejected():
    reg = ToolRegistry()

    class BadNamedTool(BaseTool):
        name = "bad-name-with-dashes"
        description = "Invalid identifier"
        risk_tier = RiskTier.READ_ONLY
        parameters_schema = DummyEchoParams

        async def execute(self, params, context):
            return ToolResult(success=True)

    with pytest.raises(ValueError, match="valid Python identifier"):
        reg.register(BadNamedTool())


def test_registry_parameter_validation():
    reg = ToolRegistry()
    reg.register(DummyEchoTool())

    # Valid params
    validated = reg.validate_parameters("dummy_echo", {"message": "hello", "repeat": 3})
    assert isinstance(validated, DummyEchoParams)
    assert validated.message == "hello"
    assert validated.repeat == 3

    # Invalid params (missing message)
    with pytest.raises(ToolValidationError):
        reg.validate_parameters("dummy_echo", {"repeat": 3})

    # Out of bounds params (repeat > 10)
    with pytest.raises(ToolValidationError):
        reg.validate_parameters("dummy_echo", {"message": "hi", "repeat": 99})


def test_policy_engine_risk_tiers(tmp_path):
    policy = PolicyEngine(allowed_paths=[str(tmp_path)])

    # 1. READ_ONLY -> ALLOW_AUTO
    echo_tool = DummyEchoTool()
    res1 = policy.evaluate(echo_tool, {"message": "test", "repeat": 1})
    assert res1.decision == PolicyDecision.ALLOW_AUTO
    assert not res1.requires_approval

    # 2. CONSEQUENTIAL without confirmation -> REQUIRE_APPROVAL
    mutating_tool = DummyConsequentialTool()
    res2 = policy.evaluate(mutating_tool, {"target": "doc.txt"})
    assert res2.decision == PolicyDecision.REQUIRE_APPROVAL
    assert res2.requires_approval

    # 3. CONSEQUENTIAL with confirmation -> ALLOW_AUTO
    res3 = policy.evaluate(mutating_tool, {"target": "doc.txt"}, user_confirmed=True)
    assert res3.decision == PolicyDecision.ALLOW_AUTO
    assert not res3.requires_approval

    # 4. CRITICAL -> BLOCK unconditionally
    crit_tool = DummyCriticalTool()
    res4 = policy.evaluate(crit_tool, {"target": "kernel"})
    assert res4.decision == PolicyDecision.BLOCK


def test_policy_engine_path_sandboxing(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    policy = PolicyEngine(allowed_paths=[str(sandbox)])

    tool = DummyFileTool()

    # Allowed inside sandbox
    valid_path = sandbox / "allowed_subfolder"
    valid_path.mkdir()
    res_valid = policy.evaluate(tool, {"folder_path": str(valid_path)})
    assert res_valid.decision == PolicyDecision.ALLOW_AUTO

    # Blocked outside sandbox (e.g. parent directory or root)
    outside_path = tmp_path / "outside_secret"
    outside_path.mkdir()
    res_outside = policy.evaluate(tool, {"folder_path": str(outside_path)})
    assert res_outside.decision == PolicyDecision.BLOCK
    assert "outside the authorized sandbox" in res_outside.reason

