from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGridLayout
from qasync import asyncSlot

from app.models.logging.log_manager import log_manager
from core.scheduled_task_manager import scheduled_task_manager
from core.tasker_manager import task_manager


class DeviceCard(QFrame):
    """Card widget to display device information with quick actions"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(self.device_config.device_name)
        self.parent_widget = parent

        # Set frame style
        self.setObjectName("deviceCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(280, 180)
        self.setMaximumSize(350, 220)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.init_ui()
        # self.update_status()

        # Connect to task manager signals
        task_manager.device_added.connect(self.on_device_changed)
        task_manager.device_removed.connect(self.on_device_changed)
        # task_manager.scheduled_task_modified.connect(self.update_status)
        # task_manager.device_status_changed.connect(self.update_status)

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header with device name and type
        header_layout = QHBoxLayout()

        # Device Icon based on type
        icon_label = QLabel()
        icon_path = "assets/icons/device.svg"  # Default icon

        # Customize icon based on device type
        if hasattr(self.device_config, 'adb_config') and self.device_config.adb_config:
            device_type = self.device_config.adb_config.name
            if "phone" in device_type.lower():
                icon_path = "assets/icons/smartphone.svg"
            elif "tablet" in device_type.lower():
                icon_path = "assets/icons/tablet.svg"

        icon_pixmap = QPixmap(icon_path)
        if not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        header_layout.addWidget(icon_label)

        # Device name
        name_label = QLabel(self.device_config.device_name)
        name_label.setObjectName("deviceCardName")
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #e0e0e0; height: 1px; margin: 1px 0;")
        layout.addWidget(separator)

        # Device info
        info_grid = QGridLayout()
        info_grid.setSpacing(0)
        info_grid.setContentsMargins(0, 0, 0, 0)

        # Device type
        type_key = QLabel("类型:")
        type_key.setObjectName("infoLabel")
        # 更安全的方式获取设备类型文本
        device_type_text = ""
        if hasattr(self.device_config.device_type, "value"):
            # 如果是枚举类型
            device_type_text = self.device_config.device_type.value
        else:
            # 如果是字符串类型
            device_type_text = str(self.device_config.device_type)

        # 将设备类型转换为用户友好的显示文本
        if device_type_text == "adb":
            display_text = "ADB设备"
        elif device_type_text == "win32":
            display_text = "Win32窗口"
        else:
            display_text = device_type_text
        type_value = QLabel(display_text)
        type_value.setObjectName("infoValue")
        info_grid.addWidget(type_key, 0, 0)
        info_grid.addWidget(type_value, 0, 1)

        # Status
        status_key = QLabel("状态:")
        status_key.setObjectName("infoLabel")
        self.status_value = QLabel("加载中...")
        self.status_value.setObjectName("infoValue")
        info_grid.addWidget(status_key, 1, 0)
        info_grid.addWidget(self.status_value, 1, 1)

        # Next scheduled run
        schedule_key = QLabel("下次执行:")
        schedule_key.setObjectName("infoLabel")
        self.schedule_value = QLabel("未设置")
        self.schedule_value.setObjectName("infoValue")
        info_grid.addWidget(schedule_key, 2, 0)
        info_grid.addWidget(self.schedule_value, 2, 1)

        layout.addLayout(info_grid)
        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()

        # Run/Stop button
        self.run_btn = QPushButton("运行")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
        self.run_btn.clicked.connect(self.handle_run_stop_action)

        # Settings button
        settings_btn = QPushButton("设备详情")
        settings_btn.setObjectName("secondaryButton")
        settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        settings_btn.clicked.connect(self.open_device_page)

        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(settings_btn)

        layout.addLayout(button_layout)

    def update_status(self):
        """Update device status and scheduled task information"""
        if not self.device_config:
            return

        # Update status
        is_active = task_manager.is_device_active(self.device_config.device_name)
        is_running = False

        if is_active:
            device_state = task_manager.get_executor_state(self.device_config.device_name)
            if device_state:
                status = device_state.status.value

                if status == "idle":
                    self.status_value.setText("空闲")
                    self.status_value.setStyleSheet("color: #4CAF50;")  # Green
                elif status == "running":
                    self.status_value.setText("运行中")
                    self.status_value.setStyleSheet("color: #2196F3;")  # Blue
                    is_running = True
                elif status == "error":
                    self.status_value.setText("错误")
                    self.status_value.setStyleSheet("color: #F44336;")  # Red
                elif status == "stopping":
                    self.status_value.setText("正在停止")
                    self.status_value.setStyleSheet("color: #FF9800;")  # Orange
        else:
            self.status_value.setText("未运行")
            self.status_value.setStyleSheet("color: #9E9E9E;")  # Gray

        # Update run/stop button based on status
        if is_running:
            self.run_btn.setText("停止")
            self.run_btn.setObjectName("stopButton")
            self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
        else:
            self.run_btn.setText("运行")
            self.run_btn.setObjectName("primaryButton")
            self.run_btn.setIcon(QIcon("assets/icons/play.svg"))

        # Update schedule information
        has_enabled_schedules = False
        for resource in self.device_config.resources:
            if resource.schedules_enable and resource.schedules and any(
                    schedule.enabled for schedule in resource.schedules):
                has_enabled_schedules = True
                break

        if has_enabled_schedules:
            tasks_info = scheduled_task_manager.get_scheduled_tasks_info()
            device_tasks = [task for task in tasks_info if task['device_name'] == self.device_config.device_name]

            if device_tasks and any(task.get('next_run') for task in device_tasks):
                next_times = sorted([task['next_run'] for task in device_tasks if task.get('next_run')])
                if next_times:
                    time_str = next_times[0]
                    if " " in time_str:
                        time_part = time_str.split(" ")[1]  # 提取 "14:30:00"
                    else:
                        time_part = time_str  # 如果本来就是时间，就直接用

                    self.schedule_value.setText(time_part)
                    self.schedule_value.setStyleSheet("color: #2196F3;")  # Blue

                else:
                    self.schedule_value.setText("未设置时间")
                    self.schedule_value.setStyleSheet("")
            else:
                self.schedule_value.setText("已启用但未设置")
                self.schedule_value.setStyleSheet("")
        else:
            self.schedule_value.setText("未启用")
            self.schedule_value.setStyleSheet("color: #9E9E9E;")  # Gray

    def on_device_changed(self, device_name):
        """Handle device state changes"""
        if device_name == self.device_config.device_name:
            # self.update_status()
            pass

    @asyncSlot()
    async def handle_run_stop_action(self):
        """Handle run/stop button click based on current state"""
        if not self.device_config:
            return

        # Check if device is running
        is_active = task_manager.is_device_active(self.device_config.device_name)
        is_running = False

        if is_active:
            device_state = task_manager.get_executor_state(self.device_config.device_name)
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
        """Run all tasks for this device"""
        if self.device_config:
            device_name = self.device_config.device_name
            try:
                # Log the start of task execution
                self.logger.info(f"开始执行设备任务")

                # Execute tasks
                self.run_btn.setEnabled(False)
                self.run_btn.setText("运行中...")

                success = await task_manager.run_device_all_resource_task(self.device_config)

                # Log completion
                if success:
                    self.logger.info(f"设备任务执行完成")

                self.run_btn.setEnabled(True)

                # Update status (this will also update the button text)
                self.update_status()
            except Exception as e:
                # Log error
                self.logger.error(f"运行任务时出错: {str(e)}")
                self.run_btn.setEnabled(True)
                # Update status (this will also update the button text)
                self.update_status()

    @asyncSlot()
    async def stop_device_tasks(self):
        """Stop all tasks for this device"""
        if self.device_config:
            device_name = self.device_config.device_name
            try:
                # Log the stop action
                self.logger.info(f"停止设备任务")

                # Stop tasks
                self.run_btn.setEnabled(False)
                self.run_btn.setText("停止中...")

                # Stop the device executor
                success = await task_manager.stop_executor(device_name)

                # Log completion
                if success:
                    self.logger.info(f"设备任务已停止")

                self.run_btn.setEnabled(True)

                # Update status (this will also update the button text)
                self.update_status()
            except Exception as e:
                # Log error
                self.logger.error(f"停止任务时出错: {str(e)}")
                self.run_btn.setEnabled(True)
                # Update status (this will also update the button text)
                self.update_status()

    def open_device_page(self):
        """Open detailed device page"""
        # Find the main window
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_device_page'):
            main_window.show_device_page(self.device_config.device_name)