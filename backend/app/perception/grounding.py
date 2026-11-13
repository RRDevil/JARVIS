"""Visual UI Element Identification & Spatial Grounding Engine (Phase 5).

Bridges the gap between screen perception (screenshots, local OCR, vision)
and reliable Windows UI automation by grounding interactive controls with
exact display coordinates, structural types, and confidence scores.
"""

from datetime import datetime, timezone
import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.automation.factory import get_platform_adapter
from app.perception.models import (
    ElementBoundingBox,
    ElementSource,
    ElementType,
    GroundedUIElement,
    LocateElementsRequest,
    LocateElementsResponse,
    PointCoordinate,
)
from app.perception.screen_capture import screen_capture_engine
from app.perception.service import screen_perception_service

logger = logging.getLogger("jarvis.perception.grounding")


class GroundingError(Exception):
    """Base exception for UI element grounding failures."""
    pass


class TargetNotFoundError(GroundingError):
    """Raised when an element matching the query cannot be located."""
    pass


class AmbiguousTargetError(GroundingError):
    """Raised when multiple conflicting targets match without distinguishing context."""
    def __init__(self, message: str, candidates: List[GroundedUIElement]):
        super().__init__(message)
        self.candidates = candidates


class StaleObservationError(GroundingError):
    """Raised when the screen observation is too old or the screen state has changed."""
    pass


class UIElementGroundingEngine:
    """Engine responsible for identifying, fusing, and grounding desktop UI elements."""

    def __init__(self):
        self._last_observation_time: Optional[float] = None
        self._last_elements_cache: List[GroundedUIElement] = []
        self._cache_max_age_seconds: float = 20.0

    def generate_element_id(self, x: int, y: int, text: str, el_type: str) -> str:
        """Derive a deterministic ID for an element based on its spatial center and identity."""
        raw = f"{x}:{y}:{text.lower().strip()}:{el_type}"
        return f"elem-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"

    def _infer_element_type(self, class_name: str, text: str) -> ElementType:
        """Infer high-level ElementType from Win32 class names and text characteristics."""
        cl = class_name.lower()
        tl = text.lower().strip()

        if "button" in cl:
            if "check" in cl or "check" in tl:
                return ElementType.CHECKBOX
            if "radio" in cl:
                return ElementType.RADIO_BUTTON
            return ElementType.BUTTON

        if "edit" in cl:
            if "search" in tl:
                return ElementType.SEARCH_BAR
            return ElementType.TEXT_FIELD

        if "combobox" in cl:
            return ElementType.COMBOBOX

        if "tab" in cl:
            return ElementType.TAB

        if "menu" in cl:
            return ElementType.MENU

        # Text heuristic
        if tl in ("search", "find"):
            return ElementType.SEARCH_BAR
        if tl in ("ok", "cancel", "apply", "save", "yes", "no", "close", "submit"):
            return ElementType.BUTTON

        return ElementType.GENERIC_CLICKABLE

    def discover_uia_elements(self, window_handle: Optional[int] = None) -> List[GroundedUIElement]:
        """Discover accessible controls using Windows UI Automation / Win32 EnumChildWindows."""
        adapter = get_platform_adapter()
        elements: List[GroundedUIElement] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # If window_handle is not provided, resolve active foreground window
        target_handle = window_handle
        active_title = "Desktop"
        if not target_handle:
            active_info = screen_capture_engine.get_active_window_info()
            if active_info:
                target_handle = active_info[0]
                active_title = active_info[1]

        if not target_handle:
            return []

        # Query controls via platform adapter
        controls = adapter.find_controls(target_handle)

        for ctrl in controls:
            try:
                child_hwnd = int(ctrl.control_id)
            except ValueError:
                child_hwnd = abs(hash(ctrl.control_id)) % 100000 + 1000

            # Query exact spatial bounding box on desktop
            bounds = adapter.get_window_bounds(child_hwnd)
            if not bounds or bounds["width"] < 4 or bounds["height"] < 4:
                continue

            left = bounds["left"]
            top = bounds["top"]
            width = bounds["width"]
            height = bounds["height"]
            center_x = left + width // 2
            center_y = top + height // 2

            el_type = self._infer_element_type(ctrl.control_type, ctrl.name)
            elem_id = self.generate_element_id(center_x, center_y, ctrl.name, el_type.value)

            elements.append(
                GroundedUIElement(
                    element_id=elem_id,
                    description=f"{ctrl.name} ({el_type.value})",
                    text=ctrl.name,
                    element_type=el_type,
                    bounding_box=ElementBoundingBox(left=left, top=top, width=width, height=height),
                    center=PointCoordinate(x=center_x, y=center_y),
                    confidence=0.95,
                    is_interactable=ctrl.is_enabled,
                    source=ElementSource.UIA,
                    timestamp=now_iso,
                    window_title=active_title,
                    window_handle=target_handle,
                )
            )

        return elements

    def discover_ocr_elements(
        self,
        ocr_lines: List[Any],
        screen_left: int = 0,
        screen_top: int = 0,
        window_title: str = "",
        window_handle: Optional[int] = None,
    ) -> List[GroundedUIElement]:
        """Convert recognized OCR text lines into interactive spatial candidate elements."""
        elements: List[GroundedUIElement] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for line in ocr_lines:
            text = getattr(line, "text", "") or ""
            text = text.strip()
            if not text or len(text) < 1:
                continue

            words = getattr(line, "words", [])
            if not words:
                continue

            # Calculate composite bounding box from words
            min_x = min(w.bounding_box.x for w in words)
            min_y = min(w.bounding_box.y for w in words)
            max_r = max(w.bounding_box.x + w.bounding_box.width for w in words)
            max_b = max(w.bounding_box.y + w.bounding_box.height for w in words)

            left = int(screen_left + min_x)
            top = int(screen_top + min_y)
            width = int(max(1, max_r - min_x))
            height = int(max(1, max_b - min_y))
            center_x = left + width // 2
            center_y = top + height // 2

            el_type = self._infer_element_type("static", text)
            elem_id = self.generate_element_id(center_x, center_y, text, el_type.value)

            elements.append(
                GroundedUIElement(
                    element_id=elem_id,
                    description=f"'{text}' ({el_type.value})",
                    text=text,
                    element_type=el_type,
                    bounding_box=ElementBoundingBox(left=left, top=top, width=width, height=height),
                    center=PointCoordinate(x=center_x, y=center_y),
                    confidence=0.85,
                    is_interactable=True,
                    source=ElementSource.OCR,
                    timestamp=now_iso,
                    window_title=window_title,
                    window_handle=window_handle,
                )
            )

        return elements

    def fuse_elements(
        self,
        uia_elements: List[GroundedUIElement],
        ocr_elements: List[GroundedUIElement],
    ) -> List[GroundedUIElement]:
        """Spatially harmonize UIA controls and OCR text to avoid duplicate overlapping elements."""
        fused: List[GroundedUIElement] = list(uia_elements)
        now_iso = datetime.now(timezone.utc).isoformat()

        for ocr_elem in ocr_elements:
            ox, oy = ocr_elem.center.x, ocr_elem.center.y
            matched_uia = False

            # Check if this OCR element falls inside an existing UIA control box
            for idx, uia_elem in enumerate(fused):
                b = uia_elem.bounding_box
                if (b.left <= ox <= b.left + b.width) and (b.top <= oy <= b.top + b.height):
                    # Harmonize: update text if UIA control had no text
                    matched_uia = True
                    if not uia_elem.text or uia_elem.text.lower() in ("window", "pane", ""):
                        fused[idx] = GroundedUIElement(
                            element_id=uia_elem.element_id,
                            description=f"'{ocr_elem.text}' ({uia_elem.element_type.value})",
                            text=ocr_elem.text,
                            element_type=uia_elem.element_type,
                            bounding_box=uia_elem.bounding_box,
                            center=uia_elem.center,
                            confidence=0.98,
                            is_interactable=uia_elem.is_interactable,
                            source=ElementSource.HYBRID,
                            timestamp=now_iso,
                            window_title=uia_elem.window_title,
                            window_handle=uia_elem.window_handle,
                        )
                    break

            if not matched_uia:
                # Independent OCR text element (e.g. web/custom drawn control)
                fused.append(ocr_elem)

        return fused

    async def scan_screen_elements(
        self,
        monitor_id: int = 1,
        active_window_only: bool = True,
        force_refresh: bool = False,
    ) -> Tuple[List[GroundedUIElement], Dict[str, Any]]:
        """Perform on-demand capture, OCR, and UIA discovery to ground all visible interactive elements."""
        if not force_refresh and self.is_observation_fresh() and self._last_elements_cache:
            meta = {
                "screen_width": 1920,
                "screen_height": 1080,
                "active_window": self._last_elements_cache[0].window_title if self._last_elements_cache else "Active Window",
                "timestamp": self._last_elements_cache[0].timestamp if self._last_elements_cache else datetime.now(timezone.utc).isoformat(),
                "scan_duration_ms": 0.0,
                "elements_count": len(self._last_elements_cache),
            }
            return self._last_elements_cache, meta

        t0 = time.perf_counter()

        # 1. Capture screen with local OCR
        from app.perception.models import ScreenInspectRequest
        inspect_resp = await screen_perception_service.inspect_screen(
            ScreenInspectRequest(
                monitor_id=monitor_id,
                active_window_only=active_window_only,
                include_ocr=True,
                authorize_gemini_vision=False,
            )
        )

        screen = inspect_resp.screen
        screen_left = screen.crop_region.left if screen.crop_region else 0
        screen_top = screen.crop_region.top if screen.crop_region else 0
        active_title = screen.active_window_title or "Desktop"

        # 2. Extract UIA controls
        uia_elements = self.discover_uia_elements()

        # 3. Extract OCR elements
        ocr_lines = screen.ocr_result.lines if screen.ocr_result else []
        ocr_elements = self.discover_ocr_elements(
            ocr_lines=ocr_lines,
            screen_left=screen_left,
            screen_top=screen_top,
            window_title=active_title,
        )

        # 4. Spatially harmonize into grounded elements
        grounded = self.fuse_elements(uia_elements, ocr_elements)

        self._last_observation_time = time.time()
        self._last_elements_cache = grounded

        meta = {
            "screen_width": screen.width,
            "screen_height": screen.height,
            "active_window": active_title,
            "timestamp": screen.captured_at,
            "scan_duration_ms": round((time.perf_counter() - t0) * 1000, 1),
            "elements_count": len(grounded),
        }

        logger.info(f"Screen scan grounded {len(grounded)} elements in {meta['scan_duration_ms']}ms.")
        return grounded, meta

    def match_element(
        self,
        query: str,
        elements: List[GroundedUIElement],
        target_type: Optional[ElementType] = None,
    ) -> Tuple[GroundedUIElement, float]:
        """Find the best matching grounded element for a given natural language query.
        
        Applies fuzzy substring matching, element type weighting, and spatial disambiguation.
        Rejects ambiguous targets if multiple identical scores exist without distinguishing context.
        """
        if not elements:
            raise TargetNotFoundError(f"No grounded elements available to match '{query}'.")

        clean_query = query.lower().strip()
        # Strip common action verbs from query if present
        clean_query = re.sub(r"^(click|press|tap|focus|select|type into)\s+(on\s+)?(the\s+)?", "", clean_query)
        clean_query = clean_query.strip()

        scored_candidates: List[Tuple[GroundedUIElement, float]] = []

        for elem in elements:
            elem_text = elem.text.lower().strip()
            score = 0.0

            if not elem.is_interactable:
                continue

            # Exact text match
            if elem_text == clean_query:
                score = 1.0
            # Query is a word in the text or text is in query
            elif clean_query and clean_query in elem_text:
                score = 0.85 + (len(clean_query) / max(1, len(elem_text))) * 0.1
            elif elem_text and elem_text in clean_query:
                score = 0.80 + (len(elem_text) / max(1, len(clean_query))) * 0.1
            else:
                # Word-level overlap
                q_words = set(clean_query.split())
                e_words = set(elem_text.split())
                overlap = q_words.intersection(e_words)
                if overlap:
                    score = 0.5 + (len(overlap) / max(1, len(q_words))) * 0.3

            # Type match bonus
            if target_type and elem.element_type == target_type:
                score += 0.15
            elif any(t_name in clean_query for t_name in (elem.element_type.value, "button", "field", "tab", "menu")):
                score += 0.1

            score = min(1.0, score)
            if score >= 0.50:
                scored_candidates.append((elem, round(score, 3)))

        if not scored_candidates:
            raise TargetNotFoundError(f"No interactive element matching '{query}' was found on screen.")

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_elem, best_score = scored_candidates[0]

        # Check for ambiguity: multiple elements with identical or nearly identical top scores
        top_tier = [c for c in scored_candidates if abs(c[1] - best_score) < 0.02]
        if len(top_tier) > 1:
            # Ambiguous target: cannot confidently determine which element was intended
            raise AmbiguousTargetError(
                f"Multiple ({len(top_tier)}) similar elements matched '{query}'. Please specify surrounding context or location.",
                candidates=[c[0] for c in top_tier],
            )

        return best_elem, best_score

    async def locate_elements(self, request: LocateElementsRequest) -> LocateElementsResponse:
        """Execute element grounding request with query filtering."""
        elements, meta = await self.scan_screen_elements(
            monitor_id=request.monitor_id,
            active_window_only=request.active_window_only,
        )

        filtered = elements
        if request.element_type:
            filtered = [e for e in filtered if e.element_type == request.element_type]

        if request.query and request.query.strip():
            matched: List[GroundedUIElement] = []
            q = request.query.lower().strip()
            for e in filtered:
                if q in e.text.lower() or q in e.description.lower():
                    matched.append(e)
            filtered = matched

        limited = filtered[:request.max_results]
        return LocateElementsResponse(
            elements=limited,
            total_found=len(limited),
            active_window=meta["active_window"],
            screen_width=meta["screen_width"],
            screen_height=meta["screen_height"],
            observation_timestamp=meta["timestamp"],
            is_stale=False,
        )

    def is_observation_fresh(self, max_age_seconds: Optional[float] = None) -> bool:
        """Verify whether the cached screen observation is within acceptable age threshold."""
        if not self._last_observation_time:
            return False
        max_age = max_age_seconds or self._cache_max_age_seconds
        return (time.time() - self._last_observation_time) <= max_age


# Global Singleton Instance
grounding_engine = UIElementGroundingEngine()
