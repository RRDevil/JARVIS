"""Data Models for Goal-Oriented Reasoning and Adaptive Task Planning (Phase 6 Foundation)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.tools.base import RiskTier


class StepStatus(str, Enum):
    """Execution status of an individual task plan step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED_AWAITING_APPROVAL = "blocked_awaiting_approval"


class TaskStatus(str, Enum):
    """Overall execution lifecycle status of a task plan."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"
    CANCELLED = "cancelled"
    REPLANNING = "replanning"


class RecoveryStrategy(str, Enum):
    """Automated recovery strategy when a plan step fails."""
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    TRY_ALTERNATIVE_TOOL = "try_alternative_tool"
    TRY_ALTERNATIVE_APPLICATION = "try_alternative_application"
    REPLAN_REMAINING_STEPS = "replan_remaining_steps"
    ASK_OPERATOR_CLARIFICATION = "ask_operator_clarification"
    ABORT = "abort"


class PlanStep(BaseModel):
    """Atomic step in a structured goal-oriented execution plan."""
    id: str = Field(..., description="Unique step identifier (e.g. 'step-1').")
    order: int = Field(..., description="1-indexed step order.")
    description: str = Field(..., description="Human-readable explanation of this step's purpose.")
    required_tool: str = Field(..., description="Name of registered tool to execute.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters to supply to the tool.")
    depends_on: List[str] = Field(default_factory=list, description="IDs of prerequisite steps that must complete first.")
    risk_tier: RiskTier = Field(default=RiskTier.READ_ONLY, description="Risk classification.")
    requires_approval: bool = Field(default=False, description="Whether human authorization is required.")
    verification_criteria: str = Field(..., description="Condition or observation that verifies successful completion.")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current step state.")
    observed_result: Optional[Any] = Field(None, description="Actual result observed after step execution.")
    error: Optional[str] = Field(None, description="Error message if step failed.")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class ClarificationQuestion(BaseModel):
    """Structured question asked to user when critical ambiguity or preference is missing."""
    question_id: str
    question_text: str
    target_entity: Optional[str] = None
    options: List[str] = Field(default_factory=list)
    default_option: Optional[str] = None
    reason_for_asking: str = Field(..., description="Why autonomous planning could not proceed safely without user input.")
    can_be_remembered: bool = Field(default=True, description="Whether answer should be stored in preference memory.")


class TaskPlan(BaseModel):
    """Complete goal-oriented task plan with dependencies, verification criteria, and recovery."""
    id: str = Field(..., description="Unique plan identifier (e.g. 'plan-12345').")
    session_id: Optional[str] = None
    original_objective: str = Field(..., description="User's original natural-language instruction.")
    interpreted_goal: str = Field(..., description="Clarified objective synthesized by reasoning layer.")
    required_outcome: str = Field(..., description="Concrete condition defining task completion.")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made by planner.")
    constraints: List[str] = Field(default_factory=list, description="Safety or domain constraints.")
    steps: List[PlanStep] = Field(default_factory=list, description="Ordered dependency-linked steps.")
    current_step_index: int = Field(default=0, description="Index of currently active step.")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Overall plan status.")
    pending_clarification: Optional[ClarificationQuestion] = None
    recovery_strategy: Optional[RecoveryStrategy] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
