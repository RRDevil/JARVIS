"""macOS Platform Adapter Implementation (Phase 6).

Provides native macOS window management and input injection using PyObjC
(AppKit, Quartz CoreGraphics, and ApplicationServices AXUIElement).
"""

import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from app.automation.platform_adapter import (
    ApprovedApp,
    AutomationError,
    FocusMismatchError,
    PlatformAdapter,
    UIControlInfo,
    WindowInfo,
)

logger = logging.getLogger("jarvis.automation.macos")

# Safe dynamic import of PyObjC macOS frameworks
HAS_PYOBJC = False
try:
    if sys.platform == "darwin":
        import AppKit
        import ApplicationServices
        import Quartz
        HAS_PYOBJC = True
    else:
        AppKit = None
        ApplicationServices = None
        Quartz = None
except ImportError:
    AppKit = None
    ApplicationServices = None
    Quartz = None
    logger.debug("PyObjC frameworks not installed; macOS adapter running in stub/degraded mode.")


# Pre-approved standard macOS productivity applications
APPROVED_MACOS_APPS = [
    ApprovedApp(
        app_id="calculator",
        display_name="Calculator",
        executable="/System/Applications/Calculator.app",
        description="Standard macOS Calculator utility.",
    ),
    ApprovedApp(
        app_id="textedit",
        display_name="TextEdit",
        executable="/System/Applications/TextEdit.app",
        description="Standard macOS lightweight plain text and rich text editor.",
    ),
    ApprovedApp(
        app_id="safari",
        display_name="Safari",
        executable="/Applications/Safari.app",
        description="Apple Safari web browser.",
    ),
    ApprovedApp(
        app_id="chrome",
        display_name="Google Chrome",
        executable="/Applications/Google Chrome.app",
        description="Google Chrome web browser.",
    ),
    ApprovedApp(
        app_id="opera_gx",
        display_name="Opera GX",
        executable="/Applications/Opera GX.app",
        description="Opera GX gaming and productivity web browser.",
    ),
    ApprovedApp(
        app_id="word",
        display_name="Microsoft Word",
        executable="/Applications/Microsoft Word.app",
        description="Microsoft Word word processing application.",
    ),
    ApprovedApp(
        app_id="excel",
        display_name="Microsoft Excel",
        executable="/Applications/Microsoft Excel.app",
        description="Microsoft Excel spreadsheet application.",
    ),
    ApprovedApp(
        app_id="powerpoint",
        display_name="Microsoft PowerPoint",
        executable="/Applications/Microsoft PowerPoint.app",
        description="Microsoft PowerPoint presentation application.",
    ),
    ApprovedApp(
        app_id="discord",
        display_name="Discord",
        executable="/Applications/Discord.app",
        description="Discord voice and text communication platform.",
    ),
    ApprovedApp(
        app_id="whatsapp",
        display_name="WhatsApp",
        executable="/Applications/WhatsApp.app",
        description="WhatsApp desktop messaging client.",
    ),
]


class MacOSPlatformAdapter(PlatformAdapter):
    """Native macOS platform adapter using Quartz and AppKit."""

    def __init__(self):
        self._approved_apps: Dict[str, ApprovedApp] = {
            app.app_id: app for app in APPROVED_MACOS_APPS
        }

    def is_permission_granted(self) -> bool:
        """Check if J.A.R.V.I.S. has macOS Accessibility permissions."""
        if not HAS_PYOBJC or sys.platform != "darwin":
            return False
        try:
            return bool(ApplicationServices.AXIsProcessTrusted())
        except Exception as exc:
            logger.warning(f"Failed to query AXIsProcessTrusted: {exc}")
            return False

    def get_approved_apps(self) -> List[ApprovedApp]:
        """Return allowlisted macOS applications."""
        return list(self._approved_apps.values())

    def launch_app(self, app_id: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        """Launch an allowlisted application by ID or path."""
        target_app = self._approved_apps.get(app_id.lower())
        exec_path = target_app.executable if target_app else app_id

        if not os.path.exists(exec_path) and not app_id.startswith("/"):
            # Check standard /Applications or /System/Applications paths
            for candidate_dir in ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]:
                candidate = os.path.join(candidate_dir, f"{app_id}.app")
                if os.path.exists(candidate):
                    exec_path = candidate
                    break

        cmd = ["open", "-a", exec_path]
        if args:
            cmd.extend(["--args"] + args)

        try:
            subprocess.Popen(cmd)
            return {
                "success": True,
                "app_id": app_id,
                "target": exec_path,
                "status": "launched",
            }
        except Exception as exc:
            logger.error(f"Failed to launch application '{app_id}': {exc}")
            raise AutomationError(f"Failed to launch '{app_id}': {exc}") from exc

    def list_windows(self) -> List[WindowInfo]:
        """Enumerate active visible desktop windows on macOS."""
        if not HAS_PYOBJC:
            return []

        windows: List[WindowInfo] = []
        try:
            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

            for win in window_list:
                layer = win.get(Quartz.kCGWindowLayer, 0)
                if layer != 0:
                    continue  # Only standard application windows

                bounds = win.get(Quartz.kCGWindowBounds, {})
                width = bounds.get("Width", 0)
                height = bounds.get("Height", 0)
                if width < 30 or height < 30:
                    continue

                handle = win.get(Quartz.kCGWindowNumber, 0)
                title = win.get(Quartz.kCGWindowName, "") or ""
                owner_name = win.get(Quartz.kCGWindowOwnerName, "") or ""
                pid = win.get(Quartz.kCGWindowOwnerPID, 0)

                windows.append(
                    WindowInfo(
                        handle=int(handle),
                        title=title or owner_name,
                        process_id=int(pid),
                        process_name=owner_name,
                        is_visible=True,
                        is_minimized=False,
                    )
                )
        except Exception as exc:
            logger.error(f"Error enumerating macOS windows: {exc}")

        return windows

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the current active frontmost desktop window."""
        if not HAS_PYOBJC:
            return None

        try:
            front_app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
            if not front_app:
                return None

            pid = front_app.processIdentifier()
            app_name = front_app.localizedName() or ""

            # Locate front window owned by this process
            windows = self.list_windows()
            for win in windows:
                if win.process_id == pid:
                    return win

            return WindowInfo(
                handle=int(pid),
                title=app_name,
                process_id=int(pid),
                process_name=app_name,
                is_visible=True,
                is_minimized=False,
            )
        except Exception as exc:
            logger.error(f"Error getting active window on macOS: {exc}")
            return None

    def is_window_valid(self, handle: int) -> bool:
        """Check if a window handle represents a valid desktop window."""
        windows = self.list_windows()
        return any(w.handle == handle for w in windows)

    def focus_window(self, handle: int) -> bool:
        """Bring target application window to foreground."""
        if not HAS_PYOBJC:
            return False

        try:
            windows = self.list_windows()
            target = next((w for w in windows if w.handle == handle), None)
            if not target:
                return False

            app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
                target.process_id
            )
            if app:
                return bool(
                    app.activateWithOptions_(
                        AppKit.NSApplicationActivateIgnoringOtherApps
                    )
                )
            return False
        except Exception as exc:
            logger.error(f"Error focusing window {handle}: {exc}")
            return False

    def restore_and_focus_window(
        self,
        handle: int,
        expected_pid: Optional[int] = None,
        timeout: float = 0.6,
    ) -> bool:
        """Activate and focus window on macOS."""
        focused = self.focus_window(handle)
        if focused:
            time.sleep(0.1)
        return focused

    def minimize_window(self, handle: int) -> bool:
        """Minimize the target window via AppleScript or AXUIElement."""
        try:
            # Fallback AppleScript to minimize
            script = f'tell application "System Events" to set miniaturized of (every window whose id is {handle}) to true'
            subprocess.run(["osascript", "-e", script], check=False)
            return True
        except Exception as exc:
            logger.warning(f"Failed to minimize window {handle}: {exc}")
            return False

    def close_window(self, handle: int) -> bool:
        """Send close signal to target window."""
        try:
            script = f'tell application "System Events" to close (every window whose id is {handle})'
            subprocess.run(["osascript", "-e", script], check=False)
            return True
        except Exception as exc:
            logger.warning(f"Failed to close window {handle}: {exc}")
            return False

    def open_folder(self, folder_path: str) -> bool:
        """Open the directory in macOS Finder."""
        try:
            subprocess.Popen(["open", folder_path])
            return True
        except Exception as exc:
            logger.error(f"Failed to open folder '{folder_path}': {exc}")
            return False

    def find_controls(
        self,
        handle: int,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
    ) -> List[UIControlInfo]:
        """Find accessible controls inside the target window via AXUIElement."""
        # Baseline stub for Milestone 6.1; deeper AX tree traversal implemented in Milestone 6.2
        return []

    def click_control(self, handle: int, control_id: str) -> bool:
        """Click UI control."""
        return False

    def set_control_text(self, handle: int, control_id: str, text: str) -> bool:
        """Set text value of UI control."""
        return False

    def send_shortcut(
        self,
        handle: int,
        shortcut: str,
        expected_pid: Optional[int] = None,
    ) -> bool:
        """Send keyboard shortcut (e.g. 'cmd+c', 'cmd+v') to focused window."""
        if not HAS_PYOBJC:
            return False

        self.focus_window(handle)
        time.sleep(0.05)

        parts = [p.strip().lower() for p in shortcut.split("+")]
        key = parts[-1]
        modifiers = parts[:-1]

        # Map common keys to macOS virtual keycodes
        key_codes = {
            "c": 8, "v": 9, "x": 7, "z": 6, "a": 0, "s": 1,
            "f": 3, "w": 13, "q": 12, "t": 17, "r": 15, "return": 36, "enter": 36,
        }
        vk = key_codes.get(key)
        if vk is None:
            return False

        try:
            flags = 0
            if "cmd" in modifiers or "command" in modifiers:
                flags |= Quartz.kCGEventFlagMaskCommand
            if "ctrl" in modifiers or "control" in modifiers:
                flags |= Quartz.kCGEventFlagMaskControl
            if "shift" in modifiers:
                flags |= Quartz.kCGEventFlagMaskShift
            if "alt" in modifiers or "option" in modifiers:
                flags |= Quartz.kCGEventFlagMaskAlternate

            down = Quartz.CGEventCreateKeyboardEvent(None, vk, True)
            up = Quartz.CGEventCreateKeyboardEvent(None, vk, False)
            Quartz.CGEventSetFlags(down, flags)
            Quartz.CGEventSetFlags(up, flags)

            Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
            time.sleep(0.02)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            return True
        except Exception as exc:
            logger.error(f"Error injecting shortcut '{shortcut}': {exc}")
            return False

    def scroll_window(self, handle: int, direction: str, amount: int) -> bool:
        """Scroll window up or down."""
        bounds = self.get_window_bounds(handle)
        if not bounds:
            return False
        cx = bounds["left"] + bounds["width"] // 2
        cy = bounds["top"] + bounds["height"] // 2
        return self.scroll_at(cx, cy, direction, amount)

    def click_at(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_hwnd: Optional[int] = None,
    ) -> bool:
        """Move cursor to coordinates (x, y) and click."""
        if not HAS_PYOBJC:
            return False

        try:
            point = Quartz.CGPoint(x=x, y=y)
            btn_type = Quartz.kCGMouseButtonLeft if button == "left" else Quartz.kCGMouseButtonRight
            down_type = (
                Quartz.kCGEventLeftMouseDown if button == "left" else Quartz.kCGEventRightMouseDown
            )
            up_type = (
                Quartz.kCGEventLeftMouseUp if button == "left" else Quartz.kCGEventRightMouseUp
            )

            for i in range(clicks):
                down = Quartz.CGEventCreateMouseEvent(None, down_type, point, btn_type)
                up = Quartz.CGEventCreateMouseEvent(None, up_type, point, btn_type)
                if clicks > 1:
                    Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventClickState, i + 1)
                    Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventClickState, i + 1)

                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                time.sleep(0.02)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
                if i < clicks - 1:
                    time.sleep(0.05)

            return True
        except Exception as exc:
            logger.error(f"Error performing mouse click at ({x}, {y}): {exc}")
            return False

    def type_text(
        self,
        text: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        target_hwnd: Optional[int] = None,
        clear_first: bool = False,
        press_enter: bool = False,
        use_clipboard: Optional[bool] = None,
    ) -> bool:
        """Type verbatim text into active window."""
        if x is not None and y is not None:
            self.click_at(x, y)
            time.sleep(0.05)

        if clear_first:
            self.send_shortcut(0, "cmd+a")
            time.sleep(0.02)
            # Send backspace
            if HAS_PYOBJC:
                down = Quartz.CGEventCreateKeyboardEvent(None, 51, True)
                up = Quartz.CGEventCreateKeyboardEvent(None, 51, False)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

        if not HAS_PYOBJC:
            return False

        try:
            for char in text:
                down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                Quartz.CGEventKeyboardSetUnicodeString(down, len(char), char)
                Quartz.CGEventKeyboardSetUnicodeString(up, len(char), char)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
                time.sleep(0.005)

            if press_enter:
                time.sleep(0.02)
                down = Quartz.CGEventCreateKeyboardEvent(None, 36, True)
                up = Quartz.CGEventCreateKeyboardEvent(None, 36, False)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

            return True
        except Exception as exc:
            logger.error(f"Error typing text on macOS: {exc}")
            return False

    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        clear_first: bool = False,
        press_enter: bool = False,
        use_clipboard: Optional[bool] = None,
    ) -> bool:
        """Focus display coordinates and enter text."""
        return self.type_text(
            text=text,
            x=x,
            y=y,
            clear_first=clear_first,
            press_enter=press_enter,
            use_clipboard=use_clipboard,
        )

    def scroll_at(self, x: int, y: int, direction: str = "down", amount: int = 3) -> bool:
        """Scroll at coordinates (x, y)."""
        if not HAS_PYOBJC:
            return False

        try:
            delta = -amount if direction == "down" else amount
            scroll_event = Quartz.CGEventCreateScrollWheelEvent(
                None,
                Quartz.kCGScrollEventUnitLine,
                1,
                delta,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, scroll_event)
            return True
        except Exception as exc:
            logger.error(f"Error scrolling at ({x}, {y}): {exc}")
            return False

    def get_window_bounds(self, handle: int) -> Optional[Dict[str, int]]:
        """Retrieve bounding box {left, top, width, height} of window."""
        if not HAS_PYOBJC:
            return None

        try:
            options = Quartz.kCGWindowListOptionIncludingWindow
            window_list = Quartz.CGWindowListCopyWindowInfo(options, handle)
            if window_list and len(window_list) > 0:
                bounds = window_list[0].get(Quartz.kCGWindowBounds, {})
                return {
                    "left": int(bounds.get("X", 0)),
                    "top": int(bounds.get("Y", 0)),
                    "width": int(bounds.get("Width", 0)),
                    "height": int(bounds.get("Height", 0)),
                }
        except Exception as exc:
            logger.error(f"Error getting window bounds for {handle}: {exc}")

        return None

    def get_virtual_desktop_bounds(self) -> Tuple[int, int, int, int]:
        """Retrieve virtual desktop bounds spanning all connected monitors."""
        if not HAS_PYOBJC:
            return (0, 0, 1920, 1080)

        try:
            screens = AppKit.NSScreen.screens()
            if not screens:
                return (0, 0, 1920, 1080)

            min_x = 0
            min_y = 0
            max_x = 0
            max_y = 0

            for screen in screens:
                frame = screen.frame()
                min_x = min(min_x, int(frame.origin.x))
                min_y = min(min_y, int(frame.origin.y))
                max_x = max(max_x, int(frame.origin.x + frame.size.width))
                max_y = max(max_y, int(frame.origin.y + frame.size.height))

            return (min_x, min_y, max_x - min_x, max_y - min_y)
        except Exception as exc:
            logger.error(f"Error querying NSScreen bounds: {exc}")
            return (0, 0, 1920, 1080)
