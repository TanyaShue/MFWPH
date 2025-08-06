# -*- coding: UTF-8 -*-
"""
设备基本信息组件
使用统一状态机显示设备状态
"""

from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from qasync import asyncSlot

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.add_device_dialog import AddDeviceDialog
from core.scheduled_task_manager import scheduled_task_manager
from core.tasker_manager import task_manager
from core.device_state_machine import DeviceState
from core.device_status_manager import device_status_manager, DeviceUIInfo


class BasicInfoWidget(QFrame):
    """设备基本信息组件 - 紧凑版本"""

    def __init__(self, device_name, device_config, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = device_config
        self.parent_widget = parent
        self.logger = log_manager.get_device_logger(device_name)

        # 设置基本属性
        self.setObjectName("infoFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumHeight(90)
        self.setMinimumHeight(80)

        # 获取或创建设备状态机
        self.device_machine = device_status_manager.get_or_create_device_machine(device_name)

        self.init_ui()
        self.connect_signals()

        # 初始化显示
        self.refresh_display()

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
        """连接信号"""
        # 监听状态机状态变化信号
        device_status_manager.state_changed.connect(self.on_state_changed)
        # 监听UI信息变化信号
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
        # 更新状态指示器
        if hasattr(self, 'status_indicator'):
            self.status_indicator.setStyleSheet(f"""
                QLabel {{
                    background-color: {ui_info.state_color};
                    border-radius: 5px;
                }}
            """)

            # 构建提示文本
            tooltip = ui_info.tooltip
            if ui_info.error_message:
                tooltip += f": {ui_info.error_message}"
            if ui_info.queue_length > 0:
                tooltip += f"，队列中还有 {ui_info.queue_length} 个任务"
            if ui_info.progress > 0 and ui_info.state == DeviceState.RUNNING:
                tooltip += f"（进度: {ui_info.progress}%）"
            self.status_indicator.setToolTip(tooltip)

        # 更新按钮
        if hasattr(self, 'run_btn'):
            self.run_btn.setText(ui_info.button_text)
            self.run_btn.setEnabled(ui_info.button_enabled)

            if ui_info.is_busy:
                self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
                self.run_btn.setToolTip("停止当前任务")
                self.run_btn.setStyleSheet("""
                    QPushButton#primaryButton {
                        background-color: #F44336;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 16px;
                        font-size: 13px;
                    }
                    QPushButton#primaryButton:hover {
                        background-color: #D32F2F;
                    }
                    QPushButton#primaryButton:disabled {
                        background-color: #cccccc;
                    }
                """)
            else:
                self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
                self.run_btn.setToolTip("开始执行任务")
                self.run_btn.setStyleSheet("""
                    QPushButton#primaryButton {
                        background-color: #4CAF50;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 4px 16px;
                        font-size: 13px;
                    }
                    QPushButton#primaryButton:hover {
                        background-color: #45A049;
                    }
                    QPushButton#primaryButton:disabled {
                        background-color: #cccccc;
                    }
                """)

            # 刷新样式
            self.run_btn.style().unpolish(self.run_btn)
            self.run_btn.style().polish(self.run_btn)

        # 更新定时任务显示
        if hasattr(self, 'schedule_value'):
            # 从scheduled_task_manager获取定时任务信息
            scheduled_info = self._get_scheduled_info()

            if scheduled_info['has_scheduled']:
                self.clock_icon.setVisible(True)
                self.schedule_value.setText(scheduled_info['text'])
                self.schedule_value.setToolTip(scheduled_info['tooltip'])
            else:
                self.clock_icon.setVisible(False)
                self.schedule_value.setText("未启用")
                self.schedule_value.setToolTip("未设置定时任务")

    def _get_scheduled_info(self) -> dict:
        """获取定时任务信息"""
        # 这里应该从scheduled_task_manager获取实际的定时任务信息
        # 暂时返回默认值
        try:
            # 尝试从scheduled_task_manager获取信息
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

        return {
            'has_scheduled': False,
            'text': '未启用',
            'tooltip': '未设置定时任务'
        }

    @asyncSlot()
    async def handle_run_stop_action(self):
        """处理运行/停止按钮点击"""
        if not self.device_config:
            return

        # 获取当前状态
        current_state = self.device_machine.get_state()

        if self.device_machine.is_busy():
            # 停止设备
            await self.stop_device_tasks()
        else:
            # 运行设备
            await self.run_device_tasks()

    @asyncSlot()
    async def run_device_tasks(self):
        """运行设备任务"""
        try:
            if self.device_config:
                self.logger.info("开始执行设备任务")

                # 禁用按钮
                self.run_btn.setEnabled(False)

                success = await task_manager.run_device_all_resource_task(self.device_config)

                if success:
                    self.logger.info("设备任务执行完成")

        except Exception as e:
            self.logger.error(f"运行任务时出错: {str(e)}")

    @asyncSlot()
    async def stop_device_tasks(self):
        """停止设备任务"""
        try:
            if self.device_config:
                self.logger.info("停止设备任务")

                # 禁用按钮
                self.run_btn.setEnabled(False)

                # 停止设备执行器
                success = await task_manager.stop_executor(self.device_name)

                if success:
                    self.logger.info("设备任务已停止")

        except Exception as e:
            self.logger.error(f"停止任务时出错: {str(e)}")

    def open_settings_dialog(self):
        """打开设备设置对话框"""
        if self.device_config:
            original_device_name = self.device_name
            dialog = AddDeviceDialog(global_config, self, edit_mode=True, device_config=self.device_config)
            dialog.exec_()

            updated_device_config = global_config.get_device_config(original_device_name)

            if updated_device_config:
                self.logger.info("设备配置已更新")
                self.device_config = updated_device_config

                if hasattr(self.parent_widget, 'refresh_ui'):
                    self.parent_widget.refresh_ui()
            else:
                main_window = self.window()
                if hasattr(main_window, 'on_device_deleted'):
                    main_window.on_device_deleted()
                if hasattr(main_window, 'show_previous_device_or_home'):
                    main_window.show_previous_device_or_home(original_device_name)

    def refresh_ui(self, device_config=None):
        """刷新组件"""
        if device_config:
            self.device_config = device_config

        # 清除现有布局和子部件
        if self.layout():
            while self.layout().count():
                child = self.layout().takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())

            QWidget().setLayout(self.layout())

        self.init_ui()
        self.connect_signals()
        self.refresh_display()

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