from datetime import datetime

from PySide6.QtCore import QMutexLocker, Qt
from PySide6.QtGui import QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from qasync import asyncSlot

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.add_device_dialog import AddDeviceDialog
from core.tasker_manager import task_manager


class BasicInfoWidget(QFrame):
    """Basic device information widget - Compact Version"""

    def __init__(self, device_name, device_config, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = device_config
        self.parent_widget = parent
        self.logger = log_manager.get_device_logger(device_name)

        # 设置基本属性
        self.setObjectName("infoFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumHeight(90)  # 限制最大高度
        self.setMinimumHeight(80)  # 设置最小高度
        self.init_ui()
        self.connect_signals()
        # 初始化显示状态
        self.update_status_display()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        if self.device_config:
            # 第一行：所有信息在一行
            info_layout = QHBoxLayout()
            info_layout.setSpacing(12)

            # 设备名称
            name_label = QLabel(self.device_config.device_name)
            name_label.setObjectName("deviceTitle")
            name_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
            info_layout.addWidget(name_label)

            # 状态指示器（圆点）
            self.status_indicator = QLabel()
            self.status_indicator.setFixedSize(10, 10)
            self.status_indicator.setStyleSheet("""
                QLabel {
                    background-color: #999999;
                    border-radius: 5px;
                }
            """)
            info_layout.addWidget(self.status_indicator)

            # 添加弹性空间
            info_layout.addStretch()

            # 时钟图标
            self.clock_icon = QLabel()
            self.clock_icon.setFixedSize(14, 14)
            self.clock_icon.setPixmap(QIcon("assets/icons/add-time.svg").pixmap(14, 14))
            info_layout.addWidget(self.clock_icon)

            # 定时任务时间
            self.schedule_value = QLabel("检查中...")
            self.schedule_value.setObjectName("scheduleText")
            self.schedule_value.setStyleSheet("""
                QLabel#scheduleText {
                    color: #666666;
                    font-size: 13px;
                }
            """)
            info_layout.addWidget(self.schedule_value)

            layout.addLayout(info_layout)

            # 第二行：按钮
            button_layout = QHBoxLayout()
            button_layout.setSpacing(10)

            # 运行/停止按钮
            self.run_btn = QPushButton("运行")
            self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
            self.run_btn.setObjectName("primaryButton")
            self.run_btn.setMinimumWidth(90)
            self.run_btn.setMaximumWidth(120)
            self.run_btn.setFixedHeight(32)
            self.run_btn.clicked.connect(self.handle_run_stop_action)

            # 设置按钮
            settings_btn = QPushButton("设置")
            settings_btn.setObjectName("secondaryButton")
            settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
            settings_btn.setFixedSize(32, 32)
            settings_btn.setMinimumWidth(90)
            settings_btn.setMaximumWidth(120)
            settings_btn.setToolTip("设备设置")
            settings_btn.clicked.connect(self.open_settings_dialog)

            button_layout.addStretch()
            button_layout.addWidget(self.run_btn)
            button_layout.addWidget(settings_btn)
            button_layout.addStretch()
            layout.addLayout(button_layout)

        else:
            error_label = QLabel("未找到设备配置")
            error_label.setObjectName("errorText")
            error_label.setStyleSheet("color: #ff4444; font-size: 12px;")
            layout.addWidget(error_label)

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
            device_tasks = [task for task in task_manager.get_scheduled_tasks_info()
                            if task['device_name'] == self.device_name]

            if device_tasks:
                next_run_times = [datetime.strptime(task['next_run'], '%Y-%m-%d %H:%M:%S')
                                  for task in device_tasks if task.get('next_run') != 'Unknown']
                if next_run_times:
                    next_time = min(next_run_times)
                    schedule_text = next_time.strftime('%H:%M')
                    self.schedule_value.setToolTip(f"下次执行时间: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    schedule_text = "已启用"
                    self.schedule_value.setToolTip("定时任务已启用，等待计划执行")
            else:
                schedule_text = "已启用"
                self.schedule_value.setToolTip("定时任务已启用，等待计划执行")
            if hasattr(self, 'clock_icon'):
                self.clock_icon.setVisible(True)
        else:
            schedule_text = "未启用"
            self.schedule_value.setToolTip("未设置定时任务")
            if hasattr(self, 'clock_icon'):
                self.clock_icon.setVisible(False)

        if hasattr(self, 'schedule_value'):
            self.schedule_value.setText(schedule_text)

        # 更新任务运行状态
        is_active = task_manager.is_device_active(self.device_name)
        is_running = False
        status_color = "#999999"  # 默认灰色
        status_tooltip = "设备离线"

        if is_active:
            device_state = task_manager.get_executor_state(self.device_name)
            if device_state:
                status = device_state.status.value

                # 设置状态颜色和提示
                status_config = {
                    "idle": ("#4CAF50", "设备就绪"),
                    "running": ("#2196F3", "正在执行任务"),
                    "error": ("#F44336", f"错误: {device_state.error or '未知错误'}"),
                    "stopping": ("#FF9800", "正在停止"),
                    "scheduled": ("#9C27B0", "已设置定时任务"),
                    "waiting": ("#607D8B", "等待执行"),
                    "disconnected": ("#999999", "设备未连接"),
                    "connecting": ("#03A9F4", "正在连接")
                }

                config = status_config.get(status, ("#999999", "未知状态"))
                status_color = config[0]
                status_tooltip = config[1]

                # 检查是否在运行状态
                if status == "running":
                    is_running = True

                # 添加队列信息到提示
                queue_length = task_manager.get_device_queue_info().get(self.device_name, 0)
                if queue_length > 0:
                    status_tooltip += f"，队列中还有 {queue_length} 个任务"

            else:
                status_tooltip = "未知状态"
        else:
            status_tooltip = "设备未启动"

        # 更新状态指示器
        if hasattr(self, 'status_indicator'):
            self.status_indicator.setStyleSheet(f"""
                QLabel {{
                    background-color: {status_color};
                    border-radius: 5px;
                }}
            """)
            self.status_indicator.setToolTip(status_tooltip)

        # 更新按钮状态
        if hasattr(self, 'run_btn'):
            if is_running:
                self.run_btn.setText("停止")
                self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
                self.run_btn.setToolTip("停止当前任务")
                self.run_btn.setStyleSheet("""
                    QPushButton#compactPrimaryButton {
                        background-color: #F44336;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 16px;
                        font-size: 13px;
                    }
                    QPushButton#compactPrimaryButton:hover {
                        background-color: #D32F2F;
                    }
                    QPushButton#compactPrimaryButton:disabled {
                        background-color: #cccccc;
                    }
                """)
            else:
                self.run_btn.setText("运行")
                self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
                self.run_btn.setToolTip("开始执行任务")
                self.run_btn.setStyleSheet("""
                    QPushButton#compactPrimaryButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 16px;
                        font-size: 13px;
                    }
                    QPushButton#compactPrimaryButton:hover {
                        background-color: #45A049;
                    }
                    QPushButton#compactPrimaryButton:disabled {
                        background-color: #cccccc;
                    }
                """)

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
                self.run_btn.setText("启动中...")

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

        # 正确清除现有布局和子部件
        if self.layout():
            # 删除所有子部件
            while self.layout().count():
                child = self.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())

            # 删除布局本身
            QWidget().setLayout(self.layout())

        self.init_ui()
        self.connect_signals()
        self.update_status_display()  # 确保状态显示更新

    def _clear_layout(self, layout):
        """递归清除布局"""
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())

    def showEvent(self, event):
        """当组件显示时更新状态"""
        super().showEvent(event)
        # 确保显示时状态是最新的
        self.update_status_display()