import socket
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot


class SyncWorker(QObject):
    status_changed = Signal(str)
    admin_alert = Signal(str, str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.timer = None
        self.last_alert = 0

    @Slot()
    def start(self):
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.status_changed.emit("Sync standby")

    @Slot()
    def stop(self):
        if self.timer is not None:
            self.timer.stop()

    def online(self):
        try:
            s = socket.create_connection(("8.8.8.8", 53), timeout=2)
            s.close()
            return True
        except Exception:
            return False

    @Slot()
    def tick(self):
        self.db.trim_expired_approvals()
        if not self.online():
            self.status_changed.emit("Offline: local logging active")
            return
        synced, status = self.db.sync_to_postgres(batch=150)
        self.status_changed.emit(status)
        if synced > 0:
            self.admin_alert.emit("info", status)
        if "failed" in status.lower() and time.time() - self.last_alert > 20:
            self.last_alert = time.time()
            self.admin_alert.emit("warning", status)
