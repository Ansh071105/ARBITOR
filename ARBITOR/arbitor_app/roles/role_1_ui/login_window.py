from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget

from arbitor_app.roles.role_1_ui.ui_utils import compact_pc_id
from arbitor_app.roles.role_1_ui.widgets import IconInput
from arbitor_app.roles.role_1_ui.admin_panel import AdminPanel


class LoginWindow(QMainWindow):
    def __init__(self, auth, db, policy, download):
        super().__init__()
        self.auth = auth
        self.db = db
        self.policy = policy
        self.download = download
        self.display_pc_id = compact_pc_id(getattr(self.db, "pc_id", "") or self.auth.machine_id)
        self.admin = None

        self.setWindowTitle("User Login")
        self.setFixedSize(1000, 650)

        root = QWidget()
        root.setObjectName("loginRoot")
        self.setCentralWidget(root)

        lay = QVBoxLayout(root)
        lay.setContentsMargins(120, 70, 120, 70)
        lay.setSpacing(26)
        lay.addStretch()

        title = QLabel("User Login")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("loginTitle")
        pc_info = QLabel(f"Credential Access Only  |  {self.db.lab_id} / Bound PC: {self.display_pc_id}")
        pc_info.setAlignment(Qt.AlignCenter)
        pc_info.setObjectName("loginSubTitle")

        self.user = IconInput("👤", "User ID")
        self.pwd = IconInput("🔒", "Password", password=True)

        btn = QPushButton("Login")
        btn.setObjectName("loginButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(66)
        btn.clicked.connect(self.open_admin)

        lay.addWidget(title)
        lay.addWidget(pc_info)
        lay.addWidget(self.user)
        lay.addWidget(self.pwd)
        lay.addWidget(btn)
        lay.addStretch()

        self.setStyleSheet(
            "#loginRoot{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0c2340,stop:1 #0f8b8d);}"
            "#loginTitle{color:#f4c542;font-size:58px;font-weight:800;}"
            "#loginSubTitle{color:#e2e8f0;font-size:15px;font-weight:700;}"
            "#inputContainer{background:rgba(255,255,255,58);border-radius:33px;}"
            "#iconBadge{background:rgba(255,255,255,90);border-radius:25px;color:white;font-size:26px;font-weight:700;}"
            "QLineEdit{border:none;background:transparent;color:white;font-size:21px;font-weight:600;padding:0 10px 0 2px;}"
            "QLineEdit::placeholder{color:rgba(255,255,255,185);}"
            "#loginButton{border:none;border-radius:33px;color:#1b1b1b;font-size:26px;font-weight:800;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #ff9f43,stop:1 #ffd19a);}"
        )

    def popup(self, title, msg, critical=False):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.setIcon(QMessageBox.Critical if critical else QMessageBox.Warning)
        box.exec()

    def open_admin(self):
        uid = self.user.line_edit.text().strip()
        pwd = self.pwd.line_edit.text()
        if not uid or not pwd:
            self.popup("Missing Credentials", "Please enter both ID and password.")
            return

        ok, msg, session = self.auth.login(uid, pwd)
        if not ok:
            self.popup("Login Rejected", msg, critical=("bound" in msg.lower()))
            return

        self.admin = AdminPanel(session, self.auth, self.db, self.policy, self.download)
        self.admin.show()
        self.close()
