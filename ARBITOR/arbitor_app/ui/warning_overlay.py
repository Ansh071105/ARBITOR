from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, pyqtSignal

class WarningOverlay(QWidget):
    # Emitted when the user clicks the acknowledge button
    acknowledged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Make the background semi-transparent black to dim the screen behind it
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(15, 23, 42, 200);") 
        self.hide() # Hidden until called
        
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # The actual solid message box
        self.box = QFrame()
        self.box.setFixedWidth(400)
        self.box.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                border: 2px solid #EAB308; /* Yellow warning border by default */
                border-radius: 8px;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            QPushButton {
                background-color: #EAB308;
                color: #0F172A;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #CA8A04;
            }
        """)
        
        box_layout = QVBoxLayout(self.box)
        box_layout.setSpacing(20)
        box_layout.setContentsMargins(30, 30, 30, 30)

        # Title
        self.title_label = QLabel("WARNING")
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #EAB308;")
        self.title_label.setAlignment(Qt.AlignCenter)

        # Message
        self.message_label = QLabel("Message goes here.")
        self.message_label.setStyleSheet("font-size: 16px; color: #E2E8F0;")
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)

        # Button
        self.ack_btn = QPushButton("Acknowledge")
        self.ack_btn.clicked.connect(self._handle_ack)

        # Assemble
        box_layout.addWidget(self.title_label)
        box_layout.addWidget(self.message_label)
        box_layout.addWidget(self.ack_btn, alignment=Qt.AlignCenter)

        layout.addWidget(self.box)

    def show_alert(self, title, message, level="warning"):
        """
        Displays the overlay.
        level can be 'warning' (yellow) or 'critical' (red).
        """
        self.title_label.setText(title)
        self.message_label.setText(message)

        if level == "critical":
            self.box.setStyleSheet(self.box.styleSheet().replace("#EAB308", "#EF4444").replace("#CA8A04", "#DC2626"))
            self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #EF4444;")
            self.ack_btn.setStyleSheet("background-color: #EF4444; color: white;")
        else:
            # Reset to warning (yellow) colors
            self.box.setStyleSheet(self.box.styleSheet().replace("#EF4444", "#EAB308").replace("#DC2626", "#CA8A04"))
            self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #EAB308;")
            self.ack_btn.setStyleSheet("background-color: #EAB308; color: #0F172A;")

        # Ensure it covers the whole parent window
        if self.parent():
            self.resize(self.parent().size())
            
        self.raise_() # Force to the very top of the UI stack
        self.show()

    def _handle_ack(self):
        self.hide()
        self.acknowledged.emit()