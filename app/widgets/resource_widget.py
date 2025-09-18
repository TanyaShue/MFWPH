# app/widgets/resource_widget.py

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox
)

from app.models.config.app_config import Resource, ResourceSettings
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.tasker_manager import task_manager


class ResourceWidget(QFrame):
    """Resource selection widget with table of available resources"""

    # Signal to notify when a resource is selected for configuration
    resource_selected = Signal(str)

    # New signal to notify when a resource's enable status changes
    resource_status_changed = Signal(str, bool)

    def __init__(self, device_name, device_config, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.logger = log_manager.get_device_logger(device_name)
        self.device_config = device_config

        self.setObjectName("resourceFrame")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        # Create resource table
        self.resource_table = self.create_resource_table()
        layout.addWidget(self.resource_table)

    def create_resource_table(self):
        """Create a compact, optimized table for resource selection"""
        # Get all available resources
        all_resources = global_config.get_all_resource_configs()

        # Create mapping of enabled resources for this device
        resource_enabled_map = {}
        if self.device_config and hasattr(self.device_config, 'resources'):
            resource_enabled_map = {r.resource_name: r.enable for r in self.device_config.resources}

        # Create table
        table = QTableWidget(len(all_resources), 3)
        table.setObjectName("resourceTable")
        table.setHorizontalHeaderLabels(["启用", "资源名称", "操作"])

        # Optimize header layout
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        # Set compact column widths
        table.setColumnWidth(0, 40)  # Checkbox column
        table.setColumnWidth(2, 80)  # Action buttons column

        # Streamline table appearance
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.NoFrame)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.NoFocus)
        table.setSelectionMode(QTableWidget.NoSelection)

        for row, resource_config in enumerate(all_resources):
            resource_name = resource_config.resource_name

            # Checkbox for enabling/disabling the resource
            checkbox = QCheckBox()
            checkbox.setChecked(resource_enabled_map.get(resource_name, False))
            checkbox.stateChanged.connect(
                lambda state, r_name=resource_name, cb=checkbox:
                self.update_resource_enable_status(r_name, cb.isChecked())
            )

            # Create a layout-less container for the checkbox
            checkbox_container = QLabel()
            layout = QHBoxLayout(checkbox_container)
            layout.setContentsMargins(4, 0, 0, 0)
            layout.addWidget(checkbox)
            table.setCellWidget(row, 0, checkbox_container)

            # Resource name - smaller font size
            name_item = QTableWidgetItem(resource_name)
            name_item.setFont(QFont("Segoe UI", 10))  # Reduced font size
            table.setItem(row, 1, name_item)

            # Action buttons in a compact container
            button_container = QLabel()
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(4, 0, 4, 0)
            button_layout.setSpacing(4)  # Reduced spacing

            # Create smaller buttons
            run_btn = QPushButton()
            run_btn.setFixedSize(24, 24)  # Smaller size
            run_btn.setIcon(QIcon("assets/icons/play.svg"))
            run_btn.setIconSize(QSize(14, 14))  # Smaller icon
            run_btn.setToolTip("运行此资源")
            run_btn.clicked.connect(lambda checked, r_name=resource_name:
                                    task_manager.run_resource_task(self.device_config.device_name, r_name))

            settings_btn = QPushButton()
            settings_btn.setFixedSize(24, 24)  # Smaller size
            settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
            settings_btn.setIconSize(QSize(14, 14))  # Smaller icon
            settings_btn.setToolTip("配置此资源")
            settings_btn.clicked.connect(lambda checked, r_name=resource_name:
                                         self.show_resource_settings(r_name))

            button_layout.addWidget(run_btn)
            button_layout.addWidget(settings_btn)
            table.setCellWidget(row, 2, button_container)

            # Optimize row height
            table.setRowHeight(row, 32)  # Reduced row height

        # Apply stylesheet for more compact appearance
        table.setStyleSheet("""
            QTableWidget {
                background-color: transparent;
                border: none;
            }
            QTableWidget::item {
                padding: 2px;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                font-size: 10pt;
                border: none;
                border-bottom: 1px solid #d0d0d0;
            }
        """)

        return table

    def _ensure_resource_exists(self, resource_name: str) -> Resource:
        """
        确保资源条目存在于设备的配置中。
        如果不存在，则为其创建一个默认条目及相应的配置方案。
        返回该资源对象。
        """
        # 检查资源是否已存在于此设备的配置中
        resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)
        if resource:
            return resource

        # 如果不存在，则创建它。首先，查找或创建一个默认的配置方案
        self.logger.info(f"资源 {resource_name} 首次在本设备上配置，将创建默认条目。")
        app_config = global_config.get_app_config()

        # 检查此资源是否已存在任何全局配置方案
        existing_settings = next((s for s in app_config.resource_settings if s.resource_name == resource_name), None)

        default_settings_name = ""
        if existing_settings:
            # 如果已存在，则使用找到的第一个作为默认
            default_settings_name = existing_settings.name
        else:
            # 如果不存在任何配置方案，则创建一个新的
            default_settings_name = "默认配置"
            new_settings = ResourceSettings(
                name=default_settings_name,
                resource_name=resource_name
            )
            app_config.resource_settings.append(new_settings)
            self.logger.info(f"为资源 {resource_name} 创建了全局默认配置方案 '{default_settings_name}'。")

        # 为此设备创建新的资源条目，此时 resource_pack 仍为默认的 ""
        new_resource = Resource(
            resource_name=resource_name,
            settings_name=default_settings_name,
            enable=False
        )

        # --- 新增逻辑：检查并设置默认的 resource_pack ---
        # 1. 获取该资源的全局定义
        global_resource_config = global_config.get_resource_config(resource_name)

        # 2. 检查是否存在可用的资源包列表
        if (global_resource_config and
                hasattr(global_resource_config, 'resource_pack') and
                isinstance(global_resource_config.resource_pack, list) and
                len(global_resource_config.resource_pack) > 0):
            # 3. 获取第一个资源包的名称作为默认值
            first_pack = global_resource_config.resource_pack[0]
            if isinstance(first_pack, dict) and 'name' in first_pack:
                default_pack_name = first_pack['name']
                new_resource.resource_pack = default_pack_name
                self.logger.info(f"为资源 {resource_name} 自动选择默认资源包 '{default_pack_name}'。")

        self.device_config.resources.append(new_resource)
        return new_resource

    def update_resource_enable_status(self, resource_name, enabled):
        """更新资源的启用状态"""
        if not self.device_config:
            return

        # 在更新前，确保资源条目已存在
        resource = self._ensure_resource_exists(resource_name)

        # 更新其状态
        resource.enable = enabled

        # 保存更新后的配置
        global_config.save_all_configs()

        # 记录变更
        status_text = "启用" if enabled else "禁用"
        self.logger.info(f"资源 {resource_name} 已{status_text}")

        # 发送信号，通知其他UI组件状态已变更
        self.resource_status_changed.emit(resource_name, enabled)

    def show_resource_settings(self, resource_name):
        """发送信号以显示所选资源的配置界面"""
        # 在显示配置前，确保资源条目已存在
        self._ensure_resource_exists(resource_name)
        # 因为可能创建了新的配置，所以在此处保存一次以确保数据一致性
        global_config.save_all_configs()

        self.resource_selected.emit(resource_name)

    def refresh_ui(self, device_config):
        """Refresh widget with updated device config"""
        self.device_config = device_config
        # Remove current layout and its widgets to prevent duplicates
        old_layout = self.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            # Delete the old layout itself
            del old_layout

        # Reinitialize UI
        self.init_ui()