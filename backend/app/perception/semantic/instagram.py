"""Instagram Direct Interface Semantic Perception and Conversation Classifier.

Distinguishes genuine conversation entries from Instagram Notes, note authors,
story bubbles, search suggestions, and navigation elements.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.perception.models import ElementBoundingBox, PointCoordinate
from app.perception.semantic.models import (
    ConversationCandidate,
    DetectedNote,
    InstagramElementRole,
    InterfaceRegionType,
    SemanticPerceptionResult,
)

logger = logging.getLogger("jarvis.perception.semantic.instagram")

# Known Instagram Direct navigation, tab, and control terms
NAV_TERMS = {"home", "search", "explore", "reels", "messages", "notifications", "create", "profile", "threads", "more"}
INBOX_TABS = {"primary", "general", "requests", "filter", "channels"}
STATUS_KEYWORDS = {"active", "seen", "sent", "you:", "liked", "shared", "replied", "ago", "yesterday", "now", "reel", "post", "story"}


class InstagramSemanticClassifier:
    """Specialized semantic classifier for Instagram Direct web and desktop interfaces."""

    def classify_screen(
        self,
        ocr_lines: List[Any],
        screen_width: int,
        screen_height: int,
        window_title: str = "Instagram",
        uia_controls: Optional[List[Any]] = None,
    ) -> SemanticPerceptionResult:
        """Analyze visible screen elements and construct structured semantic observation."""
        now_title = window_title or "Instagram"

        # 1. Normalize OCR lines into unified bounding box items
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
                application_name="Instagram",
                window_title=now_title,
                total_conversations_found=0,
            )

        # 2. Identify interface spatial layout boundaries
        # In Instagram Web:
        # Navigation bar: 0 <= X <= ~80
        # Inbox List pane: ~80 <= X <= min(screen_width * 0.45, 450)
        # Active Chat pane: X > min(screen_width * 0.45, 450)
        nav_max_x = int(screen_width * 0.08) if screen_width > 800 else 70
        inbox_max_x = int(min(screen_width * 0.45, 460)) if screen_width > 800 else int(screen_width * 0.5)

        # 3. Locate Search Bar & Tabs to establish the boundary of the Notes Bar
        search_bar_top = None
        search_bar_bottom = None
        for it in items:
            t_lower = it["text"].lower().strip()
            b = it["bounds"]
            if nav_max_x <= b.left <= inbox_max_x:
                if t_lower == "search" and b.top < screen_height * 0.4:
                    search_bar_top = b.top
                    search_bar_bottom = b.top + b.height
                    break

        # If search bar not found, estimate notes bar bottom
        notes_bar_limit_y = search_bar_top if search_bar_top else int(screen_height * 0.22)

        # 4. Classify elements into Notes, Conversation rows, Active Chat, and Navigation
        detected_notes: List[DetectedNote] = []
        inbox_row_items: List[Dict[str, Any]] = []
        open_chat_items: List[Dict[str, Any]] = []
        suggested_contacts: List[str] = []

        # Sort items by Y (top to bottom), then X (left to right)
        sorted_items = sorted(items, key=lambda x: (x["bounds"].top, x["bounds"].left))

        for it in sorted_items:
            b = it["bounds"]
            t = it["text"]
            t_lower = t.lower().strip()

            # A. Navigation Bar items
            if b.left + b.width <= nav_max_x:
                continue

            # B. Items in the Inbox column (nav_max_x <= X <= inbox_max_x)
            if nav_max_x <= b.left <= inbox_max_x:
                # Top tray: Notes Tray (above search bar)
                if b.top < notes_bar_limit_y:
                    if t_lower in ("notes", "your note", "share a thought", "leave a note"):
                        continue
                    if t_lower in NAV_TERMS:
                        continue
                    # Candidate note bubble or author name
                    # Look ahead/behind to pair note text with author
                    cx = b.left + b.width // 2
                    cy = b.top + b.height // 2
                    detected_notes.append(
                        DetectedNote(
                            author_username=t if not re.search(r"[!?.…✨☀️🎧]", t) else "unknown",
                            note_text=t,
                            bounding_box=b,
                            center=PointCoordinate(x=cx, y=cy),
                        )
                    )
                    continue

                # Below notes bar: check if Search Bar or Tab
                if search_bar_bottom and b.top <= search_bar_bottom + 10:
                    continue
                if t_lower in INBOX_TABS:
                    continue
                if "suggested" in t_lower or "explore" in t_lower:
                    continue

                # Potential conversation list element
                inbox_row_items.append(it)
                continue

            # C. Items in the Active Chat column (X > inbox_max_x)
            if b.left > inbox_max_x:
                open_chat_items.append(it)

        # 5. Deduplicate and clean up Detected Notes
        clean_notes = self._reconcile_notes(detected_notes)

        # 6. Group inbox row elements into genuine conversation rows
        # In a real conversation row:
        # Line 1: Contact name / username
        # Line 2: Message preview (e.g. "Active 2h ago", "Sent a reel", "You: Hey there", "· 1d")
        verified_conversations, uncertain_conversations = self._group_conversation_rows(
            inbox_row_items, screen_width
        )

        # 7. Identify currently open conversation from right pane
        open_conversation = self._identify_open_conversation(open_chat_items, screen_width, screen_height)

        return SemanticPerceptionResult(
            application_name="Instagram",
            window_title=now_title,
            open_conversation=open_conversation,
            verified_conversations=verified_conversations,
            uncertain_conversations=uncertain_conversations,
            detected_notes=clean_notes,
            suggested_contacts=suggested_contacts,
            total_conversations_found=len(verified_conversations),
        )

    def _reconcile_notes(self, notes: List[DetectedNote]) -> List[DetectedNote]:
        """Pair note bubble snippets with their corresponding username authors."""
        reconciled = []
        i = 0
        while i < len(notes):
            n = notes[i]
            # If two note items share close X coordinates and are vertically stacked
            if i + 1 < len(notes):
                next_n = notes[i + 1]
                if abs(n.bounding_box.left - next_n.bounding_box.left) < 60:
                    # One is note text, other is username
                    reconciled.append(
                        DetectedNote(
                            author_username=next_n.note_text,
                            note_text=n.note_text,
                            bounding_box=n.bounding_box,
                            center=n.center,
                        )
                    )
                    i += 2
                    continue
            reconciled.append(n)
            i += 1
        return reconciled

    def _group_conversation_rows(
        self,
        items: List[Dict[str, Any]],
        screen_width: int,
    ) -> Tuple[List[ConversationCandidate], List[ConversationCandidate]]:
        """Cluster text items vertically into cohesive conversation rows.

        A genuine conversation row MUST have a contact identifier AND message preview/status.
        Standalone names without previews are placed in uncertain/unverified candidates.
        """
        verified = []
        uncertain = []

        if not items:
            return verified, uncertain

        # Cluster items by vertical line proximity (rows are ~50-80px tall)
        clusters: List[List[Dict[str, Any]]] = []
        current_cluster: List[Dict[str, Any]] = [items[0]]

        for it in items[1:]:
            last_top = current_cluster[-1]["bounds"].top
            this_top = it["bounds"].top
            # If within 30px vertically, part of same conversation row (name + preview)
            if abs(this_top - last_top) <= 30:
                current_cluster.append(it)
            else:
                clusters.append(current_cluster)
                current_cluster = [it]

        if current_cluster:
            clusters.append(current_cluster)

        for cluster in clusters:
            if not cluster:
                continue

            # Compute composite bounding box
            min_l = min(c["bounds"].left for c in cluster)
            min_t = min(c["bounds"].top for c in cluster)
            max_r = max(c["bounds"].left + c["bounds"].width for c in cluster)
            max_b = max(c["bounds"].top + c["bounds"].height for c in cluster)

            row_bounds = ElementBoundingBox(
                left=min_l,
                top=min_t,
                width=max(1, max_r - min_l),
                height=max(1, max_b - min_t),
            )
            cx = min_l + (max_r - min_l) // 2
            cy = min_t + (max_b - min_t) // 2

            # Separate contact name from message snippet / status
            first_text = cluster[0]["text"].strip()
            rest_texts = [c["text"].strip() for c in cluster[1:]]
            rest_joined = " ".join(rest_texts).strip()

            # Filter out non-conversation UI terms
            first_lower = first_text.lower()
            if any(term in first_lower for term in ("primary", "general", "requests", "search", "messages")):
                continue

            has_status_or_preview = any(
                any(kw in t.lower() for kw in STATUS_KEYWORDS)
                for t in rest_texts
            ) or bool(rest_joined)

            # Determine confidence
            evidence = ["in_inbox_column"]
            if bool(rest_joined):
                evidence.append("has_message_preview")
            if any(any(kw in t.lower() for kw in STATUS_KEYWORDS) for t in rest_texts):
                evidence.append("has_activity_status")

            is_unread = any("•" in t or "unread" in t.lower() for t in [first_text] + rest_texts)
            if is_unread:
                evidence.append("unread_indicator_present")

            cand_id = f"conv-{hashlib.sha256(f'{first_text}:{min_t}'.encode()).hexdigest()[:10]}"

            # Genuine conversation row criteria
            if has_status_or_preview and len(first_text) >= 2:
                verified.append(
                    ConversationCandidate(
                        id=cand_id,
                        contact_name=first_text,
                        last_message_preview=rest_joined if rest_joined else None,
                        timestamp_or_status=next((t for t in rest_texts if any(k in t.lower() for k in STATUS_KEYWORDS)), None),
                        is_unread=is_unread,
                        is_currently_open=False,
                        bounding_box=row_bounds,
                        center=PointCoordinate(x=cx, y=cy),
                        confidence=0.92,
                        confidence_level="HIGH",
                        evidence=evidence,
                    )
                )
            else:
                # Standalone text without preview -> marked uncertain
                uncertain.append(
                    ConversationCandidate(
                        id=cand_id,
                        contact_name=first_text,
                        last_message_preview=rest_joined or None,
                        is_unread=is_unread,
                        is_currently_open=False,
                        bounding_box=row_bounds,
                        center=PointCoordinate(x=cx, y=cy),
                        confidence=0.55,
                        confidence_level="MEDIUM",
                        evidence=evidence,
                    )
                )

        return verified, uncertain

    def _identify_open_conversation(
        self,
        items: List[Dict[str, Any]],
        screen_width: int,
        screen_height: int,
    ) -> Optional[ConversationCandidate]:
        """Detect the active conversation thread rendered in the right pane."""
        if not items:
            return None

        # Filter items in the top header region of the active chat pane
        header_items = [
            it for it in items
            if it["bounds"].top < screen_height * 0.20
        ]

        if not header_items:
            return None

        # The first substantial text line in active header is the contact name
        header_sorted = sorted(header_items, key=lambda x: (x["bounds"].top, x["bounds"].left))
        for h in header_sorted:
            t = h["text"].strip()
            t_lower = t.lower()
            if t_lower in NAV_TERMS or t_lower in ("audio call", "video call", "details", "info"):
                continue
            if len(t) >= 2:
                b = h["bounds"]
                cx = b.left + b.width // 2
                cy = b.top + b.height // 2
                return ConversationCandidate(
                    id=f"open-{hashlib.sha256(t.encode()).hexdigest()[:10]}",
                    contact_name=t,
                    last_message_preview=None,
                    timestamp_or_status="Currently Open",
                    is_unread=False,
                    is_currently_open=True,
                    bounding_box=b,
                    center=PointCoordinate(x=cx, y=cy),
                    confidence=0.95,
                    confidence_level="HIGH",
                    evidence=["active_chat_header", "right_pane_position"],
                )
        return None


# Global singleton instance
instagram_semantic_classifier = InstagramSemanticClassifier()
