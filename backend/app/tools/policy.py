"""JARVIS Desktop Assistant - Security Policy Engine."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel

from app.core.config import settings
from app.tools.base import BaseTool, PolicyDecision, RiskTier


class PolicyEvaluationResult(BaseModel):
    """Outcome of evaluating a tool proposal through the policy engine."""

    decision: PolicyDecision
    reason: str
    action_summary: str
    risk_tier: RiskTier
    requires_approval: bool
    sanitized_parameters: Dict[str, Any]


class PolicyEngine:
    """Enforces authorization policies, path sandboxing, and execution constraints."""

    def __init__(
        self,
        auto_approve_controlled: bool = True,
        allowed_paths: Optional[List[str]] = None,
    ):
        self.auto_approve_controlled = auto_approve_controlled
        self.allowed_paths = [
            Path(p).resolve() for p in (allowed_paths or settings.JARVIS_ALLOWED_PATHS)
        ]
        # Always include the active workspace directory
        workspace = settings.workspace_path
        if workspace not in self.allowed_paths:
            self.allowed_paths.append(workspace)

    def is_path_allowed(self, target_path: Path) -> bool:
        """Verify that target_path resolves strictly within one of the allowed directory trees."""
        resolved = target_path.resolve()
        for allowed in self.allowed_paths:
            try:
                # If target_path is relative to allowed, it's inside the sandbox
                resolved.relative_to(allowed)
                return True
            except ValueError:
                continue
        return False

    def validate_parameter_paths(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Inspect parameters for path keys and verify sandbox boundaries."""
        path_keys = {"path", "target_path", "folder_path", "file_path", "directory"}
        for key, val in params.items():
            if key in path_keys and isinstance(val, str):
                # Reject traversal indicators
                if ".." in val.split("/") or ".." in val.split("\\"):
                    # Check resolved path
                    pass
                resolved = Path(val).resolve()
                if not self.is_path_allowed(resolved):
                    return False, f"Path '{val}' is outside the authorized sandbox directories."
        return True, None

    def evaluate(
        self,
        tool: BaseTool,
        raw_parameters: Dict[str, Any],
        user_confirmed: bool = False,
    ) -> PolicyEvaluationResult:
        """Evaluate a tool execution request against security policies."""
        # 1. Reject CRITICAL risk tier unconditionally
        if tool.risk_tier == RiskTier.CRITICAL:
            return PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason="CRITICAL tier operations are permanently blocked by security policy.",
                action_summary=f"Blocked attempt to execute critical tool '{tool.name}'.",
                risk_tier=tool.risk_tier,
                requires_approval=False,
                sanitized_parameters=raw_parameters,
            )

        # 2. Path Sandboxing Check
        path_ok, path_err = self.validate_parameter_paths(raw_parameters)
        if not path_ok:
            return PolicyEvaluationResult(
                decision=PolicyDecision.BLOCK,
                reason=path_err or "Path outside authorized bounds.",
                action_summary=f"Blocked path traversal attempt in '{tool.name}'.",
                risk_tier=tool.risk_tier,
                requires_approval=False,
                sanitized_parameters=raw_parameters,
            )

        # 3. Formulate human-readable action summary
        action_summary = self._summarize_action(tool, raw_parameters)

        # Dynamic risk tier resolution for app_execute_capability based on underlying capability
        effective_risk_tier = tool.risk_tier
        if tool.name == "app_execute_capability":
            try:
                from app.integrations.registry import application_registry
                app_id = raw_parameters.get("app_id")
                cap_id = raw_parameters.get("capability_id")
                if app_id and cap_id:
                    cap_spec = application_registry.get_capability(app_id, cap_id)
                    if cap_spec:
                        effective_risk_tier = cap_spec.risk_tier
            except Exception:
                pass

        # 4. Check Risk Tiers
        if effective_risk_tier == RiskTier.READ_ONLY:
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW_AUTO,
                reason="Read-only operations are non-mutating and automatically authorized.",
                action_summary=action_summary,
                risk_tier=effective_risk_tier,
                requires_approval=False,
                sanitized_parameters=raw_parameters,
            )

        if effective_risk_tier == RiskTier.CONTROLLED:
            if self.auto_approve_controlled:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.ALLOW_AUTO,
                    reason="Controlled action permitted under standard policy.",
                    action_summary=action_summary,
                    risk_tier=effective_risk_tier,
                    requires_approval=False,
                    sanitized_parameters=raw_parameters,
                )
            else:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.REQUIRE_APPROVAL,
                    reason="Controlled actions configured to require explicit confirmation.",
                    action_summary=action_summary,
                    risk_tier=effective_risk_tier,
                    requires_approval=True,
                    sanitized_parameters=raw_parameters,
                )

        if effective_risk_tier == RiskTier.CONSEQUENTIAL:
            if user_confirmed:
                return PolicyEvaluationResult(
                    decision=PolicyDecision.ALLOW_AUTO,
                    reason="Consequential action authorized via validated approval token.",
                    action_summary=action_summary,
                    risk_tier=effective_risk_tier,
                    requires_approval=False,
                    sanitized_parameters=raw_parameters,
                )
            return PolicyEvaluationResult(
                decision=PolicyDecision.REQUIRE_APPROVAL,
                reason="Consequential actions mutate desktop state and require explicit user approval.",
                action_summary=action_summary,
                risk_tier=effective_risk_tier,
                requires_approval=True,
                sanitized_parameters=raw_parameters,
            )

        return PolicyEvaluationResult(
            decision=PolicyDecision.BLOCK,
            reason=f"Unknown risk tier '{tool.risk_tier}'.",
            action_summary=action_summary,
            risk_tier=tool.risk_tier,
            requires_approval=False,
            sanitized_parameters=raw_parameters,
        )

    def _summarize_action(self, tool: BaseTool, params: Dict[str, Any]) -> str:
        """Create a clear, concise human-readable summary of the intended action."""
        if tool.name == "windows_launch_app":
            app = params.get("app_id") or params.get("app_name") or "application"
            return f"Launch authorized application: {app}"
        if tool.name == "windows_close_window":
            win_id = params.get("window_id", "target window")
            title = params.get("window_title", "")
            return f"Close window [{win_id}] '{title}'"
        if tool.name == "windows_focus_window":
            win_id = params.get("window_id", "target window")
            return f"Switch focus to window [{win_id}]"
        if tool.name == "windows_minimize_window":
            win_id = params.get("window_id", "target window")
            return f"Minimize window [{win_id}]"
        if tool.name == "windows_open_folder":
            folder = params.get("folder_path", "sandbox folder")
            return f"Open folder in File Explorer: {folder}"
        if tool.name == "ui_click_control":
            ctrl = params.get("control_name") or params.get("control_id") or "control"
            return f"Click UI element '{ctrl}' in target window"
        if tool.name == "ui_set_text":
            ctrl = params.get("control_name") or params.get("control_id") or "control"
            return f"Input text into UI element '{ctrl}'"
        if tool.name == "ui_send_shortcut":
            keys = params.get("shortcut", "key combination")
            target_app = params.get("target_app_name") or params.get("window_title") or "active window"
            return f"Send keyboard shortcut [{keys}] to {target_app}"
        if tool.name == "visual_click_element":
            btn = params.get("button", "left")
            target = params.get("target_description") or params.get("element_id")
            app = params.get("app_name") or params.get("window_title")
            x = params.get("x")
            y = params.get("y")
            if target and x is not None and y is not None:
                app_str = f" in {app}" if app else ""
                return f"Click on '{target}'{app_str} at screen coordinates ({x}, {y})"
            if x is not None and y is not None:
                return f"Perform {btn}-click at screen coordinates ({x}, {y})"
            target = target or "UI element"
            return f"Perform {btn}-click on grounded element '{target}'"
        if tool.name == "visual_type_into_element":
            txt_len = len(params.get("text", ""))
            if params.get("x") is not None and params.get("y") is not None:
                return f"Type {txt_len} characters at screen coordinates ({params['x']}, {params['y']})"
            target = params.get("app_name") or params.get("target_description") or params.get("element_id") or "application"
            return f"Type {txt_len} characters into '{target}'"
        if tool.name == "desktop_type_text":
            txt_len = len(params.get("text", ""))
            target = params.get("app_name") or (f"coordinates ({params['x']}, {params['y']})" if params.get("x") is not None else "active window")
            return f"Type {txt_len} characters into {target}"
        if tool.name == "visual_locate_elements":
            q = params.get("query") or "interactive controls"
            return f"Locate visible UI elements on screen: '{q}'"
        if tool.name == "visual_scroll_region":
            dir_str = params.get("direction", "down")
            target = params.get("target_description") or "window"
            return f"Scroll {dir_str} inside '{target}'"
        if tool.name == "app_discover":
            cat = params.get("category") or "desktop"
            return f"Discover {cat} applications and integration providers"
        if tool.name == "app_list_capabilities":
            app = params.get("app_id") or "application"
            return f"List integration capabilities for {app}"
        if tool.name == "app_execute_capability":
            app = params.get("app_id") or "application"
            cap = params.get("capability_id") or "action"
            p = params.get("parameters") or {}
            url = p.get("url") or p.get("target") or params.get("url")
            if cap == "browser.navigate" and url:
                app_name = "Opera GX" if "opera" in app.lower() else "Google Chrome" if "chrome" in app.lower() else app
                return f"Navigate to '{url}' in {app_name}"
            return f"Execute capability '{cap}' on {app}"

        return f"Execute {tool.name} with parameters {params}"

