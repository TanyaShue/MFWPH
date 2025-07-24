# scheduled_tasks_page.py
from PySide6.QtCore import Qt, QTime, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QGroupBox, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QLabel, QComboBox, QTimeEdit,
    QCheckBox, QSpinBox, QFrame, QDialog,
    QDialogButtonBox, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PySide6.QtGui import QIcon
from datetime import datetime
import json

from app.models.config.global_config import global_config
from app.models.config.app_config import ResourceSchedule


class ScheduleType:
    """定时任务类型枚举"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ScheduledTaskDialog(QDialog):
    """添加/编辑定时任务对话框"""

    def __init__(self, device_name, parent=None, task_data=None):
        super().__init__(parent)
        self.device_name = device_name
        self.task_data = task_data  # 编辑模式时的现有任务数据
        self.init_ui()

        # 如果是编辑模式，加载现有数据
        if task_data:
            self.load_task_data(task_data)

    def init_ui(self):
        self.setWindowTitle("添加定时任务" if not self.task_data else "编辑定时任务")
        self.setModal(True)
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        # 资源选择
        resource_group = QGroupBox("任务配置")
        resource_layout = QVBoxLayout(resource_group)

        # 资源下拉框
        resource_label = QLabel("选择资源:")
        self.resource_combo = QComboBox()
        self.load_available_resources()

        resource_layout.addWidget(resource_label)
        resource_layout.addWidget(self.resource_combo)

        # 配置选择
        config_label = QLabel("选择配置:")
        self.config_combo = QComboBox()
        self.resource_combo.currentTextChanged.connect(self.on_resource_changed)

        resource_layout.addWidget(config_label)
        resource_layout.addWidget(self.config_combo)

        layout.addWidget(resource_group)

        # 时间设置
        time_group = QGroupBox("执行时间")
        time_layout = QVBoxLayout(time_group)

        # 任务类型选择
        type_layout = QHBoxLayout()
        type_label = QLabel("任务类型:")
        self.type_combo = QComboBox()
        self.type_combo.addItems(["每日任务", "每周任务", "每月任务"])
        self.type_combo.currentIndexChanged.connect(self.on_type_changed)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()
        time_layout.addLayout(type_layout)

        # 执行时间
        time_select_layout = QHBoxLayout()
        time_select_label = QLabel("执行时间:")
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime(8, 0))
        self.time_edit.setDisplayFormat("HH:mm")
        time_select_layout.addWidget(time_select_label)
        time_select_layout.addWidget(self.time_edit)
        time_select_layout.addStretch()
        time_layout.addLayout(time_select_layout)

        # 周期设置容器
        self.schedule_widget = QWidget()
        self.schedule_layout = QVBoxLayout(self.schedule_widget)
        self.schedule_layout.setContentsMargins(0, 0, 0, 0)

        # 每周设置
        self.weekly_widget = QWidget()
        weekly_layout = QVBoxLayout(self.weekly_widget)
        weekly_layout.addWidget(QLabel("选择星期:"))

        weekday_layout = QHBoxLayout()
        self.weekday_checkboxes = []
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for i, day in enumerate(weekdays):
            cb = QCheckBox(day)
            cb.setProperty("weekday", i + 1)  # 1-7 对应周一到周日
            self.weekday_checkboxes.append(cb)
            weekday_layout.addWidget(cb)
        weekly_layout.addLayout(weekday_layout)

        # 每月设置
        self.monthly_widget = QWidget()
        monthly_layout = QHBoxLayout(self.monthly_widget)
        monthly_layout.addWidget(QLabel("每月第"))
        self.day_spinbox = QSpinBox()
        self.day_spinbox.setMinimum(1)
        self.day_spinbox.setMaximum(31)
        self.day_spinbox.setValue(1)
        monthly_layout.addWidget(self.day_spinbox)
        monthly_layout.addWidget(QLabel("天"))
        monthly_layout.addStretch()

        time_layout.addWidget(self.schedule_widget)
        layout.addWidget(time_group)

        # 任务选项
        options_group = QGroupBox("任务选项")
        options_layout = QVBoxLayout(options_group)

        self.enabled_checkbox = QCheckBox("启用任务")
        self.enabled_checkbox.setChecked(True)
        options_layout.addWidget(self.enabled_checkbox)

        layout.addWidget(options_group)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # 初始显示每日任务
        self.on_type_changed(0)

        # 触发资源变化以加载配置
        if self.resource_combo.count() > 0:
            self.on_resource_changed(self.resource_combo.currentText())

    def load_available_resources(self):
        """加载可用的资源列表"""
        device_config = global_config.get_device_config(self.device_name)
        if device_config:
            for resource in device_config.resources:
                if resource.enable:  # 只显示已启用的资源
                    self.resource_combo.addItem(resource.resource_name)

    def on_resource_changed(self, resource_name):
        """资源选择变化时更新配置列表"""
        self.config_combo.clear()

        if not resource_name:
            return

        # 获取该资源的所有配置
        resource_settings = [s for s in global_config.app_config.resource_settings
                             if s.resource_name == resource_name]

        for settings in resource_settings:
            self.config_combo.addItem(settings.name)

    def on_type_changed(self, index):
        """任务类型变化时更新UI"""
        # 清空现有布局
        while self.schedule_layout.count():
            item = self.schedule_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if index == 0:  # 每日任务
            # 不需要额外设置
            pass
        elif index == 1:  # 每周任务
            self.schedule_layout.addWidget(self.weekly_widget)
        elif index == 2:  # 每月任务
            self.schedule_layout.addWidget(self.monthly_widget)

    def load_task_data(self, task_data):
        """加载现有任务数据"""
        # 设置资源和配置
        resource_index = self.resource_combo.findText(task_data.get("resource_name", ""))
        if resource_index >= 0:
            self.resource_combo.setCurrentIndex(resource_index)

        config_index = self.config_combo.findText(task_data.get("settings_name", ""))
        if config_index >= 0:
            self.config_combo.setCurrentIndex(config_index)

        # 设置任务类型
        task_type = task_data.get("type", ScheduleType.DAILY)
        if task_type == ScheduleType.DAILY:
            self.type_combo.setCurrentIndex(0)
        elif task_type == ScheduleType.WEEKLY:
            self.type_combo.setCurrentIndex(1)
        elif task_type == ScheduleType.MONTHLY:
            self.type_combo.setCurrentIndex(2)

        # 设置时间
        time_str = task_data.get("time", "08:00")
        time = QTime.fromString(time_str, "HH:mm")
        self.time_edit.setTime(time)

        # 设置周期特定数据
        if task_type == ScheduleType.WEEKLY:
            weekdays = task_data.get("weekdays", [])
            for cb in self.weekday_checkboxes:
                cb.setChecked(cb.property("weekday") in weekdays)
        elif task_type == ScheduleType.MONTHLY:
            day = task_data.get("day", 1)
            self.day_spinbox.setValue(day)

        # 设置启用状态
        self.enabled_checkbox.setChecked(task_data.get("enabled", True))

    def get_task_data(self):
        """获取任务数据"""
        task_type_index = self.type_combo.currentIndex()
        task_types = [ScheduleType.DAILY, ScheduleType.WEEKLY, ScheduleType.MONTHLY]
        task_type = task_types[task_type_index]

        data = {
            "resource_name": self.resource_combo.currentText(),
            "settings_name": self.config_combo.currentText(),
            "type": task_type,
            "time": self.time_edit.time().toString("HH:mm"),
            "enabled": self.enabled_checkbox.isChecked()
        }

        # 添加周期特定数据
        if task_type == ScheduleType.WEEKLY:
            weekdays = []
            for cb in self.weekday_checkboxes:
                if cb.isChecked():
                    weekdays.append(cb.property("weekday"))
            data["weekdays"] = weekdays
        elif task_type == ScheduleType.MONTHLY:
            data["day"] = self.day_spinbox.value()

        return data


class ScheduledTasksPage(QWidget):
    """设备定时任务管理页面"""

    # 定义信号
    task_added = Signal(dict)
    task_updated = Signal(str, dict)
    task_removed = Signal(str)

    def __init__(self, device_name, parent=None):
        super().__init__(parent)
        self.device_name = device_name
        self.device_config = global_config.get_device_config(device_name)
        self.scheduled_tasks = {}  # 存储定时任务 {task_id: task_data}

        self.init_ui()
        self.load_scheduled_tasks()

        # 设置定时器以更新任务状态
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_task_status)
        self.update_timer.start(60000)  # 每分钟更新一次

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # 设置样式
        self.setObjectName("content_widget")

        # 标题
        title_label = QLabel(f"定时任务管理 - {self.device_name}")
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        self.add_button = QPushButton("添加任务")
        self.add_button.setObjectName("primaryButton")
        self.add_button.clicked.connect(self.add_task)

        self.edit_button = QPushButton("编辑任务")
        self.edit_button.setObjectName("secondaryButton")
        self.edit_button.clicked.connect(self.edit_task)
        self.edit_button.setEnabled(False)

        self.delete_button = QPushButton("删除任务")
        self.delete_button.setObjectName("dangerButton")
        self.delete_button.clicked.connect(self.delete_task)
        self.delete_button.setEnabled(False)

        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setObjectName("secondaryButton")
        self.refresh_button.clicked.connect(self.refresh_tasks)

        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.edit_button)
        toolbar_layout.addWidget(self.delete_button)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.refresh_button)

        main_layout.addLayout(toolbar_layout)

        # 任务表格
        self.task_table = QTableWidget()
        self.task_table.setObjectName("taskTable")
        self.setup_task_table()
        main_layout.addWidget(self.task_table)

        # 状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self.task_count_label = QLabel("共 0 个任务")
        status_layout.addWidget(self.task_count_label)

        main_layout.addLayout(status_layout)

    def setup_task_table(self):
        """设置任务表格"""
        # 设置列
        columns = ["状态", "资源", "配置", "类型", "执行时间", "下次执行", "操作"]
        self.task_table.setColumnCount(len(columns))
        self.task_table.setHorizontalHeaderLabels(columns)

        # 设置表格属性
        self.task_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.task_table.setAlternatingRowColors(True)
        self.task_table.horizontalHeader().setStretchLastSection(True)

        # 连接选择变化信号
        self.task_table.selectionModel().selectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self):
        """表格选择变化时更新按钮状态"""
        has_selection = len(self.task_table.selectedItems()) > 0
        self.edit_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def add_task(self):
        """添加新任务"""
        dialog = ScheduledTaskDialog(self.device_name, self)
        if dialog.exec_() == QDialog.Accepted:
            task_data = dialog.get_task_data()

            # 验证任务数据
            if not self.validate_task_data(task_data):
                return

            # 生成任务ID
            task_id = f"{self.device_name}_{task_data['resource_name']}_{task_data['settings_name']}_{datetime.now().timestamp()}"

            # 保存任务
            self.scheduled_tasks[task_id] = task_data

            # 添加到表格
            self.add_task_to_table(task_id, task_data)

            # 发送信号
            self.task_added.emit(task_data)

            # 更新状态
            self.update_task_count()
            self.status_label.setText("任务已添加")

    def edit_task(self):
        """编辑选中的任务"""
        current_row = self.task_table.currentRow()
        if current_row < 0:
            return

        # 获取任务ID
        task_id = self.task_table.item(current_row, 0).data(Qt.UserRole)
        task_data = self.scheduled_tasks.get(task_id)

        if not task_data:
            return

        dialog = ScheduledTaskDialog(self.device_name, self, task_data)
        if dialog.exec_() == QDialog.Accepted:
            new_task_data = dialog.get_task_data()

            # 验证任务数据
            if not self.validate_task_data(new_task_data, exclude_id=task_id):
                return

            # 更新任务
            self.scheduled_tasks[task_id] = new_task_data

            # 更新表格
            self.update_task_in_table(current_row, task_id, new_task_data)

            # 发送信号
            self.task_updated.emit(task_id, new_task_data)

            # 更新状态
            self.status_label.setText("任务已更新")

    def delete_task(self):
        """删除选中的任务"""
        current_row = self.task_table.currentRow()
        if current_row < 0:
            return

        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除选中的定时任务吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 获取任务ID
            task_id = self.task_table.item(current_row, 0).data(Qt.UserRole)

            # 删除任务
            if task_id in self.scheduled_tasks:
                del self.scheduled_tasks[task_id]

            # 从表格删除
            self.task_table.removeRow(current_row)

            # 发送信号
            self.task_removed.emit(task_id)

            # 更新状态
            self.update_task_count()
            self.status_label.setText("任务已删除")

    def refresh_tasks(self):
        """刷新任务列表"""
        self.load_scheduled_tasks()
        self.update_task_status()
        self.status_label.setText("已刷新")

    def validate_task_data(self, task_data, exclude_id=None):
        """验证任务数据"""
        # 检查必填字段
        if not task_data.get("resource_name") or not task_data.get("settings_name"):
            QMessageBox.warning(self, "验证失败", "请选择资源和配置")
            return False

        # 检查周任务的星期选择
        if task_data.get("type") == ScheduleType.WEEKLY:
            if not task_data.get("weekdays"):
                QMessageBox.warning(self, "验证失败", "请至少选择一个星期")
                return False

        # 检查重复任务
        for task_id, existing_task in self.scheduled_tasks.items():
            if exclude_id and task_id == exclude_id:
                continue

            if (existing_task["resource_name"] == task_data["resource_name"] and
                    existing_task["settings_name"] == task_data["settings_name"] and
                    existing_task["type"] == task_data["type"] and
                    existing_task["time"] == task_data["time"]):

                # 对于周任务，还需要检查星期是否相同
                if task_data["type"] == ScheduleType.WEEKLY:
                    if set(existing_task.get("weekdays", [])) == set(task_data.get("weekdays", [])):
                        QMessageBox.warning(self, "验证失败", "已存在相同的定时任务")
                        return False
                # 对于月任务，检查日期是否相同
                elif task_data["type"] == ScheduleType.MONTHLY:
                    if existing_task.get("day") == task_data.get("day"):
                        QMessageBox.warning(self, "验证失败", "已存在相同的定时任务")
                        return False
                else:
                    QMessageBox.warning(self, "验证失败", "已存在相同的定时任务")
                    return False

        return True

    def add_task_to_table(self, task_id, task_data):
        """添加任务到表格"""
        row = self.task_table.rowCount()
        self.task_table.insertRow(row)

        # 状态
        status_item = QTableWidgetItem("启用" if task_data["enabled"] else "禁用")
        status_item.setData(Qt.UserRole, task_id)
        self.task_table.setItem(row, 0, status_item)

        # 资源
        self.task_table.setItem(row, 1, QTableWidgetItem(task_data["resource_name"]))

        # 配置
        self.task_table.setItem(row, 2, QTableWidgetItem(task_data["settings_name"]))

        # 类型
        type_text = {
            ScheduleType.DAILY: "每日",
            ScheduleType.WEEKLY: "每周",
            ScheduleType.MONTHLY: "每月"
        }
        self.task_table.setItem(row, 3, QTableWidgetItem(type_text.get(task_data["type"], "未知")))

        # 执行时间
        time_desc = self.get_time_description(task_data)
        self.task_table.setItem(row, 4, QTableWidgetItem(time_desc))

        # 下次执行
        next_run = self.calculate_next_run(task_data)
        self.task_table.setItem(row, 5, QTableWidgetItem(next_run))

        # 操作按钮
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(5, 2, 5, 2)

        toggle_btn = QPushButton("禁用" if task_data["enabled"] else "启用")
        toggle_btn.setObjectName("smallButton")
        toggle_btn.clicked.connect(lambda: self.toggle_task(task_id))
        action_layout.addWidget(toggle_btn)

        self.task_table.setCellWidget(row, 6, action_widget)

    def update_task_in_table(self, row, task_id, task_data):
        """更新表格中的任务"""
        # 状态
        self.task_table.item(row, 0).setText("启用" if task_data["enabled"] else "禁用")

        # 资源
        self.task_table.item(row, 1).setText(task_data["resource_name"])

        # 配置
        self.task_table.item(row, 2).setText(task_data["settings_name"])

        # 类型
        type_text = {
            ScheduleType.DAILY: "每日",
            ScheduleType.WEEKLY: "每周",
            ScheduleType.MONTHLY: "每月"
        }
        self.task_table.item(row, 3).setText(type_text.get(task_data["type"], "未知"))

        # 执行时间
        time_desc = self.get_time_description(task_data)
        self.task_table.item(row, 4).setText(time_desc)

        # 下次执行
        next_run = self.calculate_next_run(task_data)
        self.task_table.item(row, 5).setText(next_run)

        # 更新操作按钮
        action_widget = self.task_table.cellWidget(row, 6)
        if action_widget:
            toggle_btn = action_widget.findChild(QPushButton)
            if toggle_btn:
                toggle_btn.setText("禁用" if task_data["enabled"] else "启用")

    def toggle_task(self, task_id):
        """切换任务启用/禁用状态"""
        if task_id in self.scheduled_tasks:
            task_data = self.scheduled_tasks[task_id]
            task_data["enabled"] = not task_data["enabled"]

            # 更新表格
            for row in range(self.task_table.rowCount()):
                if self.task_table.item(row, 0).data(Qt.UserRole) == task_id:
                    self.update_task_in_table(row, task_id, task_data)
                    break

            # 发送更新信号
            self.task_updated.emit(task_id, task_data)

            self.status_label.setText("任务状态已更新")

    def get_time_description(self, task_data):
        """获取任务执行时间的描述"""
        time_str = task_data["time"]
        task_type = task_data["type"]

        if task_type == ScheduleType.DAILY:
            return f"每天 {time_str}"
        elif task_type == ScheduleType.WEEKLY:
            weekdays = task_data.get("weekdays", [])
            weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            selected_days = [weekday_names[d - 1] for d in sorted(weekdays)]
            return f"{','.join(selected_days)} {time_str}"
        elif task_type == ScheduleType.MONTHLY:
            day = task_data.get("day", 1)
            return f"每月{day}日 {time_str}"

        return time_str

    def calculate_next_run(self, task_data):
        """计算下次执行时间"""
        if not task_data.get("enabled"):
            return "已禁用"

        # 这里可以根据任务类型计算实际的下次执行时间
        # 暂时返回简单的描述
        now = datetime.now()
        time_str = task_data["time"]

        try:
            hour, minute = map(int, time_str.split(":"))
            next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if next_time <= now:
                next_time = next_time.replace(day=now.day + 1)

            return next_time.strftime("%Y-%m-%d %H:%M")
        except:
            return "计算错误"

    def update_task_count(self):
        """更新任务计数"""
        count = self.task_table.rowCount()
        self.task_count_label.setText(f"共 {count} 个任务")

    def update_task_status(self):
        """更新所有任务的状态（下次执行时间等）"""
        for row in range(self.task_table.rowCount()):
            task_id = self.task_table.item(row, 0).data(Qt.UserRole)
            if task_id in self.scheduled_tasks:
                task_data = self.scheduled_tasks[task_id]
                next_run = self.calculate_next_run(task_data)
                self.task_table.item(row, 5).setText(next_run)

    def load_scheduled_tasks(self):
        """加载已保存的定时任务"""
        # 清空表格
        self.task_table.setRowCount(0)
        self.scheduled_tasks.clear()

        # 从设备配置加载任务
        device_config = global_config.get_device_config(self.device_name)
        if not device_config:
            return

        # 遍历所有资源的定时任务
        for resource in device_config.resources:
            if not resource.schedules_enable or not resource.schedules:
                continue

            for schedule in resource.schedules:
                if not schedule.enabled:
                    continue

                # 转换为新的任务数据格式
                task_data = self.convert_schedule_to_task_data(resource, schedule)
                if task_data:
                    task_id = f"{self.device_name}_{resource.resource_name}_{schedule.settings_name}_{schedule.schedule_time}"
                    self.scheduled_tasks[task_id] = task_data
                    self.add_task_to_table(task_id, task_data)

        self.update_task_count()

    def convert_schedule_to_task_data(self, resource, schedule):
        """将旧的ResourceSchedule转换为新的任务数据格式"""
        # 默认为每日任务
        task_data = {
            "resource_name": resource.resource_name,
            "settings_name": schedule.settings_name,
            "type": ScheduleType.DAILY,
            "time": schedule.schedule_time,
            "enabled": schedule.enabled
        }

        # 尝试从schedule_time解析更多信息（如果存储了扩展格式）
        # 这里可以根据实际需求扩展

        return task_data

    def refresh_ui(self):
        """刷新UI组件"""
        self.device_config = global_config.get_device_config(self.device_name)
        self.refresh_tasks()