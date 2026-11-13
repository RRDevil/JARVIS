"""JARVIS Desktop Assistant - Root Launcher Entrypoint."""

import sys
import os
from pathlib import Path

# Add project root and backend to python path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

if __name__ == "__main__":
    from scripts.launch_dev import main
    main()

