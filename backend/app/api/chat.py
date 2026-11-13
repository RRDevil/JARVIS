"""JARVIS Conversational Streaming API (Server-Sent Events)."""

import json
import uuid
from typing import AsyncIterator, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.security import verify_secret_token
from app.providers.base import ChatContextMessage, ProviderEvent
from app.providers.factory import get_ai_provider

router = APIRouter(prefix="/v1/chat", tags=["Conversational AI"])


class ChatStreamRequest(BaseModel):
    """Payload for initiating a streaming conversational turn."""

    messages: List[ChatContextMessage] = Field(
        ...,
        min_length=1,
        description="Chronological multi-turn context messages.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for current conversation session.",
    )

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, msgs: List[ChatContextMessage]) -> List[ChatContextMessage]:
        if len(msgs) > settings.AI_MAX_CONTEXT_MESSAGES:
            raise ValueError(
                f"Conversation exceeds maximum allowed messages ({settings.AI_MAX_CONTEXT_MESSAGES}). "
                "Please start a new session or truncate earlier context."
            )

        total_chars = sum(len(m.content) for m in msgs)
        if total_chars > settings.AI_MAX_INPUT_CHARS:
            raise ValueError(
                f"Total conversation characters ({total_chars}) exceeds limit ({settings.AI_MAX_INPUT_CHARS})."
            )

        # Validate that the final message is from user
        if msgs[-1].role not in ("user", "system"):
            raise ValueError("The last message in the conversation turn must originate from the user.")

        return msgs


def format_sse(event_name: str, data: dict) -> str:
    """Format dictionary payload as valid Server-Sent Event (SSE) block."""
    json_payload = json.dumps(data)
    return f"event: {event_name}\ndata: {json_payload}\n\n"


async def event_generator(
    req: ChatStreamRequest,
    http_request: Request,
    request_id: str,
    session_id: str,
) -> AsyncIterator[str]:
    """Asynchronous generator yielding SSE formatted events from the active AI provider."""
    provider = get_ai_provider()

    try:
        async for event in provider.stream_chat(
            messages=req.messages,
            session_id=session_id,
            request_id=request_id,
        ):
            payload = event.model_dump(exclude_none=True)
            yield format_sse(event.event_type, payload)

    except Exception as exc:
        err_payload = {
            "event_type": "error",
            "request_id": request_id,
            "session_id": session_id,
            "error_code": "STREAM_DISRUPTED",
            "error_message": f"Streaming pipeline failure: {str(exc)}",
        }
        yield format_sse("error", err_payload)


@router.post(
    "/stream",
    response_class=StreamingResponse,
    summary="Stream conversational AI responses via Server-Sent Events",
)
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    _authorized: bool = Depends(verify_secret_token),
) -> StreamingResponse:
    """Initiate streaming response generation for multi-turn user conversation."""
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    session_id = payload.session_id or f"sess-{uuid.uuid4().hex[:8]}"

    return StreamingResponse(
        event_generator(
            req=payload,
            http_request=request,
            request_id=request_id,
            session_id=session_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
            "X-Session-Id": session_id,
        },
    )

