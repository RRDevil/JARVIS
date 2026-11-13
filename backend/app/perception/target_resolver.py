"""Visual Target Resolution Engine.

Resolves natural language descriptions, semantic visual references (e.g. 'this video',
'second video', 'play button', 'search bar'), and UI controls into concrete on-screen
elements with exact screen coordinates, bounding boxes, host application window details,
and confidence scores BEFORE consequential execution or approval requests are generated.
"""

from datetime import datetime, timezone
import json
import logging
import re
import time
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field

from app.automation.factory import get_platform_adapter
from app.core.config import settings
from app.perception.grounding import (
    AmbiguousTargetError,
    GroundedUIElement,
    TargetNotFoundError,
    grounding_engine,
)
from app.perception.models import (
    ElementBoundingBox,
    ElementSource,
    ElementType,
    PointCoordinate,
)
from app.perception.screen_capture import screen_capture_engine
from app.perception.service import screen_perception_service

logger = logging.getLogger("jarvis.perception.target_resolver")


class ResolvedVisualTarget(BaseModel):
    """Structured resolution result from the visual target-resolution stage."""

    target_description: str = Field(..., description="Concrete resolved name or title of the element.")
    app_name: str = Field("Desktop", description="Target application name or executable (e.g. Opera GX, Chrome).")
    window_title: str = Field("", description="Title of the host application window.")
    window_handle: Optional[int] = Field(None, description="Win32 HWND of the application window.")
    bounding_box: ElementBoundingBox = Field(..., description="Screen bounding box of the resolved element.")
    click_coordinates: PointCoordinate = Field(..., description="Exact screen coordinates (x, y) to click.")
    detection_method: Literal["visual_reasoning", "uia", "ocr", "hybrid", "coordinate"] = Field(
        ..., description="Detection pipeline method that identified the target."
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score.")
    observation_timestamp: str = Field(..., description="ISO 8601 observation timestamp when target was resolved.")
    is_actionable: bool = Field(True, description="Whether the element is interactable and within screen bounds.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context or visual reasoning metadata.")


class VisualTargetResolver:
    """Dedicated service that resolves ambiguous or semantic UI targets into verified on-screen elements."""

    def __init__(self):
        self._max_stale_seconds: float = 15.0

    async def resolve_target(
        self,
        query: str,
        monitor_id: int = 1,
        active_window_only: bool = False,
        expected_app: Optional[str] = None,
        timeout_seconds: float = 8.0,
    ) -> ResolvedVisualTarget:
        """Resolve a natural language query into a concrete on-screen target with verified coordinates.

        Raises:
            TargetNotFoundError: If the element cannot be located on the screen.
            AmbiguousTargetError: If multiple elements match identically without distinguishing context.
        """
        clean_query = query.strip()
        if not clean_query:
            raise TargetNotFoundError("Target query cannot be empty.")

        t0 = time.perf_counter()
        adapter = get_platform_adapter()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Identify active or target application window
        active_win = adapter.get_active_window()
        app_name = "Desktop"
        win_title = ""
        win_hwnd: Optional[int] = None
        win_bounds: Optional[Dict[str, int]] = None

        if active_win:
            app_name = active_win.process_name or active_win.title or "Application"
            win_title = active_win.title or ""
            win_hwnd = active_win.handle
            win_bounds = adapter.get_window_bounds(active_win.handle) if active_win.handle else None

        # Clean common friendly app names
        app_name_lower = app_name.lower()
        if "opera" in app_name_lower:
            app_name = "Opera GX" if "gx" in app_name_lower or "opera gx" in win_title.lower() else "Opera"
        elif "chrome" in app_name_lower:
            app_name = "Google Chrome"
        elif "notepad" in app_name_lower:
            app_name = "Notepad"
        elif "code" in app_name_lower:
            app_name = "Visual Studio Code"
        elif "discord" in app_name_lower:
            app_name = "Discord"
        elif "calc" in app_name_lower:
            app_name = "Calculator"

        # Check virtual desktop bounds
        v_left, v_top, v_width, v_height = adapter.get_virtual_desktop_bounds()

        # 2. Capture fresh screen observation
        img, screen_model = screen_capture_engine.capture(
            monitor_id=monitor_id,
            active_window_only=active_window_only,
            encode_base64=True,
        )
        screen_left = screen_model.crop_region.left if screen_model.crop_region else v_left
        screen_top = screen_model.crop_region.top if screen_model.crop_region else v_top
        screen_w = screen_model.width
        screen_h = screen_model.height

        # 3. Determine if query is semantic/visual vs purely textual
        query_lower = clean_query.lower()
        is_semantic_visual = any(
            kw in query_lower
            for kw in [
                "video", "thumbnail", "play button", "icon", "logo", "avatar", "image",
                "second", "third", "first", "last", "top right", "top left", "bottom right",
                "bottom left", "middle", "center", "banner", "card", "tile", "this"
            ]
        )

        # 4. Attempt Fast Local Structural & OCR Grounding first (if not purely visual/relative)
        elements, scan_meta = await grounding_engine.scan_screen_elements(
            monitor_id=monitor_id,
            active_window_only=active_window_only,
            force_refresh=False,
        )

        local_match: Optional[Tuple[GroundedUIElement, float]] = None
        if not is_semantic_visual and elements:
            try:
                elem, score = grounding_engine.match_element(clean_query, elements)
                if score >= 0.80:
                    local_match = (elem, score)
            except (TargetNotFoundError, AmbiguousTargetError):
                local_match = None

        if local_match:
            elem, score = local_match
            b = elem.bounding_box
            cx, cy = elem.center.x, elem.center.y
            det_method: Literal["uia", "ocr", "hybrid"] = (
                "uia" if elem.source == ElementSource.UIA
                else "ocr" if elem.source == ElementSource.OCR
                else "hybrid"
            )

            resolved_title = elem.text or elem.description or clean_query
            return ResolvedVisualTarget(
                target_description=resolved_title,
                app_name=app_name,
                window_title=win_title,
                window_handle=win_hwnd or elem.window_handle,
                bounding_box=b,
                click_coordinates=PointCoordinate(x=cx, y=cy),
                detection_method=det_method,
                confidence=round(score, 2),
                observation_timestamp=now_iso,
                is_actionable=True,
                details={"source": elem.source.value, "element_id": elem.element_id},
            )

        # 5. Multimodal Visual Reasoning via Gemini Vision or Semantic Fallback
        # If Gemini API key is configured, use multimodal vision to ground semantic references
        if settings.GEMINI_API_KEY and screen_model.image_base64:
            try:
                resolved_vision = await self._ground_with_gemini_vision(
                    query=clean_query,
                    image_base64=screen_model.image_base64,
                    screen_left=screen_left,
                    screen_top=screen_top,
                    screen_width=screen_w,
                    screen_height=screen_h,
                    app_name=app_name,
                    window_title=win_title,
                    window_handle=win_hwnd,
                )
                if resolved_vision:
                    return resolved_vision
            except Exception as vision_err:
                logger.warning(f"Gemini vision grounding failed or degraded: {vision_err}. Falling back to local semantic heuristic.")

        # 6. Local Semantic Heuristic (for Videos, Thumbnails, Buttons, and Positional targets)
        heuristic_target = self._resolve_local_semantic_heuristic(
            query=clean_query,
            elements=elements,
            screen_left=screen_left,
            screen_top=screen_top,
            screen_w=screen_w,
            screen_h=screen_h,
            app_name=app_name,
            window_title=win_title,
            window_handle=win_hwnd,
        )
        if heuristic_target:
            return heuristic_target

        # If all resolution pathways fail
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        raise TargetNotFoundError(
            f"Could not locate target '{clean_query}' on the visible screen ({screen_w}x{screen_h} in {app_name}) after {elapsed}ms. "
            "Please ensure the target window is open and the element is clearly visible."
        )

    async def _ground_with_gemini_vision(
        self,
        query: str,
        image_base64: str,
        screen_left: int,
        screen_top: int,
        screen_width: int,
        screen_height: int,
        app_name: str,
        window_title: str,
        window_handle: Optional[int],
    ) -> Optional[ResolvedVisualTarget]:
        """Invoke Gemini Vision to localize the requested visual target in the screenshot."""
        import base64
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        image_bytes = base64.b64decode(image_base64)

        prompt = (
            f"You are a computer vision target grounder for a desktop OS.\n"
            f"Locate the user's intended target element for the request: \"{query}\".\n"
            f"Active Application: {app_name}\n"
            f"Window Title: {window_title}\n\n"
            f"Return a strict JSON object with these exact keys:\n"
            f'{{"found": true/false, "label": "<concrete descriptive name of the element, e.g. video title>", '
            f'"box_2d": [ymin, xmin, ymax, xmax], "confidence": <0.0-1.0>}}\n'
            f"Coordinates in box_2d must be normalized from 0 to 1000.\n"
            f"If multiple match (e.g. 'second video'), select the exact requested item (e.g. second in reading order).\n"
            f"If target is not visible at all, set found: false."
        )

        # Candidate models with vision support
        vision_models = [
            settings.GEMINI_DEFAULT_MODEL,
            "gemini-flash-lite-latest",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-flash-latest",
        ]

        for model_name in vision_models:
            try:
                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                raw_text = response.text or ""
                # Parse JSON
                data = json.loads(raw_text)
                if not data.get("found"):
                    return None

                box = data.get("box_2d")
                if not box or len(box) != 4:
                    return None

                ymin, xmin, ymax, xmax = [float(v) for v in box]
                # Denormalize coordinates to absolute desktop coordinates
                abs_left = int(screen_left + (xmin / 1000.0) * screen_width)
                abs_top = int(screen_top + (ymin / 1000.0) * screen_height)
                abs_right = int(screen_left + (xmax / 1000.0) * screen_width)
                abs_bottom = int(screen_top + (ymax / 1000.0) * screen_height)

                width = max(1, abs_right - abs_left)
                height = max(1, abs_bottom - abs_top)
                cx = abs_left + width // 2
                cy = abs_top + height // 2

                label = data.get("label") or query
                conf = float(data.get("confidence", 0.92))
                now_iso = datetime.now(timezone.utc).isoformat()

                return ResolvedVisualTarget(
                    target_description=label,
                    app_name=app_name,
                    window_title=window_title,
                    window_handle=window_handle,
                    bounding_box=ElementBoundingBox(left=abs_left, top=abs_top, width=width, height=height),
                    click_coordinates=PointCoordinate(x=cx, y=cy),
                    detection_method="visual_reasoning",
                    confidence=min(1.0, max(0.1, conf)),
                    observation_timestamp=now_iso,
                    is_actionable=True,
                    details={"model": model_name, "raw_box": box},
                )
            except Exception as e:
                logger.debug(f"Vision model {model_name} failed: {e}")
                continue

        return None

    def _resolve_local_semantic_heuristic(
        self,
        query: str,
        elements: List[GroundedUIElement],
        screen_left: int,
        screen_top: int,
        screen_w: int,
        screen_h: int,
        app_name: str,
        window_title: str,
        window_handle: Optional[int],
    ) -> Optional[ResolvedVisualTarget]:
        """Local heuristic when cloud vision is unreachable or running in mock/offline test environments."""
        ql = query.lower()
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Video or Thumbnail query
        if any(w in ql for w in ["video", "thumbnail", "stream"]):
            # Look for elements that resemble video titles or containers
            # In browser pages, videos usually have title text, duration stamps like '12:34', or 'views'
            video_candidates = []
            for e in elements:
                t = e.text.lower()
                # Exclude navigation/system elements
                if any(nav in t for nav in ["home", "subscriptions", "library", "search", "explore"]):
                    continue
                # Score potential video titles
                if len(e.text) > 15 or any(k in t for k in ["views", "ago", "ep", "tutorial", "how to", "official"]):
                    video_candidates.append(e)

            # Sort by top-to-bottom reading order
            video_candidates.sort(key=lambda elem: (elem.bounding_box.top, elem.bounding_box.left))

            target_idx = 0
            if "second" in ql or "2nd" in ql:
                target_idx = 1
            elif "third" in ql or "3rd" in ql:
                target_idx = 2

            if video_candidates and target_idx < len(video_candidates):
                chosen = video_candidates[target_idx]
                return ResolvedVisualTarget(
                    target_description=f"Video: {chosen.text[:60]}",
                    app_name=app_name,
                    window_title=window_title,
                    window_handle=window_handle or chosen.window_handle,
                    bounding_box=chosen.bounding_box,
                    click_coordinates=chosen.center,
                    detection_method="ocr" if chosen.source == ElementSource.OCR else "hybrid",
                    confidence=0.88,
                    observation_timestamp=now_iso,
                    is_actionable=True,
                    details={"index": target_idx, "candidate_count": len(video_candidates)},
                )

        # 2. Positional heuristics (e.g. 'top right', 'settings icon in top-right corner')
        if "top right" in ql or "top-right" in ql:
            # Candidates in top 20% vertical and right 30% horizontal
            tr_elements = [
                e for e in elements
                if e.bounding_box.top < screen_top + screen_h * 0.25
                and e.bounding_box.left > screen_left + screen_w * 0.65
            ]
            if tr_elements:
                # Prefer icon or button or matching keyword
                tr_elements.sort(key=lambda e: (0 if "setting" in e.text.lower() or "gear" in e.text.lower() else 1))
                chosen = tr_elements[0]
                return ResolvedVisualTarget(
                    target_description=chosen.text or "Top-right control",
                    app_name=app_name,
                    window_title=window_title,
                    window_handle=window_handle or chosen.window_handle,
                    bounding_box=chosen.bounding_box,
                    click_coordinates=chosen.center,
                    detection_method="hybrid",
                    confidence=0.85,
                    observation_timestamp=now_iso,
                    is_actionable=True,
                )

        # 3. Search bar heuristic
        if "search" in ql:
            search_elements = [
                e for e in elements
                if e.element_type == ElementType.SEARCH_BAR
                or "search" in e.text.lower()
                or "find" in e.text.lower()
            ]
            if search_elements:
                chosen = search_elements[0]
                return ResolvedVisualTarget(
                    target_description="Search Bar",
                    app_name=app_name,
                    window_title=window_title,
                    window_handle=window_handle or chosen.window_handle,
                    bounding_box=chosen.bounding_box,
                    click_coordinates=chosen.center,
                    detection_method="hybrid",
                    confidence=0.92,
                    observation_timestamp=now_iso,
                    is_actionable=True,
                )

        # 4. Play button heuristic
        if "play" in ql:
            play_elements = [
                e for e in elements
                if "play" in e.text.lower() or e.element_type == ElementType.BUTTON
            ]
            if play_elements:
                chosen = play_elements[0]
                return ResolvedVisualTarget(
                    target_description="Play Button",
                    app_name=app_name,
                    window_title=window_title,
                    window_handle=window_handle or chosen.window_handle,
                    bounding_box=chosen.bounding_box,
                    click_coordinates=chosen.center,
                    detection_method="hybrid",
                    confidence=0.86,
                    observation_timestamp=now_iso,
                    is_actionable=True,
                )

        return None


# Global singleton instance
target_resolver = VisualTargetResolver()
