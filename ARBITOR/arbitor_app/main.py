import sys
import os
from PyQt5.QtWidgets import QApplication

from arbitor_app.core.config import PREDEFINED_CREDENTIALS
from arbitor_app.roles.role_2_database.database_manager import DatabaseManager
from arbitor_app.roles.role_3_session_auth.session_auth_engine import SessionAuthEngine
from arbitor_app.roles.role_4_policy_engine.policy_engine import PolicyEngine
from arbitor_app.roles.role_5_download_control.download_control_engine import DownloadControlEngine
from ARBITOR.ARBITOR.arbitor_app.utils.inactivity_tracker import InactivityTracker
from arbitor_app.ui.main_window import MainWindow


def run():
    app = QApplication(sys.argv)

    # ------------------------
    # BACKEND (UNCHANGED)
    # ------------------------
    db = DatabaseManager('arbitor_local.db')
    auth = SessionAuthEngine(db, PREDEFINED_CREDENTIALS)
    policy = PolicyEngine(db)
    download = DownloadControlEngine(policy, db)

    tracker = InactivityTracker(timeout_minutes=20)
    app.installEventFilter(tracker)

    app.aboutToQuit.connect(db.close)

    # ------------------------
    # UI (NEW)
    # ------------------------
    window = MainWindow(auth, db, policy, download)
    window.show()

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(run())

sys.path.append(os.path.dirname(os.path.dirname(__file__)))