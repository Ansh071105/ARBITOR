from PyQt5.QtCore import QObject, QEvent, Qt

class KioskGuard(QObject):
    def __init__(self, dev_mode=False, parent=None):
        super().__init__(parent)
        self.dev_mode = dev_mode

    def eventFilter(self, obj, event):
        # Allow everything through if we are building/testing
        if self.dev_mode:
            return False

        # 1. Intercept Keystrokes
        if event.type() in (QEvent.KeyPress, QEvent.KeyRelease):
            key = event.key()
            modifiers = event.modifiers()

            # Block Alt combinations (Alt+Tab, Alt+F4)
            if modifiers & Qt.AltModifier:
                if key in (Qt.Key_Tab, Qt.Key_F4):
                    return True  # Swallow the event

            # Block Windows / Super / Meta key
            if key == Qt.Key_Meta:
                return True

            # Block Ctrl+Esc
            if modifiers & Qt.ControlModifier and key == Qt.Key_Escape:
                return True

            # Block standard Escape key
            if key == Qt.Key_Escape:
                return True

        # 2. Aggressive Focus Retention
        # If the OS forces another window on top, force ARBITOR back
        if event.type() == QEvent.WindowDeactivate:
            if hasattr(obj, 'activateWindow'):
                obj.activateWindow()
            return True

        return False