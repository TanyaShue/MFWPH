# app/widgets/task_settings_widget.py

from PySide6.QtCore import Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton, QStackedWidget, QLabel
)

from app.models.config.app_config import TaskInstance
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.device_info.add_task_dialog import AddTaskDialog
from app.widgets.device_info.basic_settings_page import BasicSettingsPage


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
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # === 标题栏 ===
        self.title_bar = QWidget()
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(10, 10, 10, 0)
        title_bar_layout.setSpacing(8)

        # 左侧标题
        title_label = QLabel("任务选项")
        title_label.setObjectName("sectionTitle")
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        # 右侧图标按钮
        self.add_task_icon_btn = QPushButton()
        self.add_task_icon_btn.setIcon(QIcon("assets/icons/add.svg"))
        self.add_task_icon_btn.setIconSize(QSize(16, 16))
        self.add_task_icon_btn.setFixedSize(28, 28)
        self.add_task_icon_btn.setObjectName("iconButton")
        self.add_task_icon_btn.setToolTip("添加任务")
        self.add_task_icon_btn.clicked.connect(self._on_add_task_clicked)

        self.remove_task_icon_btn = QPushButton()
        self.remove_task_icon_btn.setIcon(QIcon("assets/icons/delete.svg"))
        self.remove_task_icon_btn.setIconSize(QSize(16, 16))
        self.remove_task_icon_btn.setFixedSize(28, 28)
        self.remove_task_icon_btn.setObjectName("iconButton")
        self.remove_task_icon_btn.setToolTip("移除任务")
        self.remove_task_icon_btn.clicked.connect(self.handle_remove_mode)

        title_bar_layout.addWidget(self.add_task_icon_btn)
        title_bar_layout.addWidget(self.remove_task_icon_btn)

        self.layout.addWidget(self.title_bar)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("separator")
        self.layout.addWidget(separator)

        # === 任务列表内容区域 ===
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumHeight(200)
        self.basic_settings_page = BasicSettingsPage(self.device_config)
        self.content_stack.addWidget(self.basic_settings_page)
        self.layout.addWidget(self.content_stack)

        # === 底部批量操作按钮区域 ===
        self.buttons_container = QWidget()
        buttons_container_layout = QHBoxLayout(self.buttons_container)
        buttons_container_layout.setContentsMargins(10, 10, 10, 10)
        buttons_container_layout.setSpacing(12)

        # 左侧弹性空间
        buttons_container_layout.addStretch()

        # 启用按钮
        self.enable_all_btn = QPushButton("启用全部")
        self.enable_all_btn.setObjectName("primaryButton")
        self.enable_all_btn.setFixedWidth(100)
        self.enable_all_btn.setToolTip("启用所有任务")
        self.enable_all_btn.clicked.connect(self._on_enable_all_clicked)

        # 取消按钮（仅在移除模式下显示，替换中间位置）
        self.cancel_remove_btn = QPushButton("取消")
        self.cancel_remove_btn.setObjectName("secondaryButton")
        self.cancel_remove_btn.setFixedWidth(100)
        self.cancel_remove_btn.clicked.connect(self.cancel_remove_mode)
        self.cancel_remove_btn.setVisible(False)

        # 禁用按钮
        self.disable_all_btn = QPushButton("禁用全部")
        self.disable_all_btn.setObjectName("secondaryButton")
        self.disable_all_btn.setFixedWidth(100)
        self.disable_all_btn.setToolTip("禁用所有任务")
        self.disable_all_btn.clicked.connect(self._on_disable_all_clicked)

        buttons_container_layout.addWidget(self.enable_all_btn)
        buttons_container_layout.addWidget(self.cancel_remove_btn)
        buttons_container_layout.addWidget(self.disable_all_btn)

        # 右侧弹性空间
        buttons_container_layout.addStretch()
        
        self.layout.addWidget(self.buttons_container)

        # 初始时隐藏所有内容，直到有资源被选择
        self.clear_settings()

        # 连接信号到 basic_settings_page 的槽函数，以便同步移除模式
        self.remove_mode_changed.connect(self.basic_settings_page.set_remove_mode)

    def show_for_resource(self, resource_name: str):
        """当选择一个资源时调用，准备好显示任务，但需要等待 setting_name"""
        self.current_resource_name = resource_name
        self.title_bar.setVisible(True)
        self.buttons_container.setVisible(True)
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
            self.cancel_remove_mode()

    def clear_settings(self):
        """清除设置内容，并隐藏相关控件"""
        self.current_resource_name = None
        self.basic_settings_page.clear_settings()
        self.title_bar.setVisible(False)
        self.buttons_container.setVisible(False)
        self.content_stack.setVisible(False)
        if self.is_remove_mode:
            self.cancel_remove_mode()

    def handle_remove_mode(self):
        """处理移除模式的进入和确认"""
        if not self.is_remove_mode:
            # --- 进入移除模式 ---
            self.is_remove_mode = True
            self.remove_mode_changed.emit(True)

            # 更新标题栏按钮
            self.add_task_icon_btn.setVisible(False)
            self.remove_task_icon_btn.setIcon(QIcon("assets/icons/check.svg"))
            self.remove_task_icon_btn.setToolTip("确认移除")
            self.remove_task_icon_btn.setObjectName("dangerIconButton")
            self.remove_task_icon_btn.style().polish(self.remove_task_icon_btn)

            # 隐藏批量操作按钮，显示取消按钮
            self.enable_all_btn.setVisible(False)
            self.disable_all_btn.setVisible(False)
            self.cancel_remove_btn.setVisible(True)
        else:
            # --- 确认并退出移除模式 ---
            removed_count = self.basic_settings_page.commit_removals()
            if removed_count > 0:
                global_config.save_all_configs()
                self.logger.info(f"已确认并移除了 {removed_count} 个任务。")
            else:
                self.logger.info("没有任务被标记为移除，操作已取消。")

            self.exit_remove_mode()

    def cancel_remove_mode(self):
        """取消所有待移除的标记，并退出移除模式"""
        self.basic_settings_page.cancel_removals()
        self.logger.info("已取消任务移除操作。")
        self.exit_remove_mode()

    def exit_remove_mode(self):
        """重置UI到正常状态，这是一个公共的退出函数"""
        self.is_remove_mode = False
        self.remove_mode_changed.emit(False)

        # 恢复标题栏按钮
        self.add_task_icon_btn.setVisible(True)
        self.remove_task_icon_btn.setIcon(QIcon("assets/icons/delete.svg"))
        self.remove_task_icon_btn.setToolTip("移除任务")
        self.remove_task_icon_btn.setObjectName("iconButton")
        self.remove_task_icon_btn.style().polish(self.remove_task_icon_btn)

        # 恢复批量操作按钮，隐藏取消按钮
        self.enable_all_btn.setVisible(True)
        self.disable_all_btn.setVisible(True)
        self.cancel_remove_btn.setVisible(False)

    def _on_add_task_clicked(self):
        """处理添加任务按钮点击事件"""
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
                    new_instance = TaskInstance(task_name=task_name, options=[])
                    settings.task_instances[new_instance.instance_id] = new_instance
                    settings.task_order.append(new_instance.instance_id)

                global_config.save_all_configs()
                self.logger.info(f"为资源 {resource_name} 添加了新任务: {', '.join(new_task_names)}")
                self.display_tasks_for_setting(resource_name, settings_name)

    def _on_enable_all_clicked(self):
        """处理全选按钮点击事件，启用所有任务"""
        resource_name = self.basic_settings_page.selected_resource_name
        settings_name = self.basic_settings_page.selected_settings_name
        if not resource_name or not settings_name:
            return

        count = self.basic_settings_page.enable_all_tasks()
        if count > 0:
            global_config.save_all_configs()
            self.logger.info(f"已启用 {count} 个任务。")

    def _on_disable_all_clicked(self):
        """处理取消全选按钮点击事件，禁用所有任务"""
        resource_name = self.basic_settings_page.selected_resource_name
        settings_name = self.basic_settings_page.selected_settings_name
        if not resource_name or not settings_name:
            return

        count = self.basic_settings_page.disable_all_tasks()
        if count > 0:
            global_config.save_all_configs()
            self.logger.info(f"已禁用 {count} 个任务。")
