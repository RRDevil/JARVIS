"""Typed BaseTools for Semantic Perception and Conversation Extraction."""

from typing import Optional
from pydantic import BaseModel, Field

from app.perception.models import ScreenInspectRequest
from app.perception.semantic.classifier import semantic_perception_engine
from app.perception.service import screen_perception_service
from app.tools.base import BaseTool, ExecutionContext, RiskTier, ToolResult


class SemanticReadConversationsParams(BaseModel):
    app_name: str = Field(
        default="Instagram",
        description="Target application name: 'Instagram', 'WhatsApp', or 'Discord'.",
    )
    active_window_only: bool = Field(
        default=True,
        description="Whether to inspect only the active foreground application window.",
    )
    contact_query: Optional[str] = Field(
        default=None,
        description="Optional filter query to identify a specific conversation recipient.",
    )


class SemanticReadConversationsTool(BaseTool):
    name = "semantic_read_conversations"
    description = (
        "Accurately read and classify available chat conversations in Instagram, WhatsApp, or Discord. "
        "Strictly isolates Instagram Notes, note authors, and story bubbles so they are never misidentified as conversations."
    )
    risk_tier = RiskTier.READ_ONLY
    parameters_schema = SemanticReadConversationsParams

    async def execute(self, params: SemanticReadConversationsParams, context: ExecutionContext) -> ToolResult:
        try:
            inspect_resp = await screen_perception_service.inspect_screen(
                ScreenInspectRequest(
                    active_window_only=params.active_window_only,
                    include_ocr=True,
                    authorize_gemini_vision=False,
                )
            )

            ocr_result = inspect_resp.screen.ocr_result
            lines = ocr_result.lines if ocr_result else []
            screen_w = inspect_resp.screen.width
            screen_h = inspect_resp.screen.height
            window_title = inspect_resp.screen.active_window_title or params.app_name

            res = semantic_perception_engine.analyze_screen(
                app_name=params.app_name,
                ocr_lines=lines,
                screen_width=screen_w,
                screen_height=screen_h,
                window_title=window_title,
            )

            # If contact_query is provided, filter or find match
            verified_list = [
                c.model_dump() for c in res.verified_conversations
            ]
            if params.contact_query:
                q = params.contact_query.lower().strip()
                verified_list = [
                    c for c in verified_list
                    if q in c["contact_name"].lower()
                ]

            return ToolResult(
                success=True,
                data={
                    "application": res.application_name,
                    "window_title": res.window_title,
                    "open_conversation": res.open_conversation.model_dump() if res.open_conversation else None,
                    "total_conversations_found": len(verified_list),
                    "verified_conversations": verified_list,
                    "uncertain_candidates": [c.model_dump() for c in res.uncertain_conversations],
                    "isolated_notes": [n.model_dump() for n in res.detected_notes],
                    "suggested_contacts": res.suggested_contacts,
                },
                verified=True,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Semantic conversation extraction failed: {str(exc)}",
                error_code="SEMANTIC_PERCEPTION_FAILED",
            )
