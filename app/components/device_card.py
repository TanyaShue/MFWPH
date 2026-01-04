# -*- coding: UTF-8 -*-
"""
设备卡片组件
使用简化的状态管理器显示设备信息，并实时更新定时任务状态
"""
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGridLayout
from qasync import asyncSlot

from app.models.logging.log_manager import log_manager
from app.models.config.global_config import global_config
from app.utils.notification_manager import notification_manager
from core.scheduled_task_manager import scheduled_task_manager
from core.tasker_manager import task_manager
from core.device_state_machine import DeviceState
from core.device_status_manager import device_status_manager, DeviceUIInfo


class DeviceCard(QFrame):
    """设备信息卡片组件，提供快速操作功能"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logger(self.device_name)
        self.parent_widget = parent

        # 设置框架样式
        self.setObjectName("deviceCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumSize(280, 180)
        self.setMaximumSize(350, 220)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # 获取或创建设备状态管理器
        self.device_manager = device_status_manager.get_or_create_device_manager(self.device_name)

        self.init_ui()
        self.connect_signals()

        # 初始化显示
        self.refresh_display()

    def init_ui(self):
        # ... (init_ui 的其余部分保持不变) ...
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 顶部：设备名称和类型
        header_layout = QHBoxLayout()

        # 设备图标
        icon_label = QLabel()
        icon_path = "assets/icons/device.svg"  # 默认图标

        # 根据设备类型自定义图标
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

        # 设备名称
        name_label = QLabel(self.device_name)
        name_label.setObjectName("deviceCardName")
        header_layout.addWidget(name_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #e0e0e0; height: 1px; margin: 1px 0;")
        layout.addWidget(separator)

        # 设备信息
        info_grid = QGridLayout()
        info_grid.setSpacing(0)
        info_grid.setContentsMargins(0, 0, 0, 0)

        # 设备类型
        type_key = QLabel("类型:")
        type_key.setObjectName("infoLabel")

        # 获取设备类型文本
        device_type_text = self._get_device_type_text()
        type_value = QLabel(device_type_text)
        type_value.setObjectName("infoValue")
        info_grid.addWidget(type_key, 0, 0)
        info_grid.addWidget(type_value, 0, 1)

        # 状态
        status_key = QLabel("状态:")
        status_key.setObjectName("infoLabel")
        self.status_value = QLabel("加载中...")
        self.status_value.setObjectName("infoValue")
        info_grid.addWidget(status_key, 1, 0)
        info_grid.addWidget(self.status_value, 1, 1)

        # 下次执行
        schedule_key = QLabel("下次执行:")
        schedule_key.setObjectName("infoLabel")
        self.schedule_value = QLabel("未设置")
        self.schedule_value.setObjectName("infoValue")
        info_grid.addWidget(schedule_key, 2, 0)
        info_grid.addWidget(self.schedule_value, 2, 1)

        # 进度条（初始隐藏）
        self.progress_label = QLabel("进度: 0%")
        self.progress_label.setObjectName("progressLabel")
        self.progress_label.setVisible(False)
        info_grid.addWidget(self.progress_label, 3, 0, 1, 2)

        layout.addLayout(info_grid)
        layout.addStretch()

        # 操作按钮
        button_layout = QHBoxLayout()

        # 运行/停止按钮
        self.run_btn = QPushButton("运行")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
        self.run_btn.clicked.connect(self.handle_run_stop_action)

        # 设备详情按钮
        settings_btn = QPushButton("设备详情")
        settings_btn.setObjectName("secondaryButton")
        settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        settings_btn.clicked.connect(self.open_device_page)

        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(settings_btn)

        layout.addLayout(button_layout)

    def _get_device_type_text(self) -> str:
        # ... (此方法保持不变) ...
        """获取设备类型的显示文本"""
        device_type_text = ""
        if hasattr(self.device_config.device_type, "value"):
            device_type_text = self.device_config.device_type.value
        else:
            device_type_text = str(self.device_config.device_type)

        # 转换为用户友好的显示文本
        type_map = {
            "adb": "ADB设备",
            "win32": "Win32窗口"
        }
        return type_map.get(device_type_text, device_type_text)

    def connect_signals(self):
        """连接所有需要的信号"""
        # 监听状态管理器的状态变化
        device_status_manager.state_changed.connect(self.on_state_changed)
        device_status_manager.ui_info_changed.connect(self.on_ui_info_changed)

        # NEW: 监听定时任务管理器的变化，以实时更新UI
        scheduled_task_manager.task_added.connect(self.on_schedule_changed)
        scheduled_task_manager.task_removed.connect(self.on_schedule_changed)
        scheduled_task_manager.task_modified.connect(self.on_schedule_changed)
        scheduled_task_manager.task_status_changed.connect(self.on_schedule_changed)

    # NEW: 用于处理所有定时任务变化的槽函数
    def on_schedule_changed(self, *args):
        """
        当任何定时任务发生变化时，刷新此卡片的显示。
        这里我们不需要关心信号的具体参数，只要有变化就刷新。
        """
        self.refresh_display()

    def on_state_changed(self, name: str, old_state: DeviceState, new_state: DeviceState, context: dict):
        if name == self.device_name:
            self.refresh_display()

    def on_ui_info_changed(self, device_name: str, ui_info: DeviceUIInfo):
        if device_name == self.device_name:
            self.update_display(ui_info)

    def refresh_display(self):
        ui_info = device_status_manager.get_device_ui_info(self.device_name)
        if ui_info:
            self.update_display(ui_info)

    def update_display(self, ui_info: DeviceUIInfo):
        # ... (状态、进度、按钮的更新逻辑保持不变) ...
        # 更新状态文本
        self.status_value.setText(ui_info.state_text)
        self.status_value.setStyleSheet(f"color: {ui_info.state_color};")

        # 构建提示文本
        tooltip = ui_info.tooltip
        if ui_info.error_message:
            tooltip += f": {ui_info.error_message}"
        if ui_info.queue_length > 0:
            tooltip += f"，队列中还有 {ui_info.queue_length} 个任务"
        self.status_value.setToolTip(tooltip)

        # 更新进度显示
        if ui_info.state == DeviceState.RUNNING and ui_info.progress > 0:
            self.progress_label.setText(f"进度: {ui_info.progress}%")
            self.progress_label.setVisible(True)
            self.progress_label.setStyleSheet(f"color: {ui_info.state_color};")
        else:
            self.progress_label.setVisible(False)

        # MODIFIED: 更新定时任务显示
        scheduled_info = self._get_scheduled_info()
        self.schedule_value.setText(scheduled_info['text'])
        self.schedule_value.setToolTip(scheduled_info['tooltip'])

        if scheduled_info['has_scheduled']:
            self.schedule_value.setStyleSheet("color: #2196F3;")  # 蓝色
        else:
            self.schedule_value.setStyleSheet("color: #9E9E9E;")  # 灰色

        # ... (按钮更新逻辑保持不变) ...
        # 更新按钮
        self.run_btn.setText(ui_info.button_text)
        self.run_btn.setEnabled(ui_info.button_enabled)

        if ui_info.is_busy:
            self.run_btn.setObjectName("stopButton")
            self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
        else:
            self.run_btn.setObjectName("primaryButton")
            self.run_btn.setIcon(QIcon("assets/icons/play.svg"))

        # 刷新样式
        self.run_btn.style().unpolish(self.run_btn)
        self.run_btn.style().polish(self.run_btn)

    def _get_scheduled_info(self) -> dict:
        """MODIFIED: 从定时任务管理器获取并格式化定时任务信息"""
        try:
            # 1. 获取本设备的所有任务
            device_tasks = scheduled_task_manager.get_tasks_for_device(self.device_name)

            # 2. 筛选出活动的任务，并提取下次运行时间
            active_next_runs = []
            for task in device_tasks:
                if task.get('status') == '活动' and task.get('next_run'):
                    active_next_runs.append(task['next_run'])

            # 3. 如果没有活动的任务，返回未设置
            if not active_next_runs:
                raise ValueError("No active schedules")

            # 4. 找到最早的下次运行时间
            next_run_time = min(active_next_runs)
            now = datetime.now()
            today = now.date()
            tomorrow = (now + timedelta(days=1)).date()

            # 5. 格式化显示文本
            if next_run_time.date() == today:
                run_text = f"今日 {next_run_time.strftime('%H:%M')}"
            elif next_run_time.date() == tomorrow:
                run_text = f"明日 {next_run_time.strftime('%H:%M')}"
            else:
                run_text = next_run_time.strftime('%m-%d %H:%M')

            return {
                'has_scheduled': True,
                'text': run_text,
                'tooltip': f"下次任务时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"
            }

        except Exception:
            # 捕获所有异常（例如没有任务），返回默认值
            return {
                'has_scheduled': False,
                'text': '未设置',
                'tooltip': '此设备没有活动的定时任务'
            }

    @asyncSlot()
    async def handle_run_stop_action(self):
        # ... (此方法保持不变) ...
        if not self.device_config:
            return

        # 启动更新尚未完成时禁止启动任务
        if getattr(global_config, "startup_update_in_progress", False):
            notification_manager.show_warning("正在检查/安装更新，请稍后再开始任务。", "更新进行中")
            return

        if self.device_manager.is_busy():
            await self.stop_device_tasks()
        else:
            await self.run_device_tasks()

    @asyncSlot()
    async def run_device_tasks(self):
        # ... (此方法保持不变) ...
        if self.device_config:
            try:
                self.logger.info(f"开始执行设备任务")
                self.run_btn.setEnabled(False)
                success = await task_manager.run_device_all_resource_task(self.device_config)
                if success:
                    self.logger.info(f"设备任务创建完成")
            except Exception as e:
                self.logger.error(f"运行任务时出错: {str(e)}")

    @asyncSlot()
    async def stop_device_tasks(self):
        # ... (此方法保持不变) ...
        if self.device_config:
            try:
                self.logger.info(f"停止设备任务")
                self.run_btn.setEnabled(False)
                success = await task_manager.stop_device_processing(self.device_name)
                if success:
                    self.logger.info(f"设备任务已停止")
            except Exception as e:
                self.logger.error(f"停止任务时出错: {str(e)}")

    def open_device_page(self):
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_device_page_by_name'):
            main_window.show_device_page_by_name(self.device_name)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_display()

    def closeEvent(self, event):
        """清理资源，断开所有信号连接"""
        try:
            device_status_manager.state_changed.disconnect(self.on_state_changed)
            device_status_manager.ui_info_changed.disconnect(self.on_ui_info_changed)

            # NEW: 断开定时任务管理器的信号
            scheduled_task_manager.task_added.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_removed.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_modified.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_status_changed.disconnect(self.on_schedule_changed)
        except Exception as e:
            # 忽略断开连接时可能发生的错误（例如信号已被移除）
            self.logger.debug(f"断开信号时出现异常: {e}")
        super().closeEvent(event)