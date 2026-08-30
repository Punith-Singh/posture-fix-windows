"""
PostureFix for Windows — Main Entry Point with logging

Uses your webcam + MediaPipe Face Mesh to detect head pose in real-time.
"""

import sys
import os
import logging
import ctypes

# Fix for blurry text on High-DPI displays (Windows)
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# Setup logging to file
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posturefix.log")
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger("PostureFix")
logger.info("PostureFix starting...")

# Ensure src is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app_state import AppState
from src.dashboard import PostureFixDashboard


def main():
    logger.info("Initializing AppState...")
    app_state = AppState()
    logger.info("AppState ready. Building dashboard...")
    dashboard = PostureFixDashboard(app_state)
    logger.info("Dashboard built. Starting main loop...")
    dashboard.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        input("Press Enter to exit...")
