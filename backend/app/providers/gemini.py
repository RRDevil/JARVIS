"""Official Google Gemini SDK AI Provider Implementation."""

import asyncio
import base64
import os
import re
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from google import genai
from google.genai import types

from app.core.config import Settings, settings
from app.providers.base import (
    BaseAIProvider,
    ChatContextMessage,
    ProviderEvent,
    UsageMetadata,
)
from app.voice.narration import task_narration_engine


def sanitize_error_message(err_str: str) -> str:
    """Strip raw Python exception dictionaries and format a clean human-readable error."""
    if not err_str:
        return "An unknown upstream error occurred."

    lower = err_str.lower()
    # Check for common upstream error codes
    if any(code in lower for code in ("503", "unavailable", "high demand", "demand spike", "overloaded", "capacity")):
        return (
            "Upstream neural service is experiencing temporary high demand (503 Service Unavailable). "
            "Spikes are brief—please try your request again in a few moments."
        )
    if any(code in lower for code in ("429", "resource_exhausted", "quota", "rate limit")):
        return "Upstream neural API quota exceeded (429 Resource Exhausted). Please check quota or retry shortly."
    if any(code in lower for code in ("404", "not_found")):
        return "Requested AI model endpoint was not found on upstream provider."
    if any(code in lower for code in ("timeout", "timed out", "deadline")):
        return "Upstream AI request timed out. Please retry in a few moments."

    # Strip any curly bracket JSON/dict dumps from error string
    cleaned = re.sub(r"\{.*?\}", "", err_str).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" :.,")
    return cleaned or "Upstream AI provider error. Please retry."


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI Provider using the official google-genai Python SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self._explicit_api_key = api_key
        self._explicit_model = model
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.AI_REQUEST_TIMEOUT_SECONDS
        self._client: Optional[genai.Client] = None
        self._cached_client_key: Optional[str] = None

    @property
    def api_key(self) -> str:
        """Return explicit API key or dynamically reload latest from .env."""
        if self._explicit_api_key is not None:
            return self._explicit_api_key
        try:
            return Settings().GEMINI_API_KEY
        except Exception:
            return settings.GEMINI_API_KEY

    @property
    def model(self) -> str:
        """Return explicit model or dynamically reload latest from .env."""
        if self._explicit_model is not None:
            return self._explicit_model
        try:
            return Settings().GEMINI_DEFAULT_MODEL
        except Exception:
            return settings.GEMINI_DEFAULT_MODEL

    @model.setter
    def model(self, value: str):
        self._explicit_model = value

    def is_configured(self) -> bool:
        """Check if a valid Gemini API key is configured."""
        key = self.api_key
        return bool(
            key
            and key.strip()
            and key != "your_gemini_api_key_here"
        )

    def get_model_name(self) -> str:
        """Return active model name."""
        return self.model

    def _get_client(self) -> genai.Client:
        """Instantiate or return cached genai.Client instance, refreshing on key changes."""
        current_key = self.api_key
        if not self._client or self._cached_client_key != current_key:
            self._client = genai.Client(api_key=current_key)
            self._cached_client_key = current_key
        return self._client

    @staticmethod
    def _clean_schema_for_gemini(obj: Any) -> Any:
        """Recursively strip unsupported attributes from JSON schema for Google Gemini API."""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in ("title", "additionalProperties", "additional_properties"):
                    continue
                cleaned[k] = GeminiProvider._clean_schema_for_gemini(v)
            return cleaned
        elif isinstance(obj, list):
            return [GeminiProvider._clean_schema_for_gemini(item) for item in obj]
        return obj

    def _build_tools(self) -> Optional[List[types.Tool]]:
        """Construct Gemini FunctionDeclarations from tool_registry."""
        try:
            from app.tools.defaults import register_default_windows_tools
            from app.tools.registry import tool_registry

            register_default_windows_tools()
            declarations = []
            for meta in tool_registry.list_tools():
                schema = self._clean_schema_for_gemini(dict(meta.parameters_schema))
                declarations.append(
                    types.FunctionDeclaration(
                        name=meta.name,
                        description=meta.description,
                        parameters=schema,
                    )
                )
            if declarations:
                return [types.Tool(function_declarations=declarations)]
        except Exception:
            pass
        return None

    async def stream_chat(
        self,
        messages: List[ChatContextMessage],
        session_id: str,
        request_id: str,
    ) -> AsyncIterator[ProviderEvent]:
        """Stream conversational responses using client.aio.models.generate_content_stream."""
        start_time = time.time()

        if not self.is_configured():
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="API_KEY_NOT_CONFIGURED",
                error_message=(
                    "Gemini API key is not configured. Please supply a valid key via "
                    "GEMINI_API_KEY in your .env configuration file."
                ),
            )
            return

        # 1. Validate conversation content
        if not messages or not any(m.role in ("user", "assistant") for m in messages):
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="EMPTY_CONVERSATION",
                error_message="Cannot stream an empty conversation context.",
            )
            return

        # 2. Yield message_start event
        has_image = any(bool(getattr(m, "image_data", None)) for m in messages)
        initial_stage = "ANALYZING_VISION" if has_image else "THINKING"

        yield ProviderEvent(
            event_type="message_start",
            request_id=request_id,
            session_id=session_id,
            model=self.model,
            stage=initial_stage,
        )

        # 3. Separate system instructions from multi-turn dialogue
        system_instruction: str = settings.AI_SYSTEM_INSTRUCTION
        contents: List[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                # Augment system instruction
                system_instruction = f"{system_instruction}\n{msg.content}"
            else:
                # Map role: 'user' -> 'user', 'assistant' -> 'model'
                genai_role = "user" if msg.role == "user" else "model"
                parts = [types.Part.from_text(text=msg.content)]
                if getattr(msg, "image_data", None):
                    try:
                        raw_bytes = base64.b64decode(msg.image_data)
                        parts.append(
                            types.Part.from_bytes(
                                data=raw_bytes,
                                mime_type=getattr(msg, "image_mime_type", None) or "image/png",
                            )
                        )
                    except Exception:
                        pass
                contents.append(
                    types.Content(
                        role=genai_role,
                        parts=parts,
                    )
                )

        tools = self._build_tools()

        config = types.GenerateContentConfig(
            temperature=settings.AI_TEMPERATURE,
            max_output_tokens=settings.AI_MAX_OUTPUT_TOKENS,
            system_instruction=system_instruction,
            tools=tools,
        )

        client = self._get_client()
        accumulated_text: List[str] = []
        usage_meta: Optional[UsageMetadata] = None

        # Determine models to attempt: start with configured model, then prioritize robust fallback models
        models_to_try = [self.model]
        for candidate in [
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
        ]:
            if candidate not in models_to_try:
                models_to_try.append(candidate)

        last_exception: Optional[Exception] = None

        try:
            # Wrap the streaming call in timeout enforcement
            async with asyncio.timeout(self.timeout_seconds):
                stream_established = False

                for current_model in models_to_try:
                    try:
                        max_agent_turns = 10
                        has_pending_approval = False

                        for turn_index in range(max_agent_turns):
                            function_calls = []
                            turn_deltas = []
                            candidate_parts = []
                            turn_stream_succeeded = False

                            # Resilient call with transient error backoff (handles temporary 503 capacity spikes)
                            for attempt in range(3):
                                function_calls.clear()
                                turn_deltas.clear()
                                candidate_parts.clear()
                                try:
                                    response_stream = await client.aio.models.generate_content_stream(
                                        model=current_model,
                                        contents=contents,
                                        config=config,
                                    )
                                    async for chunk in response_stream:
                                        stream_established = True

                                        # Collect raw candidate parts (preserving thought_signature for multi-turn tool calling)
                                        for c in getattr(chunk, "candidates", []):
                                            if c.content and c.content.parts:
                                                for p in c.content.parts:
                                                    if isinstance(p, types.Part) and p not in candidate_parts:
                                                        candidate_parts.append(p)

                                        # Capture function call declarations (deduplicating across chunks within this turn)
                                        raw_fcs = []
                                        if hasattr(chunk, "function_calls") and chunk.function_calls:
                                            raw_fcs = list(chunk.function_calls)
                                        else:
                                            for c in getattr(chunk, "candidates", []):
                                                if c.content and c.content.parts:
                                                    for p in c.content.parts:
                                                        if getattr(p, "function_call", None):
                                                            raw_fcs.append(p.function_call)

                                        for fc in raw_fcs:
                                            fc_sig = (
                                                fc.name,
                                                tuple(sorted((k, str(v)) for k, v in dict(fc.args or {}).items())),
                                            )
                                            if not any(
                                                (c.name, tuple(sorted((k, str(v)) for k, v in dict(c.args or {}).items()))) == fc_sig
                                                for c in function_calls
                                            ):
                                                function_calls.append(fc)

                                        # Extract delta text
                                        delta_text = chunk.text or ""
                                        if delta_text:
                                            accumulated_text.append(delta_text)
                                            turn_deltas.append(delta_text)
                                            yield ProviderEvent(
                                                event_type="text_delta",
                                                request_id=request_id,
                                                session_id=session_id,
                                                delta=delta_text,
                                                stage="GENERATING",
                                            )

                                        # Extract usage metadata if provided on chunk
                                        if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                                            um = chunk.usage_metadata
                                            usage_meta = UsageMetadata(
                                                input_tokens=getattr(um, "prompt_token_count", None),
                                                output_tokens=getattr(um, "candidates_token_count", None),
                                                total_tokens=getattr(um, "total_token_count", None),
                                            )

                                    turn_stream_succeeded = True
                                    break
                                except Exception as stream_err:
                                    err_str = str(stream_err)
                                    lower_err = err_str.lower()
                                    # If model is deprecated or not found (404), fail fast to next candidate
                                    if any(code in lower_err for code in ("404", "not_found")):
                                        raise stream_err
                                    is_transient = any(
                                        code in lower_err
                                        for code in (
                                            "503", "429", "resource_exhausted", "unavailable",
                                            "high demand", "demand spike", "timeout", "timed out",
                                            "deadline", "overloaded", "capacity"
                                        )
                                    )
                                    if is_transient and attempt < 2:
                                        backoff = 0.5 * (2 ** attempt)
                                        await asyncio.sleep(backoff)
                                        continue
                                    raise stream_err

                            # If no function calls occurred this turn, generation is complete
                            if not function_calls:
                                break

                            # Execute tool proposals through execution engine
                            from app.execution.engine import execution_engine
                            from app.tools.base import ToolStatus

                            response_parts = []
                            for call in function_calls:
                                call_args = dict(call.args or {})
                                tool_stage = (
                                    "READING_OCR"
                                    if call.name == "windows_read_screen_text"
                                    else "CAPTURING"
                                    if call.name == "windows_capture_screen"
                                    else "EXECUTING"
                                )
                                yield ProviderEvent(
                                    event_type="tool_start",
                                    request_id=request_id,
                                    session_id=session_id,
                                    tool_name=call.name,
                                    stage=tool_stage,
                                    turn_index=turn_index,
                                    details={"args": call_args},
                                )

                                # Task progress narration for action start
                                narr_start = task_narration_engine.generate_action_started(
                                    tool_name=call.name,
                                    parameters=call_args,
                                    task_id=request_id,
                                    stage=tool_stage,
                                )
                                if narr_start and narr_start.is_narratable and narr_start.narration_text:
                                    yield ProviderEvent(
                                        event_type="narration",
                                        request_id=request_id,
                                        session_id=session_id,
                                        narration=narr_start.model_dump(),
                                        stage=tool_stage,
                                    )

                                exec_model, approval = await execution_engine.propose(
                                    tool_name=call.name,
                                    raw_parameters=call_args,
                                    session_id=session_id,
                                )

                                if approval is not None:
                                    has_pending_approval = True
                                    tool_resp = {
                                        "status": "requires_approval",
                                        "approval_id": approval.id,
                                        "action_summary": approval.actionSummary,
                                    }
                                    yield ProviderEvent(
                                        event_type="tool_result",
                                        request_id=request_id,
                                        session_id=session_id,
                                        tool_name=call.name,
                                        stage="AWAITING_APPROVAL",
                                        tool_status="requires_approval",
                                        turn_index=turn_index,
                                    )

                                    # Narration alert for approval requirement
                                    narr_appr = task_narration_engine.generate_approval_required(
                                        action_summary=approval.actionSummary,
                                        risk_tier=approval.riskTier.value if hasattr(approval.riskTier, "value") else str(approval.riskTier),
                                        capability=call_args.get("capability_id"),
                                        app_id=call_args.get("app_id"),
                                        task_id=request_id,
                                        approval_id=approval.id,
                                    )
                                    if narr_appr and narr_appr.is_narratable and narr_appr.narration_text:
                                        yield ProviderEvent(
                                            event_type="narration",
                                            request_id=request_id,
                                            session_id=session_id,
                                            narration=narr_appr.model_dump(),
                                            stage="AWAITING_APPROVAL",
                                        )
                                else:
                                    is_success = exec_model.status in (ToolStatus.SUCCESS, "success")
                                    tool_resp = {
                                        "status": "success" if is_success else "failed",
                                        "result": exec_model.result if is_success else exec_model.error,
                                    }
                                    yield ProviderEvent(
                                        event_type="tool_result",
                                        request_id=request_id,
                                        session_id=session_id,
                                        tool_name=call.name,
                                        stage="VERIFYING",
                                        tool_status="success" if is_success else "failed",
                                        turn_index=turn_index,
                                    )

                                    if is_success:
                                        narr_comp = task_narration_engine.generate_action_completed(
                                            tool_name=call.name,
                                            result=exec_model.result,
                                            task_id=request_id,
                                            is_success=True,
                                        )
                                        if narr_comp and narr_comp.is_narratable and narr_comp.narration_text:
                                            yield ProviderEvent(
                                                event_type="narration",
                                                request_id=request_id,
                                                session_id=session_id,
                                                narration=narr_comp.model_dump(),
                                                stage="VERIFYING",
                                            )
                                    else:
                                        narr_err = task_narration_engine.generate_error(
                                            tool_name=call.name,
                                            error_message=str(exec_model.error or "Operation failed"),
                                            task_id=request_id,
                                        )
                                        if narr_err and narr_err.is_narratable and narr_err.narration_text:
                                            yield ProviderEvent(
                                                event_type="narration",
                                                request_id=request_id,
                                                session_id=session_id,
                                                narration=narr_err.model_dump(),
                                                stage="FAILED",
                                            )

                                response_parts.append(
                                    types.Part.from_function_response(
                                        name=call.name,
                                        response={"result": tool_resp},
                                    )
                                )

                            # Append model turn preserving native thought_signature and function call parts
                            if candidate_parts:
                                call_parts = candidate_parts
                            else:
                                call_parts = []
                                turn_text_str = "".join(turn_deltas)
                                if turn_text_str:
                                    call_parts.append(types.Part.from_text(text=turn_text_str))
                                for fc in function_calls:
                                    call_parts.append(
                                        types.Part.from_function_call(
                                            name=fc.name,
                                            args=dict(fc.args or {}),
                                        )
                                    )
                            contents.append(types.Content(role="model", parts=call_parts))
                            # Append user turn with tool execution responses
                            contents.append(types.Content(role="user", parts=response_parts))

                            # Break agent orchestration loop immediately if human operator approval is pending
                            if has_pending_approval:
                                break

                        # Update active model to the successfully verified model
                        self.model = current_model
                        break

                    except Exception as model_err:
                        err_str = str(model_err)
                        lower_err = err_str.lower()
                        retryable_codes = (
                            "404", "429", "503", "not_found", "resource_exhausted",
                            "unavailable", "high demand", "demand spike", "overloaded",
                            "capacity", "timeout", "timed out", "deadline"
                        )
                        if any(code in lower_err for code in retryable_codes):
                            last_exception = model_err
                            continue
                        raise model_err

                else:
                    err_str = str(last_exception) if last_exception else ""
                    async for event in self._handle_offline_or_spike_fallback(
                        messages=messages,
                        session_id=session_id,
                        request_id=request_id,
                        start_time=start_time,
                        error_detail=err_str,
                    ):
                        yield event
                    return

            # 3. Emit usage event if captured
            if usage_meta:
                yield ProviderEvent(
                    event_type="usage",
                    request_id=request_id,
                    session_id=session_id,
                    usage=usage_meta,
                )

            # 4. Emit message_complete event and completion narration
            total_duration_ms = round((time.time() - start_time) * 1000, 2)
            full_text = "".join(accumulated_text)

            narr_done = task_narration_engine.generate_completion(
                task_id=request_id,
                has_pending_approval=has_pending_approval,
                is_success=True,
                conversational_text_present=bool(full_text.strip()),
            )
            if narr_done and narr_done.is_narratable and narr_done.narration_text:
                yield ProviderEvent(
                    event_type="narration",
                    request_id=request_id,
                    session_id=session_id,
                    narration=narr_done.model_dump(),
                    stage="COMPLETED",
                )

            yield ProviderEvent(
                event_type="message_complete",
                request_id=request_id,
                session_id=session_id,
                full_text=full_text,
                duration_ms=total_duration_ms,
                stage="AWAITING_APPROVAL" if has_pending_approval else "COMPLETED",
            )

        except asyncio.TimeoutError:
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="UPSTREAM_TIMEOUT",
                error_message=f"Gemini generation timed out after {self.timeout_seconds} seconds.",
                stage="FAILED",
            )
        except asyncio.CancelledError:
            # Client cancelled stream locally
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="CLIENT_CANCELLED",
                error_message="Streaming generation cancelled by client request.",
                stage="CANCELLED",
            )
            raise
        except Exception as exc:
            # Mask internal sensitive details from user error output
            error_repr = str(exc)
            # Remove any potential key leaks
            if self.api_key and self.api_key in error_repr:
                error_repr = error_repr.replace(self.api_key, "[REDACTED_API_KEY]")

            lower_err = error_repr.lower()
            is_capacity_spike = any(
                code in lower_err
                for code in (
                    "503", "429", "unavailable", "resource_exhausted", "high demand",
                    "demand spike", "overloaded", "capacity", "not_found", "404",
                    "timeout", "timed out", "deadline"
                )
            )
            if is_capacity_spike:
                async for event in self._handle_offline_or_spike_fallback(
                    messages=messages,
                    session_id=session_id,
                    request_id=request_id,
                    start_time=start_time,
                    error_detail=error_repr,
                ):
                    yield event
                return

            clean_error = sanitize_error_message(error_repr)
            yield ProviderEvent(
                event_type="error",
                request_id=request_id,
                session_id=session_id,
                error_code="UPSTREAM_PROVIDER_ERROR",
                error_message=f"Gemini API error: {clean_error}",
                stage="FAILED",
            )

    async def _handle_offline_or_spike_fallback(
        self,
        messages: List[ChatContextMessage],
        session_id: str,
        request_id: str,
        start_time: float,
        error_detail: str = "",
    ) -> AsyncIterator[ProviderEvent]:
        """Provide resilient local desktop action execution or in-character voice notice during cloud outages."""
        last_user_msg = next((m.content for m in reversed(messages) if m.role == "user"), "")
        prompt = last_user_msg.strip().lower()

        matched_tool: Optional[str] = None
        tool_params: dict = {}
        action_desc: str = ""

        try:
            # Pattern match explicit desktop automation intents (requiring an explicit launch action verb)
            is_launch_intent = any(v in prompt for v in ["open", "launch", "start", "run", "bring up", "show"])
            is_negated = any(v in prompt for v in ["don't", "dont", "do not", "never", "stop", "close", "quit", "exit", "kill", "terminate", "why", "how", "what", "is ", "was "])

            # Known web destinations and URL navigation
            known_web_targets = {
                "instagram": "https://www.instagram.com",
                "youtube": "https://www.youtube.com",
                "github": "https://www.github.com",
                "google": "https://www.google.com",
                "reddit": "https://www.reddit.com",
                "twitter": "https://x.com",
                "facebook": "https://www.facebook.com",
                "gmail": "https://mail.google.com",
                "whatsapp": "https://web.whatsapp.com",
            }
            is_nav_intent = any(v in prompt for v in ["navigate", "browse", "go to", "visit", "head to"]) or (
                is_launch_intent and any(k in prompt for k in known_web_targets)
            )

            if is_nav_intent and not is_negated:
                target_url = None
                matched_site_key = None
                for site_key, site_url in known_web_targets.items():
                    if site_key in prompt:
                        target_url = site_url
                        matched_site_key = site_key
                        break
                if not target_url:
                    import re
                    url_m = re.search(r"https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9_\-]+\.(?:com|org|net|io|edu|gov)[^\s]*", prompt)
                    if url_m:
                        raw_u = url_m.group(0)
                        target_url = raw_u if raw_u.startswith("http") else f"https://{raw_u}"

                if target_url:
                    from app.memory.service import preference_service
                    res_pref = preference_service.resolve_application(
                        website_domain=matched_site_key or "web",
                        workflow_type="browse",
                    )
                    chosen_browser = res_pref.resolved_browser_id or "browser.opera_gx"
                    matched_tool = "app_execute_capability"
                    tool_params = {
                        "app_id": chosen_browser,
                        "capability_id": "browser.navigate",
                        "parameters": {"url": target_url},
                    }
                    action_desc = f"navigated to '{target_url}' in {chosen_browser}"

            if not matched_tool and is_launch_intent and not is_negated:
                if any(kw in prompt for kw in ["notepad", "note pad"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "notepad"}
                    action_desc = "launched Notepad"
                elif any(kw in prompt for kw in ["calculator", "calc"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "calculator"}
                    action_desc = "launched the Calculator"
                elif any(kw in prompt for kw in ["paint", "mspaint"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "paint"}
                    action_desc = "launched Paint"
                elif any(kw in prompt for kw in ["terminal", "powershell", "cmd", "command prompt"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "terminal"}
                    action_desc = "launched Windows Terminal"
                elif any(kw in prompt for kw in ["file explorer", "explorer"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "explorer"}
                    action_desc = "opened File Explorer"
                elif any(kw in prompt for kw in ["opera gx", "opera"]):
                    matched_tool = "app_execute_capability"
                    tool_params = {"app_id": "browser.opera_gx", "capability_id": "browser.read_page"}
                    action_desc = "connected to Opera GX"
                elif any(kw in prompt for kw in ["chrome", "google chrome"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "chrome"}
                    action_desc = "launched Google Chrome"
                elif any(kw in prompt for kw in ["word", "winword"]):
                    matched_tool = "app_execute_capability"
                    tool_params = {"app_id": "office.word", "capability_id": "word.read_document"}
                    action_desc = "inspected Microsoft Word"
                elif any(kw in prompt for kw in ["excel"]):
                    matched_tool = "app_execute_capability"
                    tool_params = {"app_id": "office.excel", "capability_id": "excel.read_workbook"}
                    action_desc = "inspected Microsoft Excel"
                elif any(kw in prompt for kw in ["powerpoint", "powerpnt"]):
                    matched_tool = "app_execute_capability"
                    tool_params = {"app_id": "office.powerpoint", "capability_id": "powerpoint.read_presentation"}
                    action_desc = "inspected Microsoft PowerPoint"
                elif any(kw in prompt for kw in ["discord"]):
                    matched_tool = "app_execute_capability"
                    tool_params = {"app_id": "messaging.discord", "capability_id": "discord.read_messages"}
                    action_desc = "connected to Discord"
                elif any(kw in prompt for kw in ["vs code", "vscode", "code editor"]):
                    matched_tool = "windows_launch_app"
                    tool_params = {"app_id": "vscode"}
                    action_desc = "launched Visual Studio Code"
            elif any(kw in prompt for kw in ["discover apps", "show integrations", "list integrations", "installed applications"]) and not is_negated:
                matched_tool = "app_discover"
                tool_params = {"refresh": True}
                action_desc = "discovered installed applications and providers"
            elif any(kw in prompt for kw in ["list windows", "open windows", "show windows", "active windows"]) and not is_negated:
                matched_tool = "windows_list_windows"
                tool_params = {}
                action_desc = "queried active windows"
            elif any(kw in prompt for kw in ["list apps", "installed apps", "show apps"]) and not is_negated:
                matched_tool = "windows_list_apps"
                tool_params = {}
                action_desc = "enumerated installed desktop applications"
            elif any(kw in prompt for kw in ["read screen", "ocr", "screen text", "read text on screen"]) and not is_negated:
                matched_tool = "windows_read_screen_text"
                tool_params = {}
                action_desc = "performed local OCR text extraction"
            elif any(kw in prompt for kw in ["capture screen", "take screenshot", "take a screenshot"]) and not is_negated:
                matched_tool = "windows_capture_screen"
                tool_params = {}
                action_desc = "captured desktop screenshot"
            elif "click" in prompt and not is_negated:
                import re
                coord_match = re.search(r"(\d{2,4})\s*[,x\s]\s*(\d{2,4})", prompt)
                if coord_match:
                    matched_tool = "visual_click_element"
                    cx, cy = int(coord_match.group(1)), int(coord_match.group(2))
                    tool_params = {"x": cx, "y": cy}
                    action_desc = f"dispatched click at ({cx}, {cy})"
                else:
                    target_desc = re.sub(r"^(please\s+)?(can you\s+)?(could you\s+)?click\s+(on\s+)?(the\s+)?", "", prompt).strip()
                    if target_desc:
                        matched_tool = "visual_click_element"
                        tool_params = {"target_description": target_desc}
                        action_desc = f"clicked on '{target_desc}'"
            elif any(v in prompt for v in ["type ", "enter text", "write text"]) and not is_negated:
                import re
                quoted = re.search(r"['\"]([^'\"]+)['\"]", last_user_msg)
                text_to_type = quoted.group(1) if quoted else ""
                if not text_to_type:
                    type_match = re.search(r"(?:type|enter|write)\s+(.+?)(?:\s+(?:in|into|on)\s+([a-zA-Z0-9_\s]+))?$", prompt)
                    if type_match:
                        text_to_type = type_match.group(1).strip()

                target_app = None
                if "notepad" in prompt:
                    target_app = "notepad"
                elif "chrome" in prompt:
                    target_app = "chrome"
                elif "terminal" in prompt:
                    target_app = "terminal"

                if text_to_type:
                    matched_tool = "desktop_type_text"
                    tool_params = {"text": text_to_type, "app_name": target_app}
                    action_desc = f"typed text into {target_app or 'active window'}"

            fallback_msg = ""
            if matched_tool:
                try:
                    from app.execution.engine import execution_engine
                    from app.tools.base import ToolStatus

                    yield ProviderEvent(
                        event_type="tool_start",
                        request_id=request_id,
                        session_id=session_id,
                        tool_name=matched_tool,
                        stage="EXECUTING",
                        turn_index=0,
                    )

                    exec_model, approval = await execution_engine.propose(
                        tool_name=matched_tool,
                        raw_parameters=tool_params,
                        session_id=session_id,
                    )

                    if approval:
                        yield ProviderEvent(
                            event_type="tool_result",
                            request_id=request_id,
                            session_id=session_id,
                            tool_name=matched_tool,
                            stage="AWAITING_APPROVAL",
                            tool_status="requires_approval",
                            turn_index=0,
                        )
                        fallback_msg = (
                            f"Upstream neural service is experiencing high demand (503), but I have staged "
                            f"{action_desc} locally. Please authorize the action to proceed."
                        )
                        yield ProviderEvent(
                            event_type="text_delta",
                            request_id=request_id,
                            session_id=session_id,
                            delta=fallback_msg,
                            stage="AWAITING_APPROVAL",
                        )
                        yield ProviderEvent(
                            event_type="message_complete",
                            request_id=request_id,
                            session_id=session_id,
                            full_text=fallback_msg,
                            duration_ms=round((time.time() - start_time) * 1000, 2),
                            stage="AWAITING_APPROVAL",
                        )
                        return
                    else:
                        is_ok = exec_model.status in (ToolStatus.SUCCESS, "success")
                        yield ProviderEvent(
                            event_type="tool_result",
                            request_id=request_id,
                            session_id=session_id,
                            tool_name=matched_tool,
                            stage="VERIFYING",
                            tool_status="success" if is_ok else "failed",
                            turn_index=0,
                        )
                        res_summary = ""
                        if is_ok and isinstance(exec_model.result, dict):
                            res_summary = exec_model.result.get("message") or exec_model.result.get("text") or ""
                        elif is_ok and isinstance(exec_model.result, str):
                            res_summary = exec_model.result[:200]

                        fallback_msg = (
                            f"The upstream neural network is currently experiencing a capacity spike (503 Unavailable), "
                            f"but I have executed your request locally using offline automation: {action_desc}."
                        )
                        if res_summary:
                            fallback_msg += f" {res_summary}"

                except Exception:
                    matched_tool = None

            if not fallback_msg:
                fallback_msg = (
                    "I apologize, sir. The upstream neural network is currently experiencing an acute demand spike "
                    "(503 Temporarily Unavailable across cloud endpoints). I have safely returned to standby.\n\n"
                    "All on-device desktop automation tools remain operational—you can ask me to open applications, "
                    "control windows, navigate the browser, or interact with your screen. "
                    "For reasoning queries, cloud connectivity will restore automatically once upstream demand stabilizes."
                )

            yield ProviderEvent(
                event_type="text_delta",
                request_id=request_id,
                session_id=session_id,
                delta=fallback_msg,
                stage="DEGRADED",
            )
            yield ProviderEvent(
                event_type="message_complete",
                request_id=request_id,
                session_id=session_id,
                full_text=fallback_msg,
                duration_ms=round((time.time() - start_time) * 1000, 2),
                stage="COMPLETED",
            )
        except Exception:
            safe_msg = (
                "I apologize, sir. The upstream neural network is currently experiencing high demand (503). "
                "I have returned to standby. Please try again shortly, or ask for a local desktop command."
            )
            yield ProviderEvent(
                event_type="text_delta",
                request_id=request_id,
                session_id=session_id,
                delta=safe_msg,
                stage="DEGRADED",
            )
            yield ProviderEvent(
                event_type="message_complete",
                request_id=request_id,
                session_id=session_id,
                full_text=safe_msg,
                duration_ms=round((time.time() - start_time) * 1000, 2),
                stage="COMPLETED",
            )
