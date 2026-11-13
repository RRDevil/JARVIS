"""Unified Semantic Perception Engine.

Orchestrates multi-source interface classification across Instagram,
WhatsApp, Discord, and desktop applications.
"""

import logging
from typing import Any, List, Optional

from app.perception.semantic.generic import generic_semantic_classifier
from app.perception.semantic.instagram import instagram_semantic_classifier
from app.perception.semantic.models import SemanticPerceptionResult

logger = logging.getLogger("jarvis.perception.semantic.classifier")


class SemanticPerceptionEngine:
    """Central engine providing structured application interface perception."""

    def analyze_screen(
        self,
        app_name: str,
        ocr_lines: List[Any],
        screen_width: int,
        screen_height: int,
        window_title: str = "",
        uia_controls: Optional[List[Any]] = None,
    ) -> SemanticPerceptionResult:
        """Analyze visible screen content and produce semantic objects."""
        app_lower = (app_name or "").lower()
        title_lower = (window_title or "").lower()

        if "instagram" in app_lower or "instagram" in title_lower:
            return instagram_semantic_classifier.classify_screen(
                ocr_lines=ocr_lines,
                screen_width=screen_width,
                screen_height=screen_height,
                window_title=window_title,
                uia_controls=uia_controls,
            )

        return generic_semantic_classifier.classify_screen(
            app_name=app_name,
            ocr_lines=ocr_lines,
            screen_width=screen_width,
            screen_height=screen_height,
            window_title=window_title,
            uia_controls=uia_controls,
        )


# Global singleton instance
semantic_perception_engine = SemanticPerceptionEngine()
