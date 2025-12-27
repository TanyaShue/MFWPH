# create_task_dialog.py
from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QLabel, QPushButton, QTimeEdit, QCheckBox,
    QRadioButton, QButtonGroup, QMessageBox, QDialog, QGridLayout
)

from app.models.config.global_config import global_config


class CreateTaskDialog(QDialog):
    """创建或编辑任务的对话框（完全可编辑版）"""

    task_saved = Signal(dict)

    def __init__(self, parent=None, task_info: dict = None):
        super().__init__(parent)
        self.is_edit_mode = task_info is not None
        self.editing_task_info = task_info

        title = "编辑定时任务" if self.is_edit_mode else "创建定时任务"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(450, 550)
        self.init_ui()

        if self.is_edit_mode:
            self.load_task_data(task_info)
        else:
            if self.device_combo.count() > 0:
                self.on_device_changed(self.device_combo.currentText())

    def init_ui(self):
        self.setStyleSheet("""
            QDialog { background: white; }
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #2196F3;
            }
            QComboBox, QTimeEdit {
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 3px;
                font-size: 11px;
                min-height: 24px;
            }
            QComboBox:hover, QTimeEdit:hover { border-color: #2196F3; }
            QRadioButton, QCheckBox { font-size: 11px; }
            QPushButton {
                padding: 6px 15px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # 1. 选择目标
        device_group = QGroupBox("1. 选择目标")
        device_layout = QGridLayout(device_group)
        device_layout.setSpacing(8)

        device_layout.addWidget(QLabel("设备:"), 0, 0)
        self.device_combo = QComboBox()
        devices = global_config.get_app_config().devices
        for device in devices:
            self.device_combo.addItem(device.device_name)
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        device_layout.addWidget(self.device_combo, 0, 1)

        device_layout.addWidget(QLabel("资源:"), 1, 0)
        self.resource_combo = QComboBox()
        self.resource_combo.currentTextChanged.connect(self.on_resource_changed)
        device_layout.addWidget(self.resource_combo, 1, 1)
        layout.addWidget(device_group)

        # 2. 定时设置
        self.schedule_group = QGroupBox("2. 定时设置")
        schedule_layout = QVBoxLayout(self.schedule_group)
        schedule_layout.setSpacing(8)

        type_widget = QWidget()
        type_layout = QHBoxLayout(type_widget)
        type_layout.setContentsMargins(0, 0, 0, 0)
        self.schedule_type_group = QButtonGroup()
        self.once_radio = QRadioButton("单次")
        self.daily_radio = QRadioButton("每日")
        self.weekly_radio = QRadioButton("每周")
        self.once_radio.setChecked(True)
        self.schedule_type_group.addButton(self.once_radio, 0)
        self.schedule_type_group.addButton(self.daily_radio, 1)
        self.schedule_type_group.addButton(self.weekly_radio, 2)
        type_layout.addWidget(self.once_radio)
        type_layout.addWidget(self.daily_radio)
        type_layout.addWidget(self.weekly_radio)
        type_layout.addStretch()
        schedule_layout.addWidget(type_widget)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("时间:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")
        self.time_edit.setTime(QTime.currentTime())
        time_layout.addWidget(self.time_edit)
        time_layout.addStretch()
        schedule_layout.addLayout(time_layout)

        self.week_widget = QWidget()
        week_layout = QVBoxLayout(self.week_widget)
        week_layout.setContentsMargins(0, 5, 0, 0)
        week_grid = QGridLayout()
        week_grid.setSpacing(5)
        self.week_checkboxes = []
        week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i, day in enumerate(week_days):
            checkbox = QCheckBox(day)
            self.week_checkboxes.append(checkbox)
            week_grid.addWidget(checkbox, i // 4, i % 4)
        week_layout.addLayout(week_grid)

        quick_layout = QHBoxLayout()
        for text, func in [("工作日", self.select_workdays), ("周末", self.select_weekend),
                           ("全选", self.select_all_days), ("清空", self.clear_all_days)]:
            btn = QPushButton(text)
            btn.setStyleSheet("padding: 3px 8px; font-size: 10px;")
            btn.clicked.connect(func)
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        week_layout.addLayout(quick_layout)
        self.week_widget.setVisible(False)
        schedule_layout.addWidget(self.week_widget)
        self.schedule_type_group.buttonClicked.connect(self.on_schedule_type_changed)
        layout.addWidget(self.schedule_group)

        # 3. 高级设置
        self.advanced_group = QGroupBox("3. 高级设置")
        advanced_layout = QGridLayout(self.advanced_group)
        advanced_layout.setSpacing(8)
        advanced_layout.addWidget(QLabel("配置方案:"), 0, 0)
        self.config_scheme_combo = QComboBox()
        advanced_layout.addWidget(self.config_scheme_combo, 0, 1)
        self.notify_checkbox = QCheckBox("任务执行后发送通知")
        advanced_layout.addWidget(self.notify_checkbox, 1, 0, 1, 2)
        self.force_stop_checkbox = QCheckBox("运行前强制停止所有任务")
        self.force_stop_checkbox.setToolTip("开启后，本任务触发时若有其他任务在运行，将先中止它们再启动本任务。")
        self.force_stop_checkbox.setStyleSheet("color: #E91E63;") # 稍微显眼的颜色
        advanced_layout.addWidget(self.force_stop_checkbox)
        layout.addWidget(self.advanced_group)

        layout.addStretch()

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background: #f0f0f0; color: #333;")
        cancel_btn.clicked.connect(self.reject)
        self.save_btn = QPushButton("创建" if not self.is_edit_mode else "保存更改")
        self.save_btn.setStyleSheet("""
            QPushButton { background: #2196F3; color: white; }
            QPushButton:hover { background: #1976D2; }
            QPushButton:disabled { background: #ccc; color: #999; }
        """)
        self.save_btn.clicked.connect(self.on_save_task)
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

        self.update_save_button()

    def on_device_changed(self, device_name: str):
        if not device_name:
            self.resource_combo.clear()
            return
        device_config = global_config.get_device_config(device_name)
        if not device_config: return

        current_resource = self.resource_combo.currentText()
        self.resource_combo.blockSignals(True)
        self.resource_combo.clear()
        resource_names = [res.resource_name for res in device_config.resources]
        self.resource_combo.addItems(resource_names)

        if current_resource in resource_names:
            self.resource_combo.setCurrentText(current_resource)

        self.resource_combo.blockSignals(False)

        if self.resource_combo.count() > 0:
            self.on_resource_changed(self.resource_combo.currentText())
        else:
            self.on_resource_changed("")

    def on_resource_changed(self, resource_name: str):
        current_config = self.config_scheme_combo.currentText()
        self.config_scheme_combo.blockSignals(True)
        self.config_scheme_combo.clear()
        self.config_scheme_combo.addItem("默认配置")

        if resource_name:
            all_settings = global_config.get_app_config().resource_settings
            relevant_settings = [s.name for s in all_settings if s.resource_name == resource_name]
            self.config_scheme_combo.addItems(relevant_settings)

        if self.config_scheme_combo.findText(current_config) != -1:
            self.config_scheme_combo.setCurrentText(current_config)

        self.config_scheme_combo.blockSignals(False)
        self.update_save_button()

    def load_task_data(self, task_info: dict):
        self.device_combo.blockSignals(True)
        self.resource_combo.blockSignals(True)

        self.device_combo.setCurrentText(task_info.get('device_name', ''))
        self.on_device_changed(self.device_combo.currentText())
        self.resource_combo.setCurrentText(task_info.get('resource_name', ''))
        self.on_resource_changed(self.resource_combo.currentText())

        self.config_scheme_combo.setCurrentText(task_info.get('config_scheme', '默认配置'))
        self.notify_checkbox.setChecked(task_info.get('notify', False))
        self.force_stop_checkbox.setChecked(task_info.get('force_stop', False))

        self.device_combo.blockSignals(False)
        self.resource_combo.blockSignals(False)

        time_str = task_info.get('time', '00:00:00')
        self.time_edit.setTime(QTime.fromString(time_str, "HH:mm:ss"))
        schedule_type = task_info.get('schedule_type', '每日执行')
        if schedule_type == '单次执行':
            self.once_radio.setChecked(True)
        elif schedule_type == '每周执行':
            self.weekly_radio.setChecked(True)
            selected_days = task_info.get('week_days', [])
            for checkbox in self.week_checkboxes:
                checkbox.setChecked(checkbox.text() in selected_days)
        else:
            self.daily_radio.setChecked(True)
        self.on_schedule_type_changed()

        self.update_save_button()

    def on_save_task(self):
        device_name = self.device_combo.currentText()
        resource_name = self.resource_combo.currentText()
        if not device_name or not resource_name:
            QMessageBox.warning(self, "警告", "必须选择一个有效的设备和资源！")
            return

        schedule_info = self.get_schedule_info()
        if schedule_info['schedule_type'] == '每周执行' and not schedule_info.get('week_days'):
            QMessageBox.warning(self, "警告", "每周执行类型下，请选择至少一个执行日！")
            return

        task_info = {
            'device_name': device_name,
            'resource_name': resource_name,
            'config_scheme': self.config_scheme_combo.currentText(),
            'notify': self.notify_checkbox.isChecked(),
            'force_stop': self.force_stop_checkbox.isChecked(),
            **schedule_info
        }

        if self.is_edit_mode:
            task_info['id'] = self.editing_task_info.get('id')
            task_info['status'] = self.editing_task_info.get('status', '活动')
        else:
            task_info['status'] = '活动'

        self.task_saved.emit(task_info)
        self.accept()

    def update_save_button(self):
        is_ready = bool(self.device_combo.currentText() and self.resource_combo.currentText())
        self.save_btn.setEnabled(is_ready)
        self.schedule_group.setEnabled(is_ready)
        self.advanced_group.setEnabled(is_ready)

    def on_schedule_type_changed(self):
        self.week_widget.setVisible(self.weekly_radio.isChecked())

    def get_schedule_info(self):
        info = {'time': self.time_edit.time().toString("HH:mm:ss")}
        if self.once_radio.isChecked():
            info['schedule_type'] = '单次执行'
        elif self.daily_radio.isChecked():
            info['schedule_type'] = '每日执行'
        else:
            info['schedule_type'] = '每周执行'
            info['week_days'] = [cb.text() for cb in self.week_checkboxes if cb.isChecked()]
        return info

    def select_workdays(self):
        for i in range(5): self.week_checkboxes[i].setChecked(True)
        for i in range(5, 7): self.week_checkboxes[i].setChecked(False)

    def select_weekend(self):
        for i in range(5): self.week_checkboxes[i].setChecked(False)
        for i in range(5, 7): self.week_checkboxes[i].setChecked(True)

    def select_all_days(self):
        for checkbox in self.week_checkboxes: checkbox.setChecked(True)

    def clear_all_days(self):
        for checkbox in self.week_checkboxes: checkbox.setChecked(False)