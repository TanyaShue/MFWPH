from PySide6.QtCore import Qt, Signal, QMimeData, QPoint, QSize
from PySide6.QtGui import QIcon, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QPushButton, QSizePolicy, QApplication
)

from app.models.config.app_config import Resource, ResourceSettings
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class TaskItemWidget(QFrame):
    """单个任务项的widget"""

    # 发送任务设置配置的信号
    settings_requested = Signal(str, object, object)  # task_name, task_config, current_settings

    def __init__(self, task_name, task_config, is_selected=False, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_config = task_config
        self.is_selected = is_selected
        self.setObjectName("taskItemWidget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 设置拖拽相关属性
        self.setAcceptDrops(True)
        self.drag_start_position = QPoint()

        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)

        # 拖拽手柄
        self.drag_handle = QLabel("☰")
        self.drag_handle.setObjectName("dragHandle")
        self.drag_handle.setFixedWidth(20)
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        layout.addWidget(self.drag_handle)

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.is_selected)
        layout.addWidget(self.checkbox)

        # 任务名称
        self.name_label = QLabel(self.task_name)
        self.name_label.setMinimumWidth(40)
        layout.addWidget(self.name_label)

        # 弹性空间
        layout.addStretch()

        # 设置按钮
        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(24, 24)  # Smaller size
        self.settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        self.settings_btn.setIconSize(QSize(14, 14))  # Smaller icon
        self.settings_btn.setObjectName("taskSettingsButton")
        self.settings_btn.clicked.connect(self.on_settings_clicked)
        layout.addWidget(self.settings_btn)

    def on_settings_clicked(self):
        """点击设置按钮时发送信号"""
        self.settings_requested.emit(self.task_name, self.task_config, None)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 检查是否在拖拽手柄区域
            handle_rect = self.drag_handle.geometry()
            if handle_rect.contains(event.pos()):
                self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        # 创建拖拽
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(self.task_name)
        drag.setMimeData(mime_data)

        # 创建拖拽时的预览图像
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec_(Qt.MoveAction)


class DraggableTaskContainer(QWidget):
    """可拖拽的任务容器"""

    # 任务顺序改变信号
    order_changed = Signal(list)  # 新的任务顺序列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.task_widgets = []

    def add_task_widget(self, task_widget):
        """添加任务widget"""
        self.task_widgets.append(task_widget)
        self.layout.addWidget(task_widget)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText():
            return

        # 获取拖拽的任务名称
        dragged_task_name = event.mimeData().text()

        # 找到被拖拽的widget
        dragged_widget = None
        for widget in self.task_widgets:
            if widget.task_name == dragged_task_name:
                dragged_widget = widget
                break

        if not dragged_widget:
            return

        # 计算放置位置
        drop_y = event.pos().y()
        insert_index = len(self.task_widgets)

        for i, widget in enumerate(self.task_widgets):
            if drop_y < widget.geometry().center().y():
                insert_index = i
                break

        # 移除并重新插入widget
        self.task_widgets.remove(dragged_widget)
        self.task_widgets.insert(insert_index, dragged_widget)

        # 重新排列布局
        for widget in self.task_widgets:
            self.layout.removeWidget(widget)
        for widget in self.task_widgets:
            self.layout.addWidget(widget)

        # 发送新的顺序信号
        new_order = [w.task_name for w in self.task_widgets]
        self.order_changed.emit(new_order)

        event.acceptProposedAction()


class BasicSettingsPage(QFrame):
    """基本设置页面，用于配置资源任务"""

    # 任务设置请求信号
    task_settings_requested = Signal(str, str, object,
                                     object)  # resource_name, task_name, task_config, current_settings

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None
        self.task_widgets = {}

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        # 创建基本页面布局
        basic_layout = QVBoxLayout(self)
        basic_layout.setContentsMargins(0, 0, 0, 0)

        # 基本设置内容区域
        self.settings_content = QWidget()
        self.settings_content_layout = QVBoxLayout(self.settings_content)
        self.settings_content_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_content_layout.setSpacing(15)

        # 添加初始占位符信息
        self.add_placeholder()
        basic_layout.addWidget(self.settings_content)

    def add_placeholder(self):
        """添加占位符信息"""
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setSpacing(15)

        # 创建自动换行的主消息标签
        initial_message = QLabel("请从左侧资源列表中选择一个资源进行设置")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setWordWrap(True)
        initial_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # 创建自动换行的次要消息标签
        sub_message = QLabel("点击资源列表中的设置按钮来配置任务")
        sub_message.setAlignment(Qt.AlignCenter)
        sub_message.setWordWrap(True)
        sub_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        placeholder_widget.setMinimumWidth(10)

        placeholder_layout.addWidget(initial_message)
        placeholder_layout.addWidget(sub_message)
        placeholder_layout.addStretch(1)

        self.settings_content_layout.addWidget(placeholder_widget)

    def show_resource_settings(self, resource_name):
        """显示所选资源的设置"""
        self.selected_resource_name = resource_name

        # 清除当前设置内容
        self._clear_layout(self.settings_content_layout)
        self.task_widgets.clear()

        # 获取资源配置
        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            # 显示错误信息
            self.show_error_message(f"未找到资源 {resource_name} 的配置信息")
            return

        # 获取设备特定的资源配置
        device_resource = self.get_or_create_device_resource(resource_name)
        if not device_resource:
            return

        # 添加描述（如果有）
        if hasattr(full_resource_config, 'description') and full_resource_config.description:
            description_label = QLabel(full_resource_config.description)
            description_label.setObjectName("resourceDescription")
            description_label.setWordWrap(True)
            description_label.setContentsMargins(10, 10, 10, 10)
            self.settings_content_layout.addWidget(description_label)

        # 创建任务的滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 创建可拖拽的任务容器
        self.task_container = DraggableTaskContainer()
        self.task_container.setObjectName('draggableTaskContainer')
        self.task_container.order_changed.connect(self.on_task_order_changed)

        # 获取任务顺序信息
        task_order_map = {task.task_name: idx for idx, task in enumerate(full_resource_config.resource_tasks)}

        # 从当前设备资源的设置中获取选定的任务列表
        selected_tasks = device_resource.selected_tasks or []
        selected_order = {task_name: idx for idx, task_name in enumerate(selected_tasks)}

        # 按选择状态和顺序排序任务
        sorted_tasks = sorted(
            full_resource_config.resource_tasks,
            key=lambda task: (
                0 if task.task_name in selected_order else 1,
                selected_order.get(task.task_name, task_order_map.get(task.task_name, float('inf')))
            )
        )

        # 创建任务小部件
        for task in sorted_tasks:
            is_task_selected = task.task_name in selected_order

            # 创建任务项widget
            task_widget = TaskItemWidget(task.task_name, task, is_task_selected)

            # 连接复选框信号
            task_widget.checkbox.stateChanged.connect(
                lambda state, t_name=task.task_name, widget=task_widget:
                self.update_task_selection(device_resource, t_name, widget.checkbox.isChecked())
            )

            # 连接设置按钮信号
            task_widget.settings_requested.connect(
                lambda t_name, t_config, _: self.on_task_settings_requested(t_name, t_config, device_resource)
            )

            self.task_container.add_task_widget(task_widget)
            self.task_widgets[task.task_name] = task_widget

        scroll_area.setWidget(self.task_container)
        self.settings_content_layout.addWidget(scroll_area)

    def on_task_settings_requested(self, task_name, task_config, device_resource):
        """处理任务设置请求"""
        # 发送信号，包含完整的配置信息
        self.task_settings_requested.emit(
            self.selected_resource_name,
            task_name,
            task_config,
            device_resource  # Pass the Resource object, not ResourceSettings
        )
    def on_task_order_changed(self, new_order):
        """处理任务顺序改变"""
        if not self.selected_resource_name or not self.device_config:
            return

        # 获取当前资源
        resource_config = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not resource_config:
            return

        # 获取app_config对象
        app_config = global_config.get_app_config()
        if not app_config:
            return

        # 获取当前资源使用的ResourceSettings
        settings = next((s for s in app_config.resource_settings
                         if s.name == resource_config.settings_name and
                         s.resource_name == resource_config.resource_name), None)
        if not settings:
            return

        # 获取当前已选择的任务列表
        current_selected_tasks = settings.selected_tasks.copy() if settings.selected_tasks else []

        # 更新任务顺序 - 保留只有当前已选择的任务
        settings.selected_tasks = [
            task for task in new_order if task in current_selected_tasks
        ]

        # 保存更新后的配置
        global_config.save_all_configs()

        # 记录更改
        self.logger.info(f"资源 {self.selected_resource_name} 的任务顺序已更新")

    def get_or_create_device_resource(self, resource_name):
        """获取或创建设备资源配置"""
        device_resource = None
        if self.device_config:
            device_resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)

        # 如果设备没有此资源配置，创建一个新的
        if not device_resource and self.device_config:
            try:
                # 获取app配置来创建ResourceSettings
                app_config = global_config.get_app_config()

                # 创建默认设置名称
                settings_name = f"{resource_name}_settings"

                # 检查是否已存在设置配置，如果不存在则创建
                existing_settings = next((s for s in app_config.resource_settings
                                          if s.resource_name == resource_name), None)

                if not existing_settings:
                    # 创建新的ResourceSettings
                    new_settings = ResourceSettings(
                        name=settings_name,
                        resource_name=resource_name,
                        selected_tasks=[],
                        options=[]
                    )
                    app_config.resource_settings.append(new_settings)
                else:
                    # 使用已有的第一个设置
                    settings_name = existing_settings.name

                # 创建引用到ResourceSettings的Resource
                device_resource = Resource(
                    resource_name=resource_name,
                    settings_name=settings_name,
                    enable=True
                )

                # 将新资源添加到设备的资源列表中
                if not hasattr(self.device_config, 'resources'):
                    self.device_config.resources = []
                self.device_config.resources.append(device_resource)

                # 保存更新后的配置
                global_config.save_all_configs()

                # 记录创建新资源的日志
                self.logger.info(f"为设备自动创建了资源 {resource_name} 的配置")
            except Exception as e:
                # 如果创建资源时出错，记录并显示警告
                log_manager.log_device_error(
                    self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备",
                    f"自动创建资源配置失败: {str(e)}"
                )
                self.show_create_resource_prompt(resource_name)
                return None

        return device_resource

    def show_error_message(self, message):
        """显示错误信息"""
        error_widget = QWidget()
        error_layout = QVBoxLayout(error_widget)
        error_layout.setAlignment(Qt.AlignCenter)

        error_icon = QLabel()
        error_icon.setPixmap(QIcon("assets/icons/error.svg").pixmap(48, 48))
        error_icon.setAlignment(Qt.AlignCenter)

        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setObjectName("errorText")

        error_layout.addWidget(error_icon)
        error_layout.addWidget(error_label)

        self.settings_content_layout.addWidget(error_widget)

    def show_create_resource_prompt(self, resource_name):
        """显示创建资源配置的提示"""
        no_config_widget = QWidget()
        no_config_layout = QVBoxLayout(no_config_widget)
        no_config_layout.setAlignment(Qt.AlignCenter)

        warning_icon = QLabel()
        warning_icon.setPixmap(QIcon("assets/icons/warning.svg").pixmap(48, 48))
        warning_icon.setAlignment(Qt.AlignCenter)

        no_config_label = QLabel(f"设备未配置资源 {resource_name}")
        no_config_label.setAlignment(Qt.AlignCenter)

        action_btn = QPushButton("添加资源配置")
        action_btn.setObjectName("primaryButton")
        action_btn.setFixedWidth(150)
        action_btn.clicked.connect(lambda: self._create_resource_configuration(resource_name))

        no_config_layout.addWidget(warning_icon)
        no_config_layout.addWidget(no_config_label)
        no_config_layout.addSpacing(15)
        no_config_layout.addWidget(action_btn, 0, Qt.AlignCenter)

        self.settings_content_layout.addWidget(no_config_widget)

    def update_task_selection(self, resource_config, task_name, is_selected):
        """Update task selection status with improved UI feedback"""
        if not resource_config:
            return

        # 获取app_config对象
        app_config = global_config.get_app_config()
        if not app_config:
            return

        # 获取当前资源使用的ResourceSettings
        settings = next((s for s in app_config.resource_settings
                         if s.name == resource_config.settings_name and
                         s.resource_name == resource_config.resource_name), None)
        if not settings:
            return

        # 确保selected_tasks已初始化
        if not hasattr(settings, 'selected_tasks') or settings.selected_tasks is None:
            settings.selected_tasks = []

        # 更新任务选择状态
        if is_selected and task_name not in settings.selected_tasks:
            settings.selected_tasks.append(task_name)
        elif not is_selected and task_name in settings.selected_tasks:
            settings.selected_tasks.remove(task_name)

        # 保存更新后的配置
        global_config.save_all_configs()

        # 记录变更
        status_text = "已选择" if is_selected else "已取消选择"
        self.logger.info(f"资源 [{resource_config.resource_name}] 的任务 [{task_name}] {status_text}")

    def _create_resource_configuration(self, resource_name):
        """从按钮点击创建新的资源配置的辅助方法"""
        device_resource = self.get_or_create_device_resource(resource_name)
        if device_resource:
            # 使用新资源刷新设置显示
            self.show_resource_settings(resource_name)

    def clear_settings(self):
        """清除设置内容"""
        self._clear_layout(self.settings_content_layout)
        self.add_placeholder()
        self.selected_resource_name = None
        self.task_widgets.clear()

    def _clear_layout(self, layout):
        """清除布局中的所有小部件"""
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())