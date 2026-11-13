"""AI Provider Factory Module."""

from typing import Optional
from app.core.config import settings
from app.providers.base import BaseAIProvider
from app.providers.gemini import GeminiProvider

_active_provider: Optional[BaseAIProvider] = None


def get_ai_provider(provider_type: Optional[str] = None) -> BaseAIProvider:
    """Return singleton or configured AI provider instance."""
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    # Default to GeminiProvider with dynamic .env reloading
    return GeminiProvider(
        api_key=None,
        model=None,
        timeout_seconds=settings.AI_REQUEST_TIMEOUT_SECONDS,
    )


def set_ai_provider_override(provider: Optional[BaseAIProvider]) -> None:
    """Set provider override, primarily for automated tests and mocking."""
    global _active_provider
    _active_provider = provider

