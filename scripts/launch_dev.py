"""JARVIS Local Development & Desktop Shell Launcher.

Orchestrates launching:
1. Python FastAPI Backend on http://127.0.0.1:8000
2. React Vite Frontend on http://127.0.0.1:5173
3. Native Windows Desktop Shell window host
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path
import urllib.request
import json

ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
NODE_DIR = Path(r"C:\Program Files\nodejs")


def check_port_health(url: str, timeout: float = 1.0) -> bool:
    """Check if an HTTP endpoint is responding."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Launcher"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_edge_app_path() -> Path | None:
    """Find Microsoft Edge executable to launch standalone desktop app window."""
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def main():
    print("=" * 60)
    print("   J.A.R.V.I.S. DESKTOP ASSISTANT - LAUNCH SEQUENCE")
    print("=" * 60)

    # 1. Prepare environment PATH
    env = os.environ.copy()
    if NODE_DIR.exists() and str(NODE_DIR) not in env.get("PATH", ""):
        env["PATH"] = f"{NODE_DIR};{env.get('PATH', '')}"

    # 2. Check virtual environment python
    python_exe = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    print(f"[*] Backend runtime: {python_exe}")

    # 3. Launch Backend
    print("[*] Starting JARVIS FastAPI Backend (127.0.0.1:8000)...")
    backend_proc = subprocess.Popen(
        [
            python_exe,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(BACKEND_DIR),
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "info",
        ],
        cwd=str(ROOT_DIR),
        env=env,
    )

    # 4. Wait for backend to be operational
    print("[*] Waiting for backend health diagnostics...")
    for _ in range(30):
        if check_port_health("http://127.0.0.1:8000/api/health"):
            print("[+] Backend core operational!")
            break
        time.sleep(0.5)
    else:
        print("[-] Backend failed to respond within 15 seconds.")
        backend_proc.terminate()
        sys.exit(1)

    # 5. Launch Frontend Dev Server
    print("[*] Starting React Frontend Dev Server (127.0.0.1:5173)...")
    npm_cmd = str(NODE_DIR / "npm.cmd") if (NODE_DIR / "npm.cmd").exists() else "npm.cmd"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        env=env,
    )

    # 6. Wait for frontend to respond
    for _ in range(30):
        if check_port_health("http://127.0.0.1:5173"):
            print("[+] Frontend dev server operational!")
            break
        time.sleep(0.5)

    # 7. Launch Native Desktop Shell Window (Transparent HUD + System Tray)
    print("[*] Launching Native Desktop Shell Window (Transparent HUD + Tray)...")
    desktop_app_script = str(ROOT_DIR / "scripts" / "desktop_app.py")
    desktop_proc = subprocess.Popen(
        [python_exe, desktop_app_script, "--dev"],
        cwd=str(ROOT_DIR),
        env=env,
    )

    print("\n[+] JARVIS Desktop Assistant is online.")
    print("[*] Press Ctrl+C in this terminal to shut down all services.")

    def cleanup(signum=None, frame=None):
        print("\n[*] Shutting down JARVIS services...")
        for name, proc in [("Desktop Shell", desktop_proc), ("Frontend Vite", frontend_proc), ("Backend FastAPI", backend_proc)]:
            if proc and proc.poll() is None:
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                            capture_output=True,
                            check=False,
                        )
                    else:
                        proc.terminate()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        print("[+] All JARVIS services halted.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            time.sleep(0.5)
            # If desktop shell closes or backend terminates, shut down everything
            if desktop_proc and desktop_proc.poll() is not None:
                print("[*] Desktop interface closed by user.")
                break
            if backend_proc.poll() is not None:
                print("[-] Backend process terminated.")
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()

