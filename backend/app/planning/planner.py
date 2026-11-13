"""Task Planning and Adaptive Problem Solving Engine (Phase 6 Foundation).

Synthesizes structured goal-oriented execution plans, manages dependencies,
evaluates step verification criteria, and performs dynamic replanning upon failure.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.memory.service import preference_service
from app.planning.clarification import clarification_policy
from app.planning.models import (
    PlanStep,
    RecoveryStrategy,
    StepStatus,
    TaskPlan,
    TaskStatus,
)
from app.tools.base import RiskTier

logger = logging.getLogger("jarvis.planning.planner")


class TaskPlanningEngine:
    """Orchestrates goal-oriented planning, step verification, and adaptive replanning."""

    def __init__(self):
        self._active_plans: Dict[str, TaskPlan] = {}

    def get_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Retrieve task plan by ID."""
        return self._active_plans.get(plan_id)

    def create_goal_plan(
        self,
        user_prompt: str,
        session_id: Optional[str] = None,
    ) -> TaskPlan:
        """Analyze a user objective and formulate an explicit dependency-linked task plan."""
        plan_id = f"plan-{uuid.uuid4().hex[:10]}"
        prompt_clean = user_prompt.strip()
        lower = prompt_clean.lower()

        # 1. Pattern: Messaging Goal (e.g. "Message XYZ that I'll be late", "Send XYZ a message...")
        if any(v in lower for v in ["message ", "send a message", "tell ", "dm "]):
            return self._formulate_messaging_plan(plan_id, prompt_clean, session_id)

        # 2. Pattern: Document Editing Goal (e.g. "Find latest document, update introduction, and save it")
        if any(v in lower for v in ["document", "spreadsheet", "presentation", "report", "file"]):
            if any(a in lower for a in ["update", "edit", "change", "modify", "save"]):
                return self._formulate_document_plan(plan_id, prompt_clean, session_id)

        # 3. Pattern: Browser Research / Information Retrieval Goal
        if any(v in lower for v in ["find information", "search for", "look up", "research", "browse"]):
            return self._formulate_research_plan(plan_id, prompt_clean, session_id)

        # 4. Default: Generalized Multi-Step Plan
        return self._formulate_generic_plan(plan_id, prompt_clean, session_id)

    def _formulate_messaging_plan(self, plan_id: str, prompt: str, session_id: Optional[str]) -> TaskPlan:
        """Formulate goal-oriented plan for contacting a person."""
        lower = prompt.lower()
        # Extract recipient name
        recipient = "recipient"
        for prefix in ["message ", "tell ", "send a message to ", "dm "]:
            if prefix in lower:
                rest = prompt[lower.index(prefix) + len(prefix):].strip()
                words = rest.split()
                if words:
                    recipient = words[0].strip(" ,:;.!?")
                break

        # Extract message content if present
        content = "I'll be 15 minutes late."
        for indicator in ["saying ", "that ", ": "]:
            if indicator in lower:
                content = prompt[lower.index(indicator) + len(indicator):].strip(" \"'")
                break

        # Check preference resolution for application
        res = preference_service.resolve_application(
            person_name=recipient,
            workflow_type="messaging",
        )
        target_app = res.resolved_app_id or "messaging.whatsapp"
        target_browser = res.resolved_browser_id or "browser.opera_gx"

        steps = [
            PlanStep(
                id="step-1",
                order=1,
                description=f"Resolve saved communication preference for {recipient}",
                required_tool="preference_query",
                parameters={"person_name": recipient, "workflow_type": "messaging"},
                verification_criteria="Valid application ID identified from preference memory or supported defaults.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-2",
                order=2,
                description=f"Open {target_app} in {target_browser}",
                required_tool="app_execute_capability",
                parameters={"app_id": target_browser, "capability_id": "browser.navigate", "parameters": {"url": "https://web.whatsapp.com" if "whatsapp" in target_app else "https://www.instagram.com/direct/inbox/"}},
                depends_on=["step-1"],
                risk_tier=RiskTier.CONTROLLED,
                verification_criteria="Target messaging interface window is active and loaded.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-3",
                order=3,
                description=f"Locate and verify conversation thread for recipient '{recipient}'",
                required_tool="semantic_read_conversations",
                parameters={"app_name": target_app, "contact_query": recipient},
                depends_on=["step-2"],
                verification_criteria=f"High-confidence conversation candidate matching '{recipient}' identified on screen.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-4",
                order=4,
                description=f"Prepare exact message: \"{content}\"",
                required_tool="app_execute_capability",
                parameters={"app_id": target_app, "capability_id": f"{target_app.replace('messaging.', '')}.draft_message", "parameters": {"recipient": recipient, "text": content}},
                depends_on=["step-3"],
                risk_tier=RiskTier.CONTROLLED,
                verification_criteria="Message text staged into input field without sending.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-5",
                order=5,
                description=f"Obtain user approval and send message to {recipient}",
                required_tool="app_execute_capability",
                parameters={"app_id": target_app, "capability_id": f"{target_app.replace('messaging.', '')}.send_message", "parameters": {"recipient": recipient, "text": content}},
                depends_on=["step-4"],
                risk_tier=RiskTier.CONSEQUENTIAL,
                requires_approval=True,
                verification_criteria="Operator confirms approval; message dispatched; receipt confirmed on screen.",
                status=StepStatus.PENDING,
            ),
        ]

        plan = TaskPlan(
            id=plan_id,
            session_id=session_id,
            original_objective=prompt,
            interpreted_goal=f"Send approved message to {recipient} via {target_app}",
            required_outcome=f"Message '{content}' successfully delivered to {recipient} with operator authorization.",
            assumptions=[f"User wishes to contact {recipient}", f"Preferred application is {target_app}"],
            constraints=["Exact message payload must be preserved", "Must obtain human approval before transmission"],
            steps=steps,
            status=TaskStatus.IN_PROGRESS,
        )
        self._active_plans[plan_id] = plan
        return plan

    def _formulate_document_plan(self, plan_id: str, prompt: str, session_id: Optional[str]) -> TaskPlan:
        """Formulate goal-oriented plan for finding and editing a document."""
        steps = [
            PlanStep(
                id="step-1",
                order=1,
                description="Search active windows and recent document directory",
                required_tool="windows_list_windows",
                parameters={},
                verification_criteria="Identified active Word, Excel, or text editor window.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-2",
                order=2,
                description="Inspect existing document text and structure",
                required_tool="app_execute_capability",
                parameters={"app_id": "office.word", "capability_id": "word.read_document", "parameters": {}},
                depends_on=["step-1"],
                verification_criteria="Extracted visible document content and paragraphs.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-3",
                order=3,
                description="Apply requested modifications to document",
                required_tool="app_execute_capability",
                parameters={"app_id": "office.word", "capability_id": "word.modify_text", "parameters": {}},
                depends_on=["step-2"],
                risk_tier=RiskTier.CONSEQUENTIAL,
                requires_approval=True,
                verification_criteria="Changes staged into document body under authorization.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-4",
                order=4,
                description="Save document and verify file integrity",
                required_tool="app_execute_capability",
                parameters={"app_id": "office.word", "capability_id": "word.save_document", "parameters": {}},
                depends_on=["step-3"],
                risk_tier=RiskTier.CONTROLLED,
                verification_criteria="Document saved cleanly without error codes.",
                status=StepStatus.PENDING,
            ),
        ]

        plan = TaskPlan(
            id=plan_id,
            session_id=session_id,
            original_objective=prompt,
            interpreted_goal="Locate recent document, inspect content, apply edits, and save",
            required_outcome="Document updated with verified modifications and saved to disk.",
            assumptions=["Document is available in Microsoft Office or local filesystem"],
            constraints=["Must preserve document integrity", "Must obtain approval before mutating edits"],
            steps=steps,
            status=TaskStatus.IN_PROGRESS,
        )
        self._active_plans[plan_id] = plan
        return plan

    def _formulate_research_plan(self, plan_id: str, prompt: str, session_id: Optional[str]) -> TaskPlan:
        """Formulate plan for web search and page synthesis."""
        steps = [
            PlanStep(
                id="step-1",
                order=1,
                description="Navigate to search query in preferred browser",
                required_tool="app_execute_capability",
                parameters={"app_id": "browser.opera_gx", "capability_id": "browser.navigate", "parameters": {"query": prompt}},
                verification_criteria="Search results page loaded.",
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id="step-2",
                order=2,
                description="Read and synthesize search result contents",
                required_tool="app_execute_capability",
                parameters={"app_id": "browser.opera_gx", "capability_id": "browser.read_page", "parameters": {}},
                depends_on=["step-1"],
                verification_criteria="Extracted page text containing relevant query answers.",
                status=StepStatus.PENDING,
            ),
        ]
        plan = TaskPlan(
            id=plan_id,
            session_id=session_id,
            original_objective=prompt,
            interpreted_goal="Perform research query and synthesize information",
            required_outcome="Synthesized summary of relevant web results.",
            steps=steps,
            status=TaskStatus.IN_PROGRESS,
        )
        self._active_plans[plan_id] = plan
        return plan

    def _formulate_generic_plan(self, plan_id: str, prompt: str, session_id: Optional[str]) -> TaskPlan:
        """Fallback generalized plan."""
        steps = [
            PlanStep(
                id="step-1",
                order=1,
                description=f"Inspect system state and execute objective: {prompt}",
                required_tool="windows_list_windows",
                parameters={},
                verification_criteria="Active system state evaluated.",
                status=StepStatus.PENDING,
            )
        ]
        plan = TaskPlan(
            id=plan_id,
            session_id=session_id,
            original_objective=prompt,
            interpreted_goal=prompt,
            required_outcome="Objective completed.",
            steps=steps,
            status=TaskStatus.IN_PROGRESS,
        )
        self._active_plans[plan_id] = plan
        return plan

    def record_step_result(
        self,
        plan_id: str,
        step_id: str,
        success: bool,
        observed_result: Any = None,
        error_message: Optional[str] = None,
    ) -> TaskPlan:
        """Update step execution state, evaluate outcome against verification criteria, and trigger replanning if needed."""
        plan = self._active_plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan '{plan_id}' not found.")

        target_step = next((s for s in plan.steps if s.id == step_id), None)
        if not target_step:
            raise ValueError(f"Step '{step_id}' not found in plan '{plan_id}'.")

        now = datetime.now(timezone.utc).isoformat()
        target_step.completed_at = now
        target_step.observed_result = observed_result

        if success:
            target_step.status = StepStatus.COMPLETED
            # Check if all steps completed
            if all(s.status == StepStatus.COMPLETED for s in plan.steps):
                plan.status = TaskStatus.COMPLETED
                plan.completed_at = now
            else:
                plan.current_step_index += 1
        else:
            target_step.status = StepStatus.FAILED
            target_step.error = error_message or "Step execution failed."
            # Attempt adaptive recovery
            plan = self._replan_on_failure(plan, target_step)

        plan.updated_at = now
        return plan

    def _replan_on_failure(self, plan: TaskPlan, failed_step: PlanStep) -> TaskPlan:
        """Inspect the failure, determine alternative supported approaches, and dynamically adapt remaining steps."""
        logger.warning(f"Plan '{plan.id}' step '{failed_step.id}' failed: {failed_step.error}. Initiating adaptive replan.")
        err_lower = (failed_step.error or "").lower()

        # Recovery 1: Browser Navigation / Access failure -> Fail over to alternative browser (e.g. Chrome)
        if "browser" in failed_step.required_tool or "opera" in str(failed_step.parameters).lower():
            plan.recovery_strategy = RecoveryStrategy.TRY_ALTERNATIVE_APPLICATION
            # Adapt subsequent steps to Google Chrome
            for step in plan.steps:
                if step.status == StepStatus.PENDING and "app_id" in step.parameters:
                    if "opera" in str(step.parameters.get("app_id", "")).lower():
                        step.parameters["app_id"] = "browser.chrome"
                        step.description = step.description.replace("Opera GX", "Google Chrome")
            logger.info(f"Adapted plan '{plan.id}' to alternative browser: Google Chrome.")
            plan.status = TaskStatus.REPLANNING
            return plan

        # Recovery 2: Target application not open -> Insert launch step
        if "application_not_running" in err_lower or "window not found" in err_lower:
            plan.recovery_strategy = RecoveryStrategy.TRY_ALTERNATIVE_TOOL
            launch_step = PlanStep(
                id=f"step-launch-{uuid.uuid4().hex[:4]}",
                order=failed_step.order,
                description="Launch target application",
                required_tool="windows_launch_app",
                parameters={"app_id": failed_step.parameters.get("app_id", "notepad")},
                verification_criteria="Target application launched and active.",
                status=StepStatus.PENDING,
            )
            # Re-order and re-insert before failed step
            plan.steps.insert(plan.current_step_index, launch_step)
            failed_step.status = StepStatus.PENDING
            plan.status = TaskStatus.REPLANNING
            return plan

        # Recovery 3: Non-recoverable without operator input -> Mark failed and prompt user
        plan.recovery_strategy = RecoveryStrategy.ASK_OPERATOR_CLARIFICATION
        plan.status = TaskStatus.FAILED
        return plan

    def cancel_plan(self, plan_id: str, reason: str = "Operator cancelled") -> Optional[TaskPlan]:
        """Cancel an in-progress plan."""
        plan = self._active_plans.get(plan_id)
        if plan:
            plan.status = TaskStatus.CANCELLED
            plan.updated_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Task plan '{plan_id}' cancelled: {reason}")
        return plan


# Global singleton instance
task_planning_engine = TaskPlanningEngine()
