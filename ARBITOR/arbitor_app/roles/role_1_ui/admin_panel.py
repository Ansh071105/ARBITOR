from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from arbitor_app.core.config import domain_of, stamp
from arbitor_app.roles.role_1_ui.enforcement_worker import EnforcementWorker
from arbitor_app.roles.role_1_ui.ui_utils import compact_pc_id
from arbitor_app.roles.role_1_ui.widgets import AdminAlertWindow, InactivityDialog
from arbitor_app.roles.role_6_sync_engine.sync_worker import SyncWorker


class AdminPanel(QMainWindow):
    ping = Signal()
    submit_url = Signal(str)
    submit_dl = Signal(str, str, str)
    stop_enforce = Signal()
    stop_sync = Signal()

    def __init__(self, session, auth, db, policy, download):
        super().__init__()
        self.sid = session["sid"]
        self.username = session["username"]
        self.auth = auth
        self.db = db
        self.policy = policy
        self.download = download
        self.display_pc_id = compact_pc_id(getattr(self.db, "pc_id", "") or self.auth.machine_id)

        self.alert_window = AdminAlertWindow()
        self.login_window = None
        self.kiosk = False
        self.awaiting_dialog = False
        self.closing_for_logout = False
        self.session_closed = False
        self.termination_pending = False
        self.tray = None

        self.setWindowTitle("Arbitor Admin System")
        self.resize(1280, 800)
        self.setMinimumSize(1180, 760)

        root = QWidget()
        root.setObjectName("adminRoot")
        self.setCentralWidget(root)

        main = QHBoxLayout(root)
        main.setContentsMargins(24, 24, 24, 24)
        main.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)

        content = QWidget()
        content.setObjectName("contentArea")

        main.addWidget(sidebar)
        main.addWidget(content, 1)

        s = QVBoxLayout(sidebar)
        s.setContentsMargins(18, 20, 18, 20)
        s.setSpacing(10)

        head = QLabel("ARA & DCS")
        head.setObjectName("sideTitle")
        head.setAlignment(Qt.AlignCenter)
        s.addWidget(head)
        sub = QLabel("MISSION CONTROL")
        sub.setObjectName("sideSubTitle")
        sub.setAlignment(Qt.AlignCenter)
        s.addWidget(sub)
        s.addSpacing(8)

        self.menu = []
        self.nav_page_map = []
        self.nav_alert_map = []
        self.nav_header_map = []
        nav_icons = {
            "Dashboard": "⌂",
            "Whitelisted Sites": "☑",
            "Session Logs": "▦",
            "Alerts & Actions": "⚠",
            "System Settings": "⚙",
            "Admin Tools": "🛠",
        }
        nav_items = [
            ("Dashboard", 0, False),
            ("Whitelisted Sites", 2, False),
            ("Session Logs", 1, False),
            ("Alerts & Actions", 3, False),
            ("System Settings", 2, False),
            ("Admin Tools", 4, False),
        ]
        for i, (text, page_idx, opens_alert) in enumerate(nav_items):
            b = QPushButton(f"{nav_icons.get(text, '•')}  {text}")
            b.setObjectName("menuButton")
            b.setProperty("active", i == 0)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(44)
            b.clicked.connect(lambda _, idx=i: self.handle_nav_click(idx))
            s.addWidget(b)
            self.menu.append(b)
            self.nav_page_map.append(page_idx)
            self.nav_alert_map.append(opens_alert)
            self.nav_header_map.append(text)

        s.addStretch()
        out_btn = QPushButton("SHUTDOWN")
        out_btn.setObjectName("logoutButton")
        out_btn.setFixedHeight(44)
        out_btn.clicked.connect(self.shutdown_session)
        s.addWidget(out_btn)

        c = QVBoxLayout(content)
        c.setContentsMargins(18, 14, 18, 16)
        c.setSpacing(12)

        top_banner = QFrame()
        top_banner.setObjectName("topBanner")
        top_lay = QHBoxLayout(top_banner)
        top_lay.setContentsMargins(14, 10, 14, 10)
        top_lay.setSpacing(10)
        brand_wrap = QVBoxLayout()
        brand_wrap.setContentsMargins(0, 0, 0, 0)
        brand_wrap.setSpacing(2)
        brand_title = QLabel("ARA & DCS")
        brand_title.setObjectName("brandTitle")
        brand_sub = QLabel("Academic Resource Abuse & Download Control System")
        brand_sub.setObjectName("brandSub")
        brand_wrap.addWidget(brand_title)
        brand_wrap.addWidget(brand_sub)
        self.admin_user_chip = QLabel(f"{self.username} @ {self.display_pc_id}")
        self.admin_user_chip.setObjectName("userChip")
        top_lay.addLayout(brand_wrap)
        top_lay.addStretch()
        top_lay.addWidget(self.admin_user_chip)
        c.addWidget(top_banner)

        head_row = QHBoxLayout()
        self.welcome = QLabel(f"Whitelisted Sites   |   Welcome, {self.username}   |   {self.db.lab_id}")
        self.welcome.setObjectName("headerTitle")
        self.welcome.setWordWrap(False)
        self.kiosk_btn = QPushButton("Enter Kiosk")
        self.kiosk_btn.setObjectName("kioskButton")
        self.kiosk_btn.setCheckable(True)
        self.kiosk_btn.clicked.connect(self.toggle_kiosk)
        head_row.addWidget(self.welcome)
        head_row.addStretch()
        head_row.addWidget(self.kiosk_btn)
        c.addLayout(head_row)

        status_row = QHBoxLayout()
        self.hb = QLabel("Heartbeat pending")
        self.hb.setObjectName("statusLabel")
        self.sync = QLabel("Sync standby")
        self.sync.setObjectName("statusLabel")
        self.count = QLabel("")
        self.count.setObjectName("countdownBadge")
        self.count.setVisible(False)
        self.score_chip = QLabel("Score 100")
        self.score_chip.setObjectName("gamifyChip")
        self.alerts_chip = QPushButton("Open Alerts")
        self.alerts_chip.setObjectName("secondaryButton")
        self.alerts_chip.clicked.connect(self.toggle_alerts)
        status_row.addWidget(self.hb)
        status_row.addWidget(self.sync)
        status_row.addWidget(self.count)
        status_row.addWidget(self.score_chip)
        status_row.addStretch()
        status_row.addWidget(self.alerts_chip)
        c.addLayout(status_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.dashboard_page())
        self.stack.addWidget(self.sessions_page())
        self.stack.addWidget(self.logs_page())
        self.stack.addWidget(self.alerts_page())
        self.stack.addWidget(self.admin_tools_page())
        c.addWidget(self.stack, 1)

        footer_notice = QLabel("ADMIN ACCESS ONLY  •  AUTHORIZED PERSONNEL ONLY  •  UAC APPROVAL REQUIRED")
        footer_notice.setObjectName("footerNotice")
        footer_notice.setAlignment(Qt.AlignCenter)
        c.addWidget(footer_notice)
        self.setStyleSheet(
            """
            #adminRoot{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0b1220, stop:0.55 #101a2d, stop:1 #0a1324);
            }
            #sidebar{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #020617, stop:1 #050a17);
                border:1px solid #1b2a42;
                border-right:0;
                border-top-left-radius:14px;
                border-bottom-left-radius:14px;
            }
            #contentArea{
                background:transparent;
                border:1px solid #1b2a42;
                border-left:0;
                border-top-right-radius:14px;
                border-bottom-right-radius:14px;
            }
            #topBanner{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #0a162b, stop:1 #111e34);
                border:1px solid #31547a;
                border-radius:12px;
            }
            #brandTitle{
                color:#e2e8f0;
                font-size:28px;
                font-weight:900;
                letter-spacing:0.8px;
            }
            #brandSub{
                color:#93c5fd;
                font-size:13px;
                font-weight:700;
            }
            #userChip{
                background:#0b1526;
                color:#dbeafe;
                border:1px solid #334155;
                border-radius:14px;
                padding:8px 12px;
                font-size:13px;
                font-weight:800;
            }
            #sideTitle{
                color:#f8fafc;
                font-size:27px;
                font-weight:900;
                padding:10px 0 0 0;
                letter-spacing:0.8px;
            }
            #sideSubTitle{
                color:#67e8f9;
                font-size:11px;
                font-weight:800;
                padding:0 0 8px 0;
                letter-spacing:1.8px;
            }
            #menuButton{
                background:transparent;
                color:#cbd5e1;
                border:1px solid transparent;
                padding:10px 12px;
                text-align:left;
                border-radius:10px;
                font-size:14px;
                font-weight:700;
            }
            #menuButton:hover{
                background:#13233b;
                color:white;
                border:1px solid #1d4ed8;
            }
            #menuButton[active='true']{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1d4ed8, stop:1 #0284c7);
                color:white;
                border:1px solid #38bdf8;
            }
            #logoutButton{
                border:1px solid #ef4444;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #b91c1c, stop:1 #ef4444);
                color:white;
                font-size:13px;
                font-weight:900;
                border-radius:10px;
            }
            #headerTitle{
                color:#f8fafc;
                font-size:18px;
                font-weight:900;
                padding:4px 4px;
            }
            #statusLabel{
                background:#0b1526;
                color:#7dd3fc;
                border:1px solid #1f3654;
                border-radius:10px;
                padding:8px 12px;
                font-size:12px;
                font-weight:800;
            }
            #gamifyChip{
                background:#052e2b;
                color:#6ee7b7;
                border:1px solid #15803d;
                border-radius:10px;
                padding:8px 12px;
                font-size:12px;
                font-weight:900;
            }
            #countdownBadge{
                background:#f59e0b;
                color:#111827;
                border-radius:10px;
                padding:8px 10px;
                font-size:12px;
                font-weight:900;
            }
            #kioskButton{
                border:1px solid #3b82f6;
                border-radius:10px;
                background:#1d4ed8;
                color:white;
                font-size:13px;
                font-weight:800;
                padding:8px 12px;
            }
            #kioskButton:checked{
                background:#0ea5e9;
                border-color:#38bdf8;
            }
            #secondaryButton{
                border:1px solid #334155;
                border-radius:10px;
                background:#1f2937;
                color:#e2e8f0;
                font-size:12px;
                font-weight:800;
                padding:8px 12px;
            }
            #pageTitle{
                color:#f8fafc;
                font-size:28px;
                font-weight:900;
            }
            #pageSub{
                color:#94a3b8;
                font-size:14px;
                font-weight:700;
            }
            #textInput{
                border:1px solid #334155;
                background:#020617;
                border-radius:10px;
                color:#e2e8f0;
                font-size:14px;
                font-weight:700;
                padding:10px 12px;
            }
            #validateButton{
                border:none;
                border-radius:10px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2563eb, stop:1 #0284c7);
                color:white;
                font-size:13px;
                font-weight:800;
                padding:9px 14px;
            }
            #warnButton{
                border:none;
                border-radius:10px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f97316, stop:1 #fb923c);
                color:white;
                font-size:13px;
                font-weight:800;
                padding:9px 14px;
            }
            #policyList{
                border:1px solid #1f3654;
                border-radius:10px;
                background:#020617;
                color:#e5e7eb;
                font-size:13px;
                padding:8px;
            }
            #dashCard{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #061126, stop:1 #0a1a33);
                border-radius:12px;
                border:1px solid #1f3654;
                padding:10px;
            }
            #cardTitle{
                color:#93c5fd;
                font-size:13px;
                font-weight:700;
            }
            #cardValue{
                color:white;
                font-size:24px;
                font-weight:900;
            }
            #boxFrame{
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #040b1b, stop:1 #081126);
                border-radius:12px;
                border:1px solid #1f3654;
                padding:8px;
            }
            #boxTitle{
                color:#f8fafc;
                font-size:16px;
                font-weight:800;
                padding:4px 2px;
            }
            #scoreValue{
                color:#f8fafc;
                font-size:24px;
                font-weight:900;
            }
            #scoreMeta{
                color:#93c5fd;
                font-size:13px;
                font-weight:700;
            }
            #darkList{
                background:#020617;
                border:1px solid #1f3654;
                color:#e5e7eb;
                border-radius:10px;
                padding:0px;
            }
            #darkList::item{
                padding:7px 8px;
            }
            #darkTable{
                background:#020617;
                border:1px solid #1f3654;
                color:#e5e7eb;
                border-radius:10px;
                gridline-color:#1f3654;
                alternate-background-color:#0b1323;
                selection-background-color:#2563eb;
            }
            #darkTable::item{
                padding:6px;
            }
            #scoreBar, #threatBar{
                border:1px solid #1f3654;
                border-radius:7px;
                background:#020617;
                text-align:center;
                color:#dbeafe;
                height:16px;
            }
            #scoreBar::chunk{
                border-radius:6px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #10b981, stop:1 #22c55e);
            }
            #threatBar::chunk{
                border-radius:6px;
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #f59e0b, stop:1 #ef4444);
            }
            QHeaderView::section{
                background:#111827;
                color:#93c5fd;
                border:1px solid #1f3654;
                padding:6px;
                font-weight:800;
            }
            QScrollArea{
                border:none;
                background:transparent;
            }
            QScrollBar:vertical{
                width:11px;
                background:#0b1526;
                border-radius:5px;
                margin:2px;
            }
            QScrollBar::handle:vertical{
                background:#1d4ed8;
                border-radius:5px;
                min-height:20px;
            }
            QScrollBar:horizontal{
                height:11px;
                background:#0b1526;
                border-radius:5px;
                margin:2px;
            }
            QScrollBar::handle:horizontal{
                background:#1d4ed8;
                border-radius:5px;
                min-width:20px;
            }
            QScrollBar::add-line, QScrollBar::sub-line{
                width:0px;
                height:0px;
            }
            #footerNotice{
                background:#070f1c;
                border:1px solid #1f3654;
                border-radius:10px;
                color:#94a3b8;
                font-size:11px;
                font-weight:700;
                padding:6px 10px;
                letter-spacing:0.5px;
            }
            """
        )

        self.setup_enforcement()
        self.setup_sync()
        self.setup_tray()
        QApplication.instance().installEventFilter(self)
        self.log("INFO", "UI", f"Session started for user: {self.username}", {"sid": self.sid})
        self.refresh_sessions()
        self.load_logs()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(3000)
        self.refresh_timer.timeout.connect(self.refresh_sessions)
        self.refresh_timer.start()

    def dashboard_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_active = self.create_status_card("Active Users", "0 Online", "#38bdf8")
        self.card_blocked = self.create_status_card("Blocked Attempts", "0 Violations", "#f59e0b")
        self.card_downloads = self.create_status_card("Current Downloads", "0 Files", "#22c55e")
        self.card_state = self.create_status_card("System Status", "Monitoring Active", "#16a34a")
        self.card_active.setMinimumHeight(92)
        self.card_blocked.setMinimumHeight(92)
        self.card_downloads.setMinimumHeight(92)
        self.card_state.setMinimumHeight(92)
        cards.addWidget(self.card_active)
        cards.addWidget(self.card_blocked)
        cards.addWidget(self.card_downloads)
        cards.addWidget(self.card_state)
        lay.addLayout(cards)

        game_row = QHBoxLayout()
        game_row.setSpacing(10)
        game_row.addWidget(self.wrap_box("Operator Progress", self._build_ops_panel()))
        game_row.addWidget(self.wrap_box("Threat Meter", self._build_threat_panel()))
        lay.addLayout(game_row)

        middle = QHBoxLayout()
        middle.setSpacing(10)
        self.whitelist_view = QListWidget()
        self.whitelist_view.setObjectName("darkList")
        self.whitelist_view.setMinimumHeight(120)
        self.whitelist_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.dashboard_alerts = QListWidget()
        self.dashboard_alerts.setObjectName("darkList")
        self.dashboard_alerts.setMinimumHeight(120)
        self.dashboard_alerts.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        middle.addWidget(self.wrap_box("Whitelisted Websites", self.whitelist_view))
        middle.addWidget(self.wrap_box("Recent Alerts", self.dashboard_alerts))
        lay.addLayout(middle)

        self.session_table = QTableWidget(0, 4)
        self.session_table.setObjectName("darkTable")
        self.session_table.setHorizontalHeaderLabels(["User", "Login Time", "Logout Time", "Duration/State"])
        self.session_table.verticalHeader().setVisible(False)
        self.session_table.setAlternatingRowColors(True)
        self.session_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.session_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.session_table.setMinimumHeight(170)
        self.session_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.wrap_box("Session Logs", self.session_table))

        controls = QHBoxLayout()
        controls.setSpacing(8)
        terminate = QPushButton("Terminate Session")
        terminate.setObjectName("warnButton")
        terminate.clicked.connect(self.terminate_current_session)
        warn = QPushButton("Send Warning")
        warn.setObjectName("warnButton")
        warn.clicked.connect(self.send_warning)
        report = QPushButton("Generate Report")
        report.setObjectName("validateButton")
        report.clicked.connect(self.generate_report)
        settings = QPushButton("System Settings")
        settings.setObjectName("secondaryButton")
        settings.clicked.connect(lambda: self.set_page(2))
        controls.addWidget(terminate)
        controls.addWidget(warn)
        controls.addWidget(report)
        controls.addWidget(settings)
        lay.addLayout(controls)

        tools = QVBoxLayout()
        tools.setSpacing(8)
        self.url = QLineEdit()
        self.url.setObjectName("textInput")
        self.url.setPlaceholderText("Enter URL to validate")
        url_btns = QHBoxLayout()
        v = QPushButton("Validate URL")
        v.setObjectName("validateButton")
        v.clicked.connect(self.validate_url)
        b = QPushButton("Try Blocked URL")
        b.setObjectName("warnButton")
        b.clicked.connect(self.demo_blocked)
        url_btns.addWidget(v)
        url_btns.addWidget(b)

        self.file_name = QLineEdit()
        self.file_name.setObjectName("textInput")
        self.file_name.setPlaceholderText("File name (report.pdf)")
        self.mime = QLineEdit()
        self.mime.setObjectName("textInput")
        self.mime.setPlaceholderText("MIME type (application/pdf)")
        self.source = QLineEdit()
        self.source.setObjectName("textInput")
        self.source.setPlaceholderText("Source URL (https://nptel.ac.in)")
        dv = QPushButton("Validate Download")
        dv.setObjectName("validateButton")
        dv.clicked.connect(self.validate_download)

        tools.addWidget(self.url)
        tools.addLayout(url_btns)
        tools.addWidget(self.file_name)
        tools.addWidget(self.mime)
        tools.addWidget(self.source)
        tools.addWidget(dv, alignment=Qt.AlignLeft)
        lay.addWidget(self.wrap_box("Admin Tools", self._layout_to_widget(tools)))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def sessions_page(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)
        t = QLabel("Session Logs")
        t.setObjectName("pageTitle")
        t.setAlignment(Qt.AlignLeft)
        self.sessions_lbl = QLabel("")
        self.sessions_lbl.setObjectName("pageSub")
        self.sessions_lbl.setAlignment(Qt.AlignLeft)
        c = QPushButton("Simulate Credential Conflict")
        c.setObjectName("warnButton")
        c.clicked.connect(self.sim_conflict)
        lay.addWidget(t)
        lay.addWidget(self.sessions_lbl)
        lay.addWidget(c, alignment=Qt.AlignLeft)
        self.sessions_detail = QListWidget()
        self.sessions_detail.setObjectName("policyList")
        lay.addWidget(self.sessions_detail)
        return p

    def logs_page(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        t = QLabel("Whitelisted Sites & Policy Logs")
        t.setObjectName("pageTitle")
        t.setAlignment(Qt.AlignLeft)
        sub = QLabel("Manage whitelist rules, faculty approvals, and file policy controls.")
        sub.setObjectName("pageSub")
        root.addWidget(t)
        root.addWidget(sub)

        top = QHBoxLayout()
        top.setSpacing(10)

        left_box = QFrame()
        left_box.setObjectName("boxFrame")
        left = QVBoxLayout(left_box)
        left.setContentsMargins(10, 10, 10, 10)
        left.setSpacing(8)
        left_title = QLabel("Whitelist Rule Management")
        left_title.setObjectName("boxTitle")

        self.rule = QLineEdit()
        self.rule.setObjectName("textInput")
        self.rule.setPlaceholderText("Add whitelist rule: domain.com or *.college.edu")
        add = QPushButton("Add Whitelist Rule")
        add.setObjectName("validateButton")
        add.clicked.connect(self.add_rule)

        self.whitelist_rules_view = QListWidget()
        self.whitelist_rules_view.setObjectName("policyList")
        self.whitelist_rules_view.setMinimumHeight(220)

        left.addWidget(left_title)
        left.addWidget(self.rule)
        left.addWidget(add, alignment=Qt.AlignLeft)
        left.addWidget(self.whitelist_rules_view)
        top.addWidget(left_box, 1)

        right_box = QFrame()
        right_box.setObjectName("boxFrame")
        right = QVBoxLayout(right_box)
        right.setContentsMargins(10, 10, 10, 10)
        right.setSpacing(8)
        right_title = QLabel("Faculty / File Policy Controls")
        right_title.setObjectName("boxTitle")

        self.faculty_domain = QLineEdit()
        self.faculty_domain.setObjectName("textInput")
        self.faculty_domain.setPlaceholderText("Faculty approval domain (python.org)")
        self.faculty_ext = QLineEdit()
        self.faculty_ext.setObjectName("textInput")
        self.faculty_ext.setPlaceholderText("Extension (.exe, .zip)")
        self.faculty_minutes = QLineEdit()
        self.faculty_minutes.setObjectName("textInput")
        self.faculty_minutes.setPlaceholderText("Approval window in minutes (e.g., 60)")
        self.faculty_lab_scope = QLineEdit()
        self.faculty_lab_scope.setObjectName("textInput")
        self.faculty_lab_scope.setPlaceholderText("Lab scope (default *)")
        self.faculty_pc_scope = QLineEdit()
        self.faculty_pc_scope.setObjectName("textInput")
        self.faculty_pc_scope.setPlaceholderText("PC scope (default *)")
        grant = QPushButton("Grant Temporary Faculty Approval")
        grant.setObjectName("warnButton")
        grant.clicked.connect(self.add_faculty_approval)

        self.allow_ext = QLineEdit()
        self.allow_ext.setObjectName("textInput")
        self.allow_ext.setPlaceholderText("Allow extension (.pdf, .zip)")
        allow_btn = QPushButton("Allow File Type")
        allow_btn.setObjectName("validateButton")
        allow_btn.clicked.connect(self.add_allowed_extension)

        self.block_ext = QLineEdit()
        self.block_ext.setObjectName("textInput")
        self.block_ext.setPlaceholderText("Block extension (.exe, .msi)")
        self.block_reason = QLineEdit()
        self.block_reason.setObjectName("textInput")
        self.block_reason.setPlaceholderText("Block reason (optional)")
        block_btn = QPushButton("Block File Type")
        block_btn.setObjectName("warnButton")
        block_btn.clicked.connect(self.add_blocked_extension)

        right.addWidget(right_title)
        right.addWidget(self.faculty_domain)
        right.addWidget(self.faculty_ext)
        right.addWidget(self.faculty_minutes)
        right.addWidget(self.faculty_lab_scope)
        right.addWidget(self.faculty_pc_scope)
        right.addWidget(grant, alignment=Qt.AlignLeft)
        right.addSpacing(6)
        right.addWidget(self.allow_ext)
        right.addWidget(allow_btn, alignment=Qt.AlignLeft)
        right.addWidget(self.block_ext)
        right.addWidget(self.block_reason)
        right.addWidget(block_btn, alignment=Qt.AlignLeft)
        right.addStretch()
        top.addWidget(right_box, 1)

        root.addLayout(top)

        logs_box = QFrame()
        logs_box.setObjectName("boxFrame")
        logs_lay = QVBoxLayout(logs_box)
        logs_lay.setContentsMargins(10, 10, 10, 10)
        logs_lay.setSpacing(8)
        logs_title = QLabel("Policy Event Logs")
        logs_title.setObjectName("boxTitle")
        self.logs = QListWidget()
        self.logs.setObjectName("policyList")
        self.logs.setMinimumHeight(300)
        logs_lay.addWidget(logs_title)
        logs_lay.addWidget(self.logs)
        root.addWidget(logs_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        return scroll

    def alerts_page(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        t = QLabel("Alerts & Actions")
        t.setObjectName("pageTitle")
        self.alert_sub = QLabel("Active alerts, severity view, and response actions.")
        self.alert_sub.setObjectName("pageSub")

        self.alerts_table = QTableWidget(0, 5)
        self.alerts_table.setObjectName("darkTable")
        self.alerts_table.setHorizontalHeaderLabels(["Time", "User", "PC/Station", "Alert Type", "Severity"])
        self.alerts_table.verticalHeader().setVisible(False)
        self.alerts_table.setAlternatingRowColors(True)
        self.alerts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.alerts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.alerts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        b1 = QPushButton("Terminate Session")
        b1.setObjectName("warnButton")
        b1.clicked.connect(self.terminate_current_session)
        b2 = QPushButton("Send Warning")
        b2.setObjectName("warnButton")
        b2.clicked.connect(self.send_warning)
        b3 = QPushButton("Mark All Reviewed")
        b3.setObjectName("validateButton")
        b3.clicked.connect(lambda: self.on_alert("info", "All visible alerts marked as reviewed"))
        controls.addWidget(b1)
        controls.addWidget(b2)
        controls.addWidget(b3)
        controls.addStretch()

        self.alert_actions_log = QListWidget()
        self.alert_actions_log.setObjectName("policyList")

        lay.addWidget(t)
        lay.addWidget(self.alert_sub)
        lay.addWidget(self.wrap_box("Active Alerts and Violations", self.alerts_table))
        lay.addLayout(controls)
        lay.addWidget(self.wrap_box("Recent Actions Log", self.alert_actions_log))
        return p

    def admin_tools_page(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        t = QLabel("Admin Tools")
        t.setObjectName("pageTitle")
        sub = QLabel("Operational controls, policy operations, reporting, and maintenance.")
        sub.setObjectName("pageSub")

        grid_wrap = QFrame()
        grid_wrap.setObjectName("boxFrame")
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cards = [
            ("User Management", lambda: self.popup("Admin Tool", "User management module placeholder.")),
            ("Policy Configuration", lambda: self.set_page(2)),
            ("Violation Reports", self.generate_report),
            ("DB Maintenance", lambda: self.on_alert("info", "Database maintenance check completed")),
            ("System Commands", lambda: self.popup("System Commands", "Controlled command module placeholder.")),
            ("Scheduled Tasks", lambda: self.on_alert("info", "Scheduled sync/cleanup tasks executed")),
            ("Backup & Restore", lambda: self.on_alert("info", "Backup and restore workflow placeholder")),
            ("Debug Terminal", lambda: self.popup("Debug Terminal", "Restricted debug console placeholder.")),
        ]
        for idx, (label, handler) in enumerate(cards):
            btn = QPushButton(label)
            btn.setObjectName("secondaryButton")
            btn.setMinimumHeight(58)
            btn.clicked.connect(handler)
            grid.addWidget(btn, idx // 4, idx % 4)

        self.tools_activity = QListWidget()
        self.tools_activity.setObjectName("policyList")

        lay.addWidget(t)
        lay.addWidget(sub)
        lay.addWidget(self.wrap_box("Active Alerts and Violations", grid_wrap))
        lay.addWidget(self.wrap_box("Security Settings & Recent Admin Actions", self.tools_activity))
        return p

    def _layout_to_widget(self, layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def _build_ops_panel(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        self.rank_value = QLabel("Level 1 | Observer")
        self.rank_value.setObjectName("scoreValue")
        self.xp_value = QLabel("XP 0 / 150")
        self.xp_value.setObjectName("scoreMeta")
        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("scoreBar")
        self.xp_bar.setRange(0, 150)
        self.xp_bar.setValue(0)
        self.xp_bar.setFormat("%v / %m")

        lay.addWidget(self.rank_value)
        lay.addWidget(self.xp_value)
        lay.addWidget(self.xp_bar)
        return p

    def _build_threat_panel(self):
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(8)

        self.security_value = QLabel("Security Score 100")
        self.security_value.setObjectName("scoreValue")
        self.streak_value = QLabel("Clean Streak: 0 events")
        self.streak_value.setObjectName("scoreMeta")
        self.security_bar = QProgressBar()
        self.security_bar.setObjectName("scoreBar")
        self.security_bar.setRange(0, 100)
        self.security_bar.setValue(100)
        self.security_bar.setFormat("%p%")

        self.threat_value = QLabel("Threat Load: 0")
        self.threat_value.setObjectName("scoreMeta")
        self.threat_bar = QProgressBar()
        self.threat_bar.setObjectName("threatBar")
        self.threat_bar.setRange(0, 100)
        self.threat_bar.setValue(0)
        self.threat_bar.setFormat("%p%")

        lay.addWidget(self.security_value)
        lay.addWidget(self.streak_value)
        lay.addWidget(self.security_bar)
        lay.addWidget(self.threat_value)
        lay.addWidget(self.threat_bar)
        return p

    def create_status_card(self, title, value, border_color):
        card = QFrame()
        card.setObjectName("dashCard")
        card.setStyleSheet(f"#dashCard{{border-left:4px solid {border_color};}}")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        icon_map = {
            "Active Users": "👥",
            "Blocked Attempts": "⚠",
            "Current Downloads": "⬇",
            "System Status": "🛡",
        }
        icon = icon_map.get(title, "•")
        t = QLabel(f"{icon}  {title}")
        t.setObjectName("cardTitle")
        v = QLabel(value)
        v.setObjectName("cardValue")
        card.value_label = v
        lay.addWidget(t)
        lay.addWidget(v)
        return card

    def wrap_box(self, title, widget):
        frame = QFrame()
        frame.setObjectName("boxFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("boxTitle")
        lay.addWidget(label)
        lay.addWidget(widget)
        return frame

    def setup_enforcement(self):
        self.enforce_thread = QThread(self)
        self.enforce = EnforcementWorker(self.auth, self.policy, self.download, self.sid, 1200, 20)
        self.enforce.moveToThread(self.enforce_thread)
        self.enforce_thread.started.connect(self.enforce.start)
        self.ping.connect(self.enforce.mark_activity)
        self.submit_url.connect(self.enforce.submit_url)
        self.submit_dl.connect(self.enforce.submit_download)
        self.stop_enforce.connect(self.enforce.stop)
        self.enforce.countdown_changed.connect(self.on_countdown)
        self.enforce.inactivity_timeout.connect(self.on_timeout)
        self.enforce.url_result.connect(self.on_url_result)
        self.enforce.download_result.connect(self.on_download_result)
        self.enforce.admin_alert.connect(self.on_alert)
        self.enforce.heartbeat_status.connect(self.on_hb)
        self.enforce_thread.start()
        self.ping.emit()

    def setup_sync(self):
        self.sync_thread = QThread(self)
        self.sync_worker = SyncWorker(self.db)
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_thread.started.connect(self.sync_worker.start)
        self.stop_sync.connect(self.sync_worker.stop)
        self.sync_worker.status_changed.connect(self.sync.setText)
        self.sync_worker.admin_alert.connect(self.on_alert)
        self.sync_thread.start()

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon), self)
        m = QMenu(self)
        a1 = QAction("Open Admin Panel", self)
        a2 = QAction("Shutdown Session", self)
        a3 = QAction("Emergency Exit", self)
        a1.triggered.connect(self.restore)
        a2.triggered.connect(self.shutdown_session)
        a3.triggered.connect(self.emergency_exit)
        m.addAction(a1)
        m.addAction(a2)
        m.addSeparator()
        m.addAction(a3)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.restore()

    def restore(self):
        self.showFullScreen() if self.kiosk else self.showNormal()
        self.raise_()
        self.activateWindow()

    def popup(self, title, msg, critical=False):
        b = QMessageBox(self)
        b.setWindowTitle(title)
        b.setText(msg)
        b.setIcon(QMessageBox.Critical if critical else QMessageBox.Warning)
        b.exec()

    def log(self, level, category, message, payload=None):
        self.db.log(level, category, message, payload or {})
        line = f"[{stamp()}] {level.upper()} {category.upper()}  {message}"
        self.logs.insertItem(0, QListWidgetItem(line))
        if hasattr(self, "dashboard_alerts"):
            self.dashboard_alerts.insertItem(0, QListWidgetItem(line))
            while self.dashboard_alerts.count() > 50:
                self.dashboard_alerts.takeItem(self.dashboard_alerts.count() - 1)
        self.alert_window.add(level, f"{category.upper()}  {message}")
        self.update_dashboard_metrics()
        self.refresh_alerts_actions_views()

    def load_logs(self):
        self.logs.clear()
        if hasattr(self, "dashboard_alerts"):
            self.dashboard_alerts.clear()
        for r in self.db.recent_logs(120):
            t = r["created_at"].replace("T", " ").replace("Z", "")
            text = f"[{t}] {r['level']} {r['category']}  {r['message']}"
            self.logs.addItem(text)
            if hasattr(self, "dashboard_alerts"):
                self.dashboard_alerts.addItem(text)
        self.refresh_whitelist_view()
        self.update_dashboard_metrics()
        self.refresh_session_table()
        self.refresh_alerts_actions_views()

    def refresh_sessions(self):
        users = self.auth.active_users()
        self.sessions_lbl.setText(f"Current Session: {self.username} | Active IDs: {', '.join(users) if users else 'None'}")
        if hasattr(self, "sessions_detail"):
            self.sessions_detail.clear()
            for user in users:
                self.sessions_detail.addItem(f"{user} - ACTIVE")
            rows = self.db.recent_sessions(8)
            for row in rows:
                started = (row["started_at"] or "").replace("T", " ").replace("Z", "")
                status = row["status"] or "-"
                self.sessions_detail.addItem(f"{row['username']} | {started} | {status}")
        self.refresh_session_table()
        self.update_dashboard_metrics()

    def refresh_session_table(self):
        if not hasattr(self, "session_table"):
            return
        rows = self.db.recent_sessions(10)
        self.session_table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            started = (row["started_at"] or "").replace("T", " ").replace("Z", "")
            ended = (row["ended_at"] or "-").replace("T", " ").replace("Z", "")
            state = row["status"] if row["status"] else "-"
            if row["end_reason"]:
                state = f"{state} ({row['end_reason']})"
            self.session_table.setItem(row_idx, 0, QTableWidgetItem(row["username"]))
            self.session_table.setItem(row_idx, 1, QTableWidgetItem(started))
            self.session_table.setItem(row_idx, 2, QTableWidgetItem(ended))
            self.session_table.setItem(row_idx, 3, QTableWidgetItem(state))
        self.session_table.resizeRowsToContents()

    def refresh_whitelist_view(self):
        dash_exists = hasattr(self, "whitelist_view")
        logs_exists = hasattr(self, "whitelist_rules_view")
        if not dash_exists and not logs_exists:
            return
        if dash_exists:
            self.whitelist_view.clear()
        if logs_exists:
            self.whitelist_rules_view.clear()
        exact_rules = sorted(self.policy.exact)
        suffix_rules = sorted(self.policy.suffix)
        repo_rules = sorted(self.policy.internal_repo)
        for value in exact_rules:
            if dash_exists:
                self.whitelist_view.addItem(value)
            if logs_exists:
                self.whitelist_rules_view.addItem(value)
        for value in suffix_rules:
            if dash_exists:
                self.whitelist_view.addItem(f"*{value}")
            if logs_exists:
                self.whitelist_rules_view.addItem(f"*{value}")
        for value in repo_rules:
            text = f"[REPO] {value}"
            if dash_exists:
                self.whitelist_view.addItem(text)
            if logs_exists:
                self.whitelist_rules_view.addItem(text)

    def refresh_alerts_actions_views(self):
        logs = self.db.recent_logs(220)
        if hasattr(self, "alerts_table"):
            alerts = []
            for r in logs:
                lvl = (r["level"] or "").upper()
                cat = (r["category"] or "").upper()
                if lvl in {"CRITICAL", "WARNING"} or cat in {"ALERT", "ENFORCE"}:
                    alerts.append(r)
            self.alerts_table.setRowCount(len(alerts[:80]))
            for i, r in enumerate(alerts[:80]):
                ts = (r["created_at"] or "").replace("T", " ").replace("Z", "")
                sev = "HIGH" if (r["level"] or "").upper() == "CRITICAL" else "MEDIUM"
                self.alerts_table.setItem(i, 0, QTableWidgetItem(ts))
                self.alerts_table.setItem(i, 1, QTableWidgetItem(self.username))
                self.alerts_table.setItem(i, 2, QTableWidgetItem(self.auth.machine_id))
                self.alerts_table.setItem(i, 3, QTableWidgetItem(f"{r['category']}  {r['message']}"))
                self.alerts_table.setItem(i, 4, QTableWidgetItem(sev))
            if hasattr(self, "alert_sub"):
                self.alert_sub.setText(f"Active alerts shown: {min(len(alerts), 80)}")

        if hasattr(self, "alert_actions_log"):
            self.alert_actions_log.clear()
            for r in logs[:35]:
                text = f"[{(r['created_at'] or '').replace('T', ' ').replace('Z', '')}] {r['category']}  {r['message']}"
                self.alert_actions_log.addItem(text)

        if hasattr(self, "tools_activity"):
            self.tools_activity.clear()
            for r in logs[:30]:
                text = f"{r['level']}  {r['category']}  {r['message']}"
                self.tools_activity.addItem(text)

    def update_dashboard_metrics(self):
        if not hasattr(self, "card_active"):
            return
        active_users = len(self.auth.active_users())
        logs = self.db.recent_logs(200)
        blocked_attempts = sum(1 for r in logs if (r["level"] or "").upper() == "CRITICAL")
        warning_attempts = sum(1 for r in logs if (r["level"] or "").upper() == "WARNING")
        download_events = sum(1 for r in logs if (r["category"] or "").upper() == "DOWNLOAD")

        url_allowed = 0
        dl_allowed = 0
        auth_success = 0
        clean_streak = 0
        for row in logs:
            msg = (row["message"] or "").lower()
            cat = (row["category"] or "").upper()
            lvl = (row["level"] or "").upper()
            if "url allowed" in msg:
                url_allowed += 1
            if cat == "DOWNLOAD" and "allowed" in msg:
                dl_allowed += 1
            if cat == "AUTH" and "login successful" in msg:
                auth_success += 1
            if lvl == "CRITICAL":
                break
            clean_streak += 1

        reward_actions = min(25, url_allowed + dl_allowed + auth_success)
        security_score = max(0, min(100, 100 - blocked_attempts * 12 - warning_attempts * 4 + reward_actions))
        threat_load = max(0, min(100, blocked_attempts * 20 + warning_attempts * 8))
        xp = max(0, active_users * 40 + reward_actions * 16 - blocked_attempts * 30 - warning_attempts * 8)
        level = 1 + (xp // 150)
        level_tier = min(level, 6)
        rank_titles = {
            1: "Observer",
            2: "Guardian",
            3: "Sentinel",
            4: "Warden",
            5: "Commander",
            6: "Vanguard",
        }
        rank = rank_titles.get(level_tier, "Vanguard")
        xp_progress = xp % 150

        self.card_active.value_label.setText(f"{active_users} Online")
        self.card_blocked.value_label.setText(f"{blocked_attempts} Violations")
        self.card_downloads.value_label.setText(f"{download_events} Files")
        self.card_state.value_label.setText(f"L{level} {rank}")

        if hasattr(self, "rank_value"):
            self.rank_value.setText(f"Level {level} | {rank}")
            self.xp_value.setText(f"XP {xp_progress} / 150")
            self.xp_bar.setValue(xp_progress)
        if hasattr(self, "security_value"):
            self.security_value.setText(f"Security Score {security_score}")
            self.streak_value.setText(f"Clean Streak: {clean_streak} events")
            self.security_bar.setValue(security_score)
            self.threat_value.setText(f"Threat Load: {threat_load}")
            self.threat_bar.setValue(threat_load)
        if hasattr(self, "score_chip"):
            self.score_chip.setText(f"Score {security_score}")
        self._update_alert_badge()

    def _update_alert_badge(self):
        if not hasattr(self, "alerts_chip"):
            return
        alert_count = self.alert_window.list.count() if hasattr(self.alert_window, "list") else 0
        self.alerts_chip.setText(f"Open Alerts ({alert_count})")

    def update_header_for_nav(self, title):
        self.welcome.setText(
            f"{title}   |   Welcome, {self.username}   |   {self.db.lab_id}"
        )

    def set_page(self, idx):
        self.stack.setCurrentIndex(idx)
        nav_idx = None
        for i, mapped in enumerate(self.nav_page_map):
            if mapped == idx:
                nav_idx = i
                break
        for i, b in enumerate(self.menu):
            b.setProperty("active", i == nav_idx)
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()
        if nav_idx is not None and nav_idx < len(self.nav_header_map):
            self.update_header_for_nav(self.nav_header_map[nav_idx])
        self.ping.emit()

    def handle_nav_click(self, nav_idx):
        target_page = self.nav_page_map[nav_idx]
        self.stack.setCurrentIndex(target_page)
        for i, b in enumerate(self.menu):
            b.setProperty("active", i == nav_idx)
            b.style().unpolish(b)
            b.style().polish(b)
            b.update()
        if nav_idx < len(self.nav_header_map):
            self.update_header_for_nav(self.nav_header_map[nav_idx])
        if self.nav_alert_map[nav_idx]:
            self.show_alerts_window()
        if target_page == 0 and hasattr(self, "url"):
            self.url.setFocus()
        if target_page == 2 and hasattr(self, "rule"):
            self.rule.setFocus()
        self.ping.emit()

    def toggle_alerts(self):
        if self.alert_window.isVisible():
            self.alert_window.hide()
        else:
            self.show_alerts_window()
        self.ping.emit()

    def show_alerts_window(self):
        self.alert_window.show()
        self.alert_window.raise_()
        self.alert_window.activateWindow()

    def toggle_kiosk(self):
        self.kiosk = self.kiosk_btn.isChecked()
        self.kiosk_btn.setText("Exit Kiosk" if self.kiosk else "Enter Kiosk")
        flags = self.windowFlags()
        if self.kiosk:
            self.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
            self.showFullScreen()
            self.log("INFO", "UI", "Kiosk mode enabled")
        else:
            self.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
            self.showNormal()
            self.log("INFO", "UI", "Kiosk mode disabled")
        self.show()
        self.ping.emit()

    def validate_url(self):
        text = self.url.text().strip()
        if not text:
            self.popup("Missing URL", "Enter a URL to validate.")
            return
        self.submit_url.emit(text)
        self.log("INFO", "POLICY", f"URL submitted: {text}")
        self.url.clear()
        self.ping.emit()

    def demo_blocked(self):
        u = "https://youtube.com/watch?v=blocked-demo"
        self.submit_url.emit(u)
        self.log("INFO", "POLICY", f"URL submitted: {u}")
        self.ping.emit()

    def validate_download(self):
        f = self.file_name.text().strip()
        m = self.mime.text().strip()
        s = self.source.text().strip()
        if not f or not s:
            self.popup("Missing Fields", "File name and source URL are required.")
            return
        self.submit_dl.emit(f, m, s)
        self.log("INFO", "DOWNLOAD", f"Download submitted: {f}", {"source": s, "mime": m})
        self.file_name.clear()
        self.mime.clear()
        self.source.clear()
        self.ping.emit()

    def on_url_result(self, url, allowed, reason):
        if allowed:
            self.log("INFO", "POLICY", f"URL allowed: {url}")
        else:
            self.log("CRITICAL", "POLICY", f"URL blocked: {url} ({reason})")
            self.enforce_policy_violation("DOMAIN", domain_of(url) or url, reason)

    def on_download_result(self, file_name, allowed, reason, mime_type, source_url, approval_ref):
        self.db.add_download_attempt(
            self.sid,
            file_name,
            mime_type,
            source_url,
            "allowed" if allowed else "blocked",
            reason,
            approval_ref,
        )
        if allowed:
            self.log("INFO", "DOWNLOAD", f"Download allowed: {file_name}", {"source": source_url, "approval": approval_ref})
        else:
            self.log("CRITICAL", "DOWNLOAD", f"Download blocked: {file_name} ({reason})")
            self.enforce_policy_violation("DOWNLOAD", file_name, reason)

    def enforce_policy_violation(self, violation_type, resource, reason):
        if self.session_closed or self.closing_for_logout or self.termination_pending:
            return
        self.termination_pending = True
        self.db.mark_session_violation(self.sid, f"{violation_type}: {reason}")
        self.db.add_violation(self.sid, violation_type, resource, reason, severity="HIGH")
        alert_line = (
            f"Student:{self.username} | Lab:{self.db.lab_id} | PC:{self.auth.machine_id} | "
            f"Violation:{violation_type} | Resource:{resource} | Time:{stamp()}"
        )
        self.on_alert("critical", alert_line)
        self.log(
            "CRITICAL",
            "ENFORCE",
            f"Immediate session termination due to {violation_type} violation",
            {"resource": resource, "reason": reason, "sid": self.sid},
        )
        QTimer.singleShot(0, lambda: self.end_session("policy_violation"))

    def sim_conflict(self):
        msg = f"Credential conflict detected for ID '{self.username}'."
        self.popup("Credential Conflict", msg, critical=True)
        self.log("WARNING", "AUTH", msg)
        self.ping.emit()

    def add_rule(self):
        raw = self.rule.text().strip()
        if not raw:
            self.popup("Missing Rule", "Enter a domain rule to add.")
            return
        if self.policy.add_rule(raw):
            self.log("INFO", "POLICY", f"Whitelist rule added: {raw}")
            self.refresh_whitelist_view()
            self.rule.clear()
        else:
            self.popup("Rule Error", "Rule could not be added.")
        self.ping.emit()

    def add_allowed_extension(self):
        ext = self.allow_ext.text().strip()
        ok, msg = self.db.add_allowed_extension(ext)
        if ok:
            self.log("INFO", "POLICY", msg)
            self.allow_ext.clear()
        else:
            self.popup("Policy Error", msg, critical=True)
        self.ping.emit()

    def add_blocked_extension(self):
        ext = self.block_ext.text().strip()
        reason = self.block_reason.text().strip() or "Blocked by policy"
        ok, msg = self.db.add_blocked_extension(ext, reason=reason)
        if ok:
            self.log("INFO", "POLICY", msg, {"reason": reason})
            self.block_ext.clear()
            self.block_reason.clear()
        else:
            self.popup("Policy Error", msg, critical=True)
        self.ping.emit()

    def add_faculty_approval(self):
        domain = self.faculty_domain.text().strip()
        ext = self.faculty_ext.text().strip()
        minutes = self.faculty_minutes.text().strip()
        lab_scope = self.faculty_lab_scope.text().strip() or "*"
        pc_scope = self.faculty_pc_scope.text().strip() or "*"
        ok, msg = self.db.add_faculty_approval(
            domain,
            ext,
            minutes,
            created_by=self.username,
            lab_scope=lab_scope,
            pc_scope=pc_scope,
        )
        if ok:
            self.log(
                "INFO",
                "POLICY",
                f"Faculty approval added: {domain} {ext}",
                {"expires": msg, "lab_scope": lab_scope, "pc_scope": pc_scope},
            )
            self.popup("Approval Active", msg)
            self.faculty_domain.clear()
            self.faculty_ext.clear()
            self.faculty_minutes.clear()
            self.faculty_lab_scope.clear()
            self.faculty_pc_scope.clear()
        else:
            self.popup("Approval Error", msg, critical=True)
        self.ping.emit()

    def terminate_current_session(self):
        self.popup("Terminate Session", "Current session will be terminated.", critical=True)
        self.log("WARNING", "AUTH", f"Session terminated by admin control for {self.username}")
        self.end_session("terminated_by_admin")

    def send_warning(self):
        self.popup("Warning Broadcast", "Warning message sent to monitored clients.")
        self.log("WARNING", "ALERT", "Manual warning broadcast issued")

    def generate_report(self):
        report_name = f"arbitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        report_path = Path(report_name)
        sessions = self.db.all_sessions(800)
        violations = self.db.recent_violations(400)
        recent_logs = self.db.recent_logs(120)

        def parse_iso(ts):
            if not ts:
                return None
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                return None

        student_stats = {}
        pc_stats = {}
        total_seconds = 0
        for row in sessions:
            user = row["username"] or "-"
            pc = row["machine_id"] or "-"
            start_dt = parse_iso(row["started_at"])
            end_dt = parse_iso(row["ended_at"]) or parse_iso(row["started_at"])
            seconds = int((end_dt - start_dt).total_seconds()) if start_dt and end_dt and end_dt >= start_dt else 0
            total_seconds += seconds

            su = student_stats.setdefault(user, {"sessions": 0, "seconds": 0})
            su["sessions"] += 1
            su["seconds"] += seconds

            sp = pc_stats.setdefault(pc, {"sessions": 0, "seconds": 0})
            sp["sessions"] += 1
            sp["seconds"] += seconds

        violation_stats = {}
        for row in violations:
            key = row["violation_type"] or "UNKNOWN"
            violation_stats[key] = violation_stats.get(key, 0) + 1

        lines = [
            "Arbitor Admin Report",
            f"Generated: {datetime.now().isoformat(sep=' ', timespec='seconds')}",
            f"Operator: {self.username}",
            f"Lab: {self.db.lab_id}",
            f"PC: {self.auth.machine_id}",
            "",
            "Summary:",
            f"  Sessions analyzed: {len(sessions)}",
            f"  Violations analyzed: {len(violations)}",
            f"  Total usage time: {total_seconds // 3600}h {(total_seconds % 3600) // 60}m",
            "",
            "Student-Wise Usage:",
        ]
        if student_stats:
            for user, stat in sorted(student_stats.items(), key=lambda x: (-x[1]["seconds"], x[0])):
                lines.append(
                    f"  {user}: sessions={stat['sessions']}, usage={stat['seconds'] // 3600}h {(stat['seconds'] % 3600) // 60}m"
                )
        else:
            lines.append("  No session data.")

        lines.extend([
            "",
            "PC-Wise Usage:",
        ])
        if pc_stats:
            for pc, stat in sorted(pc_stats.items(), key=lambda x: (-x[1]["seconds"], x[0])):
                lines.append(
                    f"  {pc}: sessions={stat['sessions']}, usage={stat['seconds'] // 3600}h {(stat['seconds'] % 3600) // 60}m"
                )
        else:
            lines.append("  No PC usage data.")

        lines.extend([
            "",
            "Violation Frequency:",
        ])
        if violation_stats:
            for vtype, count in sorted(violation_stats.items(), key=lambda x: (-x[1], x[0])):
                lines.append(f"  {vtype}: {count}")
        else:
            lines.append("  No violations.")

        lines.extend([
            "",
            "Recent Logs:",
        ])
        for row in recent_logs[:60]:
            created = row["created_at"].replace("T", " ").replace("Z", "")
            lines.append(f"[{created}] {row['level']} {row['category']}  {row['message']}")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self.log("INFO", "REPORT", f"Report generated: {report_path}")
        self.popup("Report Generated", f"Report saved as:\n{report_path}")

    def on_countdown(self, secs):
        self.count.setText(f"Auto logout in {secs}s")
        self.count.setVisible(True)

    def on_hb(self, text):
        self.hb.setText(text)

    def on_timeout(self):
        if self.awaiting_dialog:
            return
        self.awaiting_dialog = True
        r = InactivityDialog(12, self).exec()
        self.awaiting_dialog = False
        if r == QDialog.Accepted:
            self.count.setVisible(False)
            self.log("INFO", "AUTH", "Session continued after inactivity warning")
            self.ping.emit()
        else:
            self.log("WARNING", "AUTH", "Session ended by inactivity timeout")
            self.end_session("inactivity_timeout")

    def on_alert(self, level, message):
        self.alert_window.add(level, message)
        if hasattr(self, "dashboard_alerts"):
            self.dashboard_alerts.insertItem(0, QListWidgetItem(f"[{stamp()}] {level.upper()}  {message}"))
            while self.dashboard_alerts.count() > 50:
                self.dashboard_alerts.takeItem(self.dashboard_alerts.count() - 1)
        if self.tray is not None:
            icon = QSystemTrayIcon.Warning if level.lower() in {"warning", "critical"} else QSystemTrayIcon.Information
            self.tray.showMessage("Arbitor Admin Alert", message, icon, 2800)
        self.update_dashboard_metrics()
        self.refresh_alerts_actions_views()

    def _close_session(self, reason):
        if self.session_closed:
            return
        self.session_closed = True
        self.auth.end(self.sid, reason)

    def cleanup(self):
        try:
            QApplication.instance().removeEventFilter(self)
        except Exception:
            pass
        if self.tray is not None:
            self.tray.hide()
        if hasattr(self, "refresh_timer") and self.refresh_timer.isActive():
            self.refresh_timer.stop()
        if hasattr(self, "enforce_thread") and self.enforce_thread.isRunning():
            self.stop_enforce.emit()
            self.enforce_thread.quit()
            self.enforce_thread.wait(2500)
        if hasattr(self, "sync_thread") and self.sync_thread.isRunning():
            self.stop_sync.emit()
            self.sync_thread.quit()
            self.sync_thread.wait(2500)
        if self.alert_window.isVisible():
            self.alert_window.close()

    def end_session(self, reason="system_shutdown"):
        self.closing_for_logout = True
        self._close_session(reason)
        self.cleanup()
        QApplication.instance().quit()

    def shutdown_session(self):
        b = QMessageBox(self)
        b.setWindowTitle("Shutdown Session")
        b.setText("This will terminate the active session and close the application.")
        b.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        b.setDefaultButton(QMessageBox.No)
        if b.exec() == QMessageBox.Yes:
            self.log("INFO", "AUTH", "Session terminated by controlled shutdown")
            self.end_session("system_shutdown")

    def logout(self, reason="manual_logout"):
        self.end_session(reason)

    def emergency_exit(self):
        self.closing_for_logout = True
        self.auth.suspend(self.sid, "unexpected_exit")
        self.cleanup()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self.kiosk and not self.closing_for_logout:
            self.popup("Kiosk Mode Active", "Disable kiosk mode or use SHUTDOWN from the panel.")
            event.ignore()
            return
        if not self.closing_for_logout:
            self.auth.suspend(self.sid, "window_closed_unexpected")
        self.cleanup()
        event.accept()

    def eventFilter(self, watched, event):
        if self.isVisible() and not self.awaiting_dialog:
            if event.type() in {QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.KeyPress, QEvent.Wheel, QEvent.TouchBegin}:
                self.count.setVisible(False)
                self.ping.emit()
        return super().eventFilter(watched, event)
