from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer


class SessionScreen(QWidget):
    logout_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.username = "User"
        self.time_elapsed = 0  # seconds

        self._setup_ui()
        self._setup_timer()

    # ---------------- UI SETUP ---------------- #

    def _setup_ui(self):
        self.setObjectName("SessionScreen")

        # -------- Top Bar -------- #
        self.user_label = QLabel("User: ---")
        self.timer_label = QLabel("00:00")
        self.status_label = QLabel("ACTIVE")

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.clicked.connect(self.logout_requested.emit)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.user_label)
        top_layout.addStretch()
        top_layout.addWidget(self.status_label)
        top_layout.addSpacing(20)
        top_layout.addWidget(self.timer_label)
        top_layout.addSpacing(20)
        top_layout.addWidget(self.logout_btn)

        # -------- Main Content -------- #
        self.info_label = QLabel("System is under controlled session.")
        self.info_label.setAlignment(Qt.AlignCenter)

        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addStretch()
        main_layout.addWidget(self.info_label)
        main_layout.addStretch()

        self.setLayout(main_layout)

        self._apply_styles()

    # ---------------- TIMER ---------------- #

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_timer)

    def start_session(self):
        self.time_elapsed = 0
        self.timer.start(1000)

    def stop_session(self):
        self.timer.stop()

    def _update_timer(self):
        self.time_elapsed += 1
        mins = self.time_elapsed // 60
        secs = self.time_elapsed % 60
        self.timer_label.setText(f"{mins:02}:{secs:02}")

    # ---------------- PUBLIC METHODS ---------------- #

    def set_user(self, username: str):
        self.username = username
        self.user_label.setText(f"User: {username}")

    # ---------------- STYLING ---------------- #

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget#SessionScreen {
                background-color: #0F172A;
                color: #E2E8F0;
                font-size: 16px;
            }

            QLabel {
                font-size: 16px;
            }

            QPushButton {
                background-color: #EF4444;
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
            }

            QPushButton:hover {
                background-color: #DC2626;
            }
        """)