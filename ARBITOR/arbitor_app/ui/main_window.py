import sys
from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QApplication
from PyQt5.QtCore import Qt

from arbitor_app.ui.screens.login_screen import LoginScreen
from arbitor_app.ui.screens.session_screen import SessionScreen
from arbitor_app.ui.screens.lock_screen import LockScreen            # NEW
from arbitor_app.utils.inactivity_tracker import InactivityTracker   # NEW
from arbitor_app.ui.controller.ui_controller import UIController
from arbitor_app.ui.warning_overlay import WarningOverlay

DEV_MODE = True

class MainWindow(QMainWindow):
    def __init__(self, auth, db, policy, download):
        super().__init__()

        # Backend references (ONLY here)
        self.auth = auth
        self.db = db
        self.policy = policy
        self.download = download

        # Track active user for unlock verification
        self.current_username = None 

        # Stack
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.overlay = WarningOverlay(self)
        self.overlay.acknowledged.connect(self.handle_overlay_acknowledged)

        # Screens
        self.login_screen = LoginScreen()
        self.session_screen = SessionScreen()
        self.lock_screen = LockScreen()                  # NEW

        # Add screens (ONLY ONCE)
        self.stack.addWidget(self.login_screen)    # index 0
        self.stack.addWidget(self.session_screen)  # index 1
        self.stack.addWidget(self.lock_screen)     # index 2 (NEW)

        # Controller AFTER stack is ready
        self.controller = UIController(self.stack)

        # Setup Inactivity Tracker (NEW)
        # Assuming 20 mins for production, maybe set to 1 for testing
        self.tracker = InactivityTracker(timeout_minutes=20, parent=self)
        QApplication.instance().installEventFilter(self.tracker)

        # Connect signals
        self.login_screen.login_requested.connect(self.handle_login_request)
        self.session_screen.logout_requested.connect(self.handle_logout)
        
        # Lock Screen Signals (NEW)
        self.tracker.inactivity_timeout.connect(self.handle_inactivity_lock)
        self.lock_screen.unlock_requested.connect(self.handle_unlock_request)
        self.lock_screen.logout_requested.connect(self.handle_logout)

        # Start at login
        self.controller.show_login()
        self.setup_kiosk_mode()

    def setup_kiosk_mode(self):
        if DEV_MODE:
            self.resize(900, 600)
            return

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showFullScreen()

    def closeEvent(self, event):
        if DEV_MODE:
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event):
        """Ensure the overlay always covers the whole screen when the window resizes."""
        super().resizeEvent(event)
        if hasattr(self, 'overlay') and self.overlay.isVisible():
            self.overlay.resize(self.size())

    def trigger_session_warning(self):
        """Example method to show how to trigger the overlay."""
        self.overlay.show_alert(
            title="SESSION EXPIRING", 
            message="Your lab session will expire in 5 minutes. Please save your work.",
            level="warning"
        )

    def trigger_security_alert(self):
        """Example method for a critical alert."""
        self.overlay.show_alert(
            title="SECURITY ALERT", 
            message="Unauthorized USB device detected. Please remove it immediately.",
            level="critical"
        )

    def handle_overlay_acknowledged(self):
        """Called when the user clicks 'Acknowledge' on the overlay."""
        print("User acknowledged the alert.")
        # Reset inactivity timer, tell backend, etc.
        if hasattr(self, 'tracker'):
            self.tracker.start_tracking()

    # ------------------------
    # LOGIN FLOW
    # ------------------------
    def handle_login_request(self, username, password):
        try:
            result = self.auth.login(username, password)

            if result["status"] == "success":
                self.current_username = username

                # ✅ SET USER
                self.session_screen.set_user(username)
                self.lock_screen.set_user(username)       # NEW

                # ✅ START TIMERS
                self.session_screen.start_session()
                self.tracker.start_tracking()             # NEW

                # ✅ NAVIGATE
                self.controller.show_session()

            elif result["status"] == "active_session":
                self.login_screen.show_error(
                    "Your session is already active on another PC."
                )

            elif result["status"] == "multiple_attempts":
                self.login_screen.disable_for_seconds(120)
                self.login_screen.show_error(
                    "Multiple login attempts detected. Try again later."
                )

            else:
                self.login_screen.show_error("Wrong / Failed Credentials")

        except Exception as e:
            print("Login error:", e)
            self.login_screen.show_error("System error. Try again.")

    # ------------------------
    # LOCK / UNLOCK FLOW (NEW)
    # ------------------------
    def handle_inactivity_lock(self):
        """Triggered when the user is idle."""
        self.tracker.stop_tracking()
        self.lock_screen.clear_inputs()
        self.controller.show_lock_screen()

    def handle_unlock_request(self, password):
        """Validates password to unlock the session."""
        try:
            # Assuming backend auth has a verification method. 
            # You can change this to match your actual auth logic.
            result = self.auth.login(self.current_username, password)
            
            if result["status"] == "success":
                self.lock_screen.clear_inputs()
                self.controller.show_session()
                self.tracker.start_tracking() # Resume idle tracking
            else:
                self.lock_screen.show_error("Invalid password. Try again.")
                
        except Exception as e:
            print("Unlock error:", e)
            self.lock_screen.show_error("System error. Try again.")

    # ------------------------
    # LOGOUT FLOW
    # ------------------------
    def handle_logout(self):
        # ✅ Stop timers
        self.session_screen.stop_session()
        self.tracker.stop_tracking()              # NEW

        # ✅ Reset UI
        self.current_username = None              # NEW
        self.session_screen.set_user("---")
        self.lock_screen.set_user("---")          # NEW
        self.lock_screen.clear_inputs()           # NEW

        # ✅ Go back to login
        self.controller.show_login()