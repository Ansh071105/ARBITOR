from PyQt5.QtCore import QObject, QEvent, QTimer, pyqtSignal

class InactivityTracker(QObject):
    # Signal emitted when the user goes idle
    inactivity_timeout = pyqtSignal()

    def __init__(self, timeout_minutes=20, parent=None):
        super().__init__(parent)
        self.timeout_ms = timeout_minutes * 60 * 1000
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_timeout)

    def start_tracking(self):
        """Start or restart the inactivity timer."""
        self.timer.start(self.timeout_ms)

    def stop_tracking(self):
        """Pause tracking (e.g., when already locked or logged out)."""
        self.timer.stop()

    def eventFilter(self, obj, event):
        """Intercept global application events to reset the timer."""
        # Check for mouse movement, clicks, or keyboard presses
        if event.type() in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress):
            # Only reset if the timer is actually running (active session)
            if self.timer.isActive():
                self.timer.start(self.timeout_ms)
                
        # Always return False so events continue to process normally
        return False

    def _on_timeout(self):
        self.inactivity_timeout.emit()