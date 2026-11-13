"""Task Planning and Execution State REST API Router."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.planning.models import TaskPlan
from app.planning.planner import task_planning_engine

router = APIRouter(prefix="/v1/plans", tags=["plans"])


class PlanRequest(BaseModel):
    objective: str
    session_id: Optional[str] = None


class PlanCancelRequest(BaseModel):
    reason: Optional[str] = "Operator cancelled"


@router.post("", response_model=TaskPlan)
def create_plan(req: PlanRequest):
    """Formulate an explicit goal-oriented execution plan."""
    return task_planning_engine.create_goal_plan(
        user_prompt=req.objective,
        session_id=req.session_id,
    )


@router.get("/{plan_id}", response_model=TaskPlan)
def get_plan(plan_id: str):
    """Retrieve execution progress and step verification status of a task plan."""
    plan = task_planning_engine.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Task plan not found.")
    return plan


@router.post("/{plan_id}/cancel", response_model=TaskPlan)
def cancel_plan(plan_id: str, req: PlanCancelRequest):
    """Cancel an active task plan."""
    plan = task_planning_engine.cancel_plan(plan_id, reason=req.reason or "Operator cancelled")
    if not plan:
        raise HTTPException(status_code=404, detail="Task plan not found.")
    return plan
