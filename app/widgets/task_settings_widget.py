from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QToolButton, QPushButton, QStackedWidget
)

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.advanced_settings_page import AdvancedSettingsPage
from app.widgets.basic_settings_page import BasicSettingsPage


class TaskSettingsWidget(QFrame):
    """Task settings widget for configuring resource tasks"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.selected_resource_name = None
        self.status_indicator = None
        self.status_dot = None
        self.status_text = None
        self.current_tab = "basic"  # 跟踪当前显示的标签
        self.resource_header = None  # 添加资源标题和状态指示器容器

        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)

        # Header with title and help button
        header_layout = QHBoxLayout()

        # Section title
        section_title = QLabel("任务设置")
        section_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        section_title.setObjectName("sectionTitle")

        # Help button
        help_btn = QToolButton()
        help_btn.setIcon(QIcon("assets/icons/help.svg"))
        help_btn.setIconSize(QSize(16, 16))
        help_btn.setToolTip("任务设置帮助")
        help_btn.setObjectName("helpButton")

        header_layout.addWidget(section_title)
        header_layout.addStretch()
        header_layout.addWidget(help_btn)

        self.layout.addLayout(header_layout)

        # 添加资源标题和状态指示器区域
        self.resource_header = QWidget()
        self.resource_header.setVisible(False)  # 初始隐藏，直到选择资源
        resource_header_layout = QHBoxLayout(self.resource_header)
        resource_header_layout.setContentsMargins(0, 0, 0, 10)

        # 资源名称标签
        self.resource_name_label = QLabel()
        self.resource_name_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.resource_name_label.setObjectName("resourceSettingsTitle")

        # 资源状态指示器
        self.status_indicator = QWidget()
        status_layout = QHBoxLayout(self.status_indicator)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(5)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)

        self.status_text = QLabel()
        self.status_text.setObjectName("statusText")

        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)

        resource_header_layout.addWidget(self.resource_name_label)
        resource_header_layout.addStretch()
        resource_header_layout.addWidget(self.status_indicator)

        self.layout.addWidget(self.resource_header)

        # 创建内容堆栈小部件来容纳基本设置和高级设置
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")

        # 创建基本设置页面
        self.basic_settings_page = BasicSettingsPage(self.device_config)

        # 创建高级设置页面
        self.advanced_settings_page = AdvancedSettingsPage(self.device_config)

        # 将页面添加到堆栈小部件
        self.content_stack.addWidget(self.basic_settings_page)
        self.content_stack.addWidget(self.advanced_settings_page)

        # 添加堆栈小部件到主布局
        self.layout.addWidget(self.content_stack)

        # 在底部添加标签切换按钮
        self.tab_buttons_widget = QWidget()
        self.tab_buttons_widget.setObjectName("tabButtonsWidget")
        tab_buttons_layout = QHBoxLayout(self.tab_buttons_widget)
        tab_buttons_layout.setContentsMargins(0, 10, 0, 0)

        self.basic_tab_btn = QPushButton("基本设置")
        self.basic_tab_btn.setObjectName("tabButton")
        self.basic_tab_btn.setCheckable(True)
        self.basic_tab_btn.setChecked(True)
        self.basic_tab_btn.clicked.connect(lambda: self.switch_tab("basic"))

        self.advanced_tab_btn = QPushButton("高级设置")
        self.advanced_tab_btn.setObjectName("tabButton")
        self.advanced_tab_btn.setCheckable(True)
        self.advanced_tab_btn.clicked.connect(lambda: self.switch_tab("advanced"))

        tab_buttons_layout.addWidget(self.basic_tab_btn)
        tab_buttons_layout.addWidget(self.advanced_tab_btn)

        self.layout.addWidget(self.tab_buttons_widget)
        self.layout.addStretch()

        # 初始显示基本设置标签页
        self.content_stack.setCurrentWidget(self.basic_settings_page)

        # 隐藏标签切换按钮，直到选择资源
        self.tab_buttons_widget.setVisible(False)

    def switch_tab(self, tab_name):
        """切换标签页"""
        if tab_name == "basic":
            self.content_stack.setCurrentWidget(self.basic_settings_page)
            self.basic_tab_btn.setChecked(True)
            self.advanced_tab_btn.setChecked(False)
            self.current_tab = "basic"
        elif tab_name == "advanced":
            # 确保高级设置页面更新到当前选择的资源
            self.advanced_settings_page.setup_for_resource(self.selected_resource_name)

            self.content_stack.setCurrentWidget(self.advanced_settings_page)
            self.basic_tab_btn.setChecked(False)
            self.advanced_tab_btn.setChecked(True)
            self.current_tab = "advanced"

    def show_resource_settings(self, resource_name):
        """Show settings for the selected resource"""
        self.selected_resource_name = resource_name

        # 显示资源标题和状态指示器
        self.resource_header.setVisible(True)
        self.resource_name_label.setText(resource_name)

        # 从设备配置中获取资源启用状态
        resource_enabled = False
        if self.device_config:
            resource_config = next((r for r in self.device_config.resources
                                 if r.resource_name == resource_name), None)
            if resource_config:
                resource_enabled = resource_config.enable

        # 更新状态指示器
        self.update_resource_status(resource_name, resource_enabled)

        # 更新基本设置页面（无需传递状态，因为已经集中处理）
        self.basic_settings_page.show_resource_settings(resource_name)

        # 显示标签切换按钮
        self.tab_buttons_widget.setVisible(True)

        # 如果当前是高级设置标签，也更新高级设置页面
        if self.current_tab == "advanced":
            self.advanced_settings_page.setup_for_resource(resource_name)

    def clear_settings(self):
        """Clear the settings content"""
        self.selected_resource_name = None

        # 隐藏资源标题和状态指示器
        self.resource_header.setVisible(False)

        # 清除基本设置页面
        self.basic_settings_page.clear_settings()

        # 清除高级设置页面
        self.advanced_settings_page.clear_settings()

        # 隐藏标签切换按钮
        self.tab_buttons_widget.setVisible(False)

        # 重置当前标签页并显示基本设置
        self.current_tab = "basic"
        self.content_stack.setCurrentWidget(self.basic_settings_page)
        self.basic_tab_btn.setChecked(True)
        self.advanced_tab_btn.setChecked(False)

    def update_resource_status(self, resource_name, enabled):
        """更新 UI 中的资源状态"""
        if self.selected_resource_name == resource_name:
            # 更新状态点的颜色
            self.status_dot.setStyleSheet(
                f"background-color: {'#34a853' if enabled else '#ea4335'}; border-radius: 4px;")

            # 更新状态文本
            self.status_text.setText(f"{'已启用' if enabled else '已禁用'}")
            self.status_text.setStyleSheet(f"color: {'#34a853' if enabled else '#ea4335'}; font-size: 12px;")

            # 记录日志
            log_manager.log_device_info(
                self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备",
                f"资源 {resource_name} 状态已在任务设置中更新"
            )

    def _clear_layout(self, layout):
        """Clear all widgets from a layout"""
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())