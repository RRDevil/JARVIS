"""Abstract Base Classes for Screen Capture and OCR Providers.

Enables platform-agnostic screen perception across Windows, macOS, and testing environments.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from PIL import Image

from app.perception.models import CapturedScreen, CaptureRegion, MonitorInfo, OCRResult


class ScreenCaptureProvider(ABC):
    """Abstract interface defining display and window capture capabilities."""

    @abstractmethod
    def list_monitors(self) -> List[MonitorInfo]:
        """Enumerate all available physical and virtual display monitors."""
        pass

    @abstractmethod
    def capture_monitor(self, monitor_id: int = 1) -> Tuple[Image.Image, MonitorInfo]:
        """Capture the full screen of the specified monitor index."""
        pass

    @abstractmethod
    def capture_region(self, region: CaptureRegion) -> Tuple[Image.Image, Optional[CaptureRegion]]:
        """Capture a specific bounding box region across virtual display coordinates."""
        pass

    @abstractmethod
    def capture_active_window(self) -> Tuple[Image.Image, Optional[str], Optional[CaptureRegion]]:
        """Capture the current foreground desktop application window."""
        pass

    @abstractmethod
    def capture(
        self,
        monitor_id: int = 1,
        active_window_only: bool = False,
        encode_base64: bool = False,
    ) -> Tuple[Image.Image, CapturedScreen]:
        """Unified capture interface supporting full display or active window."""
        pass

    def get_dpi_scaling_factor(self) -> float:
        """Return the current display scaling factor (e.g., 1.0, 1.25, 2.0 for Retina)."""
        return 1.0


class OCREngineProvider(ABC):
    """Abstract interface for local on-device optical character recognition."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the native local OCR engine is available and ready on this platform."""
        pass

    @abstractmethod
    async def recognize(
        self,
        image: Image.Image,
        lang: Optional[str] = None,
    ) -> OCRResult:
        """Extract text, structured lines, and spatial bounding boxes from a PIL image."""
        pass
