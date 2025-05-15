from datetime import datetime

from PySide6.QtCore import QMutexLocker
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from qasync import asyncSlot

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.add_device_dialog import AddDeviceDialog
from core.tasker_manager import task_manager


class BasicInfoWidget(QFrame):
    """Basic device information widget"""

    def __init__(self, device_name, device_config, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = device_config
        self.parent_widget = parent
        self.logger = log_manager.get_device_logger(device_name)

        # 设置基本属性
        self.setObjectName("infoFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Section title
        section_title = QLabel("基本信息")
        section_title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        section_title.setObjectName("sectionTitle")
        layout.addWidget(section_title)

        # Content container
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 5, 0, 5)
        content_layout.setSpacing(15)

        if self.device_config:
            # Device Name
            name_layout = QHBoxLayout()
            name_label = QLabel("设备名称:")
            name_label.setObjectName("infoLabel")
            name_value = QLabel(self.device_config.device_name)
            name_value.setObjectName("infoLabel")
            name_value.setFont(QFont("Segoe UI", 13, QFont.Medium))
            name_layout.addWidget(name_label)
            name_layout.addWidget(name_value)
            name_layout.addStretch()
            content_layout.addLayout(name_layout)

            # Device Type
            type_layout = QHBoxLayout()
            type_label = QLabel("设备类型:")
            type_label.setObjectName("infoLabel")

            # 获取设备类型文本
            device_type_text = getattr(self.device_config.device_type, "value", str(self.device_config.device_type))

            # 转换为用户友好的显示文本
            display_text = {
                "adb": "ADB设备",
                "win32": "Win32窗口"
            }.get(device_type_text, device_type_text)

            type_value = QLabel(display_text)
            type_value.setObjectName("infoLabel")
            type_layout.addWidget(type_label)
            type_layout.addWidget(type_value)
            type_layout.addStretch()
            content_layout.addLayout(type_layout)

            # Status
            status_layout = QHBoxLayout()
            status_label = QLabel("状态:")
            status_label.setObjectName("infoLabel")
            self.status_value = QLabel()
            self.status_value.setObjectName("infoLabel")
            self.status_value.setWordWrap(True)
            status_layout.addWidget(status_label)
            status_layout.addWidget(self.status_value)
            status_layout.addStretch()
            content_layout.addLayout(status_layout)

            # 定时任务信息
            schedule_layout = QHBoxLayout()
            schedule_label = QLabel("定时任务:")
            schedule_label.setObjectName("infoLabel")
            self.schedule_value = QLabel()
            self.schedule_value.setObjectName("infoLabel")
            self.schedule_value.setWordWrap(True)
            schedule_layout.addWidget(schedule_label)
            schedule_layout.addWidget(self.schedule_value)
            schedule_layout.addStretch()
            content_layout.addLayout(schedule_layout)

        else:
            error_label = QLabel("未找到设备配置信息")
            error_label.setObjectName("errorText")
            content_layout.addWidget(error_label)

        layout.addWidget(content_widget)
        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)
        button_layout.setSpacing(10)
        button_layout.addStretch()

        # Run/Stop button
        self.run_btn = QPushButton("运行任务")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
        self.run_btn.clicked.connect(self.handle_run_stop_action)

        settings_btn = QPushButton("设备设置")
        settings_btn.setObjectName("secondaryButton")
        settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        settings_btn.clicked.connect(self.open_settings_dialog)

        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(settings_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    def connect_signals(self):
        """连接信号到状态更新函数"""
        # 连接TaskerManager的全局信号
        task_manager.device_added.connect(self.on_device_changed)
        task_manager.device_removed.connect(self.on_device_changed)
        task_manager.device_status_changed.connect(self.update_status_display)
        task_manager.scheduled_task_modified.connect(self.update_status_display)

        # 如果设备执行器已存在，连接其信号
        if task_manager.is_device_active(self.device_name):
            self.connect_executor_signals()

    def connect_executor_signals(self):
        """连接设备执行器的信号"""
        with QMutexLocker(task_manager._mutex):
            executor = task_manager._executors.get(self.device_name)
            if not executor:
                return

            # 连接执行器信号
            executor.task_started.connect(self.update_status_display)
            executor.task_completed.connect(self.update_status_display)
            executor.task_failed.connect(self.update_status_display)
            executor.task_canceled.connect(self.update_status_display)
            executor.progress_updated.connect(lambda *args: self.update_status_display())
            executor.executor_started.connect(self.update_status_display)
            executor.executor_stopped.connect(self.update_status_display)
            executor.task_queued.connect(self.update_status_display)

            # 连接设备状态信号
            state = executor.get_state()
            if state:
                state.status_changed.connect(lambda *args: self.update_status_display())
                state.error_occurred.connect(lambda *args: self.update_status_display())

    def on_device_changed(self, device_name):
        """设备添加/移除时的处理函数"""
        if device_name != self.device_name:
            return

        self.update_status_display()

        if task_manager.is_device_active(self.device_name):
            self.connect_executor_signals()

    def update_status_display(self, *args, **kwargs):
        """更新任务状态和定时任务信息显示"""
        if not self.device_config:
            return

        # 更新定时任务信息
        has_enabled_schedules = any(
            r.schedules_enable and r.schedules and any(s.enabled for s in r.schedules)
            for r in self.device_config.resources
        )

        if has_enabled_schedules:
            # 获取设备的定时任务信息
            device_tasks = [task for task in task_manager.get_scheduled_tasks_info()
                            if task['device_name'] == self.device_name]

            if device_tasks:
                # 找出最近的下次执行时间
                next_run_times = [datetime.strptime(task['next_run'], '%Y-%m-%d %H:%M:%S')
                                  for task in device_tasks if task.get('next_run') != 'Unknown']
                schedule_text = next_run_times and f"{min(next_run_times).strftime('%H:%M:%S')}" or "已启用，但未设置具体执行时间"
            else:
                schedule_text = "已启用，但未设置具体执行时间"
        else:
            schedule_text = "未启用"

        self.schedule_value.setText(schedule_text)

        # 更新任务运行状态
        is_active = task_manager.is_device_active(self.device_name)
        is_running = False

        if is_active:
            device_state = task_manager.get_executor_state(self.device_name)
            if device_state:
                status = device_state.status.value

                # 获取状态文本
                status_map = {
                    "idle": "空闲",
                    "running": "正在执行任务",
                    "error": f"错误: {device_state.error or '未知错误'}",
                    "stopping": "正在停止",
                    "scheduled": "已设置定时任务",
                    "waiting": "等待执行",
                    "disconnected": "未连接",
                    "connecting": "连接中"
                }
                status_text = status_map.get(status, status)

                # 检查是否在运行状态
                if status == "running":
                    is_running = True

                # 添加当前任务信息
                if device_state.current_task:
                    status_text += f"，任务ID: {device_state.current_task.id}"

                # 添加队列信息
                queue_length = task_manager.get_device_queue_info().get(self.device_name, 0)
                if queue_length > 0:
                    status_text += f"，队列中还有 {queue_length} 个任务"
            else:
                status_text = "未知状态"
        else:
            status_text = "未运行"

        self.status_value.setText(status_text)

        # 更新按钮状态
        if is_running:
            self.run_btn.setText("停止任务")
            self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
        else:
            self.run_btn.setText("运行任务")
            self.run_btn.setIcon(QIcon("assets/icons/play.svg"))

    @asyncSlot()
    async def handle_run_stop_action(self):
        """Handle run/stop button click based on current state"""
        if not self.device_config:
            return

        # Check if device is running
        is_active = task_manager.is_device_active(self.device_name)
        is_running = False

        if is_active:
            device_state = task_manager.get_executor_state(self.device_name)
            if device_state and device_state.status.value == "running":
                is_running = True

        if is_running:
            # Stop the device
            await self.stop_device_tasks()
        else:
            # Run the device
            await self.run_device_tasks()

    @asyncSlot()
    async def run_device_tasks(self):
        """Run device tasks and log the action"""
        try:
            if self.device_config:
                self.logger.info("开始执行设备任务")

                # Disable button during execution
                self.run_btn.setEnabled(False)
                self.run_btn.setText("运行中...")

                success = await task_manager.run_device_all_resource_task(self.device_config)

                if success:
                    self.logger.info("设备任务执行完成")

                self.run_btn.setEnabled(True)
                self.update_status_display()

                if task_manager.is_device_active(self.device_name):
                    self.connect_executor_signals()
        except Exception as e:
            self.logger.error(f"运行任务时出错: {str(e)}")
            self.run_btn.setEnabled(True)
            self.update_status_display()

    @asyncSlot()
    async def stop_device_tasks(self):
        """Stop all tasks for this device"""
        try:
            if self.device_config:
                self.logger.info("停止设备任务")

                # Disable button during stopping
                self.run_btn.setEnabled(False)
                self.run_btn.setText("停止中...")

                # Stop the device executor
                success = await task_manager.stop_executor(self.device_name)

                if success:
                    self.logger.info("设备任务已停止")

                self.run_btn.setEnabled(True)
                self.update_status_display()
        except Exception as e:
            self.logger.error(f"停止任务时出错: {str(e)}")
            self.run_btn.setEnabled(True)
            self.update_status_display()

    def open_settings_dialog(self):
        """Open device settings dialog"""
        if self.device_config:
            original_device_name = self.device_name
            dialog = AddDeviceDialog(global_config, self, edit_mode=True, device_config=self.device_config)
            dialog.exec_()

            updated_device_config = global_config.get_device_config(original_device_name)

            if updated_device_config:
                self.logger.info("设备配置已更新")
                task_manager.update_device_scheduled_tasks(updated_device_config)
                self.logger.info("设备定时任务已更新")
                self.device_config = updated_device_config
                self.update_status_display()

                if hasattr(self.parent_widget, 'refresh_ui'):
                    self.parent_widget.refresh_ui()
            else:
                main_window = self.window()
                if hasattr(main_window, 'on_device_deleted'):
                    main_window.on_device_deleted()
                if hasattr(main_window, 'show_previous_device_or_home'):
                    main_window.show_previous_device_or_home(original_device_name)

    def refresh_ui(self, device_config=None):
        """Refresh widget with updated device config"""
        if device_config:
            self.device_config = device_config

        if self.layout():
            QWidget().setLayout(self.layout())

        self.init_ui()
        self.connect_signals()

    def showEvent(self, event):
        """当组件显示时更新状态"""
        super().showEvent(event)
        self.update_status_display()