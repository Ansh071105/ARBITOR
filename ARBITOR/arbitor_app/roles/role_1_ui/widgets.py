from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from arbitor_app.core.config import stamp


class IconInput(QWidget):
    def __init__(self, icon, placeholder, password=False):
        super().__init__()
        self.setObjectName("inputContainer")
        self.setFixedHeight(66)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 18, 8)
        lay.setSpacing(12)

        badge = QLabel(icon)
        badge.setObjectName("iconBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(50, 50)

        self.line_edit = QLineEdit()
        self.line_edit.setPlaceholderText(placeholder)
        if password:
            self.line_edit.setEchoMode(QLineEdit.Password)

        lay.addWidget(badge)
        lay.addWidget(self.line_edit)

class InactivityDialog(QDialog):
    def __init__(self, seconds=12, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Inactivity Warning")
        self.setModal(True)
        self.remaining = seconds

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(12)

        t = QLabel("Session will be logged out")
        t.setAlignment(Qt.AlignCenter)
        t.setObjectName("dialogTitle")

        self.msg = QLabel()
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setObjectName("dialogMessage")

        row = QHBoxLayout()
        self.keep_btn = QPushButton("Continue Session")
        self.keep_btn.clicked.connect(self.accept)
        self.keep_btn.setObjectName("continueButton")
        self.out_btn = QPushButton("Log Out Now")
        self.out_btn.clicked.connect(self.reject)
        self.out_btn.setObjectName("logoutDialogButton")
        row.addWidget(self.keep_btn)
        row.addWidget(self.out_btn)

        lay.addWidget(t)
        lay.addWidget(self.msg)
        lay.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.refresh()

        self.setStyleSheet(
            "QDialog{background:#f5f7fa;border-radius:14px;}"
            "#dialogTitle{color:#1f2937;font-size:24px;font-weight:800;}"
            "#dialogMessage{color:#374151;font-size:18px;font-weight:600;}"
            "#continueButton{border:none;border-radius:20px;background:#2ecc71;color:white;padding:10px 16px;font-weight:700;}"
            "#logoutDialogButton{border:none;border-radius:20px;background:#e74c3c;color:white;padding:10px 16px;font-weight:700;}"
        )

    def refresh(self):
        self.msg.setText(f"Automatic logout in {self.remaining}s due to inactivity.")

    def tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.reject()
            return
        self.refresh()

class AdminAlertWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Admin Alerts")
        self.resize(680, 430)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        t = QLabel("Real-Time Admin Alerts")
        t.setAlignment(Qt.AlignCenter)
        t.setObjectName("alertTitle")

        self.list = QListWidget()
        self.list.setObjectName("alertList")

        lay.addWidget(t)
        lay.addWidget(self.list)

        self.setStyleSheet(
            "QWidget{background:#edf2f7;}"
            "#alertTitle{color:#1f2937;font-size:24px;font-weight:800;}"
            "#alertList{background:white;border-radius:12px;border:1px solid #d1d5db;color:#111827;font-size:14px;padding:8px;}"
        )

    def add(self, level, message):
        self.list.insertItem(0, QListWidgetItem(f"[{stamp()}] {level.upper()}  {message}"))
