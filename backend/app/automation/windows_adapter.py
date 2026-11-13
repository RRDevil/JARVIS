"""Windows Native Platform Adapter using ctypes and standard Windows APIs."""

import ctypes
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.automation.windows")

from app.automation.platform_adapter import (
    ApprovedApp,
    FocusMismatchError,
    PlatformAdapter,
    UIControlInfo,
    WindowInfo,
)
from ctypes import wintypes

# ctypes Win32 SendInput structures
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000

# Pre-approved application catalog
DEFAULT_APPROVED_APPS: Dict[str, ApprovedApp] = {
    "notepad": ApprovedApp(
        app_id="notepad",
        display_name="Notepad",
        executable="notepad.exe",
        description="Windows default text editor.",
    ),
    "calculator": ApprovedApp(
        app_id="calculator",
        display_name="Calculator",
        executable="calc.exe",
        description="Windows system calculator.",
    ),
    "vscode": ApprovedApp(
        app_id="vscode",
        display_name="Visual Studio Code",
        executable="code.cmd",
        description="Code editor and development environment.",
    ),
    "terminal": ApprovedApp(
        app_id="terminal",
        display_name="Windows Terminal",
        executable="wt.exe",
        description="Tabbed command-line terminal.",
    ),
    "explorer": ApprovedApp(
        app_id="explorer",
        display_name="File Explorer",
        executable="explorer.exe",
        description="Windows file manager.",
    ),
    "paint": ApprovedApp(
        app_id="paint",
        display_name="Paint",
        executable="mspaint.exe",
        description="Basic image editing tool.",
    ),
}

# Windows API constants
WM_CLOSE = 0x0010
WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
WM_VSCROLL = 0x0115
SB_LINEUP = 0
SB_LINEDOWN = 1
SW_MINIMIZE = 6
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Virtual key codes
VK_LBUTTON = 0x01
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
KEYEVENTF_KEYUP = 0x0002

ALLOWED_KEYBOARD_SHORTCUTS = {
    "ctrl+s", "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
    "ctrl+a", "ctrl+f", "ctrl+w", "enter", "escape", "tab",
    "backspace", "space", "arrow_up", "arrow_down", "arrow_left", "arrow_right",
}


def _set_clipboard_text(text: str) -> bool:
    """Safely populate Windows system clipboard with UTF-16 text."""
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    if not user32.OpenClipboard(0):
        return False
    try:
        user32.EmptyClipboard()
        encoded = text.encode("utf-16le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        return True
    except Exception:
        return False
    finally:
        user32.CloseClipboard()


class WindowsPlatformAdapter(PlatformAdapter):
    """Interacts with Windows 11 desktop via ctypes User32 / Kernel32 / Shell32 APIs."""

    def __init__(self, approved_apps: Optional[Dict[str, ApprovedApp]] = None):
        self.approved_apps = approved_apps or DEFAULT_APPROVED_APPS
        self._init_dpi_awareness()

    def _init_dpi_awareness(self) -> None:
        """Set modern Per-Monitor V2 DPI awareness for pixel-accurate desktop automation."""
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

    def get_virtual_desktop_bounds(self) -> tuple[int, int, int, int]:
        """Return (left, top, width, height) of the virtual desktop spanning all connected monitors."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        v_left = int(user32.GetSystemMetrics(76))
        v_top = int(user32.GetSystemMetrics(77))
        v_width = max(1, int(user32.GetSystemMetrics(78)))
        v_height = max(1, int(user32.GetSystemMetrics(79)))
        return (v_left, v_top, v_width, v_height)

    def _is_jarvis_window(self, hwnd: int) -> bool:
        """Determine if a window handle belongs to the JARVIS interface or system desktop shell."""
        if not hwnd or not ctypes.windll.user32.IsWindow(ctypes.c_void_p(hwnd)):
            return False
        user32 = ctypes.windll.user32
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), buff, length + 1)
            title = buff.value.strip().lower()

        if (
            "jarvis hud" in title
            or "j.a.r.v.i.s. desktop assistant" in title
            or title in ("jarvis", "j.a.r.v.i.s.")
        ):
            return True

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        if pid.value == os.getpid():
            return True
        return False

    def _ensure_interactive_desktop(self) -> None:
        """Attach calling thread to user's interactive 'Default' desktop if running in an isolated session."""
        try:
            self._init_dpi_awareness()
            user32 = ctypes.windll.user32
            hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

    def get_approved_apps(self) -> List[ApprovedApp]:
        return list(self.approved_apps.values())

    def find_running_process(self, executable: str) -> Optional[int]:
        """Check if a process matching the executable name is already running."""
        try:
            exe_name = Path(executable).name.lower()
            creation_flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
            output = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {exe_name}"],
                text=True,
                creationflags=creation_flags,
            )
            for line in output.splitlines():
                if exe_name in line.lower():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].isdigit():
                        return int(parts[1])
        except Exception:
            pass
        return None

    def find_app_window(self, app_id: str) -> Optional[WindowInfo]:
        """Find an existing open desktop window matching the approved application."""
        app_spec = self.approved_apps.get(app_id.lower().strip())
        if not app_spec:
            return None
        windows = self.list_windows()
        for w in windows:
            if (
                app_spec.executable.lower() in w.process_name.lower()
                or app_spec.display_name.lower() in w.title.lower()
                or app_id.lower() in w.title.lower()
            ):
                return w
        return None

    def launch_app(self, app_id: str, args: Optional[List[str]] = None) -> Dict[str, Any]:
        app_spec = self.approved_apps.get(app_id.lower().strip())
        if not app_spec:
            raise ValueError(
                f"Application '{app_id}' is not in the authorized applications allowlist."
            )

        # Single-window enforcement: Only reuse if an actual visible desktop window is currently open
        matching_win = self.find_app_window(app_id)
        if matching_win and not args:
            self.focus_window(matching_win.handle)
            return {
                "app_id": app_spec.app_id,
                "display_name": app_spec.display_name,
                "pid": matching_win.process_id,
                "command": [app_spec.executable],
                "already_running": True,
                "action": "focused_existing_window",
                "window_title": matching_win.title,
                "window_handle": matching_win.handle,
            }

        # If no visible window exists but a headless/zombie process is lingering (common in Windows 11 Notepad),
        # terminate the headless background instance so Windows can launch a clean interactive UI window
        if app_spec.app_id == "notepad":
            existing_pid = self.find_running_process(app_spec.executable)
            if existing_pid is not None:
                try:
                    creation_flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
                    subprocess.run(
                        ["taskkill", "/F", "/IM", app_spec.executable],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creation_flags,
                    )
                except Exception:
                    pass

        cmd = [app_spec.executable]
        if args:
            for arg in args:
                if any(bad in arg for bad in [";", "&", "|", "`", "$", "\n"]):
                    raise ValueError(f"Dangerous character in process argument: '{arg}'")
            cmd.extend(args)

        # On Windows 11, modern Notepad is a packaged WindowsApp.
        # Spawning via explorer shell:AppsFolder guarantees the interactive desktop window opens reliably.
        proc = None
        if app_spec.app_id == "notepad" and not args:
            try:
                proc = subprocess.Popen(
                    ["explorer.exe", r"shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"],
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                proc = None

        if proc is None:
            resolved_exe = shutil.which(app_spec.executable) or app_spec.executable
            proc = subprocess.Popen(
                cmd,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return {
            "app_id": app_spec.app_id,
            "display_name": app_spec.display_name,
            "pid": proc.pid,
            "command": cmd,
            "already_running": False,
            "action": "launched_new_instance",
        }

    def list_windows(self) -> List[WindowInfo]:
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        windows: List[WindowInfo] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_windows_callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True

            title_buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buf, length + 1)
            title = title_buf.value.strip()
            if not title:
                return True

            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            is_minimized = bool(user32.IsIconic(hwnd))

            process_name = "unknown"
            h_process = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if h_process:
                name_buf = ctypes.create_unicode_buffer(1024)
                name_size = ctypes.c_ulong(1024)
                if kernel32.QueryFullProcessImageNameW(
                    h_process, 0, name_buf, ctypes.byref(name_size)
                ):
                    process_name = Path(name_buf.value).name
                kernel32.CloseHandle(h_process)

            windows.append(
                WindowInfo(
                    handle=int(hwnd),
                    title=title,
                    process_id=int(pid.value),
                    process_name=process_name,
                    is_visible=True,
                    is_minimized=is_minimized,
                )
            )
            return True

        cb = WNDENUMPROC(enum_windows_callback)
        user32.EnumWindows(cb, 0)
        if not windows:
            # Fallback for background consoles, services, or test runners: enumerate interactive 'Default' desktop
            try:
                hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                if hdesk:
                    user32.EnumDesktopWindows(hdesk, cb, 0)
                    user32.CloseDesktop(hdesk)
            except Exception:
                pass
        return windows

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the current active foreground desktop window."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        from pathlib import Path

        fore_hwnd = user32.GetForegroundWindow()
        if not fore_hwnd:
            return None

        length = user32.GetWindowTextLengthW(ctypes.c_void_p(fore_hwnd))
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(ctypes.c_void_p(fore_hwnd), buff, length + 1)
            title = buff.value.strip()

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(fore_hwnd), ctypes.byref(pid))
        process_name = "Application"
        h_proc = kernel32.OpenProcess(0x1000 | 0x0400, False, pid.value)
        if h_proc:
            name_buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(512)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, name_buf, ctypes.byref(size)):
                process_name = Path(name_buf.value).name
            kernel32.CloseHandle(h_proc)

        return WindowInfo(
            handle=int(fore_hwnd),
            title=title,
            process_id=int(pid.value),
            process_name=process_name,
            is_visible=bool(user32.IsWindowVisible(ctypes.c_void_p(fore_hwnd))),
            is_minimized=bool(user32.IsIconic(ctypes.c_void_p(fore_hwnd))),
        )

    def is_window_valid(self, handle: int) -> bool:
        """Check if a window handle represents an active, valid desktop window."""
        self._ensure_interactive_desktop()
        return bool(ctypes.windll.user32.IsWindow(ctypes.c_void_p(handle)))

    def focus_window(self, handle: int) -> bool:
        """Bring target window to foreground."""
        return self.restore_and_focus_window(handle)

    def restore_and_focus_window(
        self,
        handle: int,
        expected_pid: Optional[int] = None,
        timeout: float = 0.6,
    ) -> bool:
        """Restore window if minimized, bring to foreground, and verify focus."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = ctypes.c_void_p(handle)

        if not user32.IsWindow(hwnd):
            return False

        if expected_pid is not None:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != expected_pid:
                return False

        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOP = ctypes.c_void_p(0)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        # 1. Restore if minimized, or show
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SendMessageW(hwnd, 0x0112, 0xF120, 0)  # WM_SYSCOMMAND, SC_RESTORE
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        # 2. Allow foreground activation to bypass Windows OS restrictions
        try:
            user32.AllowSetForegroundWindow(ctypes.c_ulong(0xFFFFFFFF))  # ASFW_ANY
        except Exception:
            pass

        # 3. Attach thread input to reliably switch foreground window
        cur_thread_id = kernel32.GetCurrentThreadId()
        fore_hwnd = user32.GetForegroundWindow()
        fore_thread_id = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
        target_thread_id = user32.GetWindowThreadProcessId(hwnd, None)

        try:
            if fore_thread_id and cur_thread_id and fore_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, fore_thread_id, True)
            if target_thread_id and cur_thread_id and target_thread_id != cur_thread_id:
                user32.AttachThreadInput(cur_thread_id, target_thread_id, True)

            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetFocus(hwnd)
            user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        finally:
            if fore_thread_id and cur_thread_id and fore_thread_id != cur_thread_id:
                try:
                    user32.AttachThreadInput(cur_thread_id, fore_thread_id, False)
                except Exception:
                    pass
            if target_thread_id and cur_thread_id and target_thread_id != cur_thread_id:
                try:
                    user32.AttachThreadInput(cur_thread_id, target_thread_id, False)
                except Exception:
                    pass

        # 4. Verification loop: poll GetForegroundWindow to confirm target window is actually foreground
        import time
        start = time.perf_counter()
        while (time.perf_counter() - start) < timeout:
            current_fore = user32.GetForegroundWindow()
            if current_fore == handle:
                return True
            if expected_pid is not None:
                cur_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(current_fore, ctypes.byref(cur_pid))
                if cur_pid.value == expected_pid:
                    return True
            # If JARVIS is still foreground, retry bringing target window to front
            if self._is_jarvis_window(current_fore):
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            time.sleep(0.025)

        # Final check
        current_fore = user32.GetForegroundWindow()
        if current_fore == handle:
            return True
        if expected_pid is not None:
            cur_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(current_fore, ctypes.byref(cur_pid))
            if cur_pid.value == expected_pid:
                return True

        return False

    def minimize_window(self, handle: int) -> bool:
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            return False

        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return True

    def close_window(self, handle: int) -> bool:
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            return False

        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return True

    def open_folder(self, folder_path: str) -> bool:
        resolved = Path(folder_path).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise FileNotFoundError(f"Directory not found: '{folder_path}'")

        subprocess.Popen(
            ["explorer.exe", str(resolved)],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True

    def find_controls(
        self,
        handle: int,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
    ) -> List[UIControlInfo]:
        """Find accessible controls inside a window using EnumChildWindows."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            return []

        controls: List[UIControlInfo] = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_child_callback(child_hwnd, lparam):
            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child_hwnd, class_buf, 256)
            class_name = class_buf.value.lower()

            length = user32.GetWindowTextLengthW(child_hwnd)
            text_val = ""
            if length > 0:
                text_buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child_hwnd, text_buf, length + 1)
                text_val = text_buf.value

            is_enabled = bool(user32.IsWindowEnabled(child_hwnd))

            # Normalize control type
            ctype = "pane"
            if "button" in class_name:
                ctype = "button"
            elif "edit" in class_name:
                ctype = "edit"
            elif "static" in class_name:
                ctype = "text"
            elif "combobox" in class_name:
                ctype = "combobox"
            elif "listbox" in class_name:
                ctype = "listbox"

            # Apply filters
            if name and name.lower() not in text_val.lower():
                return True
            if control_type and control_type.lower() != ctype:
                return True

            controls.append(
                UIControlInfo(
                    control_id=str(int(child_hwnd)),
                    name=text_val or class_buf.value,
                    control_type=ctype,
                    is_enabled=is_enabled,
                    value=text_val if ctype == "edit" else None,
                )
            )
            return True

        cb = WNDENUMPROC(enum_child_callback)
        user32.EnumChildWindows(hwnd, cb, 0)
        return controls

    def click_control(self, handle: int, control_id: str) -> bool:
        user32 = ctypes.windll.user32
        try:
            child_handle = int(control_id)
        except ValueError:
            return False

        child_hwnd = ctypes.c_void_p(child_handle)
        if not user32.IsWindow(child_hwnd):
            return False

        user32.SendMessageW(child_hwnd, BM_CLICK, 0, 0)
        return True

    def set_control_text(self, handle: int, control_id: str, text: str) -> bool:
        user32 = ctypes.windll.user32
        try:
            child_handle = int(control_id)
        except ValueError:
            return False

        child_hwnd = ctypes.c_void_p(child_handle)
        if not user32.IsWindow(child_hwnd):
            return False

        user32.SendMessageW(child_hwnd, WM_SETTEXT, 0, text)
        return True

    def send_shortcut(
        self,
        handle: int,
        shortcut: str,
        expected_pid: Optional[int] = None,
    ) -> bool:
        normalized = shortcut.lower().strip()
        if normalized not in ALLOWED_KEYBOARD_SHORTCUTS:
            raise ValueError(
                f"Shortcut '{shortcut}' is not in the authorized keyboard shortcuts list."
            )

        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            raise FocusMismatchError(
                f"Target window handle {handle} is invalid or no longer exists. Shortcut aborted."
            )

        # 1. Restore target application and bring to foreground
        activated = self.restore_and_focus_window(handle, expected_pid=expected_pid)

        # 2. STRICT FOCUS SAFEGUARD: verify foreground window is target application, NOT JARVIS
        current_fore = user32.GetForegroundWindow()
        if not activated or self._is_jarvis_window(current_fore):
            raise FocusMismatchError(
                f"Target window {handle} could not be activated to foreground. "
                "Keyboard shortcut aborted to prevent input leakage into J.A.R.V.I.S."
            )

        if expected_pid is not None:
            cur_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(current_fore, ctypes.byref(cur_pid))
            if cur_pid.value != expected_pid:
                raise FocusMismatchError(
                    f"Foreground window PID ({cur_pid.value}) does not match expected target PID ({expected_pid}). "
                    "Keyboard shortcut aborted to prevent cross-application input leakage."
                )

        # 3. Dispatch key sequence
        parts = normalized.split("+")
        modifiers: List[int] = []
        main_key: int = 0

        for part in parts:
            if part == "ctrl":
                modifiers.append(VK_CONTROL)
            elif part == "shift":
                modifiers.append(VK_SHIFT)
            elif part == "alt":
                modifiers.append(VK_MENU)
            elif part == "enter":
                main_key = VK_RETURN
            elif part == "escape":
                main_key = VK_ESCAPE
            elif part == "tab":
                main_key = VK_TAB
            elif part == "backspace":
                main_key = VK_BACK
            elif part == "space":
                main_key = VK_SPACE
            elif part == "arrow_up":
                main_key = VK_UP
            elif part == "arrow_down":
                main_key = VK_DOWN
            elif part == "arrow_left":
                main_key = VK_LEFT
            elif part == "arrow_right":
                main_key = VK_RIGHT
            elif len(part) == 1:
                main_key = ord(part.upper())

        # Press modifiers
        for mod in modifiers:
            user32.keybd_event(mod, 0, 0, 0)

        # Press and release main key
        if main_key:
            user32.keybd_event(main_key, 0, 0, 0)
            user32.keybd_event(main_key, 0, KEYEVENTF_KEYUP, 0)

        # Release modifiers in reverse order
        for mod in reversed(modifiers):
            user32.keybd_event(mod, 0, KEYEVENTF_KEYUP, 0)

        return True

    def scroll_window(self, handle: int, direction: str, amount: int) -> bool:
        if direction not in ("up", "down"):
            raise ValueError("Direction must be either 'up' or 'down'.")

        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            return False

        cmd = SB_LINEUP if direction == "up" else SB_LINEDOWN
        for _ in range(max(1, amount)):
            user32.SendMessageW(hwnd, WM_VSCROLL, cmd, 0)
        return True

    def get_window_bounds(self, handle: int) -> Optional[Dict[str, int]]:
        """Retrieve bounding rectangle {left, top, width, height} of target window."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd):
            return None

        from ctypes import wintypes
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return {
                "left": int(rect.left),
                "top": int(rect.top),
                "width": max(0, int(rect.right - rect.left)),
                "height": max(0, int(rect.bottom - rect.top)),
            }
        return None

    def click_at(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        target_hwnd: Optional[int] = None,
        hover_ms: int = 40,
    ) -> bool:
        """Position cursor at (x, y) and perform mouse clicks using native SendInput."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        import time
        from ctypes import wintypes

        # 1. Validate coordinates across virtual desktop spanning all monitors
        v_left, v_top, v_width, v_height = self.get_virtual_desktop_bounds()
        if not (v_left <= int(x) < v_left + v_width and v_top <= int(y) < v_top + v_height):
            logger.error(f"Click coordinates ({x}, {y}) lie outside virtual desktop boundaries [{v_left}, {v_top}, {v_width}x{v_height}].")
            return False

        # 2. If target window is specified, restore and focus it first.
        # If target_hwnd is None, attempt to resolve the top-level application window directly at (x, y).
        if target_hwnd is None:
            try:
                pt = wintypes.POINT(int(x), int(y))
                hwnd_at_pt = user32.WindowFromPoint(pt)
                if hwnd_at_pt:
                    root_hwnd = user32.GetAncestor(hwnd_at_pt, 2)  # GA_ROOT
                    if root_hwnd and not self._is_jarvis_window(root_hwnd):
                        target_hwnd = root_hwnd
            except Exception:
                pass

        if target_hwnd is not None and not self._is_jarvis_window(target_hwnd):
            self.restore_and_focus_window(target_hwnd)
            time.sleep(0.04)

        # 3. Normalize coordinates for SendInput MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        norm_x = int(((int(x) - v_left) * 65535) / max(1, v_width - 1))
        norm_y = int(((int(y) - v_top) * 65535) / max(1, v_height - 1))

        # 4. Visible physical cursor placement: SetCursorPos + SendInput absolute movement
        user32.SetCursorPos(int(x), int(y))

        move_input = INPUT()
        move_input.type = INPUT_MOUSE
        move_input.union.mi.dx = norm_x
        move_input.union.mi.dy = norm_y
        move_input.union.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        user32.SendInput(1, ctypes.byref(move_input), ctypes.sizeof(INPUT))

        # Verify cursor position
        cur_pt = wintypes.POINT()
        if user32.GetCursorPos(ctypes.byref(cur_pt)):
            if abs(cur_pt.x - int(x)) > 20 or abs(cur_pt.y - int(y)) > 20:
                logger.warning(f"Cursor verification discrepancy: requested ({x}, {y}), actual ({cur_pt.x}, {cur_pt.y}).")

        # Allow OS hit-testing and button hover state to settle
        settle_delay = max(0.02, hover_ms / 1000.0)
        time.sleep(settle_delay)

        # 5. Dispatch discrete mouse down and up events via SendInput
        down_flag = MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_LEFTDOWN
        up_flag = MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_LEFTUP

        for i in range(max(1, clicks)):
            btn_down = INPUT()
            btn_down.type = INPUT_MOUSE
            btn_down.union.mi.dx = norm_x
            btn_down.union.mi.dy = norm_y
            btn_down.union.mi.dwFlags = down_flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

            btn_up = INPUT()
            btn_up.type = INPUT_MOUSE
            btn_up.union.mi.dx = norm_x
            btn_up.union.mi.dy = norm_y
            btn_up.union.mi.dwFlags = up_flag | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK

            res_down = user32.SendInput(1, ctypes.byref(btn_down), ctypes.sizeof(INPUT))
            # Dual-dispatch via mouse_event for guaranteed compatibility across legacy, Tkinter, and Chromium apps
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.03)  # Realistic physical hold duration (30ms)

            res_up = user32.SendInput(1, ctypes.byref(btn_up), ctypes.sizeof(INPUT))
            user32.mouse_event(up_flag, 0, 0, 0, 0)

            if res_down != 1 or res_up != 1:
                logger.warning(f"SendInput dispatch returned unexpected result (down={res_down}, up={res_up}).")

            if i < clicks - 1:
                time.sleep(0.06)

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
        """Focus target window/coordinates and enter text, supporting both Unicode typing and clipboard paste."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        import time

        # 1. Activate target application window if specified
        if target_hwnd is not None and not self._is_jarvis_window(target_hwnd):
            self.restore_and_focus_window(target_hwnd)

        # 2. If coordinates are provided, click to establish keyboard/caret focus
        if x is not None and y is not None:
            self.click_at(x, y, button="left", clicks=1, target_hwnd=target_hwnd)
            time.sleep(0.08)
        elif target_hwnd is not None:
            # If coordinates not given but window is known, click inside window client area to establish focus
            bounds = self.get_window_bounds(target_hwnd)
            if bounds and bounds["width"] > 20 and bounds["height"] > 20:
                cx = bounds["left"] + bounds["width"] // 2
                cy = bounds["top"] + bounds["height"] // 2
                self.click_at(cx, cy, button="left", clicks=1, target_hwnd=target_hwnd)
                time.sleep(0.08)

        # 3. Optionally select all and clear existing contents
        if clear_first:
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(ord("A"), 0, 0, 0)
            user32.keybd_event(ord("A"), 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.02)
            user32.keybd_event(VK_BACK, 0, 0, 0)
            user32.keybd_event(VK_BACK, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.05)

        if not text:
            if press_enter:
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            return True

        # 4. Determine dispatch strategy: Clipboard paste vs SendInput keystrokes
        should_use_clipboard = use_clipboard
        if should_use_clipboard is None:
            should_use_clipboard = ("\n" in text or len(text) > 60)

        if should_use_clipboard:
            ok = _set_clipboard_text(text)
            if ok:
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(ord("V"), 0, 0, 0)
                user32.keybd_event(ord("V"), 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                time.sleep(0.05)
            else:
                should_use_clipboard = False  # fallback to SendInput below

        if not should_use_clipboard:
            # Unicode character injection via SendInput
            KEYEVENTF_UNICODE = 0x0004
            for char in text:
                input_down = INPUT()
                input_down.type = INPUT_KEYBOARD
                input_down.union.ki.wVk = 0
                input_down.union.ki.wScan = ord(char)
                input_down.union.ki.dwFlags = KEYEVENTF_UNICODE
                input_down.union.ki.time = 0
                input_down.union.ki.dwExtraInfo = 0

                input_up = INPUT()
                input_up.type = INPUT_KEYBOARD
                input_up.union.ki.wVk = 0
                input_up.union.ki.wScan = ord(char)
                input_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
                input_up.union.ki.time = 0
                input_up.union.ki.dwExtraInfo = 0

                inputs = (INPUT * 2)(input_down, input_up)
                user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
                time.sleep(0.005)

        # 5. Optionally press enter
        if press_enter:
            time.sleep(0.03)
            user32.keybd_event(VK_RETURN, 0, 0, 0)
            user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

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
        """Focus coordinates (x, y) and enter text via native keyboard input."""
        return self.type_text(
            text=text,
            x=x,
            y=y,
            clear_first=clear_first,
            press_enter=press_enter,
            use_clipboard=use_clipboard,
        )

    def scroll_at(self, x: int, y: int, direction: str = "down", amount: int = 3) -> bool:
        """Position cursor at (x, y) and perform mouse wheel scrolling."""
        self._ensure_interactive_desktop()
        user32 = ctypes.windll.user32
        import time

        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.02)

        MOUSEEVENTF_WHEEL = 0x0800
        WHEEL_DELTA = 120

        delta = -WHEEL_DELTA if direction == "down" else WHEEL_DELTA
        total_delta = delta * max(1, amount)

        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, total_delta, 0)
        return True


