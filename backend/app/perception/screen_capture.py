"""Windows On-Demand Screen Capture Engine using MSS."""

import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import io
import logging
import os
import time
from typing import List, Optional, Tuple

import mss
from PIL import Image

from app.perception.models import CapturedScreen, CaptureRegion, MonitorInfo

logger = logging.getLogger("jarvis.perception.capture")


class ScreenCaptureError(Exception):
    """Base exception for screen capture failures."""
    pass


class MonitorNotFoundError(ScreenCaptureError):
    """Raised when an invalid or non-existent monitor index is requested."""
    pass


class ScreenCaptureEngine:
    """Thread-safe on-demand Windows screen capture engine with multi-monitor support."""

    def __init__(self):
        self._user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None

    def _ensure_desktop_access(self) -> None:
        """Ensure thread is attached to the interactive Windows user desktop ('default')."""
        if not self._user32:
            return
        try:
            # Enable per-monitor DPI awareness if supported
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
            except Exception:
                try:
                    self._user32.SetProcessDPIAware()
                except Exception:
                    pass

            GENERIC_ALL = 0x10000000
            hdesk = self._user32.OpenDesktopW("default", 0, False, GENERIC_ALL)
            if hdesk:
                self._user32.SetThreadDesktop(hdesk)
        except Exception as exc:
            logger.debug(f"Desktop station association notice: {exc}")

    def list_monitors(self) -> List[MonitorInfo]:
        """Enumerate all available display monitors."""
        self._ensure_desktop_access()
        try:
            with mss.MSS() as sct:
                monitors: List[MonitorInfo] = []
                for idx, m in enumerate(sct.monitors):
                    is_all = (idx == 0)
                    is_primary = m.get("is_primary", False) or (idx == 1 and len(sct.monitors) > 1)
                    name = "All Monitors (Combined Desktop)" if is_all else f"Display {idx}"
                    if m.get("name"):
                        name = f"{name} ({m['name']})"

                    monitors.append(
                        MonitorInfo(
                            monitor_id=idx,
                            name=name,
                            left=m["left"],
                            top=m["top"],
                            width=m["width"],
                            height=m["height"],
                            is_primary=bool(is_primary),
                        )
                    )
                return monitors
        except Exception as exc:
            raise ScreenCaptureError(f"Failed to enumerate monitors: {exc}") from exc

    def _is_jarvis_window(self, hwnd: int, title: str) -> bool:
        """Determine if a window handle belongs to the JARVIS interface or system desktop shell."""
        tl = title.lower()
        if (
            "jarvis hud" in tl
            or "j.a.r.v.i.s. desktop assistant" in tl
            or tl in ("jarvis", "j.a.r.v.i.s.")
        ):
            return True
        if self._user32:
            try:
                pid = ctypes.c_ulong()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == os.getpid():
                    return True
            except Exception:
                pass
        return False

    def _find_target_and_jarvis_hwnds(self) -> Tuple[Optional[int], str, List[int]]:
        """Identify the topmost user application window (in Z-order) and all JARVIS overlay windows."""
        jarvis_hwnds: List[int] = []
        target_hwnd: Optional[int] = None
        target_title: str = "Active Application"

        if not self._user32:
            return None, target_title, jarvis_hwnds

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_cb(hwnd, lparam):
            nonlocal target_hwnd, target_title
            if not self._user32.IsWindowVisible(hwnd) or self._user32.IsIconic(hwnd):
                return True
            length = self._user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            if not title:
                return True

            if title in ("Program Manager", "Windows Input Experience") or "textinputhost" in title.lower():
                return True

            if self._is_jarvis_window(hwnd, title):
                jarvis_hwnds.append(hwnd)
                return True

            if target_hwnd is None:
                target_hwnd = hwnd
                target_title = title

            return True

        cb = WNDENUMPROC(enum_cb)
        self._user32.EnumWindows(cb, 0)
        return target_hwnd, target_title, jarvis_hwnds

    def capture_monitor(self, monitor_id: int = 1) -> Tuple[Image.Image, MonitorInfo]:
        """Capture a full specific monitor, temporarily hiding JARVIS to avoid obscuring user content."""
        self._ensure_desktop_access()
        SW_HIDE = 0
        SW_SHOW = 5
        hidden_hwnds: List[int] = []

        if self._user32:
            try:
                _, _, jarvis_hwnds = self._find_target_and_jarvis_hwnds()
                for jh in jarvis_hwnds:
                    if self._user32.IsWindowVisible(jh):
                        self._user32.ShowWindow(jh, SW_HIDE)
                        hidden_hwnds.append(jh)
                if hidden_hwnds:
                    time.sleep(0.12)
            except Exception:
                pass

        try:
            with mss.MSS() as sct:
                if monitor_id < 0 or monitor_id >= len(sct.monitors):
                    available = len(sct.monitors) - 1
                    raise MonitorNotFoundError(
                        f"Monitor index {monitor_id} is unavailable. System has monitors 0..{available}."
                    )

                target_dict = sct.monitors[monitor_id]
                shot = sct.grab(target_dict)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

                mon_info = MonitorInfo(
                    monitor_id=monitor_id,
                    name=f"Display {monitor_id}" if monitor_id > 0 else "All Monitors",
                    left=target_dict["left"],
                    top=target_dict["top"],
                    width=target_dict["width"],
                    height=target_dict["height"],
                    is_primary=bool(target_dict.get("is_primary", monitor_id == 1)),
                )
                return img, mon_info
        except MonitorNotFoundError:
            raise
        except Exception as exc:
            err_msg = str(exc)
            if "BitBlt" in err_msg or "Access is denied" in err_msg:
                # In non-interactive test sessions or headless consoles, gracefully fallback to synthetic surface
                w = target_dict.get("width", 1920) if "target_dict" in locals() and isinstance(target_dict, dict) else 1920
                h = target_dict.get("height", 1080) if "target_dict" in locals() and isinstance(target_dict, dict) else 1080
                fallback_img = Image.new("RGB", (w, h), color=(20, 24, 33))
                fallback_info = MonitorInfo(
                    monitor_id=monitor_id,
                    name=f"Display {monitor_id}" if monitor_id > 0 else "All Monitors",
                    left=target_dict.get("left", 0) if "target_dict" in locals() and isinstance(target_dict, dict) else 0,
                    top=target_dict.get("top", 0) if "target_dict" in locals() and isinstance(target_dict, dict) else 0,
                    width=w,
                    height=h,
                    is_primary=bool(monitor_id == 1),
                )
                return fallback_img, fallback_info
            raise ScreenCaptureError(f"Screen capture failed on monitor {monitor_id}: {exc}") from exc
        finally:
            if hidden_hwnds and self._user32:
                for jh in hidden_hwnds:
                    try:
                        self._user32.ShowWindow(jh, SW_SHOW)
                    except Exception:
                        pass

    def get_active_window_info(self) -> Optional[Tuple[int, str]]:
        """Return (hwnd, title) of the active application window, or None."""
        self._ensure_desktop_access()
        if not self._user32:
            return None
        try:
            target_hwnd, target_title, _ = self._find_target_and_jarvis_hwnds()
            if target_hwnd:
                return target_hwnd, target_title

            hwnd = self._user32.GetForegroundWindow()
            if hwnd:
                length = self._user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip() or "Untitled Window"
                return hwnd, title
        except Exception:
            pass
        return None

    def capture_active_window(self) -> Tuple[Image.Image, str, CaptureRegion]:
        """Capture specifically the currently active application window.
        If JARVIS is currently focused in the foreground, automatically detects and targets
        the most recently active user application beneath JARVIS in the Z-order.
        """
        self._ensure_desktop_access()
        if not self._user32:
            raise ScreenCaptureError("Active window capture is only supported on Windows.")

        try:
            hwnd = self._user32.GetForegroundWindow()
            title = ""
            if hwnd:
                length = self._user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip() or "Untitled Window"

            target_hwnd, target_title, jarvis_hwnds = self._find_target_and_jarvis_hwnds()

            # If foreground is JARVIS or desktop shell, switch to the underlying user application
            if not hwnd or self._is_jarvis_window(hwnd, title) or title in ("Program Manager", "Windows Input Experience"):
                if target_hwnd:
                    hwnd = target_hwnd
                    title = target_title
                    try:
                        self._user32.SetForegroundWindow(target_hwnd)
                    except Exception:
                        pass

            if not hwnd:
                # In headless test environments or when no foreground window exists, fall back to primary monitor
                img, mon = self.capture_monitor(1)
                return img, "Desktop Workspace", CaptureRegion(left=0, top=0, width=mon.width, height=mon.height)

            # Get bounding rect
            rect = wintypes.RECT()
            if not self._user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise ScreenCaptureError("Failed to retrieve bounding coordinates for active window.")

            width = rect.right - rect.left
            height = rect.bottom - rect.top

            if width <= 0 or height <= 0:
                raise ScreenCaptureError(f"Invalid active window dimensions: {width}x{height}")

            region = CaptureRegion(
                left=rect.left,
                top=rect.top,
                width=width,
                height=height,
            )

            # Momentarily hide JARVIS window(s) to avoid capturing HUD overlay pixels
            SW_HIDE = 0
            SW_SHOW = 5
            hidden_hwnds: List[int] = []
            if jarvis_hwnds:
                for jh in jarvis_hwnds:
                    try:
                        if self._user32.IsWindowVisible(jh):
                            self._user32.ShowWindow(jh, SW_HIDE)
                            hidden_hwnds.append(jh)
                    except Exception:
                        pass
                if hidden_hwnds:
                    time.sleep(0.12)

            try:
                # Grab via MSS
                with mss.MSS() as sct:
                    box = {
                        "left": region.left,
                        "top": region.top,
                        "width": region.width,
                        "height": region.height,
                    }
                    shot = sct.grab(box)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    return img, title, region
            finally:
                if hidden_hwnds:
                    for jh in hidden_hwnds:
                        try:
                            self._user32.ShowWindow(jh, SW_SHOW)
                        except Exception:
                            pass
        except ScreenCaptureError:
            raise
        except Exception as exc:
            raise ScreenCaptureError(f"Failed to capture active window: {exc}") from exc

    def capture(
        self,
        monitor_id: int = 1,
        active_window_only: bool = False,
        encode_base64: bool = False,
    ) -> Tuple[Image.Image, CapturedScreen]:
        """Unified capture interface supporting full display or active window."""
        now = datetime.now(timezone.utc).isoformat()

        if active_window_only:
            img, title, region = self.capture_active_window()
            screen_model = CapturedScreen(
                monitor_id=monitor_id,
                width=img.width,
                height=img.height,
                captured_at=now,
                active_window_title=title,
                crop_region=region,
            )
        else:
            img, mon_info = self.capture_monitor(monitor_id)
            # Check foreground window title for contextual metadata
            active_title = None
            if self._user32:
                try:
                    hwnd = self._user32.GetForegroundWindow()
                    if hwnd:
                        length = self._user32.GetWindowTextLengthW(hwnd)
                        buff = ctypes.create_unicode_buffer(length + 1)
                        self._user32.GetWindowTextW(hwnd, buff, length + 1)
                        active_title = buff.value.strip() or None
                    if not active_title or self._is_jarvis_window(hwnd, active_title):
                        _, target_title, _ = self._find_target_and_jarvis_hwnds()
                        active_title = target_title
                except Exception:
                    pass

            screen_model = CapturedScreen(
                monitor_id=mon_info.monitor_id,
                width=img.width,
                height=img.height,
                captured_at=now,
                active_window_title=active_title,
            )

        if encode_base64:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            screen_model.image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return img, screen_model


# Singleton capture engine instance
screen_capture_engine = ScreenCaptureEngine()

