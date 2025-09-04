# --- START OF FILE app/widgets/basic_settings_page.py ---

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
    settings_requested = Signal(str, object, object)
    # 新增: 请求移除自身的信号, 发送自己的实例
    remove_requested = Signal(object)

    def __init__(self, task_name, task_config, is_selected=False, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.task_config = task_config
        self.is_selected = is_selected
        # 新增: 跟踪移除模式
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
        self.checkbox.setChecked(self.is_selected)
        layout.addWidget(self.checkbox)

        self.name_label = QLabel(self.task_name)
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
        """根据当前模式发送不同的信号"""
        if self.is_remove_mode:
            # 在移除模式下, 发送移除请求, 把自己传出去
            self.remove_requested.emit(self)
        else:
            # 正常模式下, 发送设置请求
            self.settings_requested.emit(self.task_name, self.task_config, None)

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

        # 刷新样式
        self.settings_btn.style().polish(self.settings_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle_rect = self.drag_handle.geometry()
            if handle_rect.contains(event.pos()):
                self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        # 拖拽时仍然使用任务名称作为标识
        mime_data.setText(self.task_name)
        drag.setMimeData(mime_data)

        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec_(Qt.MoveAction)


class DraggableTaskContainer(QWidget):
    """可拖拽的任务容器"""
    order_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.task_widgets = []  # 这是一个有序列表, 对应UI顺序

    def add_task_widget(self, task_widget):
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

        dragged_task_name = event.mimeData().text()
        # 通过事件源找到被拖拽的 widget
        dragged_widget = event.source()

        if not dragged_widget or dragged_widget not in self.task_widgets:
            return

        drop_y = event.pos().y()
        insert_index = len(self.task_widgets)

        for i, widget in enumerate(self.task_widgets):
            if drop_y < widget.geometry().center().y():
                insert_index = i
                break

        # 核心拖拽逻辑: 从列表中移除, 再插入到新位置
        self.task_widgets.remove(dragged_widget)
        self.task_widgets.insert(insert_index, dragged_widget)

        # 根据新的列表顺序更新布局
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
    task_settings_requested = Signal(str, str, object, object)

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None
        self.task_container = None  # 初始化任务容器

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

    def show_resource_settings(self, resource_name):
        """显示所选资源的设置"""
        self.selected_resource_name = resource_name
        self._clear_layout(self.settings_content_layout)

        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            self.show_error_message(f"未找到资源 {resource_name} 的配置信息")
            return

        device_resource = self.get_or_create_device_resource(resource_name)
        if not device_resource:
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

        selected_tasks = device_resource.selected_tasks or []
        if not selected_tasks:
            no_tasks_label = QLabel("当前没有已添加的任务, 请点击下方的'添加任务'按钮。")
            no_tasks_label.setAlignment(Qt.AlignCenter)
            self.settings_content_layout.addWidget(no_tasks_label)
            return

        # 遍历已选择的任务列表（可能包含重复项），为每一项创建widget
        for task_name in selected_tasks:
            task_config = next((t for t in full_resource_config.resource_tasks if t.task_name == task_name), None)
            if task_config:
                task_widget = TaskItemWidget(task_name, task_config, is_selected=True)
                task_widget.settings_requested.connect(
                    lambda t_name, t_config, _: self.on_task_settings_requested(t_name, t_config, device_resource)
                )
                # 连接移除请求信号
                task_widget.remove_requested.connect(self.on_task_remove_requested)
                self.task_container.add_task_widget(task_widget)

        scroll_area.setWidget(self.task_container)
        self.settings_content_layout.addWidget(scroll_area)

    def set_remove_mode(self, enabled: bool):
        """槽函数: 接收来自父组件的信号, 更新所有任务项的模式"""
        if self.task_container:
            for task_widget in self.task_container.task_widgets:
                task_widget.set_remove_mode(enabled)

    def on_task_remove_requested(self, widget_to_remove: TaskItemWidget):
        """槽函数: 处理来自 TaskItemWidget 的移除请求"""
        if self.task_container and widget_to_remove in self.task_container.task_widgets:
            # 1. 从UI和内部列表中移除
            self.task_container.layout.removeWidget(widget_to_remove)
            self.task_container.task_widgets.remove(widget_to_remove)
            widget_to_remove.deleteLater()

            # 2. 根据UI当前状态生成新的任务列表
            new_task_order = [w.task_name for w in self.task_container.task_widgets]

            # 3. 更新数据模型 (此时不保存, 等待父组件统一保存)
            self._update_config_task_list(new_task_order)
            self.logger.info(f"任务 '{widget_to_remove.task_name}' 已被标记为移除。")

    def on_task_order_changed(self, new_order: list):
        """处理任务顺序改变, 无论是通过拖拽还是删除"""
        self._update_config_task_list(new_order)
        global_config.save_all_configs()
        self.logger.info(f"资源 {self.selected_resource_name} 的任务顺序已更新")

    def _update_config_task_list(self, new_task_list: list):
        """一个辅助方法, 用给定的列表更新配置中的selected_tasks"""
        if not self.selected_resource_name or not self.device_config:
            return

        app_config = global_config.get_app_config()
        if not app_config: return

        device_resource = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not device_resource: return

        settings = next((s for s in app_config.resource_settings
                         if s.name == device_resource.settings_name and s.resource_name == self.selected_resource_name),
                        None)
        if settings:
            settings.selected_tasks = new_task_list

    def on_task_settings_requested(self, task_name, task_config, device_resource):
        """处理任务设置请求"""
        self.task_settings_requested.emit(
            self.selected_resource_name,
            task_name,
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
                    new_settings = ResourceSettings(name=settings_name, resource_name=resource_name, selected_tasks=[],
                                                    options=[])
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
        # 注意：这里的逻辑可能需要根据复选框的实际用途进行调整
        # 目前，复选框可以视为一个独立的“启用/禁用”标志，不影响任务的存在
        status_text = "启用" if is_selected else "禁用"
        self.logger.info(f"资源 [{resource_config.resource_name}] 的任务 [{task_name}] UI状态变更为: {status_text}")

    def _create_resource_configuration(self, resource_name):
        """从按钮点击创建新的资源配置的辅助方法"""
        if self.get_or_create_device_resource(resource_name):
            self.show_resource_settings(resource_name)

    def clear_settings(self):
        """清除设置内容"""
        self._clear_layout(self.settings_content_layout)
        self.add_placeholder()
        self.selected_resource_name = None
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