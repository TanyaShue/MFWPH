# scheduled_task_page.py
from PySide6.QtCore import QTime, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QLabel, QPushButton, QTimeEdit, QCheckBox,
    QRadioButton, QButtonGroup, QMessageBox, QDialog, QGridLayout
)

from app.models.config.global_config import global_config


class CreateTaskDialog(QDialog):
    """创建任务对话框 - 简化版"""

    task_created = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_device = None
        self.selected_resource = None
        self.setWindowTitle("创建定时任务")
        self.setModal(True)
        self.setFixedSize(450, 500)
        self.init_ui()

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

        # 设备选择
        device_group = QGroupBox("设备选择")
        device_layout = QVBoxLayout()
        device_layout.setSpacing(5)

        self.device_combo = QComboBox()
        self.device_combo.addItem("-- 请选择设备 --")
        try:
            devices = global_config.get_all_device_names()
            for device in devices:
                self.device_combo.addItem(device)
        except:
            self.device_combo.addItems(["Device_1", "Device_2", "Device_3"])
        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        device_layout.addWidget(self.device_combo)
        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # 资源选择
        self.resource_group = QGroupBox("资源选择")
        self.resource_group.setEnabled(False)
        resource_layout = QVBoxLayout()
        resource_layout.setSpacing(5)

        self.resource_combo = QComboBox()
        self.resource_combo.addItem("-- 请选择资源 --")
        self.resource_combo.currentTextChanged.connect(self.on_resource_changed)
        resource_layout.addWidget(self.resource_combo)

        self.selected_resource_label = QLabel("未选择")
        self.selected_resource_label.setStyleSheet("color: gray; font-size: 10px; padding: 3px;")
        resource_layout.addWidget(self.selected_resource_label)

        self.resource_group.setLayout(resource_layout)
        layout.addWidget(self.resource_group)

        # 定时设置
        self.schedule_group = QGroupBox("定时设置")
        self.schedule_group.setEnabled(False)
        schedule_layout = QVBoxLayout()
        schedule_layout.setSpacing(8)

        # 执行类型
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

        # 时间选择
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("时间:"))
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")
        self.time_edit.setTime(QTime.currentTime())
        time_layout.addWidget(self.time_edit)
        time_layout.addStretch()
        schedule_layout.addLayout(time_layout)

        # 周选择
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

        # 快捷按钮
        quick_layout = QHBoxLayout()
        quick_layout.setSpacing(5)

        for text, func in [("工作日", self.select_workdays),
                           ("周末", self.select_weekend),
                           ("全选", self.select_all_days),
                           ("清空", self.clear_all_days)]:
            btn = QPushButton(text)
            btn.setStyleSheet("padding: 3px 8px; font-size: 10px;")
            btn.clicked.connect(func)
            quick_layout.addWidget(btn)
        quick_layout.addStretch()

        week_layout.addLayout(quick_layout)
        self.week_widget.setVisible(False)
        schedule_layout.addWidget(self.week_widget)

        self.schedule_type_group.buttonClicked.connect(self.on_schedule_type_changed)
        self.schedule_group.setLayout(schedule_layout)
        layout.addWidget(self.schedule_group)

        layout.addStretch()

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background: #f0f0f0; color: #333;")
        cancel_btn.clicked.connect(self.reject)

        self.create_btn = QPushButton("创建")
        self.create_btn.setEnabled(False)
        self.create_btn.setStyleSheet("""
            QPushButton { background: #2196F3; color: white; }
            QPushButton:hover { background: #1976D2; }
            QPushButton:disabled { background: #ccc; color: #999; }
        """)
        self.create_btn.clicked.connect(self.on_create_task)

        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(self.create_btn)

        layout.addLayout(button_layout)

    def on_device_changed(self, device_name):
        if device_name == "-- 请选择设备 --":
            self.selected_device = None
            self.resource_group.setEnabled(False)
            self.schedule_group.setEnabled(False)
        else:
            self.selected_device = device_name
            self.resource_group.setEnabled(True)
            self.load_device_resources(device_name)
        self.update_create_button()

    def load_device_resources(self, device_name):
        self.resource_combo.clear()
        self.resource_combo.addItem("-- 请选择资源 --")
        try:
            device_config = global_config.get_device_config(device_name)
            if device_config and hasattr(device_config, 'resources'):
                for resource_name in device_config.resources:
                    self.resource_combo.addItem(resource_name)
            else:
                for i in range(1, 6):
                    self.resource_combo.addItem(f"Resource_{i}")
        except:
            for i in range(1, 6):
                self.resource_combo.addItem(f"Resource_{i}")

    def on_resource_changed(self, resource_name):
        if resource_name == "-- 请选择资源 --":
            self.selected_resource = None
            self.selected_resource_label.setText("未选择")
            self.selected_resource_label.setStyleSheet("color: gray; font-size: 10px; padding: 3px;")
            self.schedule_group.setEnabled(False)
        else:
            self.selected_resource = resource_name
            self.selected_resource_label.setText(f"已选择: {resource_name}")
            self.selected_resource_label.setStyleSheet("color: #2196F3; font-size: 10px; padding: 3px;")
            self.schedule_group.setEnabled(True)
        self.update_create_button()

    def on_schedule_type_changed(self, button):
        self.week_widget.setVisible(button == self.weekly_radio)

    def select_workdays(self):
        for i in range(5):
            self.week_checkboxes[i].setChecked(True)
        for i in range(5, 7):
            self.week_checkboxes[i].setChecked(False)

    def select_weekend(self):
        for i in range(5):
            self.week_checkboxes[i].setChecked(False)
        for i in range(5, 7):
            self.week_checkboxes[i].setChecked(True)

    def select_all_days(self):
        for checkbox in self.week_checkboxes:
            checkbox.setChecked(True)

    def clear_all_days(self):
        for checkbox in self.week_checkboxes:
            checkbox.setChecked(False)

    def update_create_button(self):
        self.create_btn.setEnabled(bool(self.selected_device and self.selected_resource))

    def get_schedule_info(self):
        info = {'time': self.time_edit.time().toString("HH:mm:ss")}

        if self.once_radio.isChecked():
            info['schedule_type'] = '单次执行'
        elif self.daily_radio.isChecked():
            info['schedule_type'] = '每日执行'
        else:
            info['schedule_type'] = '每周执行'
            info['week_days'] = [
                self.week_checkboxes[i].text()
                for i in range(len(self.week_checkboxes))
                if self.week_checkboxes[i].isChecked()
            ]
        return info

    def on_create_task(self):
        if not self.selected_device or not self.selected_resource:
            QMessageBox.warning(self, "警告", "请选择设备和资源！")
            return

        schedule_info = self.get_schedule_info()

        if schedule_info['schedule_type'] == '每周执行':
            if 'week_days' not in schedule_info or not schedule_info['week_days']:
                QMessageBox.warning(self, "警告", "请选择至少一个执行日！")
                return

        task_info = {
            'device': self.selected_device,
            'resource': self.selected_resource,
            'config_scheme': '默认配置',
            'notify': False,
            **schedule_info
        }

        self.task_created.emit(task_info)
        self.accept()