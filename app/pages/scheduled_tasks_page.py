# scheduled_task_page.py
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QCheckBox,
    QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)

from app.utils.notification_manager import notification_manager
from app.widgets.create_task_dialog import CreateTaskDialog


class TaskPlanTableWidget(QWidget):
    """任务计划表组件 - 简化版"""

    task_deleted = Signal(int)
    task_toggled = Signal(int, bool)
    task_config_changed = Signal(int, str, str)
    task_notify_changed = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_counter = 0
        self.all_tasks = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部统计栏
        stats_widget = QWidget()
        stats_widget.setStyleSheet("background: #2196F3; padding: 8px;")
        stats_layout = QHBoxLayout(stats_widget)

        self.stats_label = QLabel("任务总数: 0 | 活动: 0 | 暂停: 0")
        self.stats_label.setStyleSheet("color: white; font-size: 12px; font-weight: bold;")
        stats_layout.addWidget(self.stats_label)

        stats_layout.addStretch()

        # 筛选控件
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
            QPushButton {
                background: white;
                color: #2196F3;
                border: none;
                padding: 4px 12px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #f0f0f0; }
        """)
        clear_filter_btn.clicked.connect(self.clear_filter)
        stats_layout.addWidget(clear_filter_btn)

        layout.addWidget(stats_widget)

        # 工具栏
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

        # 添加任务按钮 - 放在工具栏右侧
        add_btn = QPushButton("+ 创建新任务")
        add_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 16px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover { background: #1976D2; }
        """)
        add_btn.clicked.connect(self.parent().show_create_dialog if self.parent() else None)
        toolbar_layout.addWidget(add_btn)

        layout.addWidget(toolbar)

        # 表格
        self.table = QTableWidget()
        self.setup_table()
        layout.addWidget(self.table)

    def get_filter_style(self):
        return """
            QComboBox {
                background: white;
                border: none;
                padding: 3px 8px;
                border-radius: 3px;
                font-size: 11px;
                min-width: 80px;
            }
            QComboBox:hover { background: #f0f0f0; }
            QComboBox::drop-down { border: none; width: 15px; }
        """

    def get_toolbar_btn_style(self, color):
        return f"""
            QPushButton {{
                background: {color};
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                padding: 5px 12px;
                border-radius: 3px;
            }}
            QPushButton:hover {{ background: {color}dd; }}
        """

    def setup_table(self):
        self.table.clear()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "设备", "资源", "类型", "执行时间", "配置方案", "通知", "状态", "操作"
        ])

        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(35)
        self.table.verticalHeader().setVisible(False)

        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e0e0e0;
                background: white;
                border: none;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background: #e3f2fd;
                color: black;
            }
            QHeaderView::section {
                background: #f5f5f5;
                font-weight: bold;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #e0e0e0;
                border-right: 1px solid #e0e0e0;
                font-size: 11px;
            }
        """)

        # 设置表格列宽模式
        header = self.table.horizontalHeader()

        # 先设置所有列为可交互（允许手动调整）
        for i in range(9):
            header.setSectionResizeMode(i, QHeaderView.Interactive)

        # 让最后一列不拉伸（避免出现空白）
        header.setStretchLastSection(False)

        # 设置资源列为拉伸模式，填充剩余空间
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        # 设置初始列宽（用户仍可手动调整）
        self.table.setColumnWidth(0, 40)  # ID
        self.table.setColumnWidth(1, 100)  # 设备
        # 资源列会自动拉伸
        self.table.setColumnWidth(3, 60)  # 类型
        self.table.setColumnWidth(4, 150)  # 执行时间
        self.table.setColumnWidth(5, 100)  # 配置方案
        self.table.setColumnWidth(6, 50)  # 通知
        self.table.setColumnWidth(7, 60)  # 状态
        self.table.setColumnWidth(8, 90)  # 操作

        # 设置最小列宽，防止列太窄
        header.setMinimumSectionSize(30)

        # 允许用户通过双击列边界自动调整列宽
        header.setSectionsClickable(True)

    def adjust_column_widths(self):
        """根据内容自动调整某些列的宽度"""
        if self.table.rowCount() == 0:
            return

        # 仅调整需要根据内容变化的列
        for col in [1, 3, 4, 7]:  # 设备、类型、执行时间、状态
            self.table.resizeColumnToContents(col)
            # 确保不会太窄或太宽
            current_width = self.table.columnWidth(col)
            if col == 1:  # 设备
                self.table.setColumnWidth(col, min(max(current_width, 80), 150))
            elif col == 3:  # 类型
                self.table.setColumnWidth(col, min(max(current_width, 50), 80))
            elif col == 4:  # 执行时间
                self.table.setColumnWidth(col, min(max(current_width, 100), 200))
            elif col == 7:  # 状态
                self.table.setColumnWidth(col, min(max(current_width, 50), 80))

    def add_task(self, task_info):
        self.task_counter += 1
        task_id = self.task_counter

        task_data = {
            'id': task_id,
            'device': task_info['device'],
            'resource': task_info['resource'],
            'schedule_type': task_info['schedule_type'],
            'time': task_info['time'],
            'config_scheme': task_info.get('config_scheme', '默认配置'),
            'notify': task_info.get('notify', False),
            'status': "活动",
            'create_time': QDateTime.currentDateTime()
        }

        if task_info['schedule_type'] == '每周执行' and 'week_days' in task_info:
            task_data['week_days'] = task_info['week_days']

        self.all_tasks.append(task_data)
        self.update_filter_options()
        self.add_task_to_table(task_data)
        self.update_stats()

        # 添加任务后调整列宽
        self.adjust_column_widths()

    def add_task_to_table(self, task_data):
        row = self.table.rowCount()
        self.table.insertRow(row)

        # ID
        id_item = QTableWidgetItem(str(task_data['id']))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setData(Qt.UserRole, task_data)
        self.table.setItem(row, 0, id_item)

        # 设备
        self.table.setItem(row, 1, QTableWidgetItem(task_data['device']))

        # 资源
        self.table.setItem(row, 2, QTableWidgetItem(task_data['resource']))

        # 类型
        type_text = {'单次执行': '单次', '每日执行': '每日', '每周执行': '每周'}.get(
            task_data['schedule_type'], task_data['schedule_type']
        )
        type_item = QTableWidgetItem(type_text)
        type_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, type_item)

        # 执行时间
        time_text = task_data['time']
        if 'week_days' in task_data:
            days = [d[1:] for d in task_data['week_days']]
            time_text = f"{task_data['time']} ({','.join(days)})"
        self.table.setItem(row, 4, QTableWidgetItem(time_text))

        # 配置方案
        config_combo = QComboBox()
        config_combo.addItems(["默认配置", "配置方案一", "配置方案二", "自定义"])
        config_combo.setCurrentText(task_data.get('config_scheme', '默认配置'))
        config_combo.setStyleSheet("font-size: 10px; padding: 2px;")
        config_combo.currentTextChanged.connect(
            lambda text, tid=task_data['id']: self.on_config_changed(tid, text)
        )
        self.table.setCellWidget(row, 5, config_combo)

        # 通知
        notify_widget = QWidget()
        notify_layout = QHBoxLayout(notify_widget)
        notify_layout.setContentsMargins(0, 0, 0, 0)
        notify_layout.setAlignment(Qt.AlignCenter)

        notify_checkbox = QCheckBox()
        notify_checkbox.setChecked(task_data.get('notify', False))
        notify_checkbox.stateChanged.connect(
            lambda state, tid=task_data['id']: self.on_notify_changed(tid, state == Qt.Checked)
        )
        notify_layout.addWidget(notify_checkbox)

        self.table.setCellWidget(row, 6, notify_widget)

        # 状态
        status_item = QTableWidgetItem(task_data['status'])
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor("#4caf50") if task_data['status'] == "活动" else QColor("#ff9800"))
        status_item.setFont(QFont("", 10, QFont.Bold))
        self.table.setItem(row, 7, status_item)

        # 操作
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(5, 2, 5, 2)
        op_layout.setSpacing(5)

        toggle_btn = QPushButton("暂停" if task_data['status'] == "活动" else "启动")
        toggle_btn.setFixedSize(35, 22)
        toggle_btn.setStyleSheet("""
            QPushButton {
                background: #ff9800;
                color: white;
                border: none;
                border-radius: 2px;
                font-size: 10px;
            }
            QPushButton:hover { background: #f57c00; }
        """)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedSize(35, 22)
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #f44336;
                color: white;
                border: none;
                border-radius: 2px;
                font-size: 10px;
            }
            QPushButton:hover { background: #d32f2f; }
        """)

        toggle_btn.clicked.connect(lambda: self.toggle_task(row))
        delete_btn.clicked.connect(lambda: self.delete_task(row))

        op_layout.addWidget(toggle_btn)
        op_layout.addWidget(delete_btn)

        self.table.setCellWidget(row, 8, op_widget)

    def toggle_task(self, row):
        id_item = self.table.item(row, 0)
        status_item = self.table.item(row, 7)

        if id_item and status_item:
            task_data = id_item.data(Qt.UserRole)
            new_status = "暂停" if status_item.text() == "活动" else "活动"

            status_item.setText(new_status)
            status_item.setForeground(QColor("#4caf50") if new_status == "活动" else QColor("#ff9800"))
            task_data['status'] = new_status

            widget = self.table.cellWidget(row, 8)
            if widget:
                toggle_btn = widget.findChildren(QPushButton)[0]
                toggle_btn.setText("暂停" if new_status == "活动" else "启动")

            self.task_toggled.emit(task_data['id'], new_status == "活动")
            self.update_stats()

    def delete_task(self, row):
        id_item = self.table.item(row, 0)
        if id_item:
            task_data = id_item.data(Qt.UserRole)

            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除任务 ID:{task_data['id']} 吗？",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.all_tasks = [t for t in self.all_tasks if t['id'] != task_data['id']]
                self.table.removeRow(row)
                self.update_filter_options()
                self.task_deleted.emit(task_data['id'])
                self.update_stats()

    def apply_filter(self):
        self.table.setRowCount(0)

        device_filter = self.device_filter.currentText()
        type_filter = self.type_filter.currentText()
        status_filter = self.status_filter.currentText()

        for task in self.all_tasks:
            if device_filter != "全部设备" and task['device'] != device_filter:
                continue
            if type_filter != "全部类型" and task['schedule_type'] != type_filter:
                continue
            if status_filter != "全部状态" and task['status'] != status_filter:
                continue

            self.add_task_to_table(task)

        self.update_stats()

        # 应用筛选后调整列宽
        self.adjust_column_widths()

    def update_filter_options(self):
        current = self.device_filter.currentText()
        devices = sorted(set(task['device'] for task in self.all_tasks))

        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("全部设备")
        self.device_filter.addItems(devices)

        index = self.device_filter.findText(current)
        if index >= 0:
            self.device_filter.setCurrentIndex(index)

        self.device_filter.blockSignals(False)

    def clear_filter(self):
        self.device_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.apply_filter()

    def on_config_changed(self, task_id, config_text):
        for task in self.all_tasks:
            if task['id'] == task_id:
                task['config_scheme'] = config_text
                break
        self.task_config_changed.emit(task_id, config_text, 'config_scheme')

    def on_notify_changed(self, task_id, notify):
        for task in self.all_tasks:
            if task['id'] == task_id:
                task['notify'] = notify
                break
        self.task_notify_changed.emit(task_id, notify)

    def pause_all_tasks(self):
        count = sum(1 for task in self.all_tasks if task['status'] == "活动")
        if count > 0:
            for task in self.all_tasks:
                if task['status'] == "活动":
                    task['status'] = "暂停"
            self.apply_filter()
            QMessageBox.information(self, "批量操作", f"已暂停 {count} 个任务")

    def start_all_tasks(self):
        count = sum(1 for task in self.all_tasks if task['status'] == "暂停")
        if count > 0:
            for task in self.all_tasks:
                if task['status'] == "暂停":
                    task['status'] = "活动"
            self.apply_filter()
            QMessageBox.information(self, "批量操作", f"已启动 {count} 个任务")

    def clear_all_tasks(self):
        if not self.all_tasks:
            return

        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空所有 {len(self.all_tasks)} 个任务吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.all_tasks.clear()
            self.table.setRowCount(0)
            self.update_stats()
            self.device_filter.clear()
            self.device_filter.addItem("全部设备")

    def update_stats(self):
        total = len(self.all_tasks)
        active = sum(1 for task in self.all_tasks if task['status'] == "活动")
        paused = sum(1 for task in self.all_tasks if task['status'] == "暂停")
        self.stats_label.setText(f"任务总数: {total} | 活动: {active} | 暂停: {paused}")


class ScheduledTaskPage(QWidget):
    """定时任务设置页面 - 简化版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.task_plan_widget = TaskPlanTableWidget(self)
        layout.addWidget(self.task_plan_widget)

        self.connect_signals()

    def show_create_dialog(self):
        dialog = CreateTaskDialog(self)
        dialog.task_created.connect(self.on_task_created)
        dialog.exec()

    def connect_signals(self):
        self.task_plan_widget.task_deleted.connect(self.on_task_deleted)
        self.task_plan_widget.task_toggled.connect(self.on_task_toggled)
        self.task_plan_widget.task_config_changed.connect(self.on_task_config_changed)
        self.task_plan_widget.task_notify_changed.connect(self.on_task_notify_changed)

    def on_task_created(self, task_info):
        self.task_plan_widget.add_task(task_info)
        notification_manager.show_success("创建定时任务成功","添加成功",1000)

    def on_task_deleted(self, task_id):
        notification_manager.show_success(f"删除定时任务{task_id}成功","删除成功",1000)

    def on_task_toggled(self, task_id, enabled):
        print(f"任务 {task_id} 状态: {'启用' if enabled else '暂停'}")

    def on_task_config_changed(self, task_id, config_text, field):
        print(f"任务 {task_id} 的 {field} 改为: {config_text}")

    def on_task_notify_changed(self, task_id, notify):
        print(f"任务 {task_id} 通知: {'开启' if notify else '关闭'}")