from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGridLayout
from qasync import asyncSlot

from app.models.logging.log_manager import log_manager
from core.scheduled_task_manager import scheduled_task_manager
from core.tasker_manager import task_manager
from core.device_status_manager import device_status_manager, DeviceStatusInfo, DeviceStatus


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

        # 注册设备到状态管理器
        device_status_manager.register_device(self.device_config.device_name)

        self.init_ui()
        self.connect_signals()

        # 初始化显示
        self.refresh_display()

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

    def connect_signals(self):
        """连接信号"""
        # 监听状态变化信号
        device_status_manager.status_changed.connect(self.on_status_changed)
        # 监听状态机状态变化信号
        device_status_manager.state_machine_changed.connect(self.on_state_machine_changed)

    def on_status_changed(self, device_name: str, status_info: DeviceStatusInfo):
        """当状态变化时更新显示"""
        if device_name != self.device_config.device_name:
            return

        self.update_display(status_info)

    def on_state_machine_changed(self, device_name: str, old_state: str, new_state: str):
        """当状态机状态变化时更新显示"""
        if device_name != self.device_config.device_name:
            return

        # 从状态管理器获取最新的状态信息并更新显示
        status_info = device_status_manager.get_device_status(self.device_config.device_name)
        if status_info:
            self.update_display(status_info)

    def refresh_display(self):
        """刷新显示（从状态管理器获取最新状态）"""
        status_info = device_status_manager.get_device_status(self.device_config.device_name)
        if status_info:
            self.update_display(status_info)

    def update_display(self, status_info: DeviceStatusInfo):
        """根据状态信息更新UI显示"""
        # 更新状态文本
        status_text_map = {
            DeviceStatus.OFFLINE: "未运行",
            DeviceStatus.IDLE: "空闲",
            DeviceStatus.RUNNING: "运行中",
            DeviceStatus.ERROR: "错误",
            DeviceStatus.STOPPING: "正在停止",
            DeviceStatus.SCHEDULED: "已计划",
            DeviceStatus.WAITING: "等待中",
            DeviceStatus.CONNECTING: "连接中"
        }

        # 获取UI配置
        ui_config = device_status_manager.get_ui_config(status_info.status)

        # 更新状态显示
        status_text = status_text_map.get(status_info.status, "未知")
        self.status_value.setText(status_text)
        self.status_value.setStyleSheet(f"color: {ui_config['color']};")

        # 构建提示文本
        tooltip = ui_config['tooltip']
        if status_info.error_message:
            tooltip += f": {status_info.error_message}"
        if status_info.queue_length > 0:
            tooltip += f"，队列中还有 {status_info.queue_length} 个任务"
        self.status_value.setToolTip(tooltip)

        # 更新定时任务显示
        self.schedule_value.setText(status_info.scheduled_time_text)
        if status_info.has_scheduled_tasks:
            self.schedule_value.setStyleSheet("color: #2196F3;")  # Blue
            if status_info.next_scheduled_time:
                tooltip = f"下次执行时间: {status_info.next_scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}"
            else:
                tooltip = "定时任务已启用"
            self.schedule_value.setToolTip(tooltip)
        else:
            self.schedule_value.setStyleSheet("color: #9E9E9E;")  # Gray
            self.schedule_value.setToolTip("未设置定时任务")

        # 更新按钮
        self.run_btn.setText(ui_config['button_text'])
        self.run_btn.setEnabled(ui_config['button_enabled'])

        if status_info.is_running:
            self.run_btn.setObjectName("stopButton")
            self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
        else:
            self.run_btn.setObjectName("primaryButton")
            self.run_btn.setIcon(QIcon("assets/icons/play.svg"))

        # 刷新样式
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)

    @asyncSlot()
    async def handle_run_stop_action(self):
        """Handle run/stop button click based on current state"""
        if not self.device_config:
            return

        # 从状态管理器获取当前状态
        status_info = device_status_manager.get_device_status(self.device_config.device_name)
        if not status_info:
            return

        if status_info.is_running:
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

                # 禁用按钮
                self.run_btn.setEnabled(False)

                success = await task_manager.run_device_all_resource_task(self.device_config)

                # Log completion
                if success:
                    self.logger.info(f"设备任务执行完成")

            except Exception as e:
                # Log error
                self.logger.error(f"运行任务时出错: {str(e)}")

    @asyncSlot()
    async def stop_device_tasks(self):
        """Stop all tasks for this device"""
        if self.device_config:
            device_name = self.device_config.device_name
            try:
                # Log the stop action
                self.logger.info(f"停止设备任务")

                # 禁用按钮
                self.run_btn.setEnabled(False)

                # Stop the device executor
                success = await task_manager.stop_executor(device_name)

                # Log completion
                if success:
                    self.logger.info(f"设备任务已停止")

            except Exception as e:
                # Log error
                self.logger.error(f"停止任务时出错: {str(e)}")

    def open_device_page(self):
        """Open detailed device page"""
        # Find the main window
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_device_page'):
            main_window.show_device_page(self.device_config.device_name)

    def showEvent(self, event):
        """组件显示时刷新状态"""
        super().showEvent(event)
        self.refresh_display()

    def closeEvent(self, event):
        """清理资源"""
        # 断开信号连接
        try:
            device_status_manager.status_changed.disconnect(self.on_status_changed)
        except:
            pass
        super().closeEvent(event)