"""Bounded Tool Execution Engine with Policy Enforcement and Lifecycle Management."""

import asyncio
import hashlib
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from app.db.audit import audit_logger
from app.execution.approval import (
    ApprovalManager,
    ApprovalRequestModel,
    approval_manager,
)
from app.tools.base import (
    ExecutionContext,
    PolicyDecision,
    RiskTier,
    ToolResult,
    ToolStatus,
)
from app.tools.policy import PolicyEngine
from app.tools.registry import ToolRegistry, tool_registry


class ToolExecutionModel(BaseModel):
    """Pydantic model representing an execution lifecycle record.

    Conforms to frontend ToolExecution integration contract.
    """

    id: str
    toolName: str
    riskTier: RiskTier
    parameters: Dict[str, Any]
    status: ToolStatus
    requestedAt: str
    completedAt: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None


class ExecutionEngine:
    """Orchestrates proposal validation, approval gates, bounded execution, and auditing."""

    def __init__(
        self,
        registry: ToolRegistry = tool_registry,
        policy: Optional[PolicyEngine] = None,
        approvals: ApprovalManager = approval_manager,
        default_timeout_seconds: float = 10.0,
    ):
        self.registry = registry
        self.policy = policy or PolicyEngine()
        self.approvals = approvals
        self.default_timeout_seconds = default_timeout_seconds

        self._executions: Dict[str, ToolExecutionModel] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._completed_action_cache: Dict[str, Tuple[ToolExecutionModel, float]] = {}
        self._lock = threading.RLock()

    def _compute_action_signature(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Deterministic cryptographic signature for deduplicating repeated action proposals."""
        canonical = json.dumps({"tool": tool_name, "params": parameters}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get_execution(self, execution_id: str) -> Optional[ToolExecutionModel]:
        """Fetch execution record by ID."""
        with self._lock:
            return self._executions.get(execution_id)

    async def propose(
        self,
        tool_name: str,
        raw_parameters: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Tuple[ToolExecutionModel, Optional[ApprovalRequestModel]]:
        """Propose a tool execution, evaluate policy, and either auto-execute or request approval."""
        execution_id = f"exec-{uuid.uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()

        # 1. Validate tool registration
        if not self.registry.has_tool(tool_name):
            err_msg = f"Tool '{tool_name}' is not registered in JARVIS Core."
            audit_logger.log(
                action_name=f"PROPOSE_{tool_name}",
                risk_tier=RiskTier.READ_ONLY,
                status="REJECTED_UNKNOWN_TOOL",
                details={"execution_id": execution_id, "error": err_msg},
            )
            failed_exec = ToolExecutionModel(
                id=execution_id,
                toolName=tool_name,
                riskTier=RiskTier.READ_ONLY,
                parameters=raw_parameters,
                status=ToolStatus.FAILED,
                requestedAt=now,
                completedAt=now,
                error=err_msg,
            )
            with self._lock:
                self._executions[execution_id] = failed_exec
            return failed_exec, None

        tool = self.registry.get(tool_name)

        # 2. Schema parameter validation
        try:
            validated_params = self.registry.validate_parameters(tool_name, raw_parameters)
            params_dict = validated_params.model_dump()
        except Exception as val_err:
            err_msg = f"Parameter validation failed: {str(val_err)}"
            audit_logger.log(
                action_name=f"VALIDATE_{tool_name}",
                risk_tier=tool.risk_tier,
                status="SCHEMA_VALIDATION_FAILED",
                details={"execution_id": execution_id, "error": err_msg, "params": raw_parameters},
            )
            failed_exec = ToolExecutionModel(
                id=execution_id,
                toolName=tool_name,
                riskTier=tool.risk_tier,
                parameters=raw_parameters,
                status=ToolStatus.FAILED,
                requestedAt=now,
                completedAt=now,
                error=err_msg,
            )
            with self._lock:
                self._executions[execution_id] = failed_exec
            return failed_exec, None

        # 2.1 Mandatory Visual Target Resolution Stage (Prior to Policy/Approval)
        if tool_name == "visual_click_element" and (params_dict.get("x") is None or params_dict.get("y") is None):
            target_query = params_dict.get("target_description") or params_dict.get("element_id")
            if target_query:
                from app.perception.target_resolver import target_resolver
                try:
                    resolved = await target_resolver.resolve_target(
                        query=target_query,
                        monitor_id=params_dict.get("monitor_id", 1),
                        active_window_only=params_dict.get("active_window_only", False),
                    )
                    params_dict["x"] = resolved.click_coordinates.x
                    params_dict["y"] = resolved.click_coordinates.y
                    params_dict["target_description"] = resolved.target_description
                    params_dict["app_name"] = resolved.app_name
                    params_dict["window_title"] = resolved.window_title
                    params_dict["window_handle"] = resolved.window_handle
                    params_dict["bounding_box"] = resolved.bounding_box.model_dump()
                    params_dict["detection_method"] = resolved.detection_method
                    params_dict["confidence"] = resolved.confidence
                    params_dict["observation_timestamp"] = resolved.observation_timestamp
                    params_dict["resolved_target"] = resolved.model_dump()
                except Exception as res_err:
                    err_msg = f"Visual target resolution failed: {str(res_err)}"
                    audit_logger.log(
                        action_name="TARGET_RESOLUTION_FAILED",
                        risk_tier=tool.risk_tier,
                        status="RESOLUTION_FAILED",
                        details={"execution_id": execution_id, "query": target_query, "error": err_msg},
                    )
                    failed_exec = ToolExecutionModel(
                        id=execution_id,
                        toolName=tool_name,
                        riskTier=tool.risk_tier,
                        parameters=params_dict,
                        status=ToolStatus.FAILED,
                        requestedAt=now,
                        completedAt=now,
                        error=err_msg,
                    )
                    with self._lock:
                        self._executions[execution_id] = failed_exec
                    return failed_exec, None

        # 2.2 Deduplication & completed action cache check (prevents loop on recently completed actions)
        sig = self._compute_action_signature(tool_name, params_dict)
        with self._lock:
            if sig in self._completed_action_cache:
                cached_exec, cached_time = self._completed_action_cache[sig]
                if (time.time() - cached_time) < 60.0 and cached_exec.status == ToolStatus.SUCCESS:
                    audit_logger.log(
                        action_name=f"CACHE_HIT_{tool_name}",
                        risk_tier=tool.risk_tier,
                        status="IDEMPOTENT_CACHE_RETURN",
                        details={"original_execution_id": cached_exec.id, "params": params_dict},
                    )
                    return cached_exec, None

        # 3. Policy evaluation
        policy_eval = self.policy.evaluate(tool, params_dict)

        if policy_eval.decision == PolicyDecision.BLOCK:
            audit_logger.log(
                action_name=f"POLICY_BLOCK_{tool_name}",
                risk_tier=tool.risk_tier,
                status="POLICY_BLOCKED",
                details={
                    "execution_id": execution_id,
                    "reason": policy_eval.reason,
                    "params": params_dict,
                },
            )
            blocked_exec = ToolExecutionModel(
                id=execution_id,
                toolName=tool_name,
                riskTier=tool.risk_tier,
                parameters=params_dict,
                status=ToolStatus.FAILED,
                requestedAt=now,
                completedAt=now,
                error=f"Blocked by policy: {policy_eval.reason}",
            )
            with self._lock:
                self._executions[execution_id] = blocked_exec
            return blocked_exec, None

        if policy_eval.decision == PolicyDecision.REQUIRE_APPROVAL:
            # Check if an identical consequential action is already pending approval (prevent duplicate cards)
            with self._lock:
                for pending_req in self.approvals.get_pending():
                    if pending_req.toolName == tool_name and self._compute_action_signature(tool_name, pending_req.parameters) == sig:
                        existing_exec = self._executions.get(pending_req.toolExecutionId)
                        if existing_exec:
                            return existing_exec, pending_req

            # Create approval request
            approval_req = self.approvals.create_request(
                execution_id=execution_id,
                tool_name=tool_name,
                risk_tier=policy_eval.risk_tier,
                parameters=params_dict,
                action_summary=policy_eval.action_summary,
            )

            pending_exec = ToolExecutionModel(
                id=execution_id,
                toolName=tool_name,
                riskTier=tool.risk_tier,
                parameters=params_dict,
                status=ToolStatus.PENDING_APPROVAL,
                requestedAt=now,
            )

            with self._lock:
                self._executions[execution_id] = pending_exec

            audit_logger.log(
                action_name=f"APPROVAL_REQUIRED_{tool_name}",
                risk_tier=tool.risk_tier,
                status="AWAITING_APPROVAL",
                details={
                    "execution_id": execution_id,
                    "approval_id": approval_req.id,
                    "summary": policy_eval.action_summary,
                    "params": params_dict,
                },
            )
            return pending_exec, approval_req

        # 4. ALLOW_AUTO: Execute immediately
        exec_model = ToolExecutionModel(
            id=execution_id,
            toolName=tool_name,
            riskTier=tool.risk_tier,
            parameters=params_dict,
            status=ToolStatus.RUNNING,
            requestedAt=now,
        )
        with self._lock:
            self._executions[execution_id] = exec_model

        executed_model = await self._execute_bounded(
            tool=tool,
            validated_params=validated_params,
            execution_model=exec_model,
            session_id=session_id,
        )
        return executed_model, None

    async def resolve_approval(
        self,
        approval_id: str,
        approved: bool,
    ) -> Tuple[ApprovalRequestModel, Optional[ToolExecutionModel]]:
        """Resolve a pending approval token and execute the action if approved."""
        approval_req = self.approvals.respond(approval_id, approved=approved)

        with self._lock:
            exec_model = self._executions.get(approval_req.toolExecutionId)

        if not exec_model:
            raise ValueError(f"Associated execution '{approval_req.toolExecutionId}' not found.")

        now = datetime.now(timezone.utc).isoformat()

        if not approved:
            exec_model.status = ToolStatus.REJECTED
            exec_model.completedAt = now
            exec_model.error = "Operation was rejected by user."
            audit_logger.log(
                action_name=f"USER_REJECT_{exec_model.toolName}",
                risk_tier=exec_model.riskTier,
                status="REJECTED_BY_USER",
                details={"execution_id": exec_model.id, "approval_id": approval_id},
            )
            return approval_req, exec_model

        # User approved: check if already resolved/executed (idempotent duplicate guard)
        if exec_model.status in (ToolStatus.SUCCESS, ToolStatus.FAILED):
            return approval_req, exec_model

        audit_logger.log(
            action_name=f"USER_APPROVE_{exec_model.toolName}",
            risk_tier=exec_model.riskTier,
            status="APPROVED_BY_USER",
            details={"execution_id": exec_model.id, "approval_id": approval_id},
        )

        exec_model.status = ToolStatus.RUNNING
        tool = self.registry.get(exec_model.toolName)
        validated_params = self.registry.validate_parameters(exec_model.toolName, exec_model.parameters)

        executed_model = await self._execute_bounded(
            tool=tool,
            validated_params=validated_params,
            execution_model=exec_model,
            approval_id=approval_id,
        )

        # Cache completed consequential action to prevent loops
        if executed_model.status == ToolStatus.SUCCESS:
            sig = self._compute_action_signature(exec_model.toolName, exec_model.parameters)
            with self._lock:
                self._completed_action_cache[sig] = (executed_model, time.time())

        return approval_req, executed_model

    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running or pending execution."""
        with self._lock:
            exec_model = self._executions.get(execution_id)
            if not exec_model:
                return False

            if exec_model.status in (ToolStatus.SUCCESS, ToolStatus.FAILED, ToolStatus.CANCELLED, ToolStatus.REJECTED):
                return False

            exec_model.status = ToolStatus.CANCELLED
            exec_model.completedAt = datetime.now(timezone.utc).isoformat()
            exec_model.error = "Execution was cancelled."

            # Invalidate any associated pending approval request
            self.approvals.invalidate_for_execution(execution_id)

            # Cancel running asyncio task if active
            task = self._running_tasks.get(execution_id)
            if task and not task.done():
                task.cancel()

        audit_logger.log(
            action_name=f"CANCEL_{exec_model.toolName}",
            risk_tier=exec_model.riskTier,
            status="CANCELLED",
            details={"execution_id": execution_id},
        )
        return True

    async def _execute_bounded(
        self,
        tool,
        validated_params,
        execution_model: ToolExecutionModel,
        session_id: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> ToolExecutionModel:
        """Execute a tool within bounded timeout constraints and verify outcome."""
        ctx = ExecutionContext(
            execution_id=execution_model.id,
            session_id=session_id,
            approval_id=approval_id,
        )

        start_time = time.perf_counter()
        current_task = asyncio.current_task()
        if current_task:
            with self._lock:
                self._running_tasks[execution_model.id] = current_task

        try:
            # Enforce bounded timeout
            result: ToolResult = await asyncio.wait_for(
                tool.execute(validated_params, ctx),
                timeout=self.default_timeout_seconds,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Post-execution verification
            verified = await tool.verify(validated_params, result, ctx)
            result.verified = verified
            result.execution_time_ms = duration_ms

            execution_model.completedAt = datetime.now(timezone.utc).isoformat()

            if result.success:
                execution_model.status = ToolStatus.SUCCESS
                execution_model.result = result.data
                audit_logger.log(
                    action_name=f"EXECUTE_SUCCESS_{tool.name}",
                    risk_tier=tool.risk_tier,
                    status="SUCCESS",
                    details={
                        "execution_id": execution_model.id,
                        "duration_ms": duration_ms,
                        "verified": verified,
                    },
                )
            else:
                execution_model.status = ToolStatus.FAILED
                execution_model.error = result.error or "Operation reported failure."
                audit_logger.log(
                    action_name=f"EXECUTE_FAILED_{tool.name}",
                    risk_tier=tool.risk_tier,
                    status="FAILED",
                    details={
                        "execution_id": execution_model.id,
                        "error": result.error,
                        "error_code": result.error_code,
                    },
                )

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            execution_model.status = ToolStatus.FAILED
            execution_model.completedAt = datetime.now(timezone.utc).isoformat()
            execution_model.error = f"Operation timed out after {self.default_timeout_seconds}s limit."
            audit_logger.log(
                action_name=f"TIMEOUT_{tool.name}",
                risk_tier=tool.risk_tier,
                status="TIMEOUT",
                details={
                    "execution_id": execution_model.id,
                    "timeout_seconds": self.default_timeout_seconds,
                },
            )
        except asyncio.CancelledError:
            execution_model.status = ToolStatus.CANCELLED
            execution_model.completedAt = datetime.now(timezone.utc).isoformat()
            execution_model.error = "Execution was asynchronously cancelled."
            raise
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            execution_model.status = ToolStatus.FAILED
            execution_model.completedAt = datetime.now(timezone.utc).isoformat()
            execution_model.error = f"Execution raised unexpected error: {str(exc)}"
            audit_logger.log(
                action_name=f"ERROR_{tool.name}",
                risk_tier=tool.risk_tier,
                status="EXCEPTION",
                details={"execution_id": execution_model.id, "exception": str(exc)},
            )
        finally:
            with self._lock:
                self._running_tasks.pop(execution_model.id, None)

        return execution_model


# Default global execution engine instance
execution_engine = ExecutionEngine()

