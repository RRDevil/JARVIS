"""JARVIS Native Windows 11 Desktop Shell & Agent Host.

Provides:
1. Native frameless, transparent WebView2 window.
2. Compact floating holographic orb + expanded glass HUD.
3. Windows Taskbar System Tray icon with control menu.
4. Global system hotkey (Alt + Space) to summon/hide anywhere on desktop.
5. Single-instance mutex lock and unified FastAPI backend management.
"""

import ctypes
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

# Setup import path for backend
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Auto-permit media streams (microphone) in WebView2 without UI permission blocks
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
    + " --use-fake-ui-for-media-stream"
).strip()

import pystray
import webview
from PIL import Image, ImageDraw

# Windows API Constants
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_USER = 0x0400
WM_UPDATE_HOTKEYS = WM_USER + 101

VK_SPACE = 0x20
VK_F20 = 0x83       # Laptop dedicated Microphone Mute / Enable key (Asus, Lenovo, HP, etc.)
VK_SCROLL = 0x91    # Scroll Lock (Obsolete Windows key)
VK_PAUSE = 0x13     # Pause / Break (Obsolete Windows key)
VK_M = 0x4D         # 'M' key
VK_Y = 0x59         # 'Y' key (Approve)
VK_N = 0x4E         # 'N' key (Deny)

HOTKEY_ID_ALT_SPACE = 9001
HOTKEY_ID_CTRL_SHIFT_J = 9002
HOTKEY_ID_MIC_F20 = 9003
HOTKEY_ID_MIC_SCROLL = 9004
HOTKEY_ID_MIC_PAUSE = 9005
HOTKEY_ID_MIC_ALT_M = 9006
HOTKEY_ID_USER_MIC = 9010
HOTKEY_ID_USER_HUD = 9011
HOTKEY_ID_USER_INSPECT = 9012
HOTKEY_ID_APPROVE = 9020
HOTKEY_ID_DENY = 9021
ERROR_ALREADY_EXISTS = 183


def parse_hotkey_string(combo_str: str) -> Optional[tuple[int, int]]:
    """Convert human-readable shortcut string (e.g. 'Ctrl+Space') to Windows (fsModifiers, vkCode)."""
    if not combo_str:
        return None

    parts = [p.strip().lower() for p in combo_str.split("+") if p.strip()]
    if not parts:
        return None

    mods = MOD_NOREPEAT
    if "ctrl" in parts or "control" in parts:
        mods |= MOD_CONTROL
    if "alt" in parts:
        mods |= MOD_ALT
    if "shift" in parts:
        mods |= MOD_SHIFT
    if "win" in parts or "meta" in parts:
        mods |= MOD_WIN

    main_parts = [p for p in parts if p not in ("ctrl", "control", "alt", "shift", "win", "meta")]
    if not main_parts:
        return None

    key = main_parts[0]
    # Never register Escape globally to protect Windows OS shortcuts
    if key in ("esc", "escape"):
        return None

    if key == "space":
        vk = VK_SPACE
    elif key in ("scrolllock", "scroll_lock", "scroll"):
        vk = VK_SCROLL
    elif key in ("pause", "break"):
        vk = VK_PAUSE
    elif key.startswith("f") and key[1:].isdigit():
        f_num = int(key[1:])
        if 1 <= f_num <= 24:
            vk = 0x70 + (f_num - 1)
        else:
            return None
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    else:
        return None

    return mods, vk


class SingleInstanceLock:
    """Enforces a single running JARVIS process via a Windows named mutex."""

    def __init__(self, mutex_name: str = "Global\\JARVIS_Desktop_Assistant_Singleton_Mutex"):
        self.mutex_name = mutex_name
        self.handle = None

    def acquire(self) -> bool:
        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateMutexW(None, True, self.mutex_name)
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        return True

    def release(self):
        if self.handle:
            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def get_desktop_work_area():
    """Returns (x, y, width, height) of the Windows primary desktop work area (excluding taskbar)."""
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]
    rect = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    return rect.left, rect.top, w, h


class JSApi:
    """Python bridge exposed to frontend JavaScript via window.pywebview.api.
    
    IMPORTANT: All internal state variables MUST start with a leading underscore
    (e.g., _window, _current_mode) so pywebview's JS bridge does NOT reflect into
    native WinForms COM properties which triggers recursion and thread violations.
    """

    def __init__(self, app=None):
        self._window: Optional[webview.Window] = None
        self._current_mode = "compact"
        self._app = app

    def bind_window(self, win: webview.Window):
        self._window = win

    def bind_app(self, app):
        self._app = app

    def exit_app(self):
        """Cleanly terminate the application and all services."""
        if self._app:
            self._app.exit_app()
        else:
            os._exit(0)

    def update_hotkeys(self, keybinds: dict):
        """Update native Windows global hotkeys from frontend configuration."""
        if self._app:
            self._app.update_hotkeys(keybinds)

    def set_mode(self, mode: str):
        self._current_mode = mode
        if not self._window:
            return
        try:
            x, y, w, h = get_desktop_work_area()
            margin = 20

            if mode == "compact":
                cw, ch = 240, 120
                tx = x + w - cw - margin
                ty = y + h - ch - margin
                self._window.resize(cw, ch)
                self._window.move(tx, ty)
            elif mode == "quick_input":
                qw = 500
                top_padding = 16
                qy = y + top_padding
                qh = h - margin - top_padding
                qx = x + w - qw - margin
                self._window.resize(qw, qh)
                self._window.move(qx, qy)
            elif mode == "expanded":
                ew, eh = 460, min(680, h - 40)
                ex = x + w - ew - margin
                ey = y + h - eh - margin
                self._window.resize(ew, eh)
                self._window.move(ex, ey)
            elif mode == "dashboard":
                # Fullscreen work area covering the entire screen above taskbar
                self._window.move(x, y)
                self._window.resize(w, h)
        except Exception as e:
            print(f"[!] Error adjusting native window for mode {mode}: {e}")

    def hide_window(self):
        if self._window:
            self._window.hide()

    def show_window(self):
        if self._window:
            self._window.show()


def create_arc_reactor_icon() -> Image.Image:
    """Generate programmatic 64x64 Arc Reactor icon for Windows System Tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer glow ring
    draw.ellipse([4, 4, 60, 60], outline=(0, 229, 255, 120), width=2)
    # Primary cyan ring
    draw.ellipse([10, 10, 54, 54], outline=(0, 229, 255, 255), width=3)
    # Inner energy core
    draw.ellipse([22, 22, 42, 42], fill=(0, 229, 255, 220), outline=(255, 255, 255, 255), width=2)
    # Center white hot spot
    draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255, 255))
    return img


def check_backend_health(url: str = "http://127.0.0.1:8000/api/health", timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Native-Shell"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_backend_thread():
    """Run FastAPI Uvicorn backend in background thread if not already running."""
    if check_backend_health():
        print("[*] Backend is already running on 127.0.0.1:8000.")
        return

    import uvicorn
    from app.core.config import settings
    from app.main import app

    def _run():
        config = uvicorn.Config(
            app=app,
            host=settings.JARVIS_HOST,
            port=settings.JARVIS_PORT,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.run()

    thread = threading.Thread(target=_run, daemon=True, name="JARVIS-Backend-Thread")
    thread.start()

    # Wait for backend to report healthy
    for _ in range(30):
        if check_backend_health():
            print("[+] Backend initialized and operational on http://127.0.0.1:8000.")
            return
        time.sleep(0.5)

    print("[-] Warning: Backend did not report operational within timeout.")


class DesktopApplication:
    """Coordinates window, system tray, hotkeys, and application lifecycle."""

    def __init__(self):
        self.js_api = JSApi(app=self)
        self.window: Optional[webview.Window] = None
        self.tray_icon: Optional[pystray.Icon] = None
        self.is_visible = True
        self.should_exit = False
        self.lock = SingleInstanceLock()
        self.hotkey_thread_id: Optional[int] = None
        self.pending_keybinds: Optional[dict] = None

    def update_hotkeys(self, keybinds: dict):
        """Thread-safe request to re-register hotkeys on the hotkey listener thread."""
        self.pending_keybinds = keybinds
        if self.hotkey_thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.hotkey_thread_id, WM_UPDATE_HOTKEYS, 0, 0)

    def toggle_window(self):
        """Toggle HUD window visibility (summon/dismiss)."""
        if not self.window:
            return
        if self.is_visible:
            self.window.hide()
            self.is_visible = False
        else:
            self.window.show()
            self.window.restore()
            self.is_visible = True

    def toggle_mode(self):
        """Switch between compact orb and full dashboard HUD."""
        new_mode = "dashboard" if self.js_api._current_mode == "compact" else "compact"
        self.js_api.set_mode(new_mode)
        if self.window:
            try:
                self.window.evaluate_js(
                    f"window.dispatchEvent(new CustomEvent('jarvis:set_mode', {{ detail: '{new_mode}' }}))"
                )
            except Exception:
                pass

    def run_hotkey_listener(self):
        """Background thread registering Windows system hotkeys and pumping messages."""
        user32 = ctypes.windll.user32
        self.hotkey_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        # Register Alt + Space (0x0001 = MOD_ALT, 0x20 = VK_SPACE)
        registered_alt_space = bool(user32.RegisterHotKey(0, HOTKEY_ID_ALT_SPACE, MOD_ALT | MOD_NOREPEAT, VK_SPACE))
        # Register fallback Ctrl + Shift + J (0x0006 = MOD_CONTROL | MOD_SHIFT, 0x4A = 'J')
        registered_ctrl_shift_j = bool(user32.RegisterHotKey(0, HOTKEY_ID_CTRL_SHIFT_J, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, 0x4A))

        # Register Hardware Push-to-Talk Hotkeys:
        # 1. Laptop dedicated Mic Mute/Enable key (0x83 = VK_F20 on Asus, Lenovo, HP laptops)
        # 2. Scroll Lock (0x91 = VK_SCROLL, classic obsolete single keypress)
        # 3. Pause / Break (0x13 = VK_PAUSE, obsolete single keypress)
        # 4. Alt + M (0x4D = 'M', universal keyboard shortcut)
        registered_f20 = bool(user32.RegisterHotKey(0, HOTKEY_ID_MIC_F20, MOD_NOREPEAT, VK_F20))
        registered_scroll = bool(user32.RegisterHotKey(0, HOTKEY_ID_MIC_SCROLL, MOD_NOREPEAT, VK_SCROLL))
        registered_pause = bool(user32.RegisterHotKey(0, HOTKEY_ID_MIC_PAUSE, MOD_NOREPEAT, VK_PAUSE))
        registered_alt_m = bool(user32.RegisterHotKey(0, HOTKEY_ID_MIC_ALT_M, MOD_ALT | MOD_NOREPEAT, VK_M))

        # Register Global Approval / Denial Hotkeys (Ctrl + Alt + Y / Ctrl + Alt + N)
        registered_approve = bool(user32.RegisterHotKey(0, HOTKEY_ID_APPROVE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_Y))
        registered_deny = bool(user32.RegisterHotKey(0, HOTKEY_ID_DENY, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_N))

        if registered_alt_space:
            print("[+] Global hotkey [Alt + Space] registered.")
        elif registered_ctrl_shift_j:
            print("[+] Global hotkey [Ctrl + Shift + J] registered (Alt+Space in use).")
        else:
            print("[!] Warning: Unable to register global system hotkeys.")

        if registered_approve and registered_deny:
            print("[+] Global approval hotkeys [Ctrl + Alt + Y] (Approve) and [Ctrl + Alt + N] (Deny) registered.")

        active_ptt_keys = []
        if registered_scroll:
            active_ptt_keys.append("Scroll Lock")
        if registered_alt_m:
            active_ptt_keys.append("Alt + M")
        if registered_pause:
            active_ptt_keys.append("Pause/Break")
        if registered_f20:
            active_ptt_keys.append("Laptop Mic Key (F20)")

        if active_ptt_keys:
            print(f"[+] Microphone Push-to-Talk hotkeys active: {', '.join(active_ptt_keys)}")

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_void_p),
                ("lParam", ctypes.c_void_p),
                ("time", ctypes.c_ulong),
                ("pt", ctypes.c_ulong * 2),
            ]

        msg = MSG()
        while not self.should_exit:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break

            if msg.message == WM_UPDATE_HOTKEYS:
                # Dynamic hotkey re-registration from frontend configuration
                keybinds = self.pending_keybinds or {}
                for hid in (HOTKEY_ID_USER_MIC, HOTKEY_ID_USER_HUD, HOTKEY_ID_USER_INSPECT):
                    user32.UnregisterHotKey(0, hid)

                mic_str = keybinds.get("toggleMic")
                if mic_str:
                    parsed = parse_hotkey_string(mic_str)
                    if parsed:
                        user32.RegisterHotKey(0, HOTKEY_ID_USER_MIC, parsed[0], parsed[1])

                hud_str = keybinds.get("toggleHud")
                if hud_str:
                    parsed = parse_hotkey_string(hud_str)
                    if parsed:
                        user32.RegisterHotKey(0, HOTKEY_ID_USER_HUD, parsed[0], parsed[1])

                screen_str = keybinds.get("inspectScreen")
                if screen_str:
                    parsed = parse_hotkey_string(screen_str)
                    if parsed:
                        user32.RegisterHotKey(0, HOTKEY_ID_USER_INSPECT, parsed[0], parsed[1])

            elif msg.message == WM_HOTKEY:
                hotkey_id = int(msg.wParam)
                if hotkey_id in (HOTKEY_ID_ALT_SPACE, HOTKEY_ID_CTRL_SHIFT_J, HOTKEY_ID_USER_HUD):
                    self.toggle_window()
                elif hotkey_id in (
                    HOTKEY_ID_MIC_F20,
                    HOTKEY_ID_MIC_SCROLL,
                    HOTKEY_ID_MIC_PAUSE,
                    HOTKEY_ID_MIC_ALT_M,
                    HOTKEY_ID_USER_MIC,
                ):
                    # Ensure window is visible
                    if not self.is_visible and self.window:
                        self.window.show()
                        self.window.restore()
                        self.is_visible = True
                    # Notify frontend to toggle voice push-to-talk
                    if self.window:
                        try:
                            self.window.evaluate_js(
                                "window.dispatchEvent(new CustomEvent('jarvis:toggle_mic'))"
                            )
                        except Exception as e:
                            print(f"[!] Error notifying frontend of mic toggle: {e}")
                elif hotkey_id == HOTKEY_ID_USER_INSPECT:
                    if not self.is_visible and self.window:
                        self.window.show()
                        self.window.restore()
                        self.is_visible = True
                    if self.window:
                        try:
                            self.window.evaluate_js(
                                "window.dispatchEvent(new CustomEvent('jarvis:inspect_screen'))"
                            )
                        except Exception as e:
                            print(f"[!] Error notifying frontend of inspect screen: {e}")
                elif hotkey_id == HOTKEY_ID_APPROVE:
                    def _approve_active():
                        try:
                            req = urllib.request.Request(
                                "http://127.0.0.1:8000/api/v1/approvals/active/respond",
                                data=b'{"approved": true}',
                                headers={"Content-Type": "application/json", "User-Agent": "JARVIS-Native-Shell"},
                                method="POST",
                            )
                            with urllib.request.urlopen(req, timeout=2.0) as resp:
                                pass
                        except Exception as e:
                            print(f"[!] Error approving active request: {e}")
                        if self.window:
                            try:
                                self.window.evaluate_js(
                                    "window.dispatchEvent(new CustomEvent('jarvis:hotkey_decision', { detail: { approved: true } }))"
                                )
                            except Exception:
                                pass
                    threading.Thread(target=_approve_active, daemon=True).start()
                elif hotkey_id == HOTKEY_ID_DENY:
                    def _deny_active():
                        try:
                            req = urllib.request.Request(
                                "http://127.0.0.1:8000/api/v1/approvals/active/respond",
                                data=b'{"approved": false}',
                                headers={"Content-Type": "application/json", "User-Agent": "JARVIS-Native-Shell"},
                                method="POST",
                            )
                            with urllib.request.urlopen(req, timeout=2.0) as resp:
                                pass
                        except Exception as e:
                            print(f"[!] Error declining active request: {e}")
                        if self.window:
                            try:
                                self.window.evaluate_js(
                                    "window.dispatchEvent(new CustomEvent('jarvis:hotkey_decision', { detail: { approved: false } }))"
                                )
                            except Exception:
                                pass
                    threading.Thread(target=_deny_active, daemon=True).start()

        # Cleanup all registered hotkeys on thread exit
        for hid in (
            HOTKEY_ID_ALT_SPACE,
            HOTKEY_ID_CTRL_SHIFT_J,
            HOTKEY_ID_MIC_F20,
            HOTKEY_ID_MIC_SCROLL,
            HOTKEY_ID_MIC_PAUSE,
            HOTKEY_ID_MIC_ALT_M,
            HOTKEY_ID_USER_MIC,
            HOTKEY_ID_USER_HUD,
            HOTKEY_ID_USER_INSPECT,
            HOTKEY_ID_APPROVE,
            HOTKEY_ID_DENY,
        ):
            user32.UnregisterHotKey(0, hid)

    def run_tray(self):
        """Initialize and run the Windows Taskbar System Tray icon."""
        icon_img = create_arc_reactor_icon()

        def on_toggle_clicked(icon, item):
            self.toggle_window()

        def on_expand_clicked(icon, item):
            self.toggle_mode()

        def on_docs_clicked(icon, item):
            webbrowser.open("http://127.0.0.1:8000/docs")

        def on_exit_clicked(icon, item):
            self.exit_app()

        menu = pystray.Menu(
            pystray.MenuItem("Toggle JARVIS (Alt+Space)", on_toggle_clicked, default=True),
            pystray.MenuItem("Expand / Compact", on_expand_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open API Docs", on_docs_clicked),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit J.A.R.V.I.S.", on_exit_clicked),
        )

        self.tray_icon = pystray.Icon(
            name="JARVIS",
            icon=icon_img,
            title="J.A.R.V.I.S. Desktop Assistant (Alt+Space)",
            menu=menu,
        )
        self.tray_icon.run()

    def exit_app(self):
        """Clean teardown of all desktop components."""
        print("\n[*] Exiting JARVIS Native Desktop Shell...")
        self.should_exit = True
        if self.tray_icon:
            self.tray_icon.stop()
        if self.window:
            self.window.destroy()
        self.lock.release()
        os._exit(0)

    def start(self):
        # 1. Acquire single-instance mutex
        if not self.lock.acquire():
            print("[!] JARVIS is already running. Only one desktop instance permitted.")
            # Bring existing window to focus if possible
            sys.exit(0)

        # 2. Start FastAPI Backend
        start_backend_thread()

        # 3. Start Global Hotkey Listener
        hotkey_thread = threading.Thread(
            target=self.run_hotkey_listener,
            daemon=True,
            name="JARVIS-Hotkey-Thread",
        )
        hotkey_thread.start()

        # 4. Start System Tray Icon
        tray_thread = threading.Thread(
            target=self.run_tray,
            daemon=True,
            name="JARVIS-Tray-Thread",
        )
        tray_thread.start()

        # 5. Create Native Frameless Transparent Window
        dev_mode = "--dev" in sys.argv
        app_url = "http://127.0.0.1:5173" if dev_mode else "http://127.0.0.1:8000"

        # Starts in compact orb mode defaulting to the bottom-right corner of desktop work area
        x, y, w, h = get_desktop_work_area()
        compact_w, compact_h = 240, 120
        margin = 20
        init_x = x + w - compact_w - margin
        init_y = y + h - compact_h - margin

        self.window = webview.create_window(
            title="J.A.R.V.I.S. Desktop Assistant",
            url=app_url,
            width=compact_w,
            height=compact_h,
            x=init_x,
            y=init_y,
            min_size=(60, 60),
            frameless=True,
            transparent=True,
            on_top=True,
            easy_drag=False,  # Dedicated .pywebview-drag-region prevents hijacking click events
            js_api=self.js_api,
        )
        self.js_api.bind_window(self.window)

        def _apply_dwm_transparency():
            """Ensure WinForms Form client area is transparent via Windows DWM glass composition."""
            try:
                if not self.window or not hasattr(self.window, "native") or not self.window.native:
                    return
                form = self.window.native
                hwnd = form.Handle.ToInt32()
                margins = _MARGINS(-1, -1, -1, -1)
                ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
                import clr
                clr.AddReference("System.Drawing")
                import System.Drawing
                form.BackColor = System.Drawing.Color.Black
                print("[+] DWM glass transparency applied to native desktop host.")

                # Hook WebView2 permissions to auto-permit microphone for push-to-talk
                if hasattr(form, "Controls") and form.Controls.Count > 0:
                    wv_control = form.Controls[0]
                    def _hook_permission(sender, e):
                        try:
                            if hasattr(e, "State"):
                                e.State = 1  # CoreWebView2PermissionState.Allow
                        except Exception:
                            pass

                    if hasattr(wv_control, "CoreWebView2") and wv_control.CoreWebView2:
                        wv_control.CoreWebView2.PermissionRequested += _hook_permission
                    elif hasattr(wv_control, "CoreWebView2InitializationCompleted"):
                        def _on_init(sender, args):
                            try:
                                if wv_control.CoreWebView2:
                                    wv_control.CoreWebView2.PermissionRequested += _hook_permission
                            except Exception:
                                pass
                        wv_control.CoreWebView2InitializationCompleted += _on_init
            except Exception as e:
                print(f"[!] Transparency / WebView2 hook note: {e}")

        self.window.events.shown += _apply_dwm_transparency

        print("[+] J.A.R.V.I.S. Native Desktop Agent online.")
        print("[*] Press Alt+Space anywhere on your desktop to summon/hide.")
        print("[*] Click the floating Arc Reactor orb to expand into Glass HUD.")

        try:
            webview.start(debug=False)
        finally:
            self.exit_app()


def main():
    app = DesktopApplication()
    app.start()


if __name__ == "__main__":
    main()
