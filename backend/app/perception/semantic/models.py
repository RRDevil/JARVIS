"""Data Models for Semantic Interface Perception and Application Understanding."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.perception.models import ElementBoundingBox, PointCoordinate


class InterfaceRegionType(str, Enum):
    """Semantic region within an application interface."""
    INBOX_CONVERSATION_LIST = "inbox_conversation_list"
    ACTIVE_CONVERSATION_THREAD = "active_conversation_thread"
    NOTES_BAR = "notes_bar"
    STORY_TRAY = "story_tray"
    SEARCH_SUGGESTIONS = "search_suggestions"
    NAVIGATION_BAR = "navigation_bar"
    MODAL_DIALOG = "modal_dialog"
    HEADER = "header"
    FOOTER_INPUT = "footer_input"
    GENERIC_CONTENT = "generic_content"


class InstagramElementRole(str, Enum):
    """Fine-grained semantic role of an element in Instagram Direct interface."""
    CONVERSATION_ROW = "conversation_row"          # Genuine conversation entry in list
    ACTIVE_CHAT_HEADER = "active_chat_header"      # Header of currently open conversation
    ACTIVE_CHAT_MESSAGE = "active_chat_message"    # Message bubble inside active chat
    ACTIVE_CHAT_INPUT = "active_chat_input"        # Direct message text entry field
    INSTAGRAM_NOTE = "instagram_note"              # Note bubble text (NOT a conversation!)
    NOTE_AUTHOR = "note_author"                    # Username under a Note (NOT a conversation!)
    STORY_BUBBLE = "story_bubble"                  # Story profile circle
    INBOX_TAB = "inbox_tab"                        # Primary, General, Requests tabs
    SEARCH_BAR = "search_bar"                      # Search input field
    SUGGESTED_CONTACT = "suggested_contact"        # Suggested profile from search/empty state
    NAVIGATION_ITEM = "navigation_item"            # Home, Search, Messages, etc.
    UNREAD_INDICATOR = "unread_indicator"          # Blue unread dot
    UNKNOWN = "unknown"


class ConversationCandidate(BaseModel):
    """Structured representation of an identified chat conversation."""
    id: str = Field(..., description="Unique deterministic identifier for this conversation candidate.")
    contact_name: str = Field(..., description="Display name or username of the recipient/group.")
    last_message_preview: Optional[str] = Field(None, description="Preview of the last message or status.")
    timestamp_or_status: Optional[str] = Field(None, description="Time of last activity or active status (e.g. 'Active 2h ago', '1d').")
    is_unread: bool = Field(default=False, description="Whether an unread notification indicator is present.")
    is_currently_open: bool = Field(default=False, description="Whether this conversation is currently open on the right pane.")
    bounding_box: ElementBoundingBox = Field(..., description="Spatial screen bounds of the conversation row.")
    center: PointCoordinate = Field(..., description="Center click coordinate.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score.")
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        default="HIGH", description="Confidence tier: only HIGH is presented as verified."
    )
    evidence: List[str] = Field(default_factory=list, description="Structural and visual evidence backing this classification.")


class DetectedNote(BaseModel):
    """Instagram Note or status bubble explicitly isolated from conversations."""
    author_username: str = Field(..., description="Username of the person who shared the note.")
    note_text: str = Field(..., description="Content of the ephemeral note bubble.")
    bounding_box: ElementBoundingBox = Field(..., description="Screen bounds of note.")
    center: PointCoordinate = Field(..., description="Click coordinates.")


class SemanticPerceptionResult(BaseModel):
    """Comprehensive semantic breakdown of an application interface."""
    application_name: str = Field(..., description="Name of application (e.g. 'Instagram', 'Discord', 'WhatsApp').")
    window_title: str = Field(..., description="Title of active window.")
    open_conversation: Optional[ConversationCandidate] = Field(
        None, description="The conversation currently active and open in the message pane."
    )
    verified_conversations: List[ConversationCandidate] = Field(
        default_factory=list, description="High-confidence genuine conversation entries in inbox."
    )
    uncertain_conversations: List[ConversationCandidate] = Field(
        default_factory=list, description="Medium-confidence candidates requiring operator confirmation."
    )
    detected_notes: List[DetectedNote] = Field(
        default_factory=list, description="Isolated Instagram Notes (NOT conversations)."
    )
    suggested_contacts: List[str] = Field(
        default_factory=list, description="Suggested or discoverable contacts (NOT active conversations)."
    )
    total_conversations_found: int = Field(0, description="Count of verified active conversations.")
    observation_timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
