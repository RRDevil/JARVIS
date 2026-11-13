"""Data models for screen perception, capture, and OCR."""

from typing import List, Optional
from pydantic import BaseModel, Field


class MonitorInfo(BaseModel):
    """Information about a connected display monitor."""

    monitor_id: int = Field(..., description="Monitor index (0 for virtual all-monitors, 1+ for physical displays).")
    name: str = Field("Display", description="Friendly name of the display.")
    left: int = Field(0, description="Virtual coordinate X offset.")
    top: int = Field(0, description="Virtual coordinate Y offset.")
    width: int = Field(..., description="Pixel width.")
    height: int = Field(..., description="Pixel height.")
    is_primary: bool = Field(False, description="True if primary system display.")


class CaptureRegion(BaseModel):
    """Bounding box region for targeted screen capture."""

    left: int
    top: int
    width: int
    height: int


class BoundingBox(BaseModel):
    """Normalized or pixel coordinates bounding box for detected text/objects."""

    x: float
    y: float
    width: float
    height: float


class OCRWord(BaseModel):
    """Individual recognized word with spatial coordinates."""

    text: str
    bounding_box: BoundingBox
    confidence: float = 1.0


class OCRLine(BaseModel):
    """A line of recognized text containing ordered words."""

    text: str
    words: List[OCRWord] = Field(default_factory=list)


class OCRResult(BaseModel):
    """Structured result of local optical character recognition."""

    full_text: str = ""
    lines: List[OCRLine] = Field(default_factory=list)
    line_count: int = 0
    word_count: int = 0
    confidence: float = 1.0
    duration_ms: float = 0.0


class CapturedScreen(BaseModel):
    """Metadata and content of an on-demand screen capture."""

    monitor_id: int
    width: int
    height: int
    captured_at: str
    active_window_title: Optional[str] = None
    crop_region: Optional[CaptureRegion] = None
    image_base64: Optional[str] = None
    ocr_result: Optional[OCRResult] = None


class ScreenInspectRequest(BaseModel):
    """Payload to request an authorized on-demand screen inspection."""

    request_id: Optional[str] = Field(
        default=None,
        description="Unique correlation ID for tracking the perception request lifecycle across backend and HUD.",
    )
    monitor_id: int = Field(1, description="Target display index (1 for primary).")
    active_window_only: bool = Field(False, description="If true, only capture the foreground application.")
    include_ocr: bool = Field(True, description="Run local OCR engine on the capture.")
    authorize_gemini_vision: bool = Field(
        False,
        description="Explicit user consent to upload image to Gemini for multimodal vision.",
    )


class ScreenInspectResponse(BaseModel):
    """Structured response returned from on-demand screen inspection."""

    request_id: Optional[str] = None
    screen: CapturedScreen
    gemini_vision_authorized: bool = False
    message: str = ""
    capture_duration_ms: float = 0.0
    ocr_duration_ms: float = 0.0
    stage: str = "COMPLETED"


# --- Phase 5: Visual UI Element Identification & Grounding Models ---

from enum import Enum


class ElementType(str, Enum):
    """Types of interactive and structural UI controls on Windows screens."""

    BUTTON = "button"
    TEXT_FIELD = "text_field"
    SEARCH_BAR = "search_bar"
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    MENU = "menu"
    TAB = "tab"
    ICON = "icon"
    LINK = "link"
    COMBOBOX = "combobox"
    LIST_ITEM = "list_item"
    WINDOW_CONTROL = "window_control"
    GENERIC_CLICKABLE = "generic_clickable"


class ElementSource(str, Enum):
    """Technique that discovered or verified the UI element."""

    UIA = "uia"          # Windows UI Automation / Win32 accessible controls
    OCR = "ocr"          # Local Windows Media OCR bounding box
    VISION = "vision"    # Gemini visual reasoning & icon understanding
    HYBRID = "hybrid"    # Fused spatial boundaries across UIA and OCR


class ElementBoundingBox(BaseModel):
    """Absolute pixel bounds of an element in virtual display coordinate space."""

    left: int = Field(..., description="X coordinate of left edge.")
    top: int = Field(..., description="Y coordinate of top edge.")
    width: int = Field(..., description="Pixel width of bounding box.")
    height: int = Field(..., description="Pixel height of bounding box.")


class PointCoordinate(BaseModel):
    """2D Cartesian point coordinates."""

    x: int
    y: int


class GroundedUIElement(BaseModel):
    """Structured representation of an identified and grounded UI element on the desktop."""

    element_id: str = Field(..., description="Unique deterministic identifier for referencing this element.")
    description: str = Field(..., description="Natural language description of the element (e.g. 'Save Button').")
    text: str = Field(default="", description="Visible text content or label.")
    element_type: ElementType = Field(default=ElementType.GENERIC_CLICKABLE, description="Categorized control type.")
    bounding_box: ElementBoundingBox = Field(..., description="Screen bounding box coordinates.")
    center: PointCoordinate = Field(..., description="Calculated center point (x, y) for precise clicking/focusing.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Grounding confidence score.")
    is_interactable: bool = Field(default=True, description="Whether the element is enabled and clickable.")
    source: ElementSource = Field(default=ElementSource.UIA, description="Discovery source.")
    timestamp: str = Field(..., description="ISO 8601 observation timestamp when this element was captured.")
    window_title: Optional[str] = Field(None, description="Title of the containing window.")
    window_handle: Optional[int] = Field(None, description="Win32 HWND of the containing window if accessible.")


class LocateElementsRequest(BaseModel):
    """Request payload to locate and ground UI elements on the current desktop."""

    query: Optional[str] = Field(None, description="Natural language element description or label to locate.")
    monitor_id: int = Field(1, description="Display monitor to inspect (1 for primary).")
    active_window_only: bool = Field(True, description="Constrain search to foreground application window.")
    element_type: Optional[ElementType] = Field(None, description="Optional control type filter.")
    max_results: int = Field(25, ge=1, le=100, description="Maximum number of candidate elements to return.")


class LocateElementsResponse(BaseModel):
    """Structured response containing grounded UI elements matching query."""

    elements: List[GroundedUIElement] = Field(default_factory=list)
    total_found: int = 0
    active_window: Optional[str] = None
    screen_width: int = 0
    screen_height: int = 0
    observation_timestamp: str = ""
    is_stale: bool = False


class GroundedActionType(str, Enum):
    """Action to execute on a grounded UI element."""

    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    SCROLL = "scroll"


class GroundedInteractionRequest(BaseModel):
    """Request payload to perform a grounded interaction on the desktop."""

    target_description: Optional[str] = Field(None, description="Natural language element description to ground and interact with.")
    element_id: Optional[str] = Field(None, description="Specific element ID from a previous locate call.")
    action: GroundedActionType = Field(default=GroundedActionType.CLICK, description="Interaction type to perform.")
    text_to_type: Optional[str] = Field(None, description="Text to enter if action is type_text.")
    scroll_direction: Optional[str] = Field("down", description="Scroll direction ('up' or 'down').")
    scroll_amount: Optional[int] = Field(3, ge=1, le=30, description="Wheel scroll click amount.")
    active_window_only: bool = Field(True, description="Constrain interaction to active foreground window.")
    monitor_id: int = Field(1, description="Target display monitor.")
    verify_post_condition: bool = Field(True, description="Capture screen after action to verify expected change.")


class GroundedInteractionResponse(BaseModel):
    """Response returned upon attempting a grounded UI interaction."""

    success: bool
    action: GroundedActionType
    target_element: Optional[GroundedUIElement] = None
    message: str
    verified: bool = False
    requires_approval: bool = False
    approval_id: Optional[str] = None
    execution_time_ms: float = 0.0


# --- Phase 5: Bounded Screen Recording Models ---

class RecordingStartRequest(BaseModel):
    """Parameters to start a bounded debugging screen recording clip."""

    duration_seconds: int = Field(default=5, ge=1, le=30, description="Recording duration limit in seconds (max 30s).")
    fps: int = Field(default=5, ge=1, le=15, description="Capture frame rate in frames per second (1 to 15 fps).")
    monitor_id: int = Field(default=1, description="Monitor index to record.")
    active_window_only: bool = Field(default=False, description="Whether to record only foreground window area.")


class RecordingStatus(BaseModel):
    """Current state of the bounded screen recorder."""

    is_recording: bool
    clip_id: Optional[str] = None
    elapsed_seconds: float = 0.0
    max_duration_seconds: float = 0.0
    fps: int = 0
    frames_captured: int = 0
    file_path: Optional[str] = None


class RecordingClipInfo(BaseModel):
    """Metadata of an exported debugging recording clip."""

    clip_id: str
    created_at: str
    duration_seconds: float
    file_size_bytes: int
    file_path: str
    format: str = "gif"
    preview_base64: Optional[str] = None


