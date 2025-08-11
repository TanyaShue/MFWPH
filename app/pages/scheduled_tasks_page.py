# scheduled_task_page.py
from PySide6.QtCore import Qt, QTime, Signal, QDateTime, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QComboBox, QLabel, QPushButton, QListWidget,
    QTimeEdit, QCheckBox, QRadioButton, QButtonGroup,
    QSpacerItem, QSizePolicy, QListWidgetItem,
    QMessageBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame, QTabWidget,
    QScrollArea, QDateEdit, QLineEdit, QSpinBox
)
from app.models.config.global_config import global_config


class DeviceResourceWidget(QWidget):
    """设备和资源选择组件"""

    selection_changed = Signal(str, list)  # 设备名称, 资源列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_device = None
        self.selected_resources = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 设备选择组
        device_group = QGroupBox("设备选择")
        device_layout = QVBoxLayout()
        device_layout.setSpacing(8)

        self.device_combo = QComboBox()
        self.device_combo.addItem("请选择设备")

        # 从global_config获取设备列表
        try:
            devices = global_config.get_all_device_names()
            for device in devices:
                self.device_combo.addItem(device)
        except:
            # 如果无法获取配置，添加示例设备
            self.device_combo.addItems(["Device_1", "Device_2", "Device_3"])

        self.device_combo.currentTextChanged.connect(self.on_device_changed)
        device_layout.addWidget(QLabel("选择设备:"))
        device_layout.addWidget(self.device_combo)

        self.device_info_label = QLabel("请先选择一个设备")
        self.device_info_label.setStyleSheet("color: gray; padding: 5px;")
        self.device_info_label.setWordWrap(True)
        device_layout.addWidget(self.device_info_label)

        device_group.setLayout(device_layout)
        layout.addWidget(device_group)

        # 资源选择组
        self.resource_group = QGroupBox("资源选择")
        self.resource_group.setEnabled(False)
        resource_layout = QVBoxLayout()
        resource_layout.setSpacing(8)

        resource_layout.addWidget(QLabel("可用资源:"))

        self.resource_list = QListWidget()
        self.resource_list.setSelectionMode(QListWidget.MultiSelection)
        self.resource_list.itemSelectionChanged.connect(self.on_resource_selection_changed)
        resource_layout.addWidget(self.resource_list)

        self.selected_resources_label = QLabel("未选择任何资源")
        self.selected_resources_label.setStyleSheet("color: gray; padding: 5px;")
        self.selected_resources_label.setWordWrap(True)
        resource_layout.addWidget(self.selected_resources_label)

        # 快捷操作按钮
        quick_action_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setMaximumWidth(60)
        self.clear_all_btn = QPushButton("清空")
        self.clear_all_btn.setMaximumWidth(60)

        self.select_all_btn.clicked.connect(self.select_all_resources)
        self.clear_all_btn.clicked.connect(self.clear_all_resources)

        quick_action_layout.addWidget(self.select_all_btn)
        quick_action_layout.addWidget(self.clear_all_btn)
        quick_action_layout.addStretch()
        resource_layout.addLayout(quick_action_layout)

        self.resource_group.setLayout(resource_layout)
        layout.addWidget(self.resource_group)

        layout.addStretch()

    def select_all_resources(self):
        """全选所有资源"""
        for i in range(self.resource_list.count()):
            self.resource_list.item(i).setSelected(True)

    def clear_all_resources(self):
        """清空所有选择"""
        self.resource_list.clearSelection()

    def on_device_changed(self, device_name):
        if device_name == "请选择设备":
            self.selected_device = None
            self.device_info_label.setText("请先选择一个设备")
            self.device_info_label.setStyleSheet("color: gray; padding: 5px;")
            self.resource_group.setEnabled(False)
            self.resource_list.clear()
        else:
            self.selected_device = device_name
            self.device_info_label.setText(f"已选择: {device_name}")
            self.device_info_label.setStyleSheet("color: green; padding: 5px;")
            self.resource_group.setEnabled(True)
            self.load_device_resources(device_name)

        self.selection_changed.emit(self.selected_device or "", self.selected_resources)

    def load_device_resources(self, device_name):
        self.resource_list.clear()

        try:
            device_config = global_config.get_device_config(device_name)
            if device_config and hasattr(device_config, 'resources'):
                resources = device_config.resources
                for resource_name in resources:
                    self.resource_list.addItem(QListWidgetItem(resource_name))
            else:
                self.add_sample_resources()
        except:
            self.add_sample_resources()

    def add_sample_resources(self):
        sample_resources = [f"Resource_{i}" for i in range(1, 6)]
        for resource in sample_resources:
            self.resource_list.addItem(QListWidgetItem(resource))

    def on_resource_selection_changed(self):
        selected_items = self.resource_list.selectedItems()
        self.selected_resources = [item.text() for item in selected_items]

        if self.selected_resources:
            count = len(self.selected_resources)
            self.selected_resources_label.setText(f"已选择 {count} 个资源")
            self.selected_resources_label.setStyleSheet("color: blue; padding: 5px;")
        else:
            self.selected_resources_label.setText("未选择任何资源")
            self.selected_resources_label.setStyleSheet("color: gray; padding: 5px;")

        self.selection_changed.emit(self.selected_device or "", self.selected_resources)


class ResourceConfigWidget(QWidget):
    """单个资源的配置组件"""

    def __init__(self, resource_name, parent=None):
        super().__init__(parent)
        self.resource_name = resource_name
        self.config_data = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # 资源标题
        title_label = QLabel(f"资源: {self.resource_name}")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(title_label)

        # 配置选择
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("配置方案:"))

        self.config_combo = QComboBox()
        self.config_combo.addItems([
            "配置方案一", "配置方案二", "配置方案三", "自定义配置"
        ])
        self.config_combo.setMinimumWidth(120)
        config_layout.addWidget(self.config_combo)
        config_layout.addStretch()
        layout.addLayout(config_layout)

        # 任务参数设置
        params_group = QGroupBox("任务参数")
        params_layout = QVBoxLayout()

        # 执行次数
        exec_layout = QHBoxLayout()
        exec_layout.addWidget(QLabel("执行次数:"))
        self.exec_count_spin = QSpinBox()
        self.exec_count_spin.setMinimum(1)
        self.exec_count_spin.setMaximum(999)
        self.exec_count_spin.setValue(1)
        self.exec_count_spin.setMinimumWidth(80)
        exec_layout.addWidget(self.exec_count_spin)
        exec_layout.addWidget(QLabel("次"))
        exec_layout.addStretch()
        params_layout.addLayout(exec_layout)

        # 超时设置
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("超时时间:"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setMinimum(0)
        self.timeout_spin.setMaximum(9999)
        self.timeout_spin.setValue(60)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setMinimumWidth(100)
        timeout_layout.addWidget(self.timeout_spin)
        timeout_layout.addWidget(QLabel("(0为不限制)"))
        timeout_layout.addStretch()
        params_layout.addLayout(timeout_layout)

        # 附加选项
        self.notify_checkbox = QCheckBox("任务完成后通知")
        params_layout.addWidget(self.notify_checkbox)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        layout.addStretch()

    def get_config(self):
        """获取配置信息"""
        return {
            'resource': self.resource_name,
            'config_scheme': self.config_combo.currentText(),
            'exec_count': self.exec_count_spin.value(),
            'timeout': self.timeout_spin.value(),
            'notify': self.notify_checkbox.isChecked()
        }


class TaskSettingsWidget(QWidget):
    """任务设置组件（包含定时设置和资源配置）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resource_configs = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 定时设置组
        schedule_group = QGroupBox("定时设置")
        schedule_layout = QVBoxLayout()
        schedule_layout.setSpacing(10)

        # 执行类型
        type_label = QLabel("执行类型:")
        schedule_layout.addWidget(type_label)

        self.schedule_type_group = QButtonGroup()
        self.once_radio = QRadioButton("单次执行")
        self.daily_radio = QRadioButton("每日执行")
        self.weekly_radio = QRadioButton("每周执行")

        self.once_radio.setChecked(True)
        self.schedule_type_group.addButton(self.once_radio, 0)
        self.schedule_type_group.addButton(self.daily_radio, 1)
        self.schedule_type_group.addButton(self.weekly_radio, 2)

        radio_layout = QHBoxLayout()
        radio_layout.addWidget(self.once_radio)
        radio_layout.addWidget(self.daily_radio)
        radio_layout.addWidget(self.weekly_radio)
        radio_layout.addStretch()
        schedule_layout.addLayout(radio_layout)

        # 时间选择
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("执行时间:"))

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm:ss")
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setMinimumWidth(100)
        time_layout.addWidget(self.time_edit)
        time_layout.addStretch()
        schedule_layout.addLayout(time_layout)

        # 周选择
        self.week_widget = QWidget()
        week_layout = QVBoxLayout(self.week_widget)
        week_layout.setContentsMargins(0, 0, 0, 0)
        week_layout.addWidget(QLabel("选择星期:"))

        week_checkbox_layout = QHBoxLayout()
        self.week_checkboxes = []
        week_days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        for day in week_days:
            checkbox = QCheckBox(day)
            self.week_checkboxes.append(checkbox)
            week_checkbox_layout.addWidget(checkbox)
        week_checkbox_layout.addStretch()
        week_layout.addLayout(week_checkbox_layout)

        self.week_widget.setVisible(False)
        schedule_layout.addWidget(self.week_widget)

        # 连接信号
        self.schedule_type_group.buttonClicked.connect(self.on_schedule_type_changed)

        schedule_group.setLayout(schedule_layout)
        layout.addWidget(schedule_group)

        # 任务配置组
        config_group = QGroupBox("任务配置")
        config_layout = QVBoxLayout()

        # 使用Tab组件展示不同资源的配置
        self.resource_tabs = QTabWidget()
        self.resource_tabs.setTabsClosable(False)

        # 初始提示
        self.no_resource_label = QLabel("请先选择资源")
        self.no_resource_label.setAlignment(Qt.AlignCenter)
        self.no_resource_label.setStyleSheet("color: gray; padding: 20px;")
        config_layout.addWidget(self.no_resource_label)
        config_layout.addWidget(self.resource_tabs)
        self.resource_tabs.setVisible(False)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 创建任务按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.create_btn = QPushButton("创建定时任务")
        self.create_btn.setMinimumHeight(35)
        self.create_btn.setMinimumWidth(150)
        self.create_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        button_layout.addWidget(self.create_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)
        layout.addStretch()

    def on_schedule_type_changed(self, button):
        if button == self.weekly_radio:
            self.week_widget.setVisible(True)
        else:
            self.week_widget.setVisible(False)

    def update_resources(self, resources):
        """更新资源配置标签页"""
        # 清空现有标签页
        self.resource_tabs.clear()
        self.resource_configs.clear()

        if not resources:
            self.no_resource_label.setVisible(True)
            self.resource_tabs.setVisible(False)
        else:
            self.no_resource_label.setVisible(False)
            self.resource_tabs.setVisible(True)

            # 为每个资源创建配置页
            for resource in resources:
                config_widget = ResourceConfigWidget(resource)
                scroll_area = QScrollArea()
                scroll_area.setWidgetResizable(True)
                scroll_area.setWidget(config_widget)
                self.resource_tabs.addTab(scroll_area, resource)
                self.resource_configs[resource] = config_widget

    def get_schedule_info(self):
        """获取定时设置信息"""
        info = {
            'time': self.time_edit.time().toString("HH:mm:ss"),
        }

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

    def get_task_configs(self):
        """获取所有资源的配置"""
        configs = {}
        for resource, widget in self.resource_configs.items():
            configs[resource] = widget.get_config()
        return configs


class TaskPlanTableWidget(QWidget):
    """任务计划表组件（优化的表格布局）"""

    task_deleted = Signal(int)  # 任务ID
    task_toggled = Signal(int, bool)  # 任务ID, 启用状态
    view_mode_changed = Signal(bool)  # True: 详细模式, False: 简化模式

    def __init__(self, parent=None):
        super().__init__(parent)
        self.task_counter = 0
        self.all_tasks = []  # 存储所有任务数据
        self.is_detailed_view = False  # 当前视图模式
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        group = QGroupBox("任务计划表")
        group_layout = QVBoxLayout()
        group_layout.setSpacing(10)

        # 筛选器区域（初始隐藏）
        self.filter_widget = self.create_filter_widget()
        self.filter_widget.setVisible(False)
        group_layout.addWidget(self.filter_widget)

        # 工具栏
        toolbar_layout = QHBoxLayout()

        self.task_count_label = QLabel("当前显示: 0 / 总计: 0")
        self.task_count_label.setStyleSheet("font-weight: bold;")
        toolbar_layout.addWidget(self.task_count_label)

        toolbar_layout.addStretch()

        # 视图切换按钮
        self.view_toggle_btn = QPushButton("📋 详细视图")
        self.view_toggle_btn.setCheckable(True)
        self.view_toggle_btn.setMaximumWidth(120)
        self.view_toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:checked {
                background-color: #FF9800;
            }
            QPushButton:checked:hover {
                background-color: #F57C00;
            }
        """)
        self.view_toggle_btn.clicked.connect(self.toggle_view_mode)
        toolbar_layout.addWidget(self.view_toggle_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setMaximumWidth(80)
        self.refresh_btn.setVisible(False)
        self.clear_btn = QPushButton("🗑️ 清空完成")
        self.clear_btn.setMaximumWidth(100)
        self.clear_btn.setVisible(False)

        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.clear_btn)

        group_layout.addLayout(toolbar_layout)

        # 创建表格
        self.table = QTableWidget()
        self.setup_table_simplified()  # 默认使用简化视图

        group_layout.addWidget(self.table)

        # 统计信息
        self.stats_widget = QWidget()
        stats_layout = QHBoxLayout(self.stats_widget)
        stats_layout.setContentsMargins(0, 5, 0, 0)

        self.stats_label = QLabel("📊 统计: 活动(0) | 暂停(0) | 完成(0)")
        self.stats_label.setStyleSheet("color: #666; font-weight: bold;")
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        self.stats_widget.setVisible(False)

        group_layout.addWidget(self.stats_widget)

        group.setLayout(group_layout)
        layout.addWidget(group)

        # 连接信号
        self.clear_btn.clicked.connect(self.clear_completed_tasks)
        self.refresh_btn.clicked.connect(self.apply_filter)

    def toggle_view_mode(self):
        """切换视图模式"""
        self.is_detailed_view = self.view_toggle_btn.isChecked()

        if self.is_detailed_view:
            self.view_toggle_btn.setText("📄 简化视图")
            self.setup_table_detailed()
            self.filter_widget.setVisible(True)
            self.refresh_btn.setVisible(True)
            self.clear_btn.setVisible(True)
            self.stats_widget.setVisible(True)
        else:
            self.view_toggle_btn.setText("📋 详细视图")
            self.setup_table_simplified()
            self.filter_widget.setVisible(False)
            self.refresh_btn.setVisible(False)
            self.clear_btn.setVisible(False)
            self.stats_widget.setVisible(False)

        # 重新加载数据到表格
        self.reload_table_data()

        # 发送视图模式变化信号
        self.view_mode_changed.emit(self.is_detailed_view)

    def setup_table_simplified(self):
        """设置简化视图表格（优化的列宽）"""
        self.table.clear()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "设备", "资源", "时间", "状态", "操作"
        ])

        # 设置表格属性
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
        """)

        # 设置列宽（自适应）
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 设备
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 资源（弹性）
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # 时间
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # 状态
        header.setSectionResizeMode(4, QHeaderView.Fixed)  # 操作

        self.table.setColumnWidth(3, 70)  # 状态列固定宽度
        self.table.setColumnWidth(4, 100)  # 操作列固定宽度

    def setup_table_detailed(self):
        """设置详细视图表格（优化的列宽）"""
        self.table.clear()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "设备", "资源", "类型", "时间", "状态", "操作"
        ])

        # 设置表格属性
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                color: black;
            }
        """)

        # 设置列宽（自适应）
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # ID
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # 设备
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 资源（弹性）
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 类型
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 时间
        header.setSectionResizeMode(5, QHeaderView.Fixed)  # 状态
        header.setSectionResizeMode(6, QHeaderView.Fixed)  # 操作

        self.table.setColumnWidth(0, 40)  # ID列
        self.table.setColumnWidth(5, 70)  # 状态列
        self.table.setColumnWidth(6, 100)  # 操作列

    def reload_table_data(self):
        """重新加载表格数据"""
        self.table.setRowCount(0)

        if self.is_detailed_view:
            # 详细视图 - 应用筛选
            self.apply_filter()
        else:
            # 简化视图 - 显示所有任务
            for task in self.all_tasks:
                self.add_task_to_table(task)

        self.update_stats()

    def add_task_to_table(self, task_data):
        """将任务添加到表格（根据当前视图模式）"""
        row = self.table.rowCount()
        self.table.insertRow(row)

        if self.is_detailed_view:
            self.add_task_detailed(row, task_data)
        else:
            self.add_task_simplified(row, task_data)

    def add_task_simplified(self, row, task_data):
        """添加任务到简化视图"""
        # 设备
        device_item = QTableWidgetItem(task_data['device'])
        device_item.setData(Qt.UserRole, task_data)  # 存储完整数据
        self.table.setItem(row, 0, device_item)

        # 资源（优化显示）
        resources = task_data['resources']
        if len(resources) <= 3:
            resources_text = ", ".join(resources)
        else:
            resources_text = f"{', '.join(resources[:2])}... (+{len(resources) - 2})"
        resources_item = QTableWidgetItem(resources_text)
        resources_item.setToolTip(", ".join(resources))  # 添加完整列表作为提示
        self.table.setItem(row, 1, resources_item)

        # 时间（优化显示）
        time_text = task_data['time']
        if task_data['schedule_type'] == '每周执行' and 'week_days' in task_data:
            days = [d[1:] for d in task_data['week_days']]
            time_text = f"{task_data['time']} ({','.join(days)})"
        elif task_data['schedule_type'] == '每日执行':
            time_text = f"{task_data['time']} (每日)"
        time_item = QTableWidgetItem(time_text)
        self.table.setItem(row, 2, time_item)

        # 状态（带颜色）
        status_item = QTableWidgetItem(task_data['status'])
        status_item.setTextAlignment(Qt.AlignCenter)
        self._set_status_style(status_item, task_data['status'])
        self.table.setItem(row, 3, status_item)

        # 操作按钮
        self.table.setCellWidget(row, 4, self._create_operation_widget(row, task_data, False))

    def add_task_detailed(self, row, task_data):
        """添加任务到详细视图"""
        # ID
        id_item = QTableWidgetItem(str(task_data['id']))
        id_item.setTextAlignment(Qt.AlignCenter)
        id_item.setData(Qt.UserRole, task_data)
        self.table.setItem(row, 0, id_item)

        # 设备
        device_item = QTableWidgetItem(task_data['device'])
        self.table.setItem(row, 1, device_item)

        # 资源（优化显示）
        resources = task_data['resources']
        if len(resources) <= 3:
            resources_text = ", ".join(resources)
        else:
            resources_text = f"{', '.join(resources[:2])}... (+{len(resources) - 2})"
        resources_item = QTableWidgetItem(resources_text)
        resources_item.setToolTip(", ".join(resources))
        self.table.setItem(row, 2, resources_item)

        # 类型
        type_item = QTableWidgetItem(task_data['schedule_type'])
        self.table.setItem(row, 3, type_item)

        # 时间
        time_text = task_data['time']
        if 'week_days' in task_data:
            days = [d[1:] for d in task_data['week_days']]
            time_text = f"{task_data['time']} ({','.join(days)})"
        time_item = QTableWidgetItem(time_text)
        self.table.setItem(row, 4, time_item)

        # 状态
        status_item = QTableWidgetItem(task_data['status'])
        status_item.setTextAlignment(Qt.AlignCenter)
        self._set_status_style(status_item, task_data['status'])
        self.table.setItem(row, 5, status_item)

        # 操作按钮
        self.table.setCellWidget(row, 6, self._create_operation_widget(row, task_data, True))

    def _set_status_style(self, item, status):
        """设置状态项的样式"""
        if status == "活动":
            item.setForeground(Qt.green)
            item.setFont(self._get_bold_font())
        elif status == "暂停":
            item.setForeground(Qt.darkYellow)
            item.setFont(self._get_bold_font())
        else:
            item.setForeground(Qt.gray)

    def _get_bold_font(self):
        """获取粗体字体"""
        from PySide6.QtGui import QFont
        font = QFont()
        font.setBold(True)
        return font

    def _create_operation_widget(self, row, task_data, is_detailed):
        """创建操作按钮组件"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(5)

        # 切换按钮
        toggle_btn = QPushButton("⏸" if task_data['status'] == "活动" else "▶")
        toggle_btn.setMaximumWidth(30)
        toggle_btn.setToolTip("暂停" if task_data['status'] == "活动" else "启动")
        toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)

        # 删除按钮
        delete_btn = QPushButton("🗑")
        delete_btn.setMaximumWidth(30)
        delete_btn.setToolTip("删除")
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffebee;
                border: 1px solid #ffcdd2;
                border-radius: 3px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #ffcdd2;
            }
        """)

        if is_detailed:
            toggle_btn.clicked.connect(lambda: self.toggle_task_detailed(row))
            delete_btn.clicked.connect(lambda: self.delete_task_detailed(row))
        else:
            toggle_btn.clicked.connect(lambda: self.toggle_task_simplified(row))
            delete_btn.clicked.connect(lambda: self.delete_task_simplified(row))

        layout.addWidget(toggle_btn)
        layout.addWidget(delete_btn)

        return widget

    def toggle_task_simplified(self, row):
        """切换任务状态（简化视图）"""
        device_item = self.table.item(row, 0)
        status_item = self.table.item(row, 3)

        if device_item and status_item:
            task_data = device_item.data(Qt.UserRole)
            self._toggle_task_status(task_data, status_item, row, 4)

    def toggle_task_detailed(self, row):
        """切换任务状态（详细视图）"""
        id_item = self.table.item(row, 0)
        status_item = self.table.item(row, 5)

        if id_item and status_item:
            task_data = id_item.data(Qt.UserRole)
            self._toggle_task_status(task_data, status_item, row, 6)

    def _toggle_task_status(self, task_data, status_item, row, op_col):
        """通用的任务状态切换逻辑"""
        current_status = status_item.text()

        if current_status == "活动":
            new_status = "暂停"
            button_text = "▶"
            button_tooltip = "启动"
        elif current_status == "暂停":
            new_status = "活动"
            button_text = "⏸"
            button_tooltip = "暂停"
        else:
            return

        status_item.setText(new_status)
        self._set_status_style(status_item, new_status)
        task_data['status'] = new_status

        # 更新按钮
        widget = self.table.cellWidget(row, op_col)
        if widget:
            toggle_btn = widget.findChildren(QPushButton)[0]
            toggle_btn.setText(button_text)
            toggle_btn.setToolTip(button_tooltip)

        self.task_toggled.emit(task_data['id'], new_status == "活动")
        self.update_stats()

    def delete_task_simplified(self, row):
        """删除任务（简化视图）"""
        device_item = self.table.item(row, 0)
        if device_item:
            task_data = device_item.data(Qt.UserRole)
            self._delete_task(task_data['id'], row)

    def delete_task_detailed(self, row):
        """删除任务（详细视图）"""
        id_item = self.table.item(row, 0)
        if id_item:
            task_data = id_item.data(Qt.UserRole)
            self._delete_task(task_data['id'], row)

    def _delete_task(self, task_id, row):
        """通用的任务删除逻辑"""
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这个任务吗？",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # 从任务列表中删除
            self.all_tasks = [t for t in self.all_tasks if t['id'] != task_id]

            # 从表格中删除
            self.table.removeRow(row)

            # 更新筛选器
            if self.is_detailed_view:
                self.update_filter_options()

            self.task_deleted.emit(task_id)
            self.update_stats()

    def create_filter_widget(self):
        """创建优化的筛选器"""
        widget = QWidget()
        widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
        """)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(15)

        # 设备筛选
        device_container = QHBoxLayout()
        device_label = QLabel("设备:")
        device_label.setStyleSheet("font-weight: bold;")
        device_container.addWidget(device_label)

        self.device_filter = QComboBox()
        self.device_filter.addItem("全部")
        self.device_filter.setMinimumWidth(100)
        self.device_filter.currentTextChanged.connect(self.apply_filter)
        device_container.addWidget(self.device_filter)
        layout.addLayout(device_container)

        # 类型筛选（替换原来的时间筛选）
        type_container = QHBoxLayout()
        type_label = QLabel("类型:")
        type_label.setStyleSheet("font-weight: bold;")
        type_container.addWidget(type_label)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["全部", "单次执行", "每日执行", "每周执行"])
        self.type_filter.setMinimumWidth(100)
        self.type_filter.currentTextChanged.connect(self.apply_filter)
        type_container.addWidget(self.type_filter)
        layout.addLayout(type_container)

        # 状态筛选
        status_container = QHBoxLayout()
        status_label = QLabel("状态:")
        status_label.setStyleSheet("font-weight: bold;")
        status_container.addWidget(status_label)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "活动", "暂停", "完成"])
        self.status_filter.setMinimumWidth(80)
        self.status_filter.currentTextChanged.connect(self.apply_filter)
        status_container.addWidget(self.status_filter)
        layout.addLayout(status_container)

        # 搜索框
        search_container = QHBoxLayout()
        search_label = QLabel("搜索:")
        search_label.setStyleSheet("font-weight: bold;")
        search_container.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词...")
        self.search_input.setMinimumWidth(150)
        self.search_input.textChanged.connect(self.apply_filter)
        search_container.addWidget(self.search_input)
        layout.addLayout(search_container)

        # 清除筛选按钮
        self.clear_filter_btn = QPushButton("清除筛选")
        self.clear_filter_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        self.clear_filter_btn.clicked.connect(self.clear_filter)
        layout.addWidget(self.clear_filter_btn)

        layout.addStretch()

        return widget

    def add_task(self, task_info):
        """添加任务到表格"""
        # 生成任务ID
        self.task_counter += 1
        task_id = self.task_counter

        # 创建任务数据
        task_data = {
            'id': task_id,
            'device': task_info['device'],
            'resources': task_info['resources'],
            'schedule_type': task_info['schedule_type'],
            'time': task_info['time'],
            'status': "活动" if task_info.get('auto_start', True) else "暂停",
            'create_time': QDateTime.currentDateTime(),
            'resource_configs': task_info.get('resource_configs', {})
        }

        if task_info['schedule_type'] == '每周执行' and 'week_days' in task_info:
            task_data['week_days'] = task_info['week_days']

        # 添加到任务列表
        self.all_tasks.append(task_data)

        # 更新筛选器选项
        if self.is_detailed_view:
            self.update_filter_options()

        # 添加到表格显示
        self.add_task_to_table(task_data)

        # 更新计数
        self.update_task_count()
        self.update_stats()

    def update_filter_options(self):
        """更新筛选器选项"""
        # 更新设备筛选器
        current_device = self.device_filter.currentText()
        devices = sorted(set(task['device'] for task in self.all_tasks))

        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("全部")
        self.device_filter.addItems(devices)

        # 恢复之前的选择
        index = self.device_filter.findText(current_device)
        if index >= 0:
            self.device_filter.setCurrentIndex(index)

        self.device_filter.blockSignals(False)

    def apply_filter(self):
        """应用筛选（仅在详细视图中有效）"""
        if not self.is_detailed_view:
            return

        # 清空表格
        self.table.setRowCount(0)

        # 获取筛选条件
        device_filter = self.device_filter.currentText()
        type_filter = self.type_filter.currentText()
        status_filter = self.status_filter.currentText()
        search_text = self.search_input.text().lower()

        # 筛选任务
        filtered_tasks = []
        for task in self.all_tasks:
            # 设备筛选
            if device_filter != "全部" and task['device'] != device_filter:
                continue

            # 类型筛选
            if type_filter != "全部" and task['schedule_type'] != type_filter:
                continue

            # 状态筛选
            if status_filter != "全部" and task['status'] != status_filter:
                continue

            # 搜索筛选
            if search_text:
                search_fields = [
                    str(task['id']),
                    task['device'].lower(),
                    ' '.join(task['resources']).lower(),
                    task['schedule_type'].lower(),
                    task['status'].lower()
                ]
                if not any(search_text in field for field in search_fields):
                    continue

            filtered_tasks.append(task)

        # 显示筛选后的任务
        for task in filtered_tasks:
            self.add_task_to_table(task)

        # 更新计数
        self.update_task_count()
        self.update_stats()

    def clear_filter(self):
        """清除筛选"""
        self.device_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.status_filter.setCurrentIndex(0)
        self.search_input.clear()
        self.apply_filter()

    def clear_completed_tasks(self):
        """清空已完成的任务"""
        completed_ids = []

        for task in self.all_tasks:
            if task['status'] == "完成":
                completed_ids.append(task['id'])

        if completed_ids:
            reply = QMessageBox.question(
                self, "确认清空",
                f"确定要清空 {len(completed_ids)} 个已完成的任务吗？",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # 从任务列表中删除
                self.all_tasks = [t for t in self.all_tasks if t['id'] not in completed_ids]

                # 重新加载数据
                self.reload_table_data()

                # 更新筛选器
                if self.is_detailed_view:
                    self.update_filter_options()
        else:
            QMessageBox.information(self, "提示", "没有已完成的任务")

    def update_task_count(self):
        """更新任务计数显示"""
        total = len(self.all_tasks)
        displayed = self.table.rowCount()
        self.task_count_label.setText(f"当前显示: {displayed} / 总计: {total}")

    def update_stats(self):
        """更新统计信息"""
        active = paused = completed = 0

        # 统计所有任务（不只是显示的）
        for task in self.all_tasks:
            status = task['status']
            if status == "活动":
                active += 1
            elif status == "暂停":
                paused += 1
            elif status == "完成":
                completed += 1

        self.stats_label.setText(f"📊 统计: 活动({active}) | 暂停({paused}) | 完成({completed})")


class ScheduledTaskPage(QWidget):
    """定时任务设置页面 - 优化版"""

    task_created = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        """初始化UI - 优化的布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 设置widget样式
        self.setObjectName("scheduled_task_widget")
        self.setStyleSheet("""
            #scheduled_task_widget {
                background-color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        # 主水平分割器
        self.horizontal_splitter = QSplitter(Qt.Horizontal)
        self.horizontal_splitter.setObjectName("horizontalSplitter")
        self.horizontal_splitter.setHandleWidth(8)
        self.horizontal_splitter.setChildrenCollapsible(False)
        self.horizontal_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e0e0e0;
                border-radius: 2px;
            }
            QSplitter::handle:hover {
                background-color: #c0c0c0;
            }
        """)

        # 左侧容器（设备选择 + 任务设置）
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # 1. 设备和资源选择
        self.device_resource_widget = DeviceResourceWidget()
        left_layout.addWidget(self.device_resource_widget)

        # 2. 任务设置
        self.task_settings_widget = TaskSettingsWidget()
        self.task_settings_widget.create_btn.setEnabled(False)
        left_layout.addWidget(self.task_settings_widget)

        # 3. 任务计划表（占用主要空间）
        self.task_plan_widget = TaskPlanTableWidget()

        # 添加到分割器
        self.horizontal_splitter.addWidget(left_container)
        self.horizontal_splitter.addWidget(self.task_plan_widget)

        # 设置初始宽度比例 (1:2)
        self.initial_sizes = [400, 800]
        self.horizontal_splitter.setSizes(self.initial_sizes)

        # 设置最小宽度
        left_container.setMinimumWidth(350)
        self.task_plan_widget.setMinimumWidth(500)

        main_layout.addWidget(self.horizontal_splitter)

        # 连接信号
        self.connect_signals()

    def connect_signals(self):
        """连接信号"""
        # 设备资源选择变化
        self.device_resource_widget.selection_changed.connect(self.on_selection_changed)

        # 创建任务按钮
        self.task_settings_widget.create_btn.clicked.connect(self.on_create_task)

        # 任务表格操作
        self.task_plan_widget.task_deleted.connect(self.on_task_deleted)
        self.task_plan_widget.task_toggled.connect(self.on_task_toggled)

        # 视图模式切换
        self.task_plan_widget.view_mode_changed.connect(self.on_view_mode_changed)

    def on_view_mode_changed(self, is_detailed):
        """处理视图模式切换"""
        if is_detailed:
            # 详细模式：隐藏左侧面板
            left_widget = self.horizontal_splitter.widget(0)
            left_widget.setVisible(False)

            # 记录当前宽度
            self.saved_sizes = self.horizontal_splitter.sizes()

            # 任务表占满整个宽度
            total_width = sum(self.saved_sizes)
            self.horizontal_splitter.setSizes([0, total_width])
        else:
            # 简化模式：恢复左侧面板
            left_widget = self.horizontal_splitter.widget(0)
            left_widget.setVisible(True)

            # 恢复之前的宽度比例
            if hasattr(self, 'saved_sizes'):
                self.horizontal_splitter.setSizes(self.saved_sizes)
            else:
                self.horizontal_splitter.setSizes(self.initial_sizes)

    def on_selection_changed(self, device, resources):
        """处理选择变化"""
        # 更新任务设置中的资源配置
        self.task_settings_widget.update_resources(resources)

        # 只有设备和资源都选择了才能创建任务
        can_create = bool(device and resources)
        self.task_settings_widget.create_btn.setEnabled(can_create)

    def on_create_task(self):
        """创建任务"""
        device = self.device_resource_widget.selected_device
        resources = self.device_resource_widget.selected_resources

        if not device:
            QMessageBox.warning(self, "警告", "请选择设备！")
            return

        if not resources:
            QMessageBox.warning(self, "警告", "请选择至少一个资源！")
            return

        # 获取定时设置
        schedule_info = self.task_settings_widget.get_schedule_info()

        # 验证周任务
        if schedule_info['schedule_type'] == '每周执行':
            if 'week_days' not in schedule_info or not schedule_info['week_days']:
                QMessageBox.warning(self, "警告", "请选择至少一个执行日！")
                return

        # 获取资源配置
        resource_configs = self.task_settings_widget.get_task_configs()

        # 组合任务信息
        task_info = {
            'device': device,
            'resources': resources,
            'resource_configs': resource_configs,
            'auto_start': True,
            **schedule_info
        }

        # 添加到表格
        self.task_plan_widget.add_task(task_info)

        # 发送信号
        self.task_created.emit(task_info)

        # 显示成功消息
        QMessageBox.information(self, "成功", "定时任务创建成功！")

    def on_task_deleted(self, task_id):
        """处理任务删除"""
        print(f"任务 {task_id} 已删除")

    def on_task_toggled(self, task_id, enabled):
        """处理任务状态切换"""
        status = "启用" if enabled else "暂停"
        print(f"任务 {task_id} 状态已更改为: {status}")