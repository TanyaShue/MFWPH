# scheduled_tasks_page.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QCheckBox,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)

from app.utils.notification_manager import notification_manager
from app.widgets.create_task_dialog import CreateTaskDialog


class TaskPlanTableWidget(QWidget):
    """任务计划表组件 - 与定时任务管理器集成"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_manager = None  # 将在初始化后设置
        self.all_tasks = []  # 本地任务列表缓存
        self.init_ui()

    # ... init_ui, get_filter_style, get_toolbar_btn_style 方法保持不变 ...
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

        # ... (表格样式和列宽设置代码保持不变) ...
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

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 50)
        self.table.setColumnWidth(7, 60)
        self.table.setColumnWidth(8, 120)  # 增加操作列宽度以容纳新按钮

    def set_task_manager(self, task_manager):
        """设置定时任务管理器并加载数据"""
        self.task_manager = task_manager

        # 连接管理器信号
        self.task_manager.task_added.connect(self.on_task_added_by_manager)
        self.task_manager.task_removed.connect(self.on_task_removed_by_manager)
        self.task_manager.task_status_changed.connect(self.on_task_status_changed_by_manager)
        self.task_manager.task_modified.connect(self.on_task_modified_by_manager)

        self.load_existing_tasks()

    def load_existing_tasks(self):
        """从定时任务管理器加载现有任务"""
        if not self.task_manager:
            return

        self.table.setRowCount(0)
        self.all_tasks.clear()

        # 从管理器初始化任务
        existing_tasks = self.task_manager.initialize_from_config()

        for task_info in existing_tasks:
            self.all_tasks.append(task_info)
            self.add_task_to_table(task_info)

        self.update_filter_options()
        self.update_stats()
        self.adjust_column_widths()

    def add_task_to_table(self, task_data):
        """添加单个任务到表格UI"""
        row = self.table.rowCount()
        self.table.insertRow(row)

        id_item = QTableWidgetItem(str(task_data.get('id', '')))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setData(Qt.UserRole, task_data)  # 将完整数据存入item
        self.table.setItem(row, 0, id_item)

        self.table.setItem(row, 1, QTableWidgetItem(task_data.get('device_name', '')))
        self.table.setItem(row, 2, QTableWidgetItem(task_data.get('resource_name', '')))

        # ... (类型、时间、配置、通知、状态等列的创建代码不变) ...
        # 类型
        schedule_type = task_data.get('schedule_type', '每日执行')
        type_text = {'单次执行': '单次', '每日执行': '每日', '每周执行': '每周'}.get(
            schedule_type, schedule_type
        )
        type_item = QTableWidgetItem(type_text)
        type_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 3, type_item)

        # 执行时间
        time_text = task_data.get('time', '00:00:00')
        if 'week_days' in task_data and task_data['week_days']:
            days = [d[1:] if d.startswith('周') else d for d in task_data['week_days']]
            time_text = f"{task_data['time']} ({','.join(days)})"
        self.table.setItem(row, 4, QTableWidgetItem(time_text))

        # 配置方案
        config_combo = QComboBox()
        config_combo.addItems(["默认配置", "配置方案一", "配置方案二", "自定义"])
        config_combo.setCurrentText(task_data.get('config_scheme', '默认配置'))
        config_combo.setStyleSheet("font-size: 10px; padding: 2px;")
        config_combo.currentTextChanged.connect(
            lambda text, tid=task_data.get('id'): self.on_config_changed(tid, text)
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
            lambda state, tid=task_data.get('id'): self.on_notify_changed(tid, state == Qt.Checked)
        )
        notify_layout.addWidget(notify_checkbox)

        self.table.setCellWidget(row, 6, notify_widget)

        # 状态
        status = task_data.get('status', '活动')
        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setForeground(QColor("#4caf50") if status == "活动" else QColor("#ff9800"))
        status_item.setFont(QFont("", 10, QFont.Bold))
        self.table.setItem(row, 7, status_item)

        # --- 操作按钮 ---
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(5, 2, 5, 2)
        op_layout.setSpacing(5)

        toggle_btn = QPushButton("暂停" if status == "活动" else "启动")
        toggle_btn.setFixedSize(35, 22)
        # ... (样式代码不变) ...
        toggle_btn.setStyleSheet("""
            QPushButton {
                background: #03a9f4; color: white; border: none;
                border-radius: 2px; font-size: 10px;
            }""")  # 样式代码省略

        edit_btn = QPushButton("编辑")
        edit_btn.setFixedSize(35, 22)
        edit_btn.setStyleSheet("""
            QPushButton {
                background: #03a9f4; color: white; border: none;
                border-radius: 2px; font-size: 10px;
            }
            QPushButton:hover { background: #0288d1; }
        """)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedSize(35, 22)
        # ... (样式代码不变) ...
        delete_btn.setStyleSheet("""...""")  # 样式代码省略

        toggle_btn.clicked.connect(lambda: self.toggle_task(row))
        edit_btn.clicked.connect(lambda: self.edit_task(row))
        delete_btn.clicked.connect(lambda: self.delete_task(row))

        op_layout.addWidget(toggle_btn)
        op_layout.addWidget(edit_btn)
        op_layout.addWidget(delete_btn)
        self.table.setCellWidget(row, 8, op_widget)

    def toggle_task(self, row):
        id_item = self.table.item(row, 0)
        if id_item and self.task_manager:
            task_id = id_item.text()
            task_data = id_item.data(Qt.UserRole)
            new_enabled = task_data.get('status') != "活动"
            self.task_manager.toggle_task_status(task_id, new_enabled)

    def edit_task(self, row):
        """打开编辑对话框"""
        id_item = self.table.item(row, 0)
        if id_item:
            task_data = id_item.data(Qt.UserRole)
            dialog = CreateTaskDialog(self, task_info=task_data)
            dialog.task_saved.connect(self.on_task_edited)
            dialog.exec()

    def on_task_edited(self, updated_task_info):
        """处理任务编辑后的保存"""
        if self.task_manager:
            self.task_manager.update_task(updated_task_info)
            notification_manager.show_success("更新定时任务成功", f"ID: {updated_task_info['id']} 已更新", 1000)

    def delete_task(self, row):
        id_item = self.table.item(row, 0)
        if id_item and self.task_manager:
            task_id = id_item.text()
            reply = QMessageBox.question(self, "确认删除", f"确定要删除任务 ID:{task_id} 吗？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.task_manager.remove_task(task_id)

    # ... on_config_changed 和 on_notify_changed 方法不变 ...
    def on_config_changed(self, task_id, config_text):
        if self.task_manager:
            self.task_manager.update_task_config(str(task_id), config_text)
            for task in self.all_tasks:
                if str(task.get('id')) == str(task_id):
                    task['config_scheme'] = config_text
                    break

    def on_notify_changed(self, task_id, notify):
        if self.task_manager:
            self.task_manager.update_task_notify(str(task_id), notify)
            for task in self.all_tasks:
                if str(task.get('id')) == str(task_id):
                    task['notify'] = notify
                    break

    # --- 以下是处理管理器信号的槽函数 ---

    def on_task_added_by_manager(self, task_info):
        """处理管理器的任务添加信号"""
        self.all_tasks.append(task_info)
        if self._task_matches_filter(task_info):
            self.add_task_to_table(task_info)
        self.update_filter_options()
        self.update_stats()
        self.adjust_column_widths()

    def on_task_removed_by_manager(self, task_id):
        self.all_tasks = [t for t in self.all_tasks if str(t.get('id')) != str(task_id)]
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0) and self.table.item(row, 0).text() == str(task_id):
                self.table.removeRow(row)
                break
        self.update_filter_options()
        self.update_stats()
        notification_manager.show_success(f"删除定时任务{task_id}成功", "删除成功", 1000)

    def on_task_status_changed_by_manager(self, task_id, enabled):
        """处理管理器的任务状态变化信号"""
        # 更新本地缓存
        for task in self.all_tasks:
            if str(task.get('id')) == str(task_id):
                task['status'] = '活动' if enabled else '暂停'
                break

        # 重新应用筛选，这将完全重绘表格，确保状态正确
        self.apply_filter()
        self.update_stats()

    def on_task_modified_by_manager(self, task_id, task_info):
        """处理管理器的任务修改信号（例如编辑后）"""
        for i, task in enumerate(self.all_tasks):
            if str(task.get('id')) == str(task_id):
                self.all_tasks[i] = task_info
                break
        # 重新应用筛选以更新表格行
        self.apply_filter()

    # ... (_task_matches_filter, apply_filter, update_filter_options, clear_filter 等方法不变) ...
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
        self.update_stats()
        self.adjust_column_widths()

    def update_filter_options(self):
        current = self.device_filter.currentText()
        devices = sorted(set(task.get('device_name', '') for task in self.all_tasks if task.get('device_name')))
        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("全部设备")
        self.device_filter.addItems(devices)
        index = self.device_filter.findText(current)
        if index >= 0: self.device_filter.setCurrentIndex(index)
        self.device_filter.blockSignals(False)

    def clear_filter(self):
        self.device_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)

    # --- 批量操作方法 ---
    def pause_all_tasks(self):
        # ... (代码不变) ...
        pass

    def start_all_tasks(self):
        """启动所有任务"""
        if not self.task_manager:
            return

        count = 0
        for task in self.all_tasks:
            if task.get('status') == "暂停":
                task_id = str(task.get('id'))
                if self.task_manager.toggle_task_status(task_id, True):
                    count += 1

        if count > 0:
            QMessageBox.information(self, "批量操作", f"已启动 {count} 个任务")

    def clear_all_tasks(self):
        """清空所有任务"""
        if not self.all_tasks or not self.task_manager:
            return

        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空所有 {len(self.all_tasks)} 个任务吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 通过管理器删除所有任务
            task_ids = [str(task.get('id')) for task in self.all_tasks]
            for task_id in task_ids:
                self.task_manager.remove_task(task_id)
            # UI会通过信号自动更新

    def update_stats(self):
        """更新统计信息"""
        total = len(self.all_tasks)
        active = sum(1 for task in self.all_tasks if task.get('status') == "活动")
        paused = sum(1 for task in self.all_tasks if task.get('status') == "暂停")
        self.stats_label.setText(f"任务总数: {total} | 活动: {active} | 暂停: {paused}")

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
        """显示创建任务对话框"""
        dialog = CreateTaskDialog(self)
        # 连接到新的 task_saved 信号
        dialog.task_saved.connect(self.on_task_created)
        dialog.exec()

    def on_task_created(self, task_info):
        """处理新任务创建"""
        if self.scheduled_task_manager:
            self.scheduled_task_manager.add_task(task_info)
            notification_manager.show_success("创建定时任务成功", "添加成功", 1000)