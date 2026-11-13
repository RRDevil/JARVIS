"""Apple Vision Framework Local OCR Engine for macOS (Phase 6).

Uses Apple's native Vision framework (VNRecognizeTextRequest) via PyObjC to perform
fast, private, hardware-accelerated on-device text and bounding box recognition.
"""

import asyncio
import logging
import sys
import time
from typing import List, Optional
from PIL import Image

from app.perception.base import OCREngineProvider
from app.perception.models import BoundingBox, OCRLine, OCRResult, OCRWord

logger = logging.getLogger("jarvis.perception.ocr.macos")

# Safe dynamic import of Apple Vision framework
HAS_APPLE_VISION = False
try:
    if sys.platform == "darwin":
        import objc
        import Vision
        import Foundation
        HAS_APPLE_VISION = True
    else:
        Vision = None
        Foundation = None
except ImportError:
    Vision = None
    Foundation = None
    logger.debug("Apple Vision framework not installed; MacOSVisionOCREngine running in fallback mode.")


class MacOSVisionOCREngine(OCREngineProvider):
    """Local Apple Vision OCR engine for macOS."""

    def __init__(self, default_lang: str = "en"):
        self.default_lang = default_lang
        self._available = HAS_APPLE_VISION and sys.platform == "darwin"

    @property
    def is_available(self) -> bool:
        """Check if Apple Vision framework is available on this macOS system."""
        return self._available

    async def recognize(
        self,
        image: Image.Image,
        lang: Optional[str] = None,
    ) -> OCRResult:
        """Extract text and bounding boxes using Apple Vision framework."""
        if image is None:
            return OCRResult(full_text="", lines=[], line_count=0, word_count=0, confidence=0.0, duration_ms=0.0)

        if image.width <= 0 or image.height <= 0:
            return OCRResult(full_text="", lines=[], line_count=0, word_count=0, confidence=1.0, duration_ms=0.0)

        start_time = time.perf_counter()

        if not self._available:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OCRResult(
                full_text="",
                lines=[],
                line_count=0,
                word_count=0,
                confidence=0.0,
                duration_ms=duration_ms,
            )

        # Offload Vision request to worker thread
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._recognize_sync, image, start_time)

    def _recognize_sync(self, image: Image.Image, start_time: float) -> OCRResult:
        """Synchronous execution of VNRecognizeTextRequest."""
        try:
            # Ensure RGB
            if image.mode != "RGB":
                image = image.convert("RGB")

            img_w, img_h = image.size

            # Save to in-memory bytes for CGImageSource
            import io
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            ns_data = Foundation.NSData.dataWithBytes_length_(img_bytes, len(img_bytes))
            cg_source = Quartz.CGImageSourceCreateWithData(ns_data, None)
            cg_image = Quartz.CGImageSourceCreateImageAtIndex(cg_source, 0, None)

            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
            success = handler.performRequests_error_([request], None)

            lines: List[OCRLine] = []
            total_words = 0

            if success:
                observations = request.results()
                for obs in observations:
                    top_candidate = obs.topCandidates_(1)
                    if not top_candidate:
                        continue
                    text = str(top_candidate[0].string())
                    confidence = float(top_candidate[0].confidence())

                    # Vision coordinates are normalized (0.0 to 1.0) with origin at bottom-left
                    box = obs.boundingBox()
                    # Convert bottom-left to top-left origin
                    box_x = float(box.origin.x) * img_w
                    box_y = (1.0 - float(box.origin.y) - float(box.size.height)) * img_h
                    box_w = float(box.size.width) * img_w
                    box_h = float(box.size.height) * img_h

                    # Decompose line into word tokens
                    words_in_line: List[OCRWord] = []
                    raw_words = text.split()
                    if raw_words:
                        word_w = box_w / len(raw_words)
                        for w_idx, w_text in enumerate(raw_words):
                            words_in_line.append(
                                OCRWord(
                                    text=w_text,
                                    bounding_box=BoundingBox(
                                        x=round(box_x + w_idx * word_w, 1),
                                        y=round(box_y, 1),
                                        width=round(word_w, 1),
                                        height=round(box_h, 1),
                                    ),
                                    confidence=confidence,
                                )
                            )
                        total_words += len(words_in_line)

                    lines.append(
                        OCRLine(
                            text=text,
                            words=words_in_line,
                        )
                    )

            full_text = "\n".join(l.text for l in lines)
            duration_ms = (time.perf_counter() - start_time) * 1000

            return OCRResult(
                full_text=full_text,
                lines=lines,
                line_count=len(lines),
                word_count=total_words,
                confidence=1.0 if lines else 0.0,
                duration_ms=duration_ms,
            )
        except Exception as exc:
            logger.error(f"Error during Apple Vision OCR processing: {exc}")
            duration_ms = (time.perf_counter() - start_time) * 1000
            return OCRResult(
                full_text="",
                lines=[],
                line_count=0,
                word_count=0,
                confidence=0.0,
                duration_ms=duration_ms,
            )
