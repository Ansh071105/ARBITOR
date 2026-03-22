from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QHBoxLayout
from PyQt5.QtCore import pyqtSignal, Qt

class LockScreen(QWidget):
    # Signals for the MainWindow to catch
    unlock_requested = pyqtSignal(str) # Passes the password entered
    logout_requested = pyqtSignal()    # User gives up and logs out

    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = "---"
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0F172A;
                color: #E2E8F0;
            }
            QLineEdit {
                padding: 10px;
                border: 2px solid #334155;
                border-radius: 5px;
                background-color: #1E293B;
                color: white;
                font-size: 16px;
            }
            QLineEdit:focus {
                border: 2px solid #3B82F6; /* Blue Accent */
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#unlockBtn {
                background-color: #3B82F6;
                color: white;
            }
            QPushButton#unlockBtn:hover {
                background-color: #2563EB;
            }
            QPushButton#logoutBtn {
                background-color: transparent;
                border: 2px solid #EF4444; /* Danger Red */
                color: #EF4444;
            }
            QPushButton#logoutBtn:hover {
                background-color: #EF4444;
                color: white;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # Status Label
        self.status_label = QLabel("SESSION LOCKED")
        self.status_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #EF4444;")
        self.status_label.setAlignment(Qt.AlignCenter)

        # User Info
        self.user_label = QLabel("Locked by: ---")
        self.user_label.setStyleSheet("font-size: 16px; color: #94A3B8;")
        self.user_label.setAlignment(Qt.AlignCenter)

        # Password Input
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password to unlock...")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setFixedWidth(300)
        self.password_input.returnPressed.connect(self._handle_unlock)

        # Error Message (Hidden by default)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #EF4444; font-size: 12px;")
        self.error_label.setAlignment(Qt.AlignCenter)

        # Buttons
        btn_layout = QHBoxLayout()
        self.unlock_btn = QPushButton("Unlock")
        self.unlock_btn.setObjectName("unlockBtn")
        self.unlock_btn.clicked.connect(self._handle_unlock)
        
        self.logout_btn = QPushButton("Force Logout")
        self.logout_btn.setObjectName("logoutBtn")
        self.logout_btn.clicked.connect(self._handle_logout)

        btn_layout.addWidget(self.logout_btn)
        btn_layout.addWidget(self.unlock_btn)

        # Assemble
        layout.addWidget(self.status_label)
        layout.addWidget(self.user_label)
        layout.addWidget(self.password_input, alignment=Qt.AlignCenter)
        layout.addWidget(self.error_label)
        layout.addLayout(btn_layout)

    def set_user(self, username):
        self.username = username
        self.user_label.setText(f"Locked by: {self.username}")

    def show_error(self, message):
        self.error_label.setText(message)
        self.password_input.clear()

    def clear_inputs(self):
        self.password_input.clear()
        self.error_label.clear()

    def _handle_unlock(self):
        pwd = self.password_input.text()
        if pwd:
            self.unlock_requested.emit(pwd)
            
    def _handle_logout(self):
        self.logout_requested.emit()