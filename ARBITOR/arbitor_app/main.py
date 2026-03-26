import sys
import os

# 1. FIX: Path append must be at the top before your custom imports
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# 2. FIX: Standardized imports
from arbitor_app.core.config import PREDEFINED_CREDENTIALS
from arbitor_app.roles.role_2_database.database_manager import DatabaseManager
from arbitor_app.roles.role_3_session_auth.session_auth_engine import SessionAuthEngine
from arbitor_app.roles.role_4_policy_engine.policy_engine import PolicyEngine
from arbitor_app.roles.role_5_download_control.download_control_engine import DownloadControlEngine
from arbitor_app.utils.inactivity_tracker import InactivityTracker
from arbitor_app.ui.main_window import MainWindow

# Optional: Import key blocker if you created it in Step 4 previously
# import keyboard 

def run():
    app = QApplication(sys.argv)

    # ------------------------
    # BACKEND
    # ------------------------
    db = DatabaseManager('arbitor_local.db')
    auth = SessionAuthEngine(db, PREDEFINED_CREDENTIALS)
    policy = PolicyEngine(db)
    download = DownloadControlEngine(policy, db)

    # Requirement 4: Inactivity Timeout
    tracker = InactivityTracker(timeout_minutes=20)
    app.installEventFilter(tracker)

    app.aboutToQuit.connect(db.close)

    # ------------------------
    # KIOSK UI & SECURITY
    # ------------------------
    window = MainWindow(auth, db, policy, download)
    
    # Requirement 3 & 8: Force Kiosk Mode
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    window.showFullScreen() 
    
    # Block system keys to prevent Alt+Tab / Windows Key escapes
    # keyboard.block_key('windows')
    # keyboard.block_key('alt+tab')

    return app.exec()

if __name__ == '__main__':
    raise SystemExit(run())