"""Typed BaseTools for Goal-Oriented Task Planning (Phase 6 Foundation)."""

from typing import Optional
from pydantic import BaseModel, Field

from app.planning.models import TaskPlan
from app.planning.planner import task_planning_engine
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class PlanCreateParams(BaseModel):
    objective: str = Field(..., description="High-level goal or objective to formulate an explicit execution plan for.")


class PlanGetParams(BaseModel):
    plan_id: str = Field(..., description="Unique plan ID to inspect.")


class PlanCreateTool(BaseTool):
    name = "plan_create"
    description = (
        "Formulate an explicit, dependency-linked task plan for a high-level goal. "
        "Breaks down objectives into verified sequential steps with verification criteria."
    )
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = PlanCreateParams

    async def execute(self, params: PlanCreateParams, context: ExecutionContext) -> ToolResult:
        try:
            plan = task_planning_engine.create_goal_plan(
                user_prompt=params.objective,
                session_id=context.execution_id,
            )
            return ToolResult(
                success=True,
                data={
                    "plan_id": plan.id,
                    "interpreted_goal": plan.interpreted_goal,
                    "required_outcome": plan.required_outcome,
                    "total_steps": len(plan.steps),
                    "steps": [s.model_dump() for s in plan.steps],
                    "status": plan.status.value,
                },
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Plan formulation failed: {str(exc)}",
                error_code="PLAN_CREATION_FAILED",
            )


class PlanGetTool(BaseTool):
    name = "plan_get"
    description = "Inspect the execution state and step verification progress of an active task plan."
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = PlanGetParams

    async def execute(self, params: PlanGetParams, context: ExecutionContext) -> ToolResult:
        plan = task_planning_engine.get_plan(params.plan_id)
        if not plan:
            return ToolResult(
                success=False,
                error=f"Plan '{params.plan_id}' not found.",
                error_code="PLAN_NOT_FOUND",
            )
        return ToolResult(
            success=True,
            data=plan.model_dump(),
            verified=True,
        )
