import time
from threading import Lock

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from arbitor_app.core.config import stamp


class EnforcementWorker(QObject):
    countdown_changed = Signal(int)
    inactivity_timeout = Signal()
    url_result = Signal(str, bool, str)
    download_result = Signal(str, bool, str, str, str, str)
    admin_alert = Signal(str, str)
    heartbeat_status = Signal(str)

    def __init__(self, auth, policy, download, sid, idle_limit=1200, warning_window=20):
        super().__init__()
        self.auth = auth
        self.policy = policy
        self.download = download
        self.sid = sid
        self.idle_limit = idle_limit
        self.warning_window = warning_window
        self.last_activity = time.monotonic()
        self.last_heartbeat = time.monotonic()
        self.timed_out = False
        self.timer = None
        self.lock = Lock()
        self.url_q = []
        self.dl_q = []

    @Slot()
    def start(self):
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    @Slot()
    def stop(self):
        if self.timer is not None:
            self.timer.stop()

    @Slot()
    def mark_activity(self):
        with self.lock:
            self.last_activity = time.monotonic()
            self.timed_out = False

    @Slot(str)
    def submit_url(self, url):
        clean = url.strip()
        if clean:
            with self.lock:
                self.url_q.append(clean)

    @Slot(str, str, str)
    def submit_download(self, file_name, mime, source):
        with self.lock:
            self.dl_q.append((file_name.strip(), mime.strip(), source.strip()))

    @Slot()
    def tick(self):
        with self.lock:
            idle = int(time.monotonic() - self.last_activity)
            remain = self.idle_limit - idle
            urls = list(self.url_q)
            dls = list(self.dl_q)
            self.url_q.clear()
            self.dl_q.clear()
            timed_out = self.timed_out

        if 0 < remain <= self.warning_window:
            self.countdown_changed.emit(remain)
        if remain <= 0 and not timed_out:
            with self.lock:
                self.timed_out = True
            self.admin_alert.emit("warning", "Inactivity threshold reached")
            self.inactivity_timeout.emit()

        if time.monotonic() - self.last_heartbeat >= 5:
            self.last_heartbeat = time.monotonic()
            if self.auth.heartbeat(self.sid):
                self.heartbeat_status.emit(f"Heartbeat {stamp()}")
            else:
                self.admin_alert.emit("critical", "Session heartbeat failed")

        for u in urls:
            ok, reason, dom = self.policy.evaluate_url(u)
            self.url_result.emit(u, ok, reason)
            if not ok:
                self.admin_alert.emit("critical", f"Policy violation: {dom or u}")

        for fname, mime, src in dls:
            ok, reason, approval_ref = self.download.evaluate(fname, mime, src)
            self.download_result.emit(fname, ok, reason, mime, src, approval_ref)
            if not ok:
                self.admin_alert.emit("critical", f"Download blocked: {fname}")
