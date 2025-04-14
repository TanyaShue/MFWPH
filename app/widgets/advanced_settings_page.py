from PySide6.QtCore import Qt, QTime, QDateTime
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QScrollArea
)

from app.components.collapsible_widget import CollapsibleWidget, DraggableContainer
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class AdvancedSettingsPage(QFrame):
    """高级设置页面，用于配置资源任务的高级选项"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.selected_resource_name = None

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)

        # 初始化高级设置控件变量（原有控件已取消，不再使用）
        self.enable_timing_checkbox = None
        self.timing_type_group = None
        self.daily_radio = None
        self.interval_radio = None
        self.once_radio = None
        self.time_edit = None
        self.interval_label = None
        self.interval_input = None
        self.date_label = None
        self.date_time_edit = None
        self.enable_notification_checkbox = None
        self.notification_type_combo = None
        self.notification_address_input = None
        self.save_advanced_btn = None

        # 创建页面布局，修改布局空隙为0，取消折叠面板之间的空白
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 创建占位符
        self.init_placeholder()

    def init_placeholder(self):
        """初始化占位符布局"""
        self._clear_layout(self.main_layout)

        placeholder_widget = QWidget()
        ph_layout = QVBoxLayout(placeholder_widget)
        ph_layout.setAlignment(Qt.AlignCenter)

        no_resource_msg = QLabel("请先从左侧资源列表中选择一个资源")
        no_resource_msg.setAlignment(Qt.AlignCenter)
        no_resource_msg.setObjectName("placeholderText")

        ph_layout.addWidget(no_resource_msg)
        self.main_layout.addWidget(placeholder_widget)

    def setup_for_resource(self, resource_name):
        """为特定资源设置高级设置页面"""
        self.selected_resource_name = resource_name
        self.setup_advanced_settings()

    def setup_advanced_settings(self):
        """设置高级设置页面内容"""
        # 清除现有布局内容
        self._clear_layout(self.main_layout)

        # 如果没有选择资源，显示占位符
        if not self.selected_resource_name:
            self.init_placeholder()
            return

        # 添加描述（根据需要可以从资源配置中获取）
        resource_config = global_config.get_resource_config(self.selected_resource_name)
        if resource_config and hasattr(resource_config, 'description') and resource_config.description:
            description_label = QLabel(resource_config.description)
            description_label.setObjectName("resourceDescription")
            description_label.setWordWrap(True)
            description_label.setContentsMargins(0, 0, 0, 10)
            self.main_layout.addWidget(description_label)

        # 拖放任务的说明
        instructions = QLabel("高级设置可配置定时和通知")
        instructions.setObjectName("instructionText")
        instructions.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instructions)

        # 创建任务的滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        # 禁用水平滚动条
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 创建任务的可拖动容器
        scroll_content = DraggableContainer()
        scroll_content.setObjectName('draggableContainer')
        scroll_content.setMinimumWidth(200)

        scroll_content.layout.setContentsMargins(0, 0, 0, 0)

        # 创建定时设置折叠面板（展开后只显示一个标签）
        timing_panel = CollapsibleWidget("定时设置")
        timing_panel.setMinimumHeight(30)
        timing_panel.setObjectName("advancedCollapsiblePanel")
        self._setup_timing_settings(timing_panel)
        scroll_content.addWidget(timing_panel)

        # 创建通知设置折叠面板（展开后只显示一个标签）
        notification_panel = CollapsibleWidget("外部通知")
        notification_panel.setMinimumHeight(30)
        notification_panel.setObjectName("advancedCollapsiblePanel")
        self._setup_notification_settings(notification_panel)
        scroll_content.addWidget(notification_panel)

        scroll_area.setWidget(scroll_content)
        self.main_layout.addWidget(scroll_area)

        # 加载资源的高级设置数据
        self.load_advanced_settings()

    def _setup_timing_settings(self, parent_widget):
        """设置定时设置面板内容，改为仅显示一个标签"""
        # 取消所有原有控件，使用一个标签来代替
        label = QLabel("定时设置内容")
        label.setObjectName("advancedLabel")
        label.setAlignment(Qt.AlignCenter)
        parent_widget.content_layout.addWidget(label)

    def _setup_notification_settings(self, parent_widget):
        """设置通知设置面板内容，改为仅显示一个标签"""
        # 取消所有原有控件，使用一个标签来代替
        label = QLabel("外部通知设置内容")
        label.setObjectName("advancedLabel")
        label.setAlignment(Qt.AlignCenter)
        parent_widget.content_layout.addWidget(label)

    def load_advanced_settings(self):
        """加载资源的高级设置"""
        if not self.selected_resource_name or not self.device_config:
            return

        # 获取资源配置
        resource_config = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not resource_config:
            return

        # 如果需要从资源中加载数据设置标签文本，可以在此添加相关逻辑，目前仅作为占位示例
        # 例如：label.setText(resource_config.some_property)

    def save_advanced_settings(self):
        """保存高级设置到资源配置"""
        if not self.selected_resource_name or not self.device_config:
            return

        # 此处保存逻辑按实际需要修改，示例中未涉及具体输入控件
        resource_config = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not resource_config:
            return

        # 示例中没有收集新的设置值，只做日志记录
        global_config.save_all_configs()
        device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
        log_manager.log_device_info(device_name, f"资源 {self.selected_resource_name} 的高级设置已更新")

    def clear_settings(self):
        """清除设置并显示占位符"""
        self.selected_resource_name = None
        self.init_placeholder()

    def _clear_layout(self, layout):
        """清除布局中的所有控件"""
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())