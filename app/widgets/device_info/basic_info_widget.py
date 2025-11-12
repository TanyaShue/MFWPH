# -*- coding: UTF-8 -*-
"""
设备基本信息组件
使用简化的状态管理器显示设备状态，并实时显示定时任务信息
"""

from datetime import datetime, timedelta
from PySide6.QtGui import QFont, QIcon
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

        # 获取或创建设备状态管理器
        self.device_manager = device_status_manager.get_or_create_device_manager(self.device_name)

        self.init_ui()
        self.connect_signals()

        # 初始化显示
        self.refresh_display()

    def init_ui(self):
        """初始化用户界面"""
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
            self.clock_icon.setVisible(False)  # 初始隐藏
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
            # 如果没有设备配置，显示错误信息
            error_label = QLabel("未找到设备配置")
            error_label.setObjectName("errorText")
            error_label.setStyleSheet("color: #ff4444; font-size: 12px;")
            layout.addWidget(error_label)

    def connect_signals(self):
        """连接所有需要的信号"""
        # 监听状态管理器的状态变化信号
        device_status_manager.state_changed.connect(self.on_state_changed)
        device_status_manager.ui_info_changed.connect(self.on_ui_info_changed)

        # 监听定时任务管理器的变化
        scheduled_task_manager.task_added.connect(self.on_schedule_changed)
        scheduled_task_manager.task_removed.connect(self.on_schedule_changed)
        scheduled_task_manager.task_modified.connect(self.on_schedule_changed)
        scheduled_task_manager.task_status_changed.connect(self.on_schedule_changed)

    def on_schedule_changed(self, *args):
        """当任何定时任务变化时，刷新此组件的显示"""
        self.refresh_display()

    def on_state_changed(self, name: str, old_state: DeviceState, new_state: DeviceState, context: dict):
        """当设备状态改变时的槽函数"""
        if name == self.device_name:
            self.refresh_display()

    def on_ui_info_changed(self, device_name: str, ui_info: DeviceUIInfo):
        """当设备UI信息改变时的槽函数"""
        if device_name == self.device_name:
            self.update_display(ui_info)

    def refresh_display(self):
        """从管理器获取最新信息并刷新整个组件的显示"""
        ui_info = device_status_manager.get_device_ui_info(self.device_name)
        if ui_info:
            self.update_display(ui_info)

    def update_display(self, ui_info: DeviceUIInfo):
        """根据传入的UI信息更新界面元素"""
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

        # 更新运行/停止按钮
        if hasattr(self, 'run_btn'):
            self.run_btn.setText(ui_info.button_text)
            self.run_btn.setEnabled(ui_info.button_enabled)

            if ui_info.is_busy:
                self.run_btn.setIcon(QIcon("assets/icons/stop.svg"))
                self.run_btn.setToolTip("停止当前任务")
            else:
                self.run_btn.setIcon(QIcon("assets/icons/play.svg"))
                self.run_btn.setToolTip("开始执行任务")

            # 强制刷新按钮样式
            self.run_btn.style().unpolish(self.run_btn)
            self.run_btn.style().polish(self.run_btn)

        # 更新定时任务显示
        if hasattr(self, 'schedule_value'):
            scheduled_info = self._get_scheduled_info()

            if scheduled_info['has_scheduled']:
                self.clock_icon.setVisible(True)
                self.schedule_value.setText(scheduled_info['text'])
                self.schedule_value.setToolTip(scheduled_info['tooltip'])
            else:
                self.clock_icon.setVisible(False)
                self.schedule_value.setText("未启用")
                self.schedule_value.setToolTip("此设备没有活动的定时任务")

    def _get_scheduled_info(self) -> dict:
        """从定时任务管理器获取并格式化定时任务信息"""
        try:
            device_tasks = scheduled_task_manager.get_tasks_for_device(self.device_name)

            active_next_runs = [
                task['next_run'] for task in device_tasks
                if task.get('status') == '活动' and task.get('next_run')
            ]

            if not active_next_runs:
                raise ValueError("No active schedules")

            next_run_time = min(active_next_runs)
            now = datetime.now()
            today = now.date()
            tomorrow = (now + timedelta(days=1)).date()

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
            return {
                'has_scheduled': False,
                'text': '未启用',
                'tooltip': '此设备没有活动的定时任务'
            }

    @asyncSlot()
    async def handle_run_stop_action(self):
        """处理运行/停止按钮的点击事件"""
        if not self.device_config: return
        if self.device_manager.is_busy():
            await self.stop_device_tasks()
        else:
            await self.run_device_tasks()

    @asyncSlot()
    async def run_device_tasks(self):
        """异步运行设备的所有任务"""
        try:
            if self.device_config:
                self.logger.info("开始任务")
                self.run_btn.setEnabled(False)
                success = await task_manager.run_device_all_resource_task(self.device_config)
                if success: self.logger.info("设备任务创建完成")
        except Exception as e:
            self.logger.error(f"运行任务时出错: {str(e)}")

    @asyncSlot()
    async def stop_device_tasks(self):
        """异步停止设备的所有任务"""
        try:
            if self.device_config:
                self.logger.info("停止设备任务")
                self.run_btn.setEnabled(False)
                success = await task_manager.stop_device_processing(self.device_name)
                if success: self.logger.info("设备任务已停止")
        except Exception as e:
            self.logger.error(f"停止任务时出错: {str(e)}")

    def open_settings_dialog(self):
        """打开设备设置对话框"""
        if self.device_config:
            original_device_name = self.device_name
            dialog = AddDeviceDialog(global_config, self, edit_mode=True, device_config=self.device_config)
            dialog.exec_()
            # 对话框关闭后，检查配置是否仍然存在
            updated_device_config = global_config.get_device_config(original_device_name)
            if updated_device_config:
                self.logger.info("设备配置已更新")
                self.device_config = updated_device_config
                # 如果父组件有 refresh_ui 方法，则调用它来刷新整个页面
                if hasattr(self.parent_widget, 'refresh_ui'):
                    self.parent_widget.refresh_ui()
            else:
                # 如果配置不存在，说明设备可能已被删除
                main_window = self.window()
                if hasattr(main_window, 'on_device_deleted'):
                    main_window.on_device_deleted()
                if hasattr(main_window, 'show_previous_device_or_home'):
                    main_window.show_previous_device_or_home(original_device_name)

    def refresh_ui(self, device_config=None):
        """安全地刷新UI，先清除旧的UI再重新初始化"""
        if device_config: self.device_config = device_config
        if self.layout():
            # 使用一个虚拟QWidget接管并销毁旧布局及其所有子项，这是最安全的方式
            QWidget().setLayout(self.layout())

        # 重新创建UI和信号连接
        self.init_ui()
        self.connect_signals()
        self.refresh_display()

    def _clear_layout(self, layout):
        """递归地清除布局中的所有项目"""
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    self._clear_layout(child.layout())

    def showEvent(self, event):
        """当组件显示时，确保其内容是最新的"""
        super().showEvent(event)
        self.refresh_display()

    def closeEvent(self, event):
        """清理资源，断开所有信号连接，防止内存泄漏"""
        try:
            device_status_manager.state_changed.disconnect(self.on_state_changed)
            device_status_manager.ui_info_changed.disconnect(self.on_ui_info_changed)

            scheduled_task_manager.task_added.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_removed.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_modified.disconnect(self.on_schedule_changed)
            scheduled_task_manager.task_status_changed.disconnect(self.on_schedule_changed)
        except Exception as e:
            self.logger.debug(f"断开信号时出现异常: {e}")
        super().closeEvent(event)