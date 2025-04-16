from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFrame, QLabel
)

from app.components.log_display import LogDisplay


class DeviceLogWidget(QFrame):
    """Log display widget with automatic update using signals"""

    def __init__(self, device_name, parent=None):
        super().__init__(parent)
        self.device_name = device_name

        self.setObjectName("logFrame")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header with title only (buttons removed)
        header_layout = QHBoxLayout()

        # Section title
        section_title = QLabel("设备日志")
        section_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        section_title.setObjectName("sectionTitle")

        header_layout.addWidget(section_title)
        header_layout.addStretch()

        layout.addLayout(header_layout)


        # Create and configure log display with device logs
        self.log_display = LogDisplay(enable_log_level_filter=True,show_device_selector=False)
        self.log_display.setObjectName("logDisplay")
        self.log_display.show_device_logs(self.device_name)

        layout.addWidget(self.log_display)