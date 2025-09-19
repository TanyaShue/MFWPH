# app/widgets/task_settings_widget.py

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QMessageBox, QPushButton, QStackedWidget
)

from app.models.config.app_config import TaskInstance
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.add_task_dialog import AddTaskDialog
from app.widgets.basic_settings_page import BasicSettingsPage


class TaskSettingsWidget(QFrame):
    """任务设置小部件，用于显示和管理特定资源配置下的任务列表"""
    # 当进入或退出移除模式时发出信号
    remove_mode_changed = Signal(bool)

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        # 当前活动的资源名称，由外部通过 show_for_resource 设置
        self.current_resource_name = None
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.is_remove_mode = False

        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(12)

        # 使用 QStackedWidget 来显示内容，方便未来扩展
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumHeight(200)
        self.basic_settings_page = BasicSettingsPage(self.device_config)
        self.content_stack.addWidget(self.basic_settings_page)
        self.layout.addWidget(self.content_stack)

        # 任务管理按钮区域（添加、移除）
        self.task_buttons_widget = QWidget()
        task_buttons_layout = QHBoxLayout(self.task_buttons_widget)
        task_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.add_task_btn = QPushButton("添加任务")
        self.add_task_btn.setObjectName("primaryButton")
        self.add_task_btn.clicked.connect(self._on_add_task_clicked)

        self.remove_task_btn = QPushButton("移除任务")
        self.remove_task_btn.setObjectName("secondaryButton")
        self.remove_task_btn.clicked.connect(self.toggle_remove_mode)

        task_buttons_layout.addWidget(self.add_task_btn)
        task_buttons_layout.addWidget(self.remove_task_btn)
        self.layout.addWidget(self.task_buttons_widget)

        # 初始时隐藏所有内容，直到有资源被选择
        self.clear_settings()

        # 连接信号到 basic_settings_page 的槽函数，以便同步移除模式
        self.remove_mode_changed.connect(self.basic_settings_page.set_remove_mode)

    def show_for_resource(self, resource_name: str):
        """当选择一个资源时调用，准备好显示任务，但需要等待 setting_name"""
        self.current_resource_name = resource_name
        self.task_buttons_widget.setVisible(True)
        # 确保 basic_settings_page 知道当前设备配置
        self.basic_settings_page.device_config = self.device_config

    def display_tasks_for_setting(self, resource_name: str, settings_name: str):
        """
        公共槽函数：接收到信号后，显示指定资源和设置方案下的任务列表。
        """
        if self.current_resource_name != resource_name:
            self.show_for_resource(resource_name)

        self.basic_settings_page.show_resource_settings(resource_name, settings_name)
        self.content_stack.setVisible(True)
        # 如果之前在移除模式，则退出该模式以避免状态混淆
        if self.is_remove_mode:
            self.toggle_remove_mode()

    def clear_settings(self):
        """清除设置内容，并隐藏相关控件"""
        self.current_resource_name = None
        self.basic_settings_page.clear_settings()
        self.task_buttons_widget.setVisible(False)
        self.content_stack.setVisible(False)
        if self.is_remove_mode:
            self.toggle_remove_mode()

    def toggle_remove_mode(self):
        """切换任务移除模式"""
        self.is_remove_mode = not self.is_remove_mode
        self.remove_mode_changed.emit(self.is_remove_mode)

        if self.is_remove_mode:
            self.remove_task_btn.setText("保存移除")
            self.remove_task_btn.setObjectName("dangerButton")
            self.add_task_btn.setEnabled(False) # 移除模式下禁用添加
        else:
            self.remove_task_btn.setText("移除任务")
            self.remove_task_btn.setObjectName("secondaryButton")
            self.add_task_btn.setEnabled(True)
            # 退出移除模式时，保存所有更改
            global_config.save_all_configs()
            self.logger.info(f"已保存对资源 {self.current_resource_name} 的任务移除操作")

        # 强制刷新按钮样式
        self.remove_task_btn.style().polish(self.remove_task_btn)

    def _on_add_task_clicked(self):
        """处理添加任务按钮点击事件"""
        # 从 basic_settings_page 获取当前上下文（资源名称和配置方案名称）
        resource_name = self.basic_settings_page.selected_resource_name
        settings_name = self.basic_settings_page.selected_settings_name
        if not resource_name or not settings_name: return

        dialog = AddTaskDialog(resource_name, self.device_config, self)
        if dialog.exec():
            new_task_names = dialog.get_selected_tasks()
            if not new_task_names: return

            app_config = global_config.get_app_config()
            settings = next((s for s in app_config.resource_settings
                             if s.name == settings_name and s.resource_name == resource_name), None)

            if settings:
                for task_name in new_task_names:
                    # 创建新的任务实例
                    new_instance = TaskInstance(task_name=task_name, options=[])
                    # 添加到配置中
                    settings.task_instances[new_instance.instance_id] = new_instance
                    settings.task_order.append(new_instance.instance_id)

                global_config.save_all_configs()
                self.logger.info(f"为资源 {resource_name} 添加了新任务: {', '.join(new_task_names)}")
                # 刷新UI以显示新添加的任务
                self.display_tasks_for_setting(resource_name, settings_name)