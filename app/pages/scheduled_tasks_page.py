# scheduled_tasks_page.py
import asyncio
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from qasync import asyncSlot

from app.utils.notification_manager import notification_manager
from app.widgets.scheduled.create_task_dialog import CreateTaskDialog


class TaskPlanTableWidget(QWidget):
    """任务计划表组件（纯展示版）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_manager = None
        self.all_tasks = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        stats_widget = QWidget()
        stats_widget.setStyleSheet("background: #2196F3; padding: 8px;")
        stats_layout = QHBoxLayout(stats_widget)
        self.stats_label = QLabel("任务总数: 0 | 活动: 0 | 暂停: 0")
        self.stats_label.setStyleSheet("color: white; font-size: 12px; font-weight: bold;")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        self.device_filter = QComboBox()
        self.device_filter.addItem("全部设备")
        self.device_filter.setStyleSheet(self.get_filter_style())
        self.device_filter.currentTextChanged.connect(self.apply_filter)
        stats_layout.addWidget(self.device_filter)
        self.type_filter = QComboBox()
        self.type_filter.addItems(["全部类型", "单次执行", "每日执行", "每周执行"])
        self.type_filter.setStyleSheet(self.get_filter_style())
        self.type_filter.currentTextChanged.connect(self.apply_filter)
        stats_layout.addWidget(self.type_filter)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部状态", "活动", "暂停"])
        self.status_filter.setStyleSheet(self.get_filter_style())
        self.status_filter.currentTextChanged.connect(self.apply_filter)
        stats_layout.addWidget(self.status_filter)
        clear_filter_btn = QPushButton("清除")
        clear_filter_btn.setStyleSheet("""
            QPushButton { background: white; color: #2196F3; border: none; padding: 4px 12px;
                          border-radius: 3px; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background: #f0f0f0; } """)
        clear_filter_btn.clicked.connect(self.clear_filter)
        stats_layout.addWidget(clear_filter_btn)
        layout.addWidget(stats_widget)

        toolbar = QWidget()
        toolbar.setStyleSheet("background: white; border-bottom: 1px solid #e0e0e0;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 8, 10, 8)
        pause_btn = QPushButton("全部暂停")
        pause_btn.setStyleSheet(self.get_toolbar_btn_style("#ff9800"))
        pause_btn.clicked.connect(self.pause_all_tasks)
        start_btn = QPushButton("全部启动")
        start_btn.setStyleSheet(self.get_toolbar_btn_style("#4caf50"))
        start_btn.clicked.connect(self.start_all_tasks)
        clear_btn = QPushButton("清空全部")
        clear_btn.setStyleSheet(self.get_toolbar_btn_style("#f44336"))
        clear_btn.clicked.connect(self.clear_all_tasks)
        toolbar_layout.addWidget(pause_btn)
        toolbar_layout.addWidget(start_btn)
        toolbar_layout.addWidget(clear_btn)
        toolbar_layout.addStretch()
        add_btn = QPushButton("+ 创建新任务")
        add_btn.setStyleSheet("""
            QPushButton { background: #2196F3; color: white; font-size: 12px; font-weight: bold;
                          padding: 6px 16px; border: none; border-radius: 3px; }
            QPushButton:hover { background: #1976D2; } """)
        add_btn.clicked.connect(self.parent().show_create_dialog if self.parent() else None)
        toolbar_layout.addWidget(add_btn)
        layout.addWidget(toolbar)

        self.table = QTableWidget()
        self.setup_table()
        layout.addWidget(self.table)

    def get_filter_style(self):
        return """
            QComboBox { background: white; border: none; padding: 3px 8px; border-radius: 3px;
                        font-size: 11px; min-width: 80px; }
            QComboBox:hover { background: #f0f0f0; }
            QComboBox::drop-down { border: none; width: 15px; } """

    def get_toolbar_btn_style(self, color):
        return f"""
            QPushButton {{ background: {color}; color: white; font-size: 11px; font-weight: bold;
                           border: none; padding: 5px 12px; border-radius: 3px; }}
            QPushButton:hover {{ background: {color}dd; }} """

    def setup_table(self):
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            ["ID", "设备", "资源", "类型", "执行时间", "配置方案", "通知", "运行前强制停止所有任务", "状态", "操作"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(35)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget { gridline-color: #e0e0e0; background: white; border: none; font-size: 11px; }
            QTableWidget::item { padding: 5px; }
            QTableWidget::item:selected { background: #e3f2fd; color: black; }
            QHeaderView::section { background: #f5f5f5; font-weight: bold; padding: 6px; border: none;
                                   border-bottom: 1px solid #e0e0e0; border-right: 1px solid #e0e0e0;
                                   font-size: 11px; }
        """)

        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        header = self.table.horizontalHeader()

        # 固定宽度列
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # ID
        self.table.setColumnWidth(0, 40)

        header.setSectionResizeMode(6, QHeaderView.Fixed)  # 通知
        self.table.setColumnWidth(6, 50)

        header.setSectionResizeMode(7, QHeaderView.Fixed)  # 运行前强制停止所有任务
        self.table.setColumnWidth(7, 160)

        header.setSectionResizeMode(8, QHeaderView.Fixed)  # 状态
        self.table.setColumnWidth(8, 60)

        header.setSectionResizeMode(9, QHeaderView.Fixed)  # 操作按钮
        self.table.setColumnWidth(9, 120)  # 三个按钮大概这个宽度

        # 自适应列（占剩余空间）
        for col in [1, 2, 3, 4, 5]:
            header.setSectionResizeMode(col, QHeaderView.Stretch)

        header.setStretchLastSection(True)

    def set_task_manager(self, task_manager):
        self.task_manager = task_manager
        self.task_manager.task_added.connect(self.on_task_added_by_manager)
        self.task_manager.task_removed.connect(self.on_task_removed_by_manager)
        self.task_manager.task_status_changed.connect(self.on_task_status_changed_by_manager)
        self.task_manager.task_modified.connect(self.on_task_modified_by_manager)
        self.load_existing_tasks()

    def load_existing_tasks(self):
        if not self.task_manager: return
        self.table.setRowCount(0)
        self.all_tasks.clear()
        existing_tasks = self.task_manager.initialize_from_config()
        for task_info in existing_tasks:
            self.all_tasks.append(task_info)
        self.apply_filter()
        self.update_filter_options()
        self.update_stats()

    def add_task_to_table(self, task_data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        id_item = QTableWidgetItem(str(task_data.get('id', '')))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setData(Qt.UserRole, task_data)
        self.table.setItem(row, 0, id_item)

        device_name = task_data.get('device_name', '')
        device_item = QTableWidgetItem(device_name)
        device_item.setToolTip(device_name)
        self.table.setItem(row, 1, device_item)

        resource_name = task_data.get('resource_name', '')
        resource_item = QTableWidgetItem(resource_name)
        resource_item.setToolTip(resource_name)
        self.table.setItem(row, 2, resource_item)

        schedule_type = task_data.get('schedule_type', '每日执行')
        type_item = QTableWidgetItem(schedule_type)
        type_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, type_item)

        time_text = task_data.get('time', '00:00:00')
        if 'week_days' in task_data and task_data['week_days']:
            days_text = ",".join(task_data['week_days'])
            time_text = f"{time_text} ({days_text})"
        time_item = QTableWidgetItem(time_text)
        time_item.setToolTip(time_text)
        self.table.setItem(row, 4, time_item)

        config_scheme = task_data.get('config_scheme', '默认配置')
        config_item = QTableWidgetItem(config_scheme)
        config_item.setToolTip(config_scheme)
        self.table.setItem(row, 5, config_item)

        notify_text = "是" if task_data.get('notify', False) else "否"
        notify_item = QTableWidgetItem(notify_text)
        notify_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 6, notify_item)

        force_stop = task_data.get('force_stop', False)
        force_item = QTableWidgetItem("是" if force_stop else "否")
        force_item.setTextAlignment(Qt.AlignCenter)
        if force_stop:
            force_item.setForeground(QColor("#f44336")) # 如果是则用红色标注提醒
        self.table.setItem(row, 7, force_item)

        status = task_data.get('status', '活动')
        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor("#4caf50") if status == "活动" else QColor("#ff9800"))
        status_item.setFont(QFont("", 10, QFont.Bold))
        self.table.setItem(row, 8, status_item)

        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(5, 2, 5, 2)
        op_layout.setSpacing(5)
        toggle_btn = QPushButton("暂停" if status == "活动" else "启动")
        toggle_btn.setFixedSize(35, 22)
        toggle_btn.setStyleSheet(""" QPushButton { background: #ff9800; color: white; ...} """)
        edit_btn = QPushButton("编辑")
        edit_btn.setFixedSize(35, 22)
        edit_btn.setStyleSheet(""" QPushButton { background: #03a9f4; color: white; ...} """)
        delete_btn = QPushButton("删除")
        delete_btn.setFixedSize(35, 22)
        delete_btn.setStyleSheet(""" QPushButton { background: #f44336; color: white; ...} """)
        toggle_btn.clicked.connect(lambda _, r=row: self.toggle_task(r))
        edit_btn.clicked.connect(lambda _, r=row: self.edit_task(r))
        delete_btn.clicked.connect(lambda _, r=row: self.delete_task(r))
        op_layout.addWidget(toggle_btn)
        op_layout.addWidget(edit_btn)
        op_layout.addWidget(delete_btn)
        self.table.setCellWidget(row, 9, op_widget)

    @asyncSlot()
    async def toggle_task(self, row):
        id_item = self.table.item(row, 0)
        if id_item and self.task_manager:
            task_data = id_item.data(Qt.UserRole)
            await self.task_manager.toggle_task_status(task_data['id'], task_data['status'] != "活动")

    def edit_task(self, row):
        id_item = self.table.item(row, 0)
        if id_item:
            task_data = id_item.data(Qt.UserRole)
            dialog = CreateTaskDialog(self, task_info=task_data)
            dialog.task_saved.connect(self.on_task_edited)
            dialog.exec()

    @asyncSlot(dict)
    async def on_task_edited(self, updated_task_info):
        if self.task_manager:
            await self.task_manager.update_task(updated_task_info)
            notification_manager.show_success("更新定时任务成功", f"ID: {updated_task_info['id']} 已更新", 1000)

    @asyncSlot()
    async def delete_task(self, row):
        id_item = self.table.item(row, 0)
        if not id_item: return
        task_data = id_item.data(Qt.UserRole)
        task_id = task_data.get('id')

        if task_id and self.task_manager:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除任务 ID:{task_id} 吗？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                await self.task_manager.remove_task(task_id)

    def on_task_added_by_manager(self, task_info):
        self.all_tasks.append(task_info)
        self.apply_filter()
        self.update_filter_options()
        self.update_stats()

    def on_task_removed_by_manager(self, task_id):
        self.all_tasks = [t for t in self.all_tasks if str(t.get('id')) != str(task_id)]
        self.apply_filter()
        self.update_filter_options()
        self.update_stats()
        notification_manager.show_success(f"删除定时任务{task_id}成功", "删除成功", 1000)

    def on_task_status_changed_by_manager(self, task_id, enabled):
        for task in self.all_tasks:
            if str(task.get('id')) == str(task_id):
                task['status'] = '活动' if enabled else '暂停'
                break
        self.apply_filter()
        self.update_stats()

    def on_task_modified_by_manager(self, task_id, task_info):
        for i, task in enumerate(self.all_tasks):
            if str(task.get('id')) == str(task_id):
                self.all_tasks[i] = task_info
                break
        self.apply_filter()
        self.update_filter_options()

    def _task_matches_filter(self, task):
        device_filter = self.device_filter.currentText()
        type_filter = self.type_filter.currentText()
        status_filter = self.status_filter.currentText()
        if device_filter != "全部设备" and task.get('device_name') != device_filter: return False
        if type_filter != "全部类型" and task.get('schedule_type') != type_filter: return False
        if status_filter != "全部状态" and task.get('status') != status_filter: return False
        return True

    def apply_filter(self):
        self.table.setRowCount(0)
        for task in self.all_tasks:
            if self._task_matches_filter(task):
                self.add_task_to_table(task)

    def update_filter_options(self):
        current_device = self.device_filter.currentText()
        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("全部设备")
        devices = sorted(set(task.get('device_name', '') for task in self.all_tasks))
        self.device_filter.addItems(devices)
        if self.device_filter.findText(current_device) != -1:
            self.device_filter.setCurrentText(current_device)
        self.device_filter.blockSignals(False)

    def clear_filter(self):
        self.device_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)

    @asyncSlot()
    async def pause_all_tasks(self):
        if not self.task_manager: return
        tasks_to_pause = [
            self.task_manager.toggle_task_status(str(task.get('id')), False)
            for task in self.all_tasks if task.get('status') == '活动'
        ]
        if tasks_to_pause:
            results = await asyncio.gather(*tasks_to_pause)
            count = sum(1 for r in results if r)
            if count > 0: QMessageBox.information(self, "批量操作", f"已暂停 {count} 个任务")

    @asyncSlot()
    async def start_all_tasks(self):
        if not self.task_manager: return
        tasks_to_start = [
            self.task_manager.toggle_task_status(str(task.get('id')), True)
            for task in self.all_tasks if task.get('status') == '暂停'
        ]
        if tasks_to_start:
            results = await asyncio.gather(*tasks_to_start)
            count = sum(1 for r in results if r)
            if count > 0: QMessageBox.information(self, "批量操作", f"已启动 {count} 个任务")

    @asyncSlot()
    async def clear_all_tasks(self):
        if not self.all_tasks or not self.task_manager: return
        reply = QMessageBox.question(self, "确认清空", f"确定要清空所有 {len(self.all_tasks)} 个任务吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            tasks_to_remove = [
                self.task_manager.remove_task(str(task.get('id')))
                for task in self.all_tasks
            ]
            await asyncio.gather(*tasks_to_remove)

    def update_stats(self):
        total = len(self.all_tasks)
        active = sum(1 for task in self.all_tasks if task.get('status') == "活动")
        self.stats_label.setText(f"任务总数: {total} | 活动: {active} | 暂停: {total - active}")


class ScheduledTaskPage(QWidget):
    """定时任务设置页面 - 集成版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scheduled_task_manager = None
        self.init_ui()
        self.setup_task_manager()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.task_plan_widget = TaskPlanTableWidget(self)
        layout.addWidget(self.task_plan_widget)

    def setup_task_manager(self):
        from core.scheduled_task_manager import scheduled_task_manager
        self.scheduled_task_manager = scheduled_task_manager
        self.task_plan_widget.set_task_manager(self.scheduled_task_manager)

    def show_create_dialog(self):
        dialog = CreateTaskDialog(self)
        dialog.task_saved.connect(self.on_task_created)
        dialog.exec()

    @asyncSlot(dict)
    async def on_task_created(self, task_info):
        if self.scheduled_task_manager:
            await self.scheduled_task_manager.add_task(task_info)
            notification_manager.show_success("创建定时任务成功", "添加成功", 1000)