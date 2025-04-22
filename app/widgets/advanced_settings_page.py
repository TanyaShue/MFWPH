from PySide6.QtCore import Qt, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QScrollArea,
    QPushButton, QComboBox, QCheckBox, QTimeEdit
)

from app.components.collapsible_widget import CollapsibleWidget
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.no_wheel_ComboBox import NoWheelComboBox
from core.tasker_manager import task_manager


class AdvancedSettingsPage(QFrame):
    """简化版的高级设置页面，使用基础滚动区域和折叠面板"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)

        # 创建主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 初始化占位符
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
            description_label.setContentsMargins(10, 10, 10, 10)
            self.main_layout.addWidget(description_label)

        # 添加页面标题
        instructions = QLabel("高级设置可配置定时和通知")
        instructions.setObjectName("instructionText")
        instructions.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instructions)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # 关键：使内容可以调整大小
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 创建滚动内容容器
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(5)

        # 创建定时设置面板
        timing_panel = CollapsibleWidget("定时设置")
        timing_panel.setObjectName("advancedCollapsiblePanel")
        self._setup_timing_settings(timing_panel)
        content_layout.addWidget(timing_panel)

        # 创建通知设置面板
        notification_panel = CollapsibleWidget("外部通知")
        notification_panel.setObjectName("advancedCollapsiblePanel")
        self._setup_notification_settings(notification_panel)
        content_layout.addWidget(notification_panel)

        # 添加底部空间
        content_layout.addStretch(1)

        # 设置滚动区域内容
        scroll_area.setWidget(scroll_content)

        # 添加滚动区域到主布局
        self.main_layout.addWidget(scroll_area)

        # 加载资源的高级设置数据
        self.load_advanced_settings(timing_panel)

    def _setup_timing_settings(self, panel):
        """设置定时设置面板内容"""
        resource_config = None
        for resource in self.device_config.resources:
            if resource.resource_name == self.selected_resource_name:
                resource_config = resource
                break

        if not resource_config:
            label = QLabel("未找到资源配置")
            label.setAlignment(Qt.AlignCenter)
            panel.content_layout.addWidget(label)
            return

        # 初始化schedules_enable属性
        if not hasattr(resource_config, 'schedules_enable'):
            resource_config.schedules_enable = False

        # 设置标题栏复选框状态并绑定事件
        panel.checkbox.setChecked(resource_config.schedules_enable)

        def on_checkbox_changed(state):
            resource_config.schedules_enable = state
            global_config.save_all_configs()
            self.logger.info(f"资源 {self.selected_resource_name} 的定时任务已{'启用' if state else '禁用'}")

        panel.checkbox.stateChanged.connect(on_checkbox_changed)

        # 如果没有定时设置，添加一个空的定时设置列表
        if not hasattr(resource_config, 'schedules') or not resource_config.schedules:
            resource_config.schedules = []

        # 获取可用的设置配置
        available_settings = []
        for setting in global_config.get_app_config().resource_settings:
            if setting.resource_name == self.selected_resource_name:
                available_settings.append(setting)

        # 存储所有行的引用
        schedule_rows = []

        # 创建定时配置容器
        schedules_container = QWidget()
        schedules_layout = QVBoxLayout(schedules_container)
        schedules_layout.setContentsMargins(0, 5, 0, 5)
        schedules_layout.setSpacing(5)

        # 添加一个函数用于创建新的定时行
        def create_schedule_row(schedule=None):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)

            # 启用复选框
            enable_checkbox = QCheckBox()
            enable_checkbox.setChecked(schedule.enabled if schedule else False)
            row_layout.addWidget(enable_checkbox)

            # 单个时间选择器
            time_edit = QTimeEdit()
            time_edit.setDisplayFormat("HH:mm")
            if schedule and schedule.schedule_time:
                time = QTime.fromString(schedule.schedule_time, "HH:mm")
                time_edit.setTime(time)
            else:
                # 默认设置为12:00
                time_edit.setTime(QTime(12, 0))

            row_layout.addWidget(time_edit, 2)

            # 设置选择下拉框
            settings_combo = NoWheelComboBox()
            settings_combo.setMinimumWidth(2)
            for setting in available_settings:
                settings_combo.addItem(setting.name)

            # 设置当前值
            if schedule and schedule.settings_name:
                index = settings_combo.findText(schedule.settings_name)
                if index >= 0:
                    settings_combo.setCurrentIndex(index)
            elif available_settings:
                # 默认选第一个
                settings_combo.setCurrentIndex(0)

            row_layout.addWidget(settings_combo, 2)

            # 删除按钮
            delete_btn = QPushButton()
            delete_btn.setIcon(QIcon("assets/icons/delete.svg"))
            delete_btn.setMaximumWidth(30)
            delete_btn.setObjectName("secondaryButton")

            def delete_schedule_row():
                # 从界面和数据中删除该行
                row_index = schedule_rows.index(row_widget)
                if schedule and schedule in resource_config.schedules:
                    resource_config.schedules.remove(schedule)

                # 从界面移除
                row_widget.deleteLater()
                if row_widget in schedule_rows:
                    schedule_rows.remove(row_widget)

                # 自动保存更改
                global_config.save_all_configs()
                self.logger.debug(f"已删除定时配置行 {row_index}")

            delete_btn.clicked.connect(delete_schedule_row)
            row_layout.addWidget(delete_btn)

            # 添加自动保存功能
            def auto_save():
                # 先声明nonlocal，必须在函数开头
                nonlocal schedule

                # 如果调度不在列表中，创建一个新的
                if not schedule or schedule not in resource_config.schedules:
                    from app.models.config.app_config import ResourceSchedule
                    new_schedule = ResourceSchedule()
                    resource_config.schedules.append(new_schedule)

                    # 更新引用
                    schedule = new_schedule

                # 更新设置
                schedule.enabled = enable_checkbox.isChecked()
                schedule.settings_name = settings_combo.currentText()
                schedule.schedule_time = time_edit.time().toString("HH:mm")

                # 保存配置
                global_config.save_all_configs()
                task_manager.update_device_scheduled_tasks(self.device_config)
                self.logger.debug(f"已自动保存定时配置")

            # 连接控件事件到自动保存函数
            enable_checkbox.stateChanged.connect(auto_save)
            time_edit.timeChanged.connect(auto_save)
            settings_combo.currentTextChanged.connect(auto_save)

            # 将行添加到布局中
            schedules_layout.addWidget(row_widget)
            schedule_rows.append(row_widget)

            # 返回行和相关控件
            return {
                'widget': row_widget,
                'enable': enable_checkbox,
                'time': time_edit,
                'settings': settings_combo,
                'schedule': schedule
            }

        # 创建现有定时设置行
        row_data = []
        if resource_config.schedules:
            for schedule in resource_config.schedules:
                row_data.append(create_schedule_row(schedule))
        else:
            # 如果没有定时设置，创建一个空行
            row_data.append(create_schedule_row())

        # 添加定时配置容器到内容布局
        panel.content_layout.addWidget(schedules_container)

        # 添加新定时设置按钮
        add_schedule_btn = QPushButton("添加定时配置")
        add_schedule_btn.setObjectName("addScheduleBtn")

        def add_new_schedule():
            from app.models.config.app_config import ResourceSchedule
            new_schedule = ResourceSchedule()
            if available_settings:
                new_schedule.settings_name = available_settings[0].name
            new_schedule.enabled = False
            new_schedule.schedule_time = "12:00"
            resource_config.schedules.append(new_schedule)

            # 添加新行
            row_data.append(create_schedule_row(new_schedule))

            # 自动保存
            global_config.save_all_configs()
            task_manager.update_device_scheduled_tasks(self.device_config)

        add_schedule_btn.clicked.connect(add_new_schedule)
        panel.content_layout.addWidget(add_schedule_btn)

    def _setup_notification_settings(self, panel):
        """设置通知设置面板内容，仅显示一个标签"""
        label = QLabel("外部通知设置内容--这个人很懒,还没写")
        label.setObjectName("advancedLabel")
        label.setAlignment(Qt.AlignCenter)
        panel.content_layout.addWidget(label)

    def load_advanced_settings(self, timing_panel):
        """加载资源的高级设置"""
        if not self.selected_resource_name or not self.device_config:
            return

        # 获取资源配置
        resource_config = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not resource_config:
            return

        # 记录加载的资源配置
        self.logger.debug(f"已加载资源 {self.selected_resource_name} 的高级设置")

        # 设置是否启用定时任务
        if hasattr(resource_config, 'schedules_enable'):
            timing_panel.checkbox.setChecked(resource_config.schedules_enable)

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