"""Data Models for User Preference and Workflow Memory Subsystem (Phase 7 Foundation)."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PreferenceCategory(str, Enum):
    """Categorical classification of user preferences."""
    GLOBAL_DEFAULTS = "global_defaults"
    WEBSITE_BROWSERS = "website_browsers"
    PERSON_COMMUNICATIONS = "person_communications"
    WORKFLOW_PREFERENCES = "workflow_preferences"
    APPLICATION_PROFILES = "application_profiles"
    FILE_DOCUMENT_PREFERENCES = "file_document_preferences"
    GENERAL_INTERACTION_PREFERENCES = "general_interaction_preferences"


class PreferenceType(str, Enum):
    """Origin and permanence tier of a preference."""
    EXPLICIT = "explicit"                  # Directly stated by the user
    CONFIRMED_LEARNED = "confirmed_learned"  # Learned from repetition and explicitly confirmed
    INFERRED = "inferred"                  # Observed by pattern, pending user confirmation


class PreferenceSource(str, Enum):
    """Source that created or updated the preference."""
    USER_EXPLICIT = "user_explicit"
    CONVERSATION_CONFIRMATION = "conversation_confirmation"
    HEURISTIC_INFERRED = "heuristic_inferred"


class UserPreference(BaseModel):
    """Individual structured user preference record."""
    id: str = Field(..., description="Unique preference identifier (e.g. 'pref-abc12345').")
    category: PreferenceCategory = Field(..., description="Classification category.")
    preference_key: str = Field(..., description="Normalized lookup key (e.g. 'person:john_doe', 'domain:instagram.com').")
    app_id: Optional[str] = Field(None, description="Associated application identifier (e.g. 'browser.opera_gx').")
    target_entity: Optional[str] = Field(None, description="Target entity: contact name, domain, file type, etc.")
    browser_id: Optional[str] = Field(None, description="Preferred browser if relevant (e.g. 'browser.opera_gx', 'browser.chrome').")
    profile_name: Optional[str] = Field(None, description="Account or browser profile if applicable.")
    workflow_type: Optional[str] = Field(None, description="Workflow type (e.g. 'messaging', 'document_editing').")
    preference_type: PreferenceType = Field(default=PreferenceType.EXPLICIT, description="Explicit, confirmed, or inferred.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence level of this preference.")
    source: PreferenceSource = Field(default=PreferenceSource.USER_EXPLICIT, description="How preference was established.")
    is_enabled: bool = Field(default=True, description="Whether preference is active.")
    user_confirmed: bool = Field(default=True, description="Whether user explicitly confirmed persistence.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary non-sensitive metadata (NO credentials/messages).")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_confirmed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PreferenceResolution(BaseModel):
    """Result of resolving a preferred application, browser, or workflow for a task."""
    resolved_app_id: Optional[str] = Field(None, description="Recommended target application ID.")
    resolved_browser_id: Optional[str] = Field(None, description="Recommended browser ID if applicable.")
    resolved_profile: Optional[str] = Field(None, description="Recommended profile or account if applicable.")
    preference_match: Optional[UserPreference] = Field(None, description="The preference record that resolved this choice.")
    resolution_source: str = Field(
        ...,
        description="Source tier: 'explicit_request', 'person_preference', 'website_preference', 'workflow_preference', 'global_default', 'system_fallback'"
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    requires_confirmation: bool = Field(
        default=False,
        description="True if choice was inferred and requires user confirmation before taking action."
    )
    explanation: str = Field("", description="Human-readable explanation of why this preference was selected.")


class MemorySettings(BaseModel):
    """Privacy and operational controls for persistent memory."""
    memory_enabled: bool = Field(default=True, description="Master switch for persistent user memory.")
    learning_enabled: bool = Field(default=True, description="Whether JARVIS observes and infers repeated preferences.")
    confirmation_prompt_threshold: int = Field(
        default=2,
        description="Number of repeated identical selections before prompting user to confirm persistence."
    )
    max_inferred_age_days: int = Field(default=30, description="Retention limit for unconfirmed inferred preferences.")
