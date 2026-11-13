"""In-memory Mock Platform Adapter for Testing and Simulation."""

from typing import Any, Dict, List, Optional
from app.automation.platform_adapter import ApprovedApp, PlatformAdapter, UIControlInfo, WindowInfo
from app.automation.windows_adapter import DEFAULT_APPROVED_APPS

# Allowlist of safe keyboard shortcuts
ALLOWED_KEYBOARD_SHORTCUTS = {
    "ctrl+s", "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
    "ctrl+a", "ctrl+f", "ctrl+w", "enter", "escape", "tab",
    "backspace", "space", "arrow_up", "arrow_down", "arrow_left", "arrow_right",
}


class MockPlatformAdapter(PlatformAdapter):
    """Hermetic platform adapter that simulates Windows OS actions in-memory."""

    def __init__(self, initial_windows: Optional[List[WindowInfo]] = None):
        self.approved_apps = DEFAULT_APPROVED_APPS
        self.windows: Dict[int, WindowInfo] = {}
        self.active_window_handle: Optional[int] = None
        self.launch_history: List[Dict[str, Any]] = []
        self.opened_folders: List[str] = []
        self.closed_windows: List[int] = []
        self.ui_actions_history: List[Dict[str, Any]] = []

        # Populate initial dummy windows
        if initial_windows:
            for w in initial_windows:
                self.windows[w.handle] = w
        else:
            self.windows = {
                1001: WindowInfo(
                    handle=1001,
                    title="JARVIS Holographic HUD - Google Chrome",
                    process_id=4520,
                    process_name="chrome.exe",
                    is_visible=True,
                    is_minimized=False,
                ),
                1002: WindowInfo(
                    handle=1002,
                    title="Visual Studio Code - JARVIS",
                    process_id=8920,
                    process_name="Code.exe",
                    is_visible=True,
                    is_minimized=False,
                ),
                1003: WindowInfo(
                    handle=1003,
                    title="Untitled - Notepad",
                    process_id=1240,
                    process_name="notepad.exe",
                    is_visible=True,
                    is_minimized=True,
                ),
            }
            self.active_window_handle = 1001

        # Mock accessible UI controls for window 1003 (Notepad)
        self.controls: Dict[int, Dict[str, UIControlInfo]] = {
            1003: {
                "ctrl_edit_doc": UIControlInfo(
                    control_id="ctrl_edit_doc",
                    name="Text Editor",
                    control_type="edit",
                    is_enabled=True,
                    value="",
                ),
                "ctrl_menu_file": UIControlInfo(
                    control_id="ctrl_menu_file",
                    name="File",
                    control_type="menu_item",
                    is_enabled=True,
                ),
                "ctrl_btn_save": UIControlInfo(
                    control_id="ctrl_btn_save",
                    name="Save",
                    control_type="button",
                    is_enabled=True,
                ),
            }
        }

    def find_app_window(self, app_id: str) -> Optional[WindowInfo]:
        """Find an open mock window matching the application name or executable."""
        app_spec = self.approved_apps.get(app_id.lower().strip())
        for w in self.windows.values():
            if app_spec and (
                app_spec.executable.lower() in w.process_name.lower()
                or app_spec.display_name.lower() in w.title.lower()
                or app_id.lower() in w.title.lower()
            ):
                return w
            if app_id.lower() in w.process_name.lower() or app_id.lower() in w.title.lower():
                return w
        return None

    def create_window(
        self,
        handle: int,
        title: str,
        process_name: str,
        is_visible: bool = True,
        is_minimized: bool = False,
    ) -> WindowInfo:
        """Helper to create mock window dynamically in tests."""
        win = WindowInfo(
            handle=handle,
            title=title,
            process_id=handle * 10,
            process_name=process_name,
            is_visible=is_visible,
            is_minimized=is_minimized,
        )
        self.windows[handle] = win
        return win

    def get_approved_apps(self) -> List[ApprovedApp]:
        return list(self.approved_apps.values())

    def launch_app(self, app_id: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        app_spec = self.approved_apps.get(app_id.lower().strip())
        if not app_spec:
            raise ValueError(
                f"Application '{app_id}' is not in the authorized applications allowlist."
            )

        new_pid = 20000 + len(self.launch_history)
        new_handle = 3000 + len(self.launch_history)

        record = {
            "app_id": app_spec.app_id,
            "display_name": app_spec.display_name,
            "pid": new_pid,
            "command": [app_spec.executable] + (args or []),
        }
        self.launch_history.append(record)

        self.windows[new_handle] = WindowInfo(
            handle=new_handle,
            title=f"{app_spec.display_name} - Active",
            process_id=new_pid,
            process_name=app_spec.executable,
            is_visible=True,
            is_minimized=False,
        )
        self.active_window_handle = new_handle
        return record

    def list_windows(self) -> List[WindowInfo]:
        return list(self.windows.values())

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the current active foreground window in mock environment."""
        if self.active_window_handle and self.active_window_handle in self.windows:
            return self.windows[self.active_window_handle]
        if self.windows:
            return next(iter(self.windows.values()))
        return WindowInfo(
            handle=1001,
            title="Desktop",
            process_id=1,
            process_name="explorer.exe",
            is_visible=True,
            is_minimized=False,
        )

    def is_window_valid(self, handle: int) -> bool:
        """Check if a window handle exists in mock open windows."""
        if getattr(self, "invalid_handles", None) and handle in self.invalid_handles:
            return False
        if handle in (99999999, -1, 0):
            return False
        if handle in self.windows or handle == self.active_window_handle:
            return True
        return True

    def focus_window(self, handle: int) -> bool:
        if handle not in self.windows:
            return False
        win = self.windows[handle]
        win.is_minimized = False
        self.active_window_handle = handle
        return True

    def restore_and_focus_window(
        self,
        handle: int,
        expected_pid: Optional[int] = None,
        timeout: float = 0.6,
    ) -> bool:
        if getattr(self, "prevent_focus", False):
            return False
        if handle not in self.windows:
            return False
        win = self.windows[handle]
        if expected_pid is not None and win.process_id != expected_pid:
            return False
        win.is_minimized = False
        self.active_window_handle = handle
        return True

    def minimize_window(self, handle: int) -> bool:
        if handle not in self.windows:
            return False
        win = self.windows[handle]
        win.is_minimized = True
        if self.active_window_handle == handle:
            self.active_window_handle = None
        return True

    def close_window(self, handle: int) -> bool:
        if handle not in self.windows:
            return False
        self.closed_windows.append(handle)
        del self.windows[handle]
        if self.active_window_handle == handle:
            self.active_window_handle = None
        return True

    def open_folder(self, folder_path: str) -> bool:
        self.opened_folders.append(folder_path)
        return True

    def find_controls(
        self,
        handle: int,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
    ) -> List[UIControlInfo]:
        if handle not in self.windows:
            return []
        window_ctrls = self.controls.get(handle, {})
        results: List[UIControlInfo] = []
        for ctrl in window_ctrls.values():
            if name and name.lower() not in ctrl.name.lower():
                continue
            if control_type and control_type.lower() != ctrl.control_type.lower():
                continue
            results.append(ctrl)
        return results

    def click_control(self, handle: int, control_id: str) -> bool:
        if handle not in self.windows:
            return False
        window_ctrls = self.controls.get(handle, {})
        if control_id not in window_ctrls:
            return False
        ctrl = window_ctrls[control_id]
        if not ctrl.is_enabled:
            return False
        self.ui_actions_history.append({
            "action": "click",
            "handle": handle,
            "control_id": control_id,
            "control_name": ctrl.name,
        })
        return True

    def set_control_text(self, handle: int, control_id: str, text: str) -> bool:
        if handle not in self.windows:
            return False
        window_ctrls = self.controls.get(handle, {})
        if control_id not in window_ctrls:
            return False
        ctrl = window_ctrls[control_id]
        if not ctrl.is_enabled or ctrl.control_type != "edit":
            return False
        ctrl.value = text
        self.ui_actions_history.append({
            "action": "set_text",
            "handle": handle,
            "control_id": control_id,
            "text": text,
        })
        return True

    def send_shortcut(
        self,
        handle: int,
        shortcut: str,
        expected_pid: Optional[int] = None,
    ) -> bool:
        normalized = shortcut.lower().strip()
        if normalized not in ALLOWED_KEYBOARD_SHORTCUTS:
            raise ValueError(f"Shortcut '{shortcut}' is not in the authorized keyboard shortcuts list.")

        from app.automation.platform_adapter import FocusMismatchError

        # Verify target can be restored and focused
        if not self.restore_and_focus_window(handle, expected_pid=expected_pid):
            raise FocusMismatchError(
                f"Target window {handle} could not be activated to foreground. Shortcut aborted to prevent input leakage."
            )

        self.ui_actions_history.append({
            "action": "send_shortcut",
            "handle": handle,
            "shortcut": normalized,
            "expected_pid": expected_pid,
        })
        return True

    def scroll_window(self, handle: int, direction: str, amount: int) -> bool:
        if handle not in self.windows:
            return False
        if direction not in ("up", "down"):
            raise ValueError("Direction must be either 'up' or 'down'.")
        self.ui_actions_history.append({
            "action": "scroll",
            "handle": handle,
            "direction": direction,
            "amount": amount,
        })
        return True

    def get_window_bounds(self, handle: int) -> Optional[Dict[str, int]]:
        if handle in self.windows:
            return {"left": 100, "top": 100, "width": 800, "height": 600}
        # Mock bounds for child controls
        return {"left": 120, "top": 150, "width": 100, "height": 30}

    def get_virtual_desktop_bounds(self) -> tuple[int, int, int, int]:
        return getattr(self, "virtual_desktop_bounds", (0, 0, 1920, 1080))

    def click_at(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_hwnd: Optional[int] = None,
        hover_ms: int = 40,
    ) -> bool:
        if target_hwnd is not None:
            self.restore_and_focus_window(target_hwnd)

        self.ui_actions_history.append({
            "action": "click_at",
            "x": x,
            "y": y,
            "button": button,
            "clicks": clicks,
            "target_hwnd": target_hwnd,
            "hover_ms": hover_ms,
        })
        return True

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
        if target_hwnd is not None:
            self.restore_and_focus_window(target_hwnd)
        self.ui_actions_history.append({
            "action": "type_text",
            "x": x,
            "y": y,
            "text": text,
            "target_hwnd": target_hwnd,
            "clear_first": clear_first,
            "press_enter": press_enter,
            "use_clipboard": use_clipboard,
        })
        if x is not None and y is not None:
            self.ui_actions_history.append({
                "action": "type_text_at",
                "x": x,
                "y": y,
                "text": text,
                "clear_first": clear_first,
                "press_enter": press_enter,
                "use_clipboard": use_clipboard,
            })
        return True

    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        clear_first: bool = False,
        press_enter: bool = False,
        use_clipboard: Optional[bool] = None,
    ) -> bool:
        self.ui_actions_history.append({
            "action": "type_text_at",
            "x": x,
            "y": y,
            "text": text,
            "clear_first": clear_first,
            "press_enter": press_enter,
            "use_clipboard": use_clipboard,
        })
        return self.type_text(
            text=text,
            x=x,
            y=y,
            clear_first=clear_first,
            press_enter=press_enter,
            use_clipboard=use_clipboard,
        )

    def scroll_at(self, x: int, y: int, direction: str = "down", amount: int = 3) -> bool:
        self.ui_actions_history.append({
            "action": "scroll_at",
            "x": x,
            "y": y,
            "direction": direction,
            "amount": amount,
        })
        return True


