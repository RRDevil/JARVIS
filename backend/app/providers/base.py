"""Base AI Provider Protocol and Normalized Event Models."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field

ProviderEventType = Literal[
    "message_start",
    "text_delta",
    "tool_start",
    "tool_result",
    "narration",
    "message_complete",
    "usage",
    "error",
]


class ChatContextMessage(BaseModel):
    """Normalized chat message for AI provider context, supporting optional multimodal vision."""

    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1)
    image_data: Optional[str] = Field(
        default=None,
        description="Base64-encoded image data for authorized multimodal vision reasoning.",
    )
    image_mime_type: Optional[str] = Field(
        default="image/png",
        description="MIME type of the attached image.",
    )


class UsageMetadata(BaseModel):
    """Token usage metrics reported by provider."""

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ProviderEvent(BaseModel):
    """Normalized stream event yielded during conversational generation."""

    event_type: ProviderEventType
    request_id: str
    session_id: Optional[str] = None
    delta: Optional[str] = None
    full_text: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[UsageMetadata] = None
    duration_ms: Optional[float] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    tool_status: Optional[str] = None
    turn_index: Optional[int] = None
    narration: Optional[Dict[str, Any]] = None
    stage: Optional[str] = Field(
        default=None,
        description="Active perception or agent processing stage (e.g. ANALYZING_VISION, GENERATING).",
    )


class BaseAIProvider(ABC):
    """Abstract Base Class for pluggable AI model providers."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Check if necessary credentials and environment configurations are present."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the active configured model identifier."""
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[ChatContextMessage],
        session_id: str,
        request_id: str,
    ) -> AsyncIterator[ProviderEvent]:
        """Asynchronously stream generation events for the provided conversation context."""
        pass

