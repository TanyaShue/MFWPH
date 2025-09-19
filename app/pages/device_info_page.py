from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QSplitter
)

from app.components.log_display import LogDisplay
from app.models.config.global_config import global_config
from app.widgets.basic_info_widget import BasicInfoWidget
# 新增导入
from app.widgets.resource_config_widget import ResourceConfigWidget
from app.widgets.resource_widget import ResourceWidget
from app.widgets.task_settings_widget import TaskSettingsWidget
from app.widgets.task_options_widget import TaskOptionsWidget


class DeviceInfoPage(QWidget):
    """设备信息页面，集成所有设备相关的UI组件"""

    def __init__(self, device_name, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = global_config.get_device_config(device_name)
        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)
        self.setObjectName("content_widget")

        # 主水平分割器
        self.horizontal_splitter = QSplitter(Qt.Horizontal)
        self.horizontal_splitter.setObjectName("horizontalSplitter")
        self.horizontal_splitter.setHandleWidth(0)
        self.horizontal_splitter.setChildrenCollapsible(False)

        # 初始化所有UI组件
        self.basic_info_widget = BasicInfoWidget(self.device_name, self.device_config, self)
        self.resource_widget = ResourceWidget(self.device_name, self.device_config, self)
        self.task_settings_widget = TaskSettingsWidget(self.device_config, self)
        self.task_options_widget = TaskOptionsWidget(self)
        self.log_widget = LogDisplay(enable_log_level_filter=True, show_device_selector=False)
        self.log_widget.show_device_logs(self.device_name)
        # 初始化新的资源配置组件
        self.resource_config_widget = ResourceConfigWidget(self)

        # --- 第一部分 (左侧) ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setHandleWidth(0)
        self.left_splitter.setChildrenCollapsible(False)
        self.left_splitter.addWidget(self.resource_widget)
        self.left_splitter.addWidget(self.task_settings_widget)
        self.left_splitter.setSizes([100, 250])
        left_layout.addWidget(self.left_splitter)

        # --- 第二部分 (中间) ---
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        self.middle_splitter = QSplitter(Qt.Vertical)
        self.middle_splitter.setHandleWidth(0)
        self.middle_splitter.setChildrenCollapsible(False)
        # 将新的 resource_config_widget 放在顶部
        self.middle_splitter.addWidget(self.resource_config_widget)
        self.middle_splitter.addWidget(self.task_options_widget)
        self.middle_splitter.setSizes([100, 250])
        middle_layout.addWidget(self.middle_splitter)

        # --- 第三部分 (右侧) ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_splitter = QSplitter(Qt.Vertical)
        self.right_splitter.setHandleWidth(0)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.addWidget(self.basic_info_widget)
        self.right_splitter.addWidget(self.log_widget)
        self.right_splitter.setSizes([100, 300])
        right_layout.addWidget(self.right_splitter)

        # 添加所有部分到水平分割器
        self.horizontal_splitter.addWidget(left_widget)
        self.horizontal_splitter.addWidget(middle_widget)
        self.horizontal_splitter.addWidget(right_widget)
        self.horizontal_splitter.setSizes([300, 300, 200])

        main_layout.addWidget(self.horizontal_splitter)
        self.connect_signals()

    def connect_signals(self):
        """设置组件之间的信号和槽连接"""
        # 1. 当在资源列表(左上)中选择一个资源时，触发 on_resource_selected
        self.resource_widget.resource_selected.connect(self.on_resource_selected)

        # 2. 当资源启用状态改变时，更新配置小部件(中上)的UI
        self.resource_widget.resource_status_changed.connect(self.resource_config_widget.update_resource_status)

        # 3. 当在配置小部件(中上)中切换设置方案时，更新任务列表(左下)
        self.resource_config_widget.settings_changed.connect(self.task_settings_widget.display_tasks_for_setting)

        # 4. 当在任务列表(左下)中请求任务设置时，更新任务选项(中下)
        self.task_settings_widget.basic_settings_page.task_settings_requested.connect(
            self.task_options_widget.show_task_options)

    def on_resource_selected(self, resource_name: str):
        """
        槽函数：处理从 ResourceWidget 发出的资源选择信号。
        这是协调更新流程的核心。
        """
        # 步骤1: 告知 ResourceConfigWidget 显示指定资源的配置
        self.resource_config_widget.show_for_resource(self.device_config, resource_name)

        # 步骤2: 告知 TaskSettingsWidget 准备好显示这个资源的任务
        # (它会等待 ResourceConfigWidget 发出 settings_changed 信号后再真正加载任务)
        self.task_settings_widget.show_for_resource(resource_name)

        # 步骤3: 清除旧的任务选项，显示占位符
        self.task_options_widget.clear()

    def refresh_ui(self):
        """
        刷新所有UI组件。
        通常在设备配置发生变化后（例如，编辑设备设置后）调用。
        """
        self.device_config = global_config.get_device_config(self.device_name)

        # 依次刷新每个子组件
        self.basic_info_widget.refresh_ui(self.device_config)
        self.resource_widget.refresh_ui(self.device_config)

        # 清空依赖于资源选择的组件
        self.task_settings_widget.clear_settings()
        self.task_options_widget.clear()
        self.resource_config_widget.clear()