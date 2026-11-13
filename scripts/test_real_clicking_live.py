"""Live Windows Integration Test for Visual Target Resolution & Physical Mouse Clicking.

Creates a native test GUI window containing:
1. A simulated Video Card: "YouTube Video: Building JARVIS AI"
2. An interactive Button: "Click Me Test Button"
3. A Search Field: "Search Query"

Tests the real Windows clicking pipeline:
- Active window identification
- Screen capture and target resolution
- Physical cursor placement and verification (SetCursorPos / GetCursorPos)
- Real SendInput left-click dispatch
- Post-click UI state verification
"""

import asyncio
import os
import sys
import threading
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import tkinter as tk
from app.automation.windows_adapter import WindowsPlatformAdapter
from app.perception.target_resolver import target_resolver
from app.tools.grounded_interaction import VisualClickElementParams, VisualClickElementTool


def run_suite():
    print("=" * 70)
    print("J.A.R.V.I.S. Phase 5 Real Windows Live Clicking Verification")
    print("=" * 70)

    import ctypes
    user32 = ctypes.windll.user32
    hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
    if hdesk:
        user32.SetThreadDesktop(hdesk)

    root = tk.Tk()
    root.title("JARVIS Real Windows Click Test Window")
    root.geometry("600x450+150+150")
    root.configure(bg="#0b1329")

    # State variables
    results = {
        "button_clicked": False,
        "video_clicked": False,
        "click_coords": (0, 0),
    }

    # Title Label
    title_lbl = tk.Label(
        root,
        text="JARVIS Automation Test Surface",
        font=("Segoe UI", 14, "bold"),
        fg="#00e5ff",
        bg="#0b1329",
    )
    title_lbl.pack(pady=10)

    # Video Card Simulation
    video_frame = tk.Frame(
        root,
        bg="#1e293b",
        highlightbackground="#38bdf8",
        highlightthickness=2,
        width=480,
        height=120,
    )
    video_frame.pack_propagate(False)
    video_frame.pack(pady=15)

    video_title = tk.Label(
        video_frame,
        text="YouTube Video: Building JARVIS AI Assistant",
        font=("Segoe UI", 12, "bold"),
        fg="#f8fafc",
        bg="#1e293b",
    )
    video_title.pack(pady=15)

    video_sub = tk.Label(
        video_frame,
        text="125K views • 2 hours ago • Duration 18:42",
        font=("Segoe UI", 9),
        fg="#94a3b8",
        bg="#1e293b",
    )
    video_sub.pack()

    def on_video_click(event):
        results["video_clicked"] = True
        results["click_coords"] = (event.x_root, event.y_root)
        video_title.config(text="✓ VIDEO CLICK DETECTED & PLAYING", fg="#4ade80")

    video_frame.bind("<Button-1>", on_video_click)
    video_title.bind("<Button-1>", on_video_click)
    video_sub.bind("<Button-1>", on_video_click)

    def on_button_clicked():
        results["button_clicked"] = True
        test_btn.config(text="✓ BUTTON CLICKED SUCCESSFULLY", bg="#16a34a")
        status_lbl.config(text="Status: Real click event registered!", fg="#4ade80")

    # Interactive Button
    test_btn = tk.Button(
        root,
        text="Click Me Test Button",
        font=("Segoe UI", 11, "bold"),
        bg="#0284c7",
        fg="#ffffff",
        activebackground="#38bdf8",
        padx=15,
        pady=8,
        command=on_button_clicked,
    )
    test_btn.bind("<Button-1>", lambda e: on_button_clicked())
    test_btn.pack(pady=15)

    # Search Bar Entry
    entry = tk.Entry(root, font=("Segoe UI", 11), width=35)
    entry.insert(0, "Search query...")
    entry.pack(pady=10)

    status_lbl = tk.Label(
        root,
        text="Status: Waiting for J.A.R.V.I.S. click interaction...",
        font=("Segoe UI", 10),
        fg="#cbd5e1",
        bg="#0b1329",
    )
    status_lbl.pack(pady=15)

    root.update()
    import ctypes
    hwnd = root.winfo_id()
    toplevel_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd

    async def execute_test_steps():
        adapter = WindowsPlatformAdapter()

        # 1. Bring window to foreground
        print(f"[+] Test GUI window initialized. HWND: {toplevel_hwnd}")
        print("[1] Restoring and bringing test window to foreground...")
        adapter.restore_and_focus_window(toplevel_hwnd)
        await asyncio.sleep(0.3)
        root.update()

        # 2. Test button coordinates direct click
        btn_x = test_btn.winfo_rootx() + test_btn.winfo_width() // 2
        btn_y = test_btn.winfo_rooty() + test_btn.winfo_height() // 2
        print(f"[2] Testing physical click on 'Click Me Test Button' at ({btn_x}, {btn_y})...")

        tool = VisualClickElementTool()
        btn_params = VisualClickElementParams(
            x=btn_x,
            y=btn_y,
            target_description="Click Me Test Button",
            window_handle=toplevel_hwnd,
            hover_ms=50,
            verify_post_condition=True,
        )
        from unittest.mock import MagicMock
        btn_result = await tool.execute(btn_params, MagicMock())

        print(f"    Tool result: {btn_result.success}, Status: {btn_result.data.get('status')}")
        await asyncio.sleep(0.2)
        root.update()
        if results["button_clicked"]:
            print("    [PASS] GUI confirmed button click callback was executed!")
        else:
            print("    [-] Button click not detected by GUI.")

        # 3. Test video card click
        vid_x = video_frame.winfo_rootx() + video_frame.winfo_width() // 2
        vid_y = video_frame.winfo_rooty() + video_frame.winfo_height() // 2
        print(f"[3] Testing physical click on Video Card at ({vid_x}, {vid_y})...")

        vid_params = VisualClickElementParams(
            x=vid_x,
            y=vid_y,
            target_description="YouTube Video: Building JARVIS AI Assistant",
            window_handle=toplevel_hwnd,
            hover_ms=50,
            verify_post_condition=True,
        )
        vid_result = await tool.execute(vid_params, MagicMock())

        print(f"    Tool result: {vid_result.success}, Status: {vid_result.data.get('status')}")
        await asyncio.sleep(0.2)
        root.update()
        if results["video_clicked"]:
            print(f"    [PASS] GUI confirmed video card click was executed at {results['click_coords']}!")
        else:
            print("    [-] Video click not detected by GUI.")

        # 4. Clean up
        print("[4] Cleaning up test window...")
        root.destroy()

    def run_async_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(execute_test_steps())
        finally:
            loop.close()

    root.after(300, lambda: threading.Thread(target=run_async_in_thread, daemon=True).start())
    root.mainloop()

    success = results["button_clicked"] and results["video_clicked"]
    print("=" * 70)
    print(f"VERIFICATION RESULT: {'ALL REAL WINDOWS CLICKS PASSED' if success else 'PARTIAL/FAILED'}")
    print("=" * 70)
    return 0 if success else 1


if __name__ == "__main__":
    code = run_suite()
    sys.exit(code)
