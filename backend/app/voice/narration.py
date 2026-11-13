"""Centralized Voice Narration System for J.A.R.V.I.S. Task Execution (Phase 5.3).

Translates task lifecycle events (acknowledgment, planning, tool execution,
approval requests, recovery, completion) into natural, grounded spoken narration.
Throttles routine progress to prevent excessive chatter while ensuring J.A.R.V.I.S.
feels present, responsive, and grounded.
"""

from datetime import datetime, timezone
from enum import Enum
import logging
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid
from pydantic import BaseModel, Field

logger = logging.getLogger("jarvis.voice.narration")


class TaskLifecycleEventType(str, Enum):
    """Normalized lifecycle event types during agentic task execution."""
    TASK_RECEIVED = "TASK_RECEIVED"
    TASK_ACKNOWLEDGED = "TASK_ACKNOWLEDGED"
    PLANNING_STARTED = "PLANNING_STARTED"
    PLANNING_COMPLETED = "PLANNING_COMPLETED"
    ACTION_STARTED = "ACTION_STARTED"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    ACTION_FAILED = "ACTION_FAILED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"


class NarrationPriority(int, Enum):
    """Prioritization tiers for the speech queue. Lower number = higher priority."""
    CRITICAL = 1        # Safety warnings, severe faults
    APPROVAL = 2        # Approval requests and user decisions
    ACKNOWLEDGMENT = 3  # Immediate task receipt acknowledgment
    PROGRESS = 4        # Execution progress updates
    PREVIEW = 5         # User voice testing / previews in settings
    FINAL_RESPONSE = 6  # Conversational final responses


class TaskLifecycleEvent(BaseModel):
    """Rich event payload representing a milestone in task execution."""
    task_id: str = Field(..., description="Unique identifier for the associated task or turn.")
    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:10]}")
    event_type: TaskLifecycleEventType = Field(..., description="Lifecycle event type.")
    approval_id: Optional[str] = Field(None, description="Bound approval request ID if applicable.")
    action_or_app: Optional[str] = Field(None, description="Target tool or desktop application name.")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    task_state: str = Field(default="EXECUTING", description="Assistant state (THINKING, EXECUTING, AWAITING_APPROVAL, etc.).")
    progress_info: Optional[Dict[str, Any]] = Field(default=None, description="Detailed event metadata.")
    is_narratable: bool = Field(default=True, description="Whether this event should be announced verbally.")
    narration_text: Optional[str] = Field(None, description="Concise, natural spoken utterance.")
    priority: int = Field(default=NarrationPriority.PROGRESS, description="Speech priority (1-5).")


class NarrationSettings(BaseModel):
    """Configurable narration thresholds and feature flags."""
    enabled: bool = True
    progress_interval_seconds: float = 8.0
    acknowledge_tasks: bool = True
    announce_approvals: bool = True
    announce_errors: bool = True
    announce_progress: bool = True
    announce_completion: bool = True


class TaskNarrationEngine:
    """Centralized engine evaluating lifecycle events and generating grounded spoken narration."""

    def __init__(self, settings: Optional[NarrationSettings] = None):
        self.settings = settings or NarrationSettings()
        self._lock = threading.RLock()
        self._last_narration_time: Dict[str, float] = {}
        self._last_narration_text: Dict[str, str] = {}
        self._last_action_by_task: Dict[str, str] = {}
        self._pending_approvals: Dict[str, bool] = {}

    def configure(self, settings_update: Dict[str, Any]) -> NarrationSettings:
        """Update narration settings dynamically."""
        with self._lock:
            data = self.settings.model_dump()
            data.update(settings_update)
            self.settings = NarrationSettings(**data)
            return self.settings

    def reset_task(self, task_id: str) -> None:
        """Clear task state and throttling history upon completion or cancellation."""
        with self._lock:
            self._last_narration_time.pop(task_id, None)
            self._last_narration_text.pop(task_id, None)
            self._last_action_by_task.pop(task_id, None)
            self._pending_approvals.pop(task_id, None)

    # -------------------------------------------------------------------------
    # 1. Immediate Acknowledgment Generation
    # -------------------------------------------------------------------------

    def generate_acknowledgment(self, user_prompt: str, task_id: str) -> Optional[TaskLifecycleEvent]:
        """Generate prompt, natural acknowledgment when user submits a task."""
        with self._lock:
            p_strip = user_prompt.strip().lower()
            # Do not acknowledge internal system / continuation prompts
            if p_strip.startswith("[system") or p_strip.startswith("[approval") or not p_strip:
                return None

            text = self._formulate_acknowledgment_text(user_prompt)
            event = TaskLifecycleEvent(
                task_id=task_id,
                event_id=f"ack:{task_id}",
                event_type=TaskLifecycleEventType.TASK_ACKNOWLEDGED,
                action_or_app=None,
                task_state="THINKING",
                is_narratable=self.settings.enabled and self.settings.acknowledge_tasks,
                narration_text=text,
                priority=NarrationPriority.ACKNOWLEDGMENT,
                progress_info={"context": "acknowledgment", "prompt_preview": user_prompt[:80]},
            )
            self._record_narration(task_id, text)
            return event

    def _formulate_acknowledgment_text(self, prompt: str) -> str:
        p = prompt.lower().strip()

        # Specific destination detection
        dest = None
        if "instagram" in p:
            dest = "Instagram"
        elif "youtube" in p:
            dest = "YouTube"
        elif "reddit" in p:
            dest = "Reddit"
        elif "github" in p:
            dest = "GitHub"

        # Specific desktop and browser applications check first
        for app_name, display in [
            ("opera", "Opera GX"),
            ("chrome", "Chrome"),
            ("word", "Microsoft Word"),
            ("excel", "Microsoft Excel"),
            ("powerpoint", "PowerPoint"),
            ("discord", "Discord"),
            ("notepad", "Notepad"),
            ("calculator", "Calculator"),
            ("terminal", "Windows Terminal"),
        ]:
            if app_name in p:
                if app_name in ("opera", "chrome"):
                    if dest:
                        return f"Certainly, sir. Opening {display} and navigating to {dest}."
                    if any(w in p for w in ("search", "navigate", "go to", "visit")):
                        return f"Certainly, sir. Opening {display} and navigating to the page."
                return f"Certainly, sir. Opening {display}."

        # Browser / Web Navigation without explicit browser name
        if any(w in p for w in ("instagram", "youtube", "browse", "website", "navigate", "search for", "google")):
            if dest:
                return f"Certainly, sir. Opening {dest} in your browser."
            return "Certainly, sir. Navigating to the requested page."

        # Desktop Applications Launch generic
        if any(w in p for w in ("open", "launch", "start")):
            return "Of course, sir. Opening that now."

        # Grounded clicking & screen interaction
        if any(w in p for w in ("click", "press", "select", "tap", "type into", "enter text")):
            return "On it, sir. Locating the requested element."

        # Screen perception & reading
        if any(w in p for w in ("read the screen", "inspect", "what is on", "look at", "capture")):
            return "Looking into that now, sir. Inspecting the display."

        # Document & Office preparation
        if any(w in p for w in ("document", "write", "spreadsheet", "draft", "presentation")):
            return "Right away. Preparing the workspace."

        # General conversational or research query
        return "Understood, sir. Looking into that for you."

    # -------------------------------------------------------------------------
    # 2. Action & Progress Narration
    # -------------------------------------------------------------------------

    def generate_action_started(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        task_id: str,
        stage: str = "EXECUTING",
    ) -> Optional[TaskLifecycleEvent]:
        """Generate grounded spoken narration when a meaningful tool execution begins."""
        with self._lock:
            if not self.settings.enabled or not self.settings.announce_progress:
                return None

            action_key, spoken = self._formulate_action_started_text(tool_name, parameters)
            if not spoken:
                return None

            # Deduplication & Throttling
            now = time.time()
            last_time = self._last_narration_time.get(task_id, 0.0)
            last_action = self._last_action_by_task.get(task_id, "")

            # If it's the exact same action key within the throttle interval, suppress
            if action_key == last_action and (now - last_time) < self.settings.progress_interval_seconds:
                return None

            # If it's a minor step and less than progress_interval_seconds since last narration
            is_milestone = any(m in action_key for m in ("navigate", "launch", "click", "draft", "send"))
            if not is_milestone and (now - last_time) < self.settings.progress_interval_seconds:
                return None

            self._last_action_by_task[task_id] = action_key
            self._record_narration(task_id, spoken)

            return TaskLifecycleEvent(
                task_id=task_id,
                event_type=TaskLifecycleEventType.ACTION_STARTED,
                action_or_app=action_key,
                task_state=stage,
                is_narratable=True,
                narration_text=spoken,
                priority=NarrationPriority.PROGRESS,
                progress_info={"context": "progress", "tool_name": tool_name, "parameters": parameters},
            )

    def _formulate_action_started_text(self, tool_name: str, params: Dict[str, Any]) -> (str, Optional[str]):
        """Derive grounded action identifier and natural speech text from tool parameters."""
        t_clean = tool_name.lower().strip()

        # Application Framework Capabilities
        if t_clean == "app_execute_capability":
            app_id = params.get("app_id", "")
            cap_id = params.get("capability_id", "")
            inner_params = params.get("parameters", {}) or {}

            # Browser navigation
            if cap_id == "browser.navigate":
                url = inner_params.get("url", "")
                dest = self._clean_url_destination(url)
                return f"{app_id}::navigate", f"I'm navigating to {dest}."

            # Browser inspection
            if cap_id == "browser.read_page":
                return f"{app_id}::read_page", "I'm inspecting the contents of the active page."

            # Tab management
            if cap_id == "browser.manage_tabs":
                action = inner_params.get("action", "manage")
                return f"{app_id}::tabs", f"I'm updating the browser tabs."

            # Word operations
            if "word" in cap_id:
                if "create" in cap_id:
                    return f"{app_id}::create_doc", "I'm creating a new Word document."
                if "edit" in cap_id:
                    return f"{app_id}::edit_doc", "I'm updating the text in Word."
                return f"{app_id}::word", "I'm working in Microsoft Word."

            # Excel operations
            if "excel" in cap_id:
                return f"{app_id}::excel", "I'm accessing Microsoft Excel."

            # Messaging
            if "discord" in cap_id or "messaging" in app_id:
                return f"{app_id}::messaging", "I'm accessing the messaging client."

            return f"{app_id}::{cap_id}", f"Executing capability {cap_id} on {app_id}."

        # Native Desktop Launch
        if t_clean == "windows_launch_app":
            app_name = params.get("app_name") or params.get("executable") or "application"
            clean_name = Path(str(app_name)).stem.capitalize()
            return f"launch::{clean_name}", f"I'm opening {clean_name} now."

        # Grounded Visual Interaction
        if t_clean in ("windows_grounded_click", "grounded_click"):
            target = params.get("target_description") or "the target element"
            return f"click::{target}", f"I'm locating {target} on screen."

        if t_clean in ("windows_grounded_type", "grounded_type", "windows_write_input"):
            return "typing", "I'm entering the text into the selected field."

        if t_clean in ("windows_capture_screen", "windows_read_screen_text"):
            return "screen_perception", "I'm inspecting the active display."

        return t_clean, None

    def _clean_url_destination(self, url: str) -> str:
        """Format friendly destination from URL."""
        if not url:
            return "the requested page"
        clean = url.lower()
        if "instagram.com" in clean:
            return "Instagram"
        if "youtube.com" in clean:
            return "YouTube"
        if "google.com" in clean:
            return "Google"
        if "github.com" in clean:
            return "GitHub"
        if "reddit.com" in clean:
            return "Reddit"
        # Extract domain
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if match:
            return match.group(1)
        return "the requested page"

    def generate_action_completed(
        self,
        tool_name: str,
        result: Any,
        task_id: str,
        is_success: bool = True,
    ) -> Optional[TaskLifecycleEvent]:
        """Announce important completed milestones without over-narrating small steps."""
        with self._lock:
            if not self.settings.enabled or not self.settings.announce_progress:
                return None

            t_clean = tool_name.lower().strip()
            spoken = None

            # Only announce completed milestones for prominent actions
            if t_clean == "app_execute_capability":
                spoken = "The application operation has succeeded."
            elif t_clean == "windows_launch_app":
                spoken = "The application is ready."
            elif t_clean in ("windows_grounded_click", "grounded_click"):
                spoken = "I've clicked the target element."

            if not spoken:
                return None

            now = time.time()
            last_time = self._last_narration_time.get(task_id, 0.0)
            if (now - last_time) < self.settings.progress_interval_seconds:
                return None

            self._record_narration(task_id, spoken)
            return TaskLifecycleEvent(
                task_id=task_id,
                event_type=TaskLifecycleEventType.ACTION_COMPLETED,
                action_or_app=tool_name,
                task_state="EXECUTING",
                is_narratable=True,
                narration_text=spoken,
                priority=NarrationPriority.PROGRESS,
                progress_info={"context": "progress", "result_status": "success" if is_success else "failed"},
            )

    # -------------------------------------------------------------------------
    # 3. Approval Narration
    # -------------------------------------------------------------------------

    def generate_approval_required(
        self,
        action_summary: str,
        risk_tier: str,
        capability: Optional[str],
        app_id: Optional[str],
        task_id: str,
        approval_id: Optional[str] = None,
    ) -> TaskLifecycleEvent:
        """Generate high-priority spoken alert when consequential approval is required."""
        with self._lock:
            self._pending_approvals[task_id] = True

            clean_summary = action_summary.replace("Execute ", "").replace(" in Opera GX", "").strip()
            spoken = f"Sir, I need your permission before {clean_summary}."
            if "navigate" in clean_summary.lower() or "instagram" in clean_summary.lower():
                spoken = f"Sir, I need your permission before navigating to {self._clean_url_destination(clean_summary)}."

            event_id = f"approval:{approval_id}:required" if approval_id else f"evt-{uuid.uuid4().hex[:10]}"
            event = TaskLifecycleEvent(
                task_id=task_id,
                event_id=event_id,
                event_type=TaskLifecycleEventType.APPROVAL_REQUIRED,
                approval_id=approval_id,
                action_or_app=app_id or capability,
                task_state="AWAITING_APPROVAL",
                is_narratable=self.settings.enabled and self.settings.announce_approvals,
                narration_text=spoken,
                priority=NarrationPriority.APPROVAL,
                progress_info={"context": "approval", "action_summary": action_summary, "risk_tier": risk_tier, "approval_id": approval_id},
            )
            self._record_narration(task_id, spoken)
            return event

    def generate_approval_decision(
        self,
        approved: bool,
        action_summary: str,
        task_id: str,
        approval_id: Optional[str] = None,
    ) -> TaskLifecycleEvent:
        """Announce operator approval or rejection."""
        with self._lock:
            self._pending_approvals.pop(task_id, None)

            if approved:
                spoken = "Authorization received. Proceeding."
                evt_type = TaskLifecycleEventType.APPROVAL_GRANTED
            else:
                spoken = "Understood. I will not perform that action."
                evt_type = TaskLifecycleEventType.APPROVAL_DENIED

            event_id = f"approval:{approval_id}:decision" if approval_id else f"evt-{uuid.uuid4().hex[:10]}"
            event = TaskLifecycleEvent(
                task_id=task_id,
                event_id=event_id,
                event_type=evt_type,
                approval_id=approval_id,
                action_or_app=None,
                task_state="EXECUTING" if approved else "IDLE",
                is_narratable=self.settings.enabled and self.settings.announce_approvals,
                narration_text=spoken,
                priority=NarrationPriority.APPROVAL,
                progress_info={"context": "approval", "approved": approved, "action_summary": action_summary, "approval_id": approval_id},
            )
            self._record_narration(task_id, spoken)
            return event

    # -------------------------------------------------------------------------
    # 4. Error & Recovery Narration
    # -------------------------------------------------------------------------

    def generate_error(
        self,
        tool_name: str,
        error_message: str,
        task_id: str,
        recovery_attempted: bool = False,
    ) -> TaskLifecycleEvent:
        """Announce meaningful error without reading raw code or stack traces."""
        with self._lock:
            clean_err = self._sanitize_spoken_error(error_message)
            if recovery_attempted:
                spoken = f"I encountered an issue with {tool_name}. Let me attempt to recover."
                evt_type = TaskLifecycleEventType.RECOVERY_STARTED
            else:
                spoken = f"The operation encountered an issue: {clean_err}."
                evt_type = TaskLifecycleEventType.ACTION_FAILED

            event = TaskLifecycleEvent(
                task_id=task_id,
                event_type=evt_type,
                action_or_app=tool_name,
                task_state="EXECUTING" if recovery_attempted else "FAILED",
                is_narratable=self.settings.enabled and self.settings.announce_errors,
                narration_text=spoken,
                priority=NarrationPriority.CRITICAL if not recovery_attempted else NarrationPriority.PROGRESS,
                progress_info={"context": "error", "tool_name": tool_name, "error": error_message},
            )
            self._record_narration(task_id, spoken)
            return event

    def _sanitize_spoken_error(self, err: str) -> str:
        """Strip raw traces, brackets, and code numbers for speech."""
        e = str(err)
        if "503" in e or "unavailable" in e.lower() or "high demand" in e.lower():
            return "the cloud service is experiencing temporary high demand"
        if "timeout" in e.lower() or "timed out" in e.lower():
            return "the request timed out"
        if "window" in e.lower() and "not found" in e.lower():
            return "the target application window could not be found"
        if "target" in e.lower() and "not found" in e.lower():
            return "the target visual element could not be located"
        # Truncate and clean generic errors
        clean = re.sub(r"[{}[\]'\"]", "", e)
        if len(clean) > 80:
            clean = clean[:77] + "..."
        return clean

    # -------------------------------------------------------------------------
    # 5. Completion Narration
    # -------------------------------------------------------------------------

    def generate_completion(
        self,
        task_id: str,
        has_pending_approval: bool = False,
        is_success: bool = True,
        is_cancelled: bool = False,
        conversational_text_present: bool = False,
    ) -> Optional[TaskLifecycleEvent]:
        """Announce task completion only when no tool is running, no approval is pending, and not cancelled."""
        with self._lock:
            # Strictly do NOT announce completion if approval is pending, or if task was cancelled
            if has_pending_approval or self._pending_approvals.get(task_id, False):
                return None

            if is_cancelled:
                self.reset_task(task_id)
                return TaskLifecycleEvent(
                    task_id=task_id,
                    event_type=TaskLifecycleEventType.TASK_CANCELLED,
                    task_state="IDLE",
                    is_narratable=self.settings.enabled,
                    narration_text="Task cancelled, sir.",
                    priority=NarrationPriority.CRITICAL,
                )

            if not is_success:
                self.reset_task(task_id)
                return TaskLifecycleEvent(
                    task_id=task_id,
                    event_type=TaskLifecycleEventType.TASK_FAILED,
                    task_state="FAILED",
                    is_narratable=self.settings.enabled and self.settings.announce_errors,
                    narration_text="I was unable to complete the task, sir.",
                    priority=NarrationPriority.CRITICAL,
                )

            # If Gemini already delivered a full conversational spoken response,
            # do not speak a redundant "That's done" on top of it!
            if conversational_text_present:
                self.reset_task(task_id)
                return None

            if not self.settings.enabled or not self.settings.announce_completion:
                self.reset_task(task_id)
                return None

            spoken = "That's done, sir."
            self.reset_task(task_id)
            return TaskLifecycleEvent(
                task_id=task_id,
                event_id=f"completion:{task_id}",
                event_type=TaskLifecycleEventType.TASK_COMPLETED,
                task_state="IDLE",
                is_narratable=True,
                narration_text=spoken,
                priority=NarrationPriority.PROGRESS,
                progress_info={"context": "completion"},
            )

    def _record_narration(self, task_id: str, text: str) -> None:
        self._last_narration_time[task_id] = time.time()
        self._last_narration_text[task_id] = text


# Global singleton instance
task_narration_engine = TaskNarrationEngine()
