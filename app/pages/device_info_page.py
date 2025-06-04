from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter, QLabel
)

from app.components.log_display import LogDisplay
from app.models.config.global_config import global_config
from app.widgets.basic_info_widget import BasicInfoWidget
from app.widgets.resource_widget import ResourceWidget
from app.widgets.task_settings_widget import TaskSettingsWidget


class DeviceInfoPage(QWidget):
    """Device information page with three-column layout, first and third columns split vertically"""

    def __init__(self, device_name, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = global_config.get_device_config(device_name)
        self.selected_resource_name = None
        self.task_option_widgets = {}

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # Set widget style
        self.setObjectName("content_widget")

        # Main horizontal splitter (3 parts)
        self.horizontal_splitter = QSplitter(Qt.Horizontal)
        self.horizontal_splitter.setObjectName("horizontalSplitter")
        self.horizontal_splitter.setHandleWidth(0)
        self.horizontal_splitter.setChildrenCollapsible(False)

        # Create widgets
        self.basic_info_widget = BasicInfoWidget(self.device_name, self.device_config, self)
        self.resource_widget = ResourceWidget(self.device_name, self.device_config, self)
        self.task_settings_widget = TaskSettingsWidget(self.device_config, self)
        self.log_widget = LogDisplay(enable_log_level_filter=True, show_device_selector=False)
        self.log_widget.show_device_logs(self.device_name)

        # Connect signals
        self.resource_widget.resource_selected.connect(self.task_settings_widget.show_resource_settings)
        # Connect the new resource status changed signal
        self.resource_widget.resource_status_changed.connect(self.task_settings_widget.update_resource_status)

        # 1. First Part (Left): Resource Selection (top) + Task Settings (bottom)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # Vertical splitter for left part
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setObjectName("leftSplitter")
        self.left_splitter.setHandleWidth(0)
        self.left_splitter.setChildrenCollapsible(False)

        # Add Resource Selection on top, Task Settings on bottom
        self.left_splitter.addWidget(self.resource_widget)
        self.left_splitter.addWidget(self.task_settings_widget)

        # Set initial sizes for left splitter (1:1 ratio)
        self.left_splitter.setSizes([250, 250])

        left_layout.addWidget(self.left_splitter)

        # 2. Second Part (Middle): New Empty Container
        self.empty_container = QWidget()
        self.empty_container.setObjectName("emptyContainer")
        empty_layout = QVBoxLayout(self.empty_container)
        empty_layout.setContentsMargins(10, 10, 10, 10)

        # Add a placeholder label
        placeholder_label = QLabel("新容器\n(暂时为空)")
        placeholder_label.setAlignment(Qt.AlignCenter)
        placeholder_label.setStyleSheet("color: #888; font-style: italic;")
        empty_layout.addWidget(placeholder_label)

        # 3. Third Part (Right): Basic Info (top) + Log (bottom)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Vertical splitter for right part
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setObjectName("rightSplitter")
        self.right_splitter.setHandleWidth(0)
        self.right_splitter.setChildrenCollapsible(False)

        # Add Basic Info on top, Log on bottom
        self.right_splitter.addWidget(self.basic_info_widget)
        self.right_splitter.addWidget(self.log_widget)

        # Set initial sizes for right splitter (1:2 ratio for basic info and log)
        self.right_splitter.setSizes([150, 300])

        right_layout.addWidget(self.right_splitter)

        # Add all three parts to horizontal splitter
        self.horizontal_splitter.addWidget(left_widget)
        self.horizontal_splitter.addWidget(self.empty_container)
        self.horizontal_splitter.addWidget(right_widget)

        # Set initial sizes for horizontal splitter (1:1:1 ratio)
        self.horizontal_splitter.setSizes([300, 200, 300])

        main_layout.addWidget(self.horizontal_splitter)

    def refresh_ui(self):
        """Refresh all UI components with updated device config"""
        self.device_config = global_config.get_device_config(self.device_name)
        self.basic_info_widget.refresh_ui(self.device_config)
        self.resource_widget.refresh_ui(self.device_config)
        self.task_settings_widget.clear_settings()