# scheduled_tasks_page.py
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton, QCheckBox,
    QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)

from app.utils.notification_manager import notification_manager
from app.widgets.create_task_dialog import CreateTaskDialog


class TaskPlanTableWidget(QWidget):
    """任务计划表组件 - 与定时任务管理器集成"""

    task_deleted = Signal(int)
    task_toggled = Signal(int, bool)
    task_config_changed = Signal(int, str, str)
    task_notify_changed = Signal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_manager = None  # 将在初始化后设置
        self.all_tasks = []  # 本地任务列表缓存
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

    def set_task_manager(self, task_manager):
        """设置定时任务管理器"""
        self.task_manager = task_manager

        # 连接信号
        self.task_manager.task_added.connect(self.on_task_added_by_manager)
        self.task_manager.task_removed.connect(self.on_task_removed_by_manager)
        self.task_manager.task_status_changed.connect(self.on_task_status_changed_by_manager)
        self.task_manager.task_modified.connect(self.on_task_modified_by_manager)

        # 加载现有任务
        self.load_existing_tasks()

    def load_existing_tasks(self):
        """从定时任务管理器加载现有任务"""
        if not self.task_manager:
            return

        # 清空现有表格
        self.table.setRowCount(0)
        self.all_tasks.clear()

        # 初始化任务（从配置加载）
        existing_tasks = self.task_manager.initialize_from_config()

        # 添加到本地列表和表格
        for task_info in existing_tasks:
            self.all_tasks.append(task_info)
            self.add_task_to_table(task_info)

        self.update_filter_options()
        self.update_stats()
        self.adjust_column_widths()

    def add_task(self, task_info):
        """通过管理器添加任务"""
        if self.task_manager:
            # 通过管理器添加任务，管理器会发出信号
            task_id = self.task_manager.add_task(task_info)
            task_info['id'] = task_id
            # UI更新会通过信号自动处理

    def add_task_to_table(self, task_data):
        """添加任务到表格（内部方法）"""
        row = self.table.rowCount()
        self.table.insertRow(row)

        # ID
        id_item = QTableWidgetItem(str(task_data.get('id', '')))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setData(Qt.UserRole, task_data)
        self.table.setItem(row, 0, id_item)

        # 设备
        self.table.setItem(row, 1, QTableWidgetItem(task_data.get('device', '')))

        # 资源
        self.table.setItem(row, 2, QTableWidgetItem(task_data.get('resource', '')))

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

        # 操作
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(5, 2, 5, 2)
        op_layout.setSpacing(5)

        toggle_btn = QPushButton("暂停" if status == "活动" else "启动")
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
        """切换任务状态"""
        id_item = self.table.item(row, 0)
        status_item = self.table.item(row, 7)

        if id_item and status_item and self.task_manager:
            task_id = id_item.text()
            new_enabled = status_item.text() != "活动"

            # 通过管理器切换状态
            if self.task_manager.toggle_task_status(task_id, new_enabled):
                # UI更新会通过信号自动处理
                pass

    def delete_task(self, row):
        """删除任务"""
        id_item = self.table.item(row, 0)
        if id_item and self.task_manager:
            task_id = id_item.text()
            task_data = id_item.data(Qt.UserRole)

            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除任务 ID:{task_id} 吗？",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # 通过管理器删除任务
                if self.task_manager.remove_task(task_id):
                    # UI更新会通过信号自动处理
                    pass

    def on_config_changed(self, task_id, config_text):
        """配置方案变更"""
        if self.task_manager:
            self.task_manager.update_task_config(str(task_id), config_text)
            # 更新本地缓存
            for task in self.all_tasks:
                if str(task.get('id')) == str(task_id):
                    task['config_scheme'] = config_text
                    break
        self.task_config_changed.emit(int(task_id) if task_id else 0, config_text, 'config_scheme')

    def on_notify_changed(self, task_id, notify):
        """通知设置变更"""
        if self.task_manager:
            self.task_manager.update_task_notify(str(task_id), notify)
            # 更新本地缓存
            for task in self.all_tasks:
                if str(task.get('id')) == str(task_id):
                    task['notify'] = notify
                    break
        self.task_notify_changed.emit(int(task_id) if task_id else 0, notify)

    def on_task_added_by_manager(self, task_info):
        """处理管理器的任务添加信号"""
        # 添加到本地列表
        self.all_tasks.append(task_info)
        # 如果符合当前筛选条件，添加到表格
        if self._task_matches_filter(task_info):
            self.add_task_to_table(task_info)
        self.update_filter_options()
        self.update_stats()
        self.adjust_column_widths()

    def on_task_removed_by_manager(self, task_id):
        """处理管理器的任务删除信号"""
        # 从本地列表删除
        self.all_tasks = [t for t in self.all_tasks if str(t.get('id')) != str(task_id)]

        # 从表格删除
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if id_item and id_item.text() == str(task_id):
                self.table.removeRow(row)
                break

        self.update_filter_options()
        self.update_stats()

    def on_task_status_changed_by_manager(self, task_id, enabled):
        """处理管理器的任务状态变化信号"""
        # 更新本地缓存
        for task in self.all_tasks:
            if str(task.get('id')) == str(task_id):
                task['status'] = '活动' if enabled else '暂停'
                break

        # 更新表格
        for row in range(self.table.rowCount()):
            id_item = self.table.item(row, 0)
            if id_item and id_item.text() == str(task_id):
                status_item = self.table.item(row, 7)
                if status_item:
                    new_status = "活动" if enabled else "暂停"
                    status_item.setText(new_status)
                    status_item.setForeground(
                        QColor("#4caf50") if enabled else QColor("#ff9800")
                    )

                    # 更新按钮文本
                    widget = self.table.cellWidget(row, 8)
                    if widget:
                        buttons = widget.findChildren(QPushButton)
                        if buttons:
                            toggle_btn = buttons[0]
                            toggle_btn.setText("暂停" if enabled else "启动")
                break

        self.update_stats()

    def on_task_modified_by_manager(self, task_id, task_info):
        """处理管理器的任务修改信号"""
        # 更新本地缓存
        for i, task in enumerate(self.all_tasks):
            if str(task.get('id')) == str(task_id):
                self.all_tasks[i] = task_info
                break

        # 重新应用筛选以更新表格
        self.apply_filter()

    def _task_matches_filter(self, task):
        """检查任务是否符合当前筛选条件"""
        device_filter = self.device_filter.currentText()
        type_filter = self.type_filter.currentText()
        status_filter = self.status_filter.currentText()

        if device_filter != "全部设备" and task.get('device') != device_filter:
            return False
        if type_filter != "全部类型" and task.get('schedule_type') != type_filter:
            return False
        if status_filter != "全部状态" and task.get('status') != status_filter:
            return False

        return True

    def apply_filter(self):
        """应用筛选条件"""
        self.table.setRowCount(0)

        device_filter = self.device_filter.currentText()
        type_filter = self.type_filter.currentText()
        status_filter = self.status_filter.currentText()

        for task in self.all_tasks:
            if device_filter != "全部设备" and task.get('device') != device_filter:
                continue
            if type_filter != "全部类型" and task.get('schedule_type') != type_filter:
                continue
            if status_filter != "全部状态" and task.get('status') != status_filter:
                continue

            self.add_task_to_table(task)

        self.update_stats()
        self.adjust_column_widths()

    def update_filter_options(self):
        """更新筛选选项"""
        current = self.device_filter.currentText()
        devices = sorted(set(task.get('device', '') for task in self.all_tasks if task.get('device')))

        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("全部设备")
        self.device_filter.addItems(devices)

        index = self.device_filter.findText(current)
        if index >= 0:
            self.device_filter.setCurrentIndex(index)

        self.device_filter.blockSignals(False)

    def clear_filter(self):
        """清除筛选条件"""
        self.device_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.apply_filter()

    def pause_all_tasks(self):
        """暂停所有任务"""
        if not self.task_manager:
            return

        count = 0
        for task in self.all_tasks:
            if task.get('status') == "活动":
                task_id = str(task.get('id'))
                if self.task_manager.toggle_task_status(task_id, False):
                    count += 1

        if count > 0:
            QMessageBox.information(self, "批量操作", f"已暂停 {count} 个任务")

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

        self.connect_signals()

    def setup_task_manager(self):
        """设置定时任务管理器"""
        # 使用全局的定时任务管理器
        from core.scheduled_task_manager import scheduled_task_manager

        self.scheduled_task_manager = scheduled_task_manager

        # 设置到表格组件
        self.task_plan_widget.set_task_manager(self.scheduled_task_manager)

    def show_create_dialog(self):
        """显示创建任务对话框"""
        dialog = CreateTaskDialog(self)
        dialog.task_created.connect(self.on_task_created)
        dialog.exec()

    def connect_signals(self):
        """连接信号"""
        self.task_plan_widget.task_deleted.connect(self.on_task_deleted)
        self.task_plan_widget.task_toggled.connect(self.on_task_toggled)
        self.task_plan_widget.task_config_changed.connect(self.on_task_config_changed)
        self.task_plan_widget.task_notify_changed.connect(self.on_task_notify_changed)

    def on_task_created(self, task_info):
        """处理新任务创建"""
        self.task_plan_widget.add_task(task_info)
        notification_manager.show_success("创建定时任务成功", "添加成功", 1000)

    def on_task_deleted(self, task_id):
        """处理任务删除（兼容旧信号）"""
        notification_manager.show_success(f"删除定时任务{task_id}成功", "删除成功", 1000)

    def on_task_toggled(self, task_id, enabled):
        """处理任务状态切换（兼容旧信号）"""
        print(f"任务 {task_id} 状态: {'启用' if enabled else '暂停'}")

    def on_task_config_changed(self, task_id, config_text, field):
        """处理配置变更（兼容旧信号）"""
        print(f"任务 {task_id} 的 {field} 改为: {config_text}")

    def on_task_notify_changed(self, task_id, notify):
        """处理通知设置变更（兼容旧信号）"""
        print(f"任务 {task_id} 通知: {'开启' if notify else '关闭'}")