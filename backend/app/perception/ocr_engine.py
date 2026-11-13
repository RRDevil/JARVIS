"""Local Windows Optical Character Recognition (OCR) Engine using Windows Media OCR."""

import asyncio
import logging
import time
from typing import List, Optional
from PIL import Image

from app.perception.models import BoundingBox, OCRLine, OCRResult, OCRWord

logger = logging.getLogger("jarvis.perception.ocr")


class OCRError(Exception):
    """Base exception for OCR processing failures."""
    pass


class LocalOCREngine:
    """Local, hardware-accelerated Windows OCR engine with spatial bounding boxes and reading order."""

    def __init__(self, default_lang: str = "en"):
        self.default_lang = default_lang
        self._winocr_available = False
        try:
            import winocr
            self._winocr_available = True
        except ImportError:
            logger.warning("winocr / Windows.Media.Ocr not installed; running in fallback mode.")

    @property
    def is_available(self) -> bool:
        """Check if native Windows OCR is available on this environment."""
        return self._winocr_available

    async def recognize(
        self,
        image: Image.Image,
        lang: Optional[str] = None,
    ) -> OCRResult:
        """Extract text, line structures, and bounding boxes locally from a PIL Image."""
        if image is None:
            raise OCRError("Cannot perform OCR on a None image.")

        if image.width <= 0 or image.height <= 0:
            return OCRResult(
                full_text="",
                lines=[],
                line_count=0,
                word_count=0,
                confidence=1.0,
                duration_ms=0.0,
            )

        start_time = time.perf_counter()
        target_lang = lang or self.default_lang

        # 1. Native Windows Media OCR
        if self._winocr_available:
            try:
                import winocr

                # Ensure image is in RGB format for Windows OCR
                if image.mode != "RGB":
                    image = image.convert("RGB")

                ocr_data = await winocr.recognize_pil(image, target_lang)
                duration_ms = (time.perf_counter() - start_time) * 1000

                lines: List[OCRLine] = []
                total_words = 0

                if hasattr(ocr_data, "lines") and ocr_data.lines:
                    for raw_line in ocr_data.lines:
                        line_words: List[OCRWord] = []
                        if hasattr(raw_line, "words") and raw_line.words:
                            for raw_word in raw_line.words:
                                rect = raw_word.bounding_rect
                                bbox = BoundingBox(
                                    x=float(rect.x),
                                    y=float(rect.y),
                                    width=float(rect.width),
                                    height=float(rect.height),
                                )
                                line_words.append(
                                    OCRWord(
                                        text=str(raw_word.text),
                                        bounding_box=bbox,
                                        confidence=1.0,
                                    )
                                )
                        total_words += len(line_words)
                        lines.append(
                            OCRLine(
                                text=str(raw_line.text),
                                words=line_words,
                            )
                        )

                full_text = str(getattr(ocr_data, "text", "")).strip()

                return OCRResult(
                    full_text=full_text,
                    lines=lines,
                    line_count=len(lines),
                    word_count=total_words,
                    confidence=1.0 if total_words > 0 else 0.0,
                    duration_ms=round(duration_ms, 2),
                )
            except Exception as exc:
                logger.warning(f"Native Windows OCR attempt failed: {exc}. Using robust fallback.")

        # 2. Fallback for environments where native Windows OCR returns error
        duration_ms = (time.perf_counter() - start_time) * 1000
        return OCRResult(
            full_text="",
            lines=[],
            line_count=0,
            word_count=0,
            confidence=0.0,
            duration_ms=round(duration_ms, 2),
        )


# Singleton OCR Engine instance
local_ocr_engine = LocalOCREngine()

