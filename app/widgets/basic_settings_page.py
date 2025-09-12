# --- START OF FILE app/widgets/basic_settings_page.py ---

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint, QSize
from PySide6.QtGui import QIcon, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QPushButton, QSizePolicy, QApplication
)

# 导入新的 TaskInstance
from app.models.config.app_config import Resource, ResourceSettings, TaskInstance
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class TaskItemWidget(QFrame):
    """单个任务实例的widget"""
    # 信号现在发送 instance_id 来唯一标识任务
    settings_requested = Signal(str)  # instance_id
    remove_requested = Signal(str)  # instance_id
    enabled_changed = Signal(str, bool)  # instance_id, is_enabled

    def __init__(self, task_instance: TaskInstance, task_config, parent=None):
        super().__init__(parent)
        self.task_instance = task_instance
        self.task_config = task_config
        self.is_remove_mode = False

        self.setObjectName("taskItemWidget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setAcceptDrops(True)
        self.drag_start_position = QPoint()

        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)

        self.drag_handle = QLabel("☰")
        self.drag_handle.setObjectName("dragHandle")
        self.drag_handle.setFixedWidth(20)
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        layout.addWidget(self.drag_handle)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.task_instance.enabled)
        # 连接 stateChanged 信号
        self.checkbox.stateChanged.connect(self.on_enabled_changed)
        layout.addWidget(self.checkbox)

        self.name_label = QLabel(self.task_instance.task_name)
        self.name_label.setMinimumWidth(40)
        layout.addWidget(self.name_label)

        layout.addStretch()

        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        self.settings_btn.setIconSize(QSize(14, 14))
        self.settings_btn.setObjectName("taskSettingsButton")
        self.settings_btn.setToolTip("配置任务")
        self.settings_btn.clicked.connect(self.on_button_clicked)
        layout.addWidget(self.settings_btn)

    def on_button_clicked(self):
        """根据当前模式发送不同的信号，携带 instance_id"""
        if self.is_remove_mode:
            self.remove_requested.emit(self.task_instance.instance_id)
        else:
            self.settings_requested.emit(self.task_instance.instance_id)

    def on_enabled_changed(self, state):
        """当复选框状态改变时，发出信号"""
        is_enabled = state == Qt.CheckState.Checked.value
        self.enabled_changed.emit(self.task_instance.instance_id, is_enabled)

    def set_remove_mode(self, enabled: bool):
        """设置或取消移除模式, 改变按钮图标和行为"""
        self.is_remove_mode = enabled
        if enabled:
            self.settings_btn.setIcon(QIcon("assets/icons/delete.svg"))
            self.settings_btn.setToolTip("移除此任务")
            self.settings_btn.setObjectName("dangerButton")
        else:
            self.settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
            self.settings_btn.setToolTip("配置任务")
            self.settings_btn.setObjectName("taskSettingsButton")
        self.settings_btn.style().polish(self.settings_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle_rect = self.drag_handle.geometry()
            if handle_rect.contains(event.pos()):
                self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton): return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance(): return

        drag = QDrag(self)
        mime_data = QMimeData()
        # 拖拽时使用 instance_id 作为唯一标识
        mime_data.setText(self.task_instance.instance_id)
        drag.setMimeData(mime_data)

        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec_(Qt.MoveAction)


class DraggableTaskContainer(QWidget):
    """可拖拽的任务容器"""
    # 信号现在发送 instance_id 的列表
    order_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.task_widgets = []

    def add_task_widget(self, task_widget):
        self.task_widgets.append(task_widget)
        self.layout.addWidget(task_widget)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText(): event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasText(): event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasText(): return

        dragged_widget = event.source()
        if not dragged_widget or dragged_widget not in self.task_widgets: return

        drop_y = event.pos().y()
        insert_index = len(self.task_widgets)
        for i, widget in enumerate(self.task_widgets):
            if drop_y < widget.geometry().center().y():
                insert_index = i
                break

        self.task_widgets.remove(dragged_widget)
        self.task_widgets.insert(insert_index, dragged_widget)

        for widget in self.task_widgets: self.layout.removeWidget(widget)
        for widget in self.task_widgets: self.layout.addWidget(widget)

        # 发送新的 instance_id 顺序
        new_order = [w.task_instance.instance_id for w in self.task_widgets]
        self.order_changed.emit(new_order)
        event.acceptProposedAction()


class BasicSettingsPage(QFrame):
    """基本设置页面，用于配置资源任务"""
    # 信号现在包含 instance_id
    task_settings_requested = Signal(str, str, str, object,
                                     object)  # resource_name, instance_id, task_name, task_config, device_resource

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None
        self.selected_settings_name = None  # 新增：跟踪当前选择的设置方案名称
        self.task_container = None

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()

    def init_ui(self):
        basic_layout = QVBoxLayout(self)
        basic_layout.setContentsMargins(0, 0, 0, 0)

        self.settings_content = QWidget()
        self.settings_content_layout = QVBoxLayout(self.settings_content)
        self.settings_content_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_content_layout.setSpacing(15)

        self.add_placeholder()
        basic_layout.addWidget(self.settings_content)

    def add_placeholder(self):
        """添加占位符信息"""
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setSpacing(15)

        initial_message = QLabel("请从左侧资源列表中选择一个资源进行设置")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setWordWrap(True)
        initial_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        sub_message = QLabel("选择后可在此处配置其任务列表")
        sub_message.setAlignment(Qt.AlignCenter)
        sub_message.setWordWrap(True)
        sub_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        placeholder_widget.setMinimumWidth(10)

        placeholder_layout.addWidget(initial_message)
        placeholder_layout.addWidget(sub_message)
        placeholder_layout.addStretch(1)

        self.settings_content_layout.addWidget(placeholder_widget)

    def show_resource_settings(self, resource_name: str, settings_name: str):
        """显示所选资源的设置，现在需要传入 settings_name"""
        self.selected_resource_name = resource_name
        self.selected_settings_name = settings_name
        self._clear_layout(self.settings_content_layout)

        app_config = global_config.get_app_config()
        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config or not app_config:
            self.show_error_message(f"未找到资源 {resource_name} 的配置信息")
            return

        settings = next(
            (s for s in app_config.resource_settings if s.name == settings_name and s.resource_name == resource_name),
            None)
        if not settings:
            self.show_error_message(f"未找到名为 '{settings_name}' 的设置方案")
            return

        if hasattr(full_resource_config, 'description') and full_resource_config.description:
            description_label = QLabel(full_resource_config.description)
            description_label.setObjectName("resourceDescription")
            description_label.setWordWrap(True)
            description_label.setContentsMargins(10, 10, 10, 10)
            self.settings_content_layout.addWidget(description_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.task_container = DraggableTaskContainer()
        self.task_container.setObjectName('draggableTaskContainer')
        self.task_container.order_changed.connect(self.on_task_order_changed)

        if not settings.task_order:
            no_tasks_label = QLabel("当前没有已添加的任务, 请点击下方的'添加任务'按钮。")
            no_tasks_label.setAlignment(Qt.AlignCenter)
            self.settings_content_layout.addWidget(no_tasks_label)
        else:
            # 核心逻辑变更：遍历 task_order 来构建UI
            for instance_id in settings.task_order:
                task_instance = settings.task_instances.get(instance_id)
                if not task_instance:
                    self.logger.warning(f"数据不一致: task_order 中的 ID '{instance_id}' 在 task_instances 中找不到。")
                    continue

                task_config = next(
                    (t for t in full_resource_config.resource_tasks if t.task_name == task_instance.task_name), None)
                if task_config:
                    task_widget = TaskItemWidget(task_instance, task_config)
                    task_widget.settings_requested.connect(self.on_task_settings_requested)
                    task_widget.remove_requested.connect(self.on_task_remove_requested)
                    task_widget.enabled_changed.connect(self.on_task_enabled_changed)
                    self.task_container.add_task_widget(task_widget)

            scroll_area.setWidget(self.task_container)
            self.settings_content_layout.addWidget(scroll_area)

    def set_remove_mode(self, enabled: bool):
        """槽函数: 接收来自父组件的信号, 更新所有任务项的模式"""
        if self.task_container:
            for task_widget in self.task_container.task_widgets:
                task_widget.set_remove_mode(enabled)

    def on_task_remove_requested(self, instance_id: str):
        """根据 instance_id 移除任务"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if not settings or instance_id not in settings.task_instances:
            return

        # 从数据模型中移除
        removed_task = settings.task_instances.pop(instance_id)
        settings.task_order.remove(instance_id)

        # 从UI中移除
        widget_to_remove = next(
            (w for w in self.task_container.task_widgets if w.task_instance.instance_id == instance_id), None)
        if widget_to_remove:
            self.task_container.layout.removeWidget(widget_to_remove)
            self.task_container.task_widgets.remove(widget_to_remove)
            widget_to_remove.deleteLater()

        self.logger.info(f"任务 '{removed_task.task_name}' (ID: {instance_id}) 已被标记为移除。")

    def on_task_order_changed(self, new_order_ids: list):
        """处理任务顺序改变，直接更新 task_order"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if settings:
            settings.task_order = new_order_ids
            global_config.save_all_configs()
            self.logger.info(f"资源 {self.selected_resource_name} 的任务顺序已更新")

    def on_task_enabled_changed(self, instance_id: str, is_enabled: bool):
        """处理任务启用/禁用状态改变"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if settings and instance_id in settings.task_instances:
            settings.task_instances[instance_id].enabled = is_enabled
            global_config.save_all_configs()
            status = "启用" if is_enabled else "禁用"
            task_name = settings.task_instances[instance_id].task_name
            self.logger.info(f"任务 '{task_name}' (ID: {instance_id}) 已被{status}。")

    def on_task_settings_requested(self, instance_id: str):
        """处理任务设置请求"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)
        device_resource = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)

        if settings and device_resource and instance_id in settings.task_instances:
            task_instance = settings.task_instances[instance_id]
            full_resource_config = global_config.get_resource_config(self.selected_resource_name)
            task_config = next(
                (t for t in full_resource_config.resource_tasks if t.task_name == task_instance.task_name), None)

            if task_config:
                self.task_settings_requested.emit(
                    self.selected_resource_name,
                    instance_id,
                    task_instance.task_name,
                    task_config,
                    device_resource
                )

    def get_or_create_device_resource(self, resource_name):
        """获取或创建设备资源配置"""
        device_resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)
        if not device_resource:
            try:
                app_config = global_config.get_app_config()
                settings_name = f"{resource_name}_settings"
                existing_settings = next((s for s in app_config.resource_settings if s.resource_name == resource_name),
                                         None)
                if not existing_settings:
                    # 使用新的数据结构创建
                    new_settings = ResourceSettings(name=settings_name, resource_name=resource_name, task_instances={},
                                                    task_order=[])
                    app_config.resource_settings.append(new_settings)
                else:
                    settings_name = existing_settings.name
                device_resource = Resource(resource_name=resource_name, settings_name=settings_name, enable=True)
                if not hasattr(self.device_config, 'resources'): self.device_config.resources = []
                self.device_config.resources.append(device_resource)
                global_config.save_all_configs()
                self.logger.info(f"为设备自动创建了资源 {resource_name} 的配置")
            except Exception as e:
                log_manager.log_device_error(self.device_config.device_name, f"自动创建资源配置失败: {str(e)}")
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
        prompt_widget = QWidget()
        layout = QVBoxLayout(prompt_widget)
        layout.setAlignment(Qt.AlignCenter)
        icon = QLabel()
        icon.setPixmap(QIcon("assets/icons/warning.svg").pixmap(48, 48))
        icon.setAlignment(Qt.AlignCenter)
        label = QLabel(f"设备未配置资源 {resource_name}")
        label.setAlignment(Qt.AlignCenter)
        button = QPushButton("添加资源配置")
        button.setObjectName("primaryButton")
        button.setFixedWidth(150)
        button.clicked.connect(lambda: self._create_resource_configuration(resource_name))
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addSpacing(15)
        layout.addWidget(button, 0, Qt.AlignCenter)
        self.settings_content_layout.addWidget(prompt_widget)

    def update_task_selection(self, resource_config, task_name, is_selected):
        """更新任务选择状态 (此函数现在主要用于复选框，可以保留或调整其逻辑)"""
        status_text = "启用" if is_selected else "禁用"
        self.logger.info(f"资源 [{resource_config.resource_name}] 的任务 [{task_name}] UI状态变更为: {status_text}")

    def _create_resource_configuration(self, resource_name):
        """从按钮点击创建新的资源配置的辅助方法"""
        if self.get_or_create_device_resource(resource_name):
            # 需要知道当前的 settings_name 来显示
            device_resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)
            if device_resource:
                self.show_resource_settings(resource_name, device_resource.settings_name)

    def clear_settings(self):
        """清除设置内容"""
        self._clear_layout(self.settings_content_layout)
        self.add_placeholder()
        self.selected_resource_name = None
        self.selected_settings_name = None
        self.task_container = None

    def _clear_layout(self, layout):
        """清除布局中的所有小部件"""
        if layout is None: return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

# --- END OF FILE app/widgets/basic_settings_page.py ---