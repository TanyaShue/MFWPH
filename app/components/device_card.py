# -*- coding: UTF-8 -*-
"""
设备卡片组件
使用简化的状态管理器显示设备信息
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QGridLayout
from qasync import asyncSlot

from app.models.logging.log_manager import log_manager
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
        """连接信号"""
        # 监听状态管理器的状态变化
        device_status_manager.state_changed.connect(self.on_state_changed)
        # 监听UI信息变化
        device_status_manager.ui_info_changed.connect(self.on_ui_info_changed)

    def on_state_changed(self, name: str, old_state: DeviceState, new_state: DeviceState, context: dict):
        """当状态变化时更新显示"""
        if name != self.device_name:
            return

        # 状态变化时刷新显示
        self.refresh_display()

    def on_ui_info_changed(self, device_name: str, ui_info: DeviceUIInfo):
        """当UI信息变化时更新显示"""
        if device_name != self.device_name:
            return

        self.update_display(ui_info)

    def refresh_display(self):
        """刷新显示（从状态管理器获取最新状态）"""
        ui_info = device_status_manager.get_device_ui_info(self.device_name)
        if ui_info:
            self.update_display(ui_info)

    def update_display(self, ui_info: DeviceUIInfo):
        """根据UI信息更新显示"""
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

        # 更新定时任务显示
        scheduled_info = self._get_scheduled_info()
        self.schedule_value.setText(scheduled_info['text'])

        if scheduled_info['has_scheduled']:
            self.schedule_value.setStyleSheet("color: #2196F3;")  # 蓝色
            self.schedule_value.setToolTip(scheduled_info['tooltip'])
        else:
            self.schedule_value.setStyleSheet("color: #9E9E9E;")  # 灰色
            self.schedule_value.setToolTip("未设置定时任务")

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
        """获取定时任务信息"""
        # 从scheduled_task_manager获取实际的定时任务信息
        try:
            if hasattr(scheduled_task_manager, 'get_device_schedule'):
                schedule = scheduled_task_manager.get_device_schedule(self.device_name)
                if schedule:
                    return {
                        'has_scheduled': True,
                        'text': schedule.get('next_run_text', '已设置'),
                        'tooltip': schedule.get('tooltip', '定时任务已启用')
                    }
        except:
            pass

        # 默认返回未设置
        return {
            'has_scheduled': False,
            'text': '未设置',
            'tooltip': '未设置定时任务'
        }

    @asyncSlot()
    async def handle_run_stop_action(self):
        """处理运行/停止按钮点击"""
        if not self.device_config:
            return

        # 根据当前状态决定操作
        if self.device_manager.is_busy():
            # 停止设备
            await self.stop_device_tasks()
        else:
            # 运行设备
            await self.run_device_tasks()

    @asyncSlot()
    async def run_device_tasks(self):
        """运行设备任务"""
        if self.device_config:
            try:
                self.logger.info(f"开始执行设备任务")

                # 禁用按钮
                self.run_btn.setEnabled(False)

                success = await task_manager.run_device_all_resource_task(self.device_config)

                if success:
                    self.logger.info(f"设备任务执行完成")

            except Exception as e:
                self.logger.error(f"运行任务时出错: {str(e)}")

    @asyncSlot()
    async def stop_device_tasks(self):
        """停止设备任务"""
        if self.device_config:
            try:
                self.logger.info(f"停止设备任务")

                # 禁用按钮
                self.run_btn.setEnabled(False)

                # 停止设备执行器
                success = await task_manager.stop_executor(self.device_name)

                if success:
                    self.logger.info(f"设备任务已停止")

            except Exception as e:
                self.logger.error(f"停止任务时出错: {str(e)}")

    def open_device_page(self):
        """打开设备详情页面"""
        # 查找主窗口
        main_window = self.window()
        if main_window and hasattr(main_window, 'show_device_page'):
            main_window.show_device_page(self.device_name)

    def showEvent(self, event):
        """组件显示时刷新状态"""
        super().showEvent(event)
        self.refresh_display()

    def closeEvent(self, event):
        """清理资源"""
        # 断开信号连接
        try:
            device_status_manager.state_changed.disconnect(self.on_state_changed)
            device_status_manager.ui_info_changed.disconnect(self.on_ui_info_changed)
        except:
            pass
        super().closeEvent(event)