"""Generic Semantic Interface Perception for WhatsApp, Discord, and Desktop Applications."""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.perception.models import ElementBoundingBox, PointCoordinate
from app.perception.semantic.models import (
    ConversationCandidate,
    SemanticPerceptionResult,
)

logger = logging.getLogger("jarvis.perception.semantic.generic")


class GenericSemanticClassifier:
    """Classifies interface elements and conversation lists across WhatsApp, Discord, and desktop apps."""

    def classify_screen(
        self,
        app_name: str,
        ocr_lines: List[Any],
        screen_width: int,
        screen_height: int,
        window_title: str = "",
        uia_controls: Optional[List[Any]] = None,
    ) -> SemanticPerceptionResult:
        """Extract structured semantic conversation lists and active chats from generic messaging screens."""
        app_clean = (app_name or "Application").lower()

        # Normalize OCR lines
        items = []
        for line in ocr_lines:
            text = (getattr(line, "text", "") or "").strip()
            if not text:
                continue
            words = getattr(line, "words", [])
            if words:
                min_x = min(w.bounding_box.x for w in words)
                min_y = min(w.bounding_box.y for w in words)
                max_x = max(w.bounding_box.x + w.bounding_box.width for w in words)
                max_y = max(w.bounding_box.y + w.bounding_box.height for w in words)
                b = ElementBoundingBox(
                    left=int(min_x),
                    top=int(min_y),
                    width=int(max(1, max_x - min_x)),
                    height=int(max(1, max_y - min_y)),
                )
            else:
                bb = getattr(line, "bounding_box", None)
                if bb:
                    b = ElementBoundingBox(
                        left=int(bb.x),
                        top=int(bb.y),
                        width=int(bb.width),
                        height=int(bb.height),
                    )
                else:
                    continue
            items.append({"text": text, "bounds": b, "raw": line})

        if not items:
            return SemanticPerceptionResult(
                application_name=app_name,
                window_title=window_title,
                total_conversations_found=0,
            )

        # In WhatsApp / Discord / Teams:
        # Chat/Channel list typically occupies left 25%-40% of window
        list_max_x = int(screen_width * 0.38)

        list_items = [it for it in items if it["bounds"].left < list_max_x]
        thread_items = [it for it in items if it["bounds"].left >= list_max_x]

        verified, uncertain = self._group_rows(list_items, app_clean)
        open_conv = self._find_active_thread(thread_items, screen_width, screen_height)

        return SemanticPerceptionResult(
            application_name=app_name,
            window_title=window_title,
            open_conversation=open_conv,
            verified_conversations=verified,
            uncertain_conversations=uncertain,
            total_conversations_found=len(verified),
        )

    def _group_rows(
        self,
        items: List[Dict[str, Any]],
        app_name: str,
    ) -> Tuple[List[ConversationCandidate], List[ConversationCandidate]]:
        verified = []
        uncertain = []
        if not items:
            return verified, uncertain

        sorted_items = sorted(items, key=lambda x: (x["bounds"].top, x["bounds"].left))
        clusters: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = [sorted_items[0]]

        for it in sorted_items[1:]:
            last_top = current[-1]["bounds"].top
            if abs(it["bounds"].top - last_top) < 40:
                current.append(it)
            else:
                clusters.append(current)
                current = [it]
        if current:
            clusters.append(current)

        for cluster in clusters:
            if not cluster:
                continue
            first_text = cluster[0]["text"].strip()
            rest = [c["text"].strip() for c in cluster[1:]]
            rest_joined = " ".join(rest).strip()

            if any(term in first_text.lower() for term in ("chats", "status", "channels", "search", "unread")):
                continue

            min_l = min(c["bounds"].left for c in cluster)
            min_t = min(c["bounds"].top for c in cluster)
            max_r = max(c["bounds"].left + c["bounds"].width for c in cluster)
            max_b = max(c["bounds"].top + c["bounds"].height for c in cluster)

            b = ElementBoundingBox(left=min_l, top=min_t, width=max(1, max_r - min_l), height=max(1, max_b - min_t))
            cx = min_l + (max_r - min_l) // 2
            cy = min_t + (max_b - min_t) // 2

            is_unread = any("•" in t or "unread" in t.lower() for t in [first_text] + rest)
            cand_id = f"gen-{hashlib.sha256(f'{first_text}:{min_t}'.encode()).hexdigest()[:10]}"

            if rest_joined:
                verified.append(
                    ConversationCandidate(
                        id=cand_id,
                        contact_name=first_text,
                        last_message_preview=rest_joined,
                        timestamp_or_status=rest[0] if rest else None,
                        is_unread=is_unread,
                        is_currently_open=False,
                        bounding_box=b,
                        center=PointCoordinate(x=cx, y=cy),
                        confidence=0.88,
                        confidence_level="HIGH",
                        evidence=["in_list_pane", "has_preview"],
                    )
                )
            else:
                uncertain.append(
                    ConversationCandidate(
                        id=cand_id,
                        contact_name=first_text,
                        last_message_preview=None,
                        is_unread=is_unread,
                        is_currently_open=False,
                        bounding_box=b,
                        center=PointCoordinate(x=cx, y=cy),
                        confidence=0.50,
                        confidence_level="MEDIUM",
                        evidence=["in_list_pane"],
                    )
                )

        return verified, uncertain

    def _find_active_thread(
        self,
        items: List[Dict[str, Any]],
        screen_width: int,
        screen_height: int,
    ) -> Optional[ConversationCandidate]:
        if not items:
            return None
        header_items = [it for it in items if it["bounds"].top < screen_height * 0.16]
        if not header_items:
            return None
        sorted_h = sorted(header_items, key=lambda x: (x["bounds"].top, x["bounds"].left))
        for h in sorted_h:
            t = h["text"].strip()
            if len(t) >= 2 and not any(term in t.lower() for term in ("call", "search", "video", "menu")):
                b = h["bounds"]
                return ConversationCandidate(
                    id=f"open-{hashlib.sha256(t.encode()).hexdigest()[:10]}",
                    contact_name=t,
                    last_message_preview=None,
                    timestamp_or_status="Currently Open",
                    is_unread=False,
                    is_currently_open=True,
                    bounding_box=b,
                    center=PointCoordinate(x=b.left + b.width // 2, y=b.top + b.height // 2),
                    confidence=0.92,
                    confidence_level="HIGH",
                    evidence=["active_thread_header"],
                )
        return None


# Global singleton instance
generic_semantic_classifier = GenericSemanticClassifier()
