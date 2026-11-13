"""Automated Test Suite for Goal-Oriented Reasoning & Adaptive Task Planning (Phase 6)."""

import pytest

from app.planning.clarification import clarification_policy
from app.planning.models import RecoveryStrategy, StepStatus, TaskStatus
from app.planning.planner import task_planning_engine
from app.planning.tools import (
    PlanCreateParams,
    PlanCreateTool,
    PlanGetParams,
    PlanGetTool,
)
from app.tools.base import ExecutionContext


def test_messaging_goal_formulation():
    """Verify autonomous plan formulation for high-level messaging objective."""
    prompt = "Message David that I'll be 15 minutes late."
    plan = task_planning_engine.create_goal_plan(user_prompt=prompt, session_id="test-session-msg")

    assert plan is not None
    assert "David" in plan.interpreted_goal
    assert len(plan.steps) >= 4

    # Verify dependency chain
    step_ids = [s.id for s in plan.steps]
    assert "step-1" in step_ids
    assert "step-2" in step_ids
    assert "step-1" in plan.steps[1].depends_on

    # Consequential step has requires_approval == True
    send_step = next(s for s in plan.steps if "send" in s.description.lower())
    assert send_step.requires_approval is True
    assert send_step.verification_criteria != ""


def test_document_goal_formulation():
    """Verify autonomous plan formulation for finding, updating, and saving a document."""
    prompt = "Find the latest project document, update the introduction, and save it."
    plan = task_planning_engine.create_goal_plan(user_prompt=prompt, session_id="test-session-doc")

    assert plan is not None
    assert len(plan.steps) == 4
    # Step 1: list/search
    assert plan.steps[0].required_tool == "windows_list_windows"
    # Step 2: read
    assert "read" in str(plan.steps[1].parameters) or "inspect" in plan.steps[1].description.lower()
    # Step 3: edit/modify (consequential)
    assert plan.steps[2].requires_approval is True
    # Step 4: save
    assert "save" in plan.steps[3].description.lower()


def test_adaptive_replanning_on_step_failure():
    """Verify planner dynamically adapts and replans when an action fails."""
    prompt = "Open my browser and find information about quantum computing."
    plan = task_planning_engine.create_goal_plan(user_prompt=prompt)

    # Simulate failure on step-1 (e.g. Opera GX fails to launch)
    failed_step = plan.steps[0]
    updated_plan = task_planning_engine.record_step_result(
        plan_id=plan.id,
        step_id=failed_step.id,
        success=False,
        error_message="Browser launch timeout: Opera GX did not start.",
    )

    # Planner should adapt to alternative browser (Google Chrome)
    assert updated_plan.status == TaskStatus.REPLANNING
    assert updated_plan.recovery_strategy == RecoveryStrategy.TRY_ALTERNATIVE_APPLICATION
    assert any("chrome" in str(s.parameters).lower() for s in updated_plan.steps)


def test_clarification_policy_guidelines():
    """Verify when questions should be asked vs when autonomous execution proceeds."""
    # Scenario A: Known saved preference for person -> Should NOT ask
    from app.memory.models import PreferenceCategory
    from app.memory.service import preference_service

    preference_service.set_explicit_preference(
        category=PreferenceCategory.PERSON_COMMUNICATIONS,
        key="person:sarah",
        app_id="messaging.whatsapp",
        target_entity="sarah",
    )

    q1 = clarification_policy.should_ask_messaging_application(
        recipient_name="sarah",
        available_apps=["messaging.whatsapp", "messaging.discord"],
    )
    assert q1 is None, "Should proceed autonomously when reliable preference exists"

    # Scenario B: Unknown recipient preference with multiple apps -> SHOULD ask
    q2 = clarification_policy.should_ask_messaging_application(
        recipient_name="unknown_contact",
        available_apps=["messaging.whatsapp", "messaging.discord"],
    )
    assert q2 is not None
    assert "unknown_contact" in q2.question_text
    assert q2.can_be_remembered is True

    # Scenario C: User explicitly requested an app -> Should NOT ask
    q3 = clarification_policy.should_ask_messaging_application(
        recipient_name="unknown_contact",
        available_apps=["messaging.whatsapp", "messaging.discord"],
        explicit_app="WhatsApp",
    )
    assert q3 is None


def test_plan_cancellation():
    """Verify user or operator can cleanly cancel an in-progress task plan."""
    plan = task_planning_engine.create_goal_plan(user_prompt="Message John that I arrived")
    cancelled = task_planning_engine.cancel_plan(plan.id, reason="User clicked stop")

    assert cancelled is not None
    assert cancelled.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_plan_tools():
    """Verify plan_create and plan_get tools."""
    create_tool = PlanCreateTool()
    get_tool = PlanGetTool()
    ctx = ExecutionContext(execution_id="test-plan-tool")

    res_create = await create_tool.execute(
        PlanCreateParams(objective="Find my spreadsheet and calculate total"),
        ctx,
    )
    assert res_create.success is True
    plan_id = res_create.data["plan_id"]

    res_get = await get_tool.execute(
        PlanGetParams(plan_id=plan_id),
        ctx,
    )
    assert res_get.success is True
    assert res_get.data["id"] == plan_id


def test_browser_research_goal_formulation():
    """Verify autonomous plan formulation for multi-step browser search and article discovery."""
    prompt = "can you open a new tab in opera and find me an article about species of snakes found in Nepal"
    plan = task_planning_engine.create_goal_plan(user_prompt=prompt, session_id="test-snakes-plan")

    assert plan is not None
    assert "species of snakes found in Nepal" in plan.interpreted_goal or "snakes" in plan.interpreted_goal.lower()
    assert len(plan.steps) == 2
    # Step 1: Navigate to query in Opera GX
    assert plan.steps[0].required_tool == "app_execute_capability"
    assert plan.steps[0].parameters["app_id"] == "browser.opera_gx"
    assert plan.steps[0].parameters["capability_id"] == "browser.navigate"
    assert "species of snakes found in Nepal" in plan.steps[0].parameters["parameters"]["query"]
    # Step 2: Read active page
    assert plan.steps[1].required_tool == "app_execute_capability"
    assert plan.steps[1].parameters["capability_id"] == "browser.read_page"
    assert plan.steps[1].depends_on == ["step-1"]

