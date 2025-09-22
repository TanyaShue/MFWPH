# --- START OF FILE app/widgets/basic_settings_page.py ---

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint, QSize
from PySide6.QtGui import QIcon, QDrag, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QPushButton, QSizePolicy, QApplication
)

from app.models.config.app_config import Resource, ResourceSettings, TaskInstance
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class TaskItemWidget(QFrame):
    """单个任务实例的UI控件，支持拖拽和配置"""
    # 信号现在发送 instance_id 来唯一标识任务
    settings_requested = Signal(str)  # instance_id
    remove_requested = Signal(str)  # instance_id
    enabled_changed = Signal(str, bool)  # instance_id, is_enabled

    def __init__(self, task_instance: TaskInstance, task_config, parent=None):
        super().__init__(parent)
        self.task_instance = task_instance
        self.task_config = task_config
        self.is_remove_mode = False
        self.is_marked_for_removal = False  # 新增状态：是否被标记为待删除

        self.setObjectName("taskItemWidget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 启用拖放
        self.setAcceptDrops(True)
        self.drag_start_position = QPoint()

        self.init_ui()

    def init_ui(self):
        """初始化任务项的UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(0)

        # 拖拽手柄
        self.drag_handle = QLabel("☰")
        self.drag_handle.setObjectName("dragHandle")
        self.drag_handle.setFixedWidth(20)
        self.drag_handle.setCursor(Qt.SizeAllCursor)
        layout.addWidget(self.drag_handle)

        # 启用/禁用复选框
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.task_instance.enabled)
        self.checkbox.stateChanged.connect(self.on_enabled_changed)
        layout.addWidget(self.checkbox)

        # 任务名称
        self.name_label = QLabel(self.task_instance.task_name)
        self.name_label.setMinimumWidth(40)
        layout.addWidget(self.name_label)

        layout.addStretch()

        # 设置/删除按钮（根据模式切换功能）
        self.settings_btn = QPushButton()
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
        self.settings_btn.setIconSize(QSize(14, 14))
        self.settings_btn.setObjectName("taskSettingsButton")
        self.settings_btn.setToolTip("配置任务")
        self.settings_btn.clicked.connect(self.on_button_clicked)
        layout.addWidget(self.settings_btn)

    def on_button_clicked(self):
        """根据当前是否为移除模式，发送不同的信号"""
        if self.is_remove_mode:
            self.remove_requested.emit(self.task_instance.instance_id)
        else:
            self.settings_requested.emit(self.task_instance.instance_id)

    def on_enabled_changed(self, state):
        """当复选框状态改变时，发出信号通知父组件"""
        is_enabled = state == Qt.CheckState.Checked.value
        self.enabled_changed.emit(self.task_instance.instance_id, is_enabled)

    def set_remove_mode(self, enabled: bool):
        """设置或取消移除模式, 改变按钮图标和行为"""
        self.is_remove_mode = enabled
        if enabled:
            # 进入移除模式时，如果自己已经被标记，显示取消标记图标
            if self.is_marked_for_removal:
                self.settings_btn.setIcon(QIcon("assets/icons/revert.svg"))  # 假设你有一个“撤销”图标
                self.settings_btn.setToolTip("取消移除")
            else:
                self.settings_btn.setIcon(QIcon("assets/icons/delete.svg"))
                self.settings_btn.setToolTip("标记此任务为待移除")
            self.settings_btn.setObjectName("dangerButton")
        else:
            # 退出移除模式，恢复正常状态
            self.set_marked_for_removal(False)  # 确保标记状态被清除
            self.settings_btn.setIcon(QIcon("assets/icons/settings.svg"))
            self.settings_btn.setToolTip("配置任务")
            self.settings_btn.setObjectName("taskSettingsButton")

        # 强制刷新样式
        self.settings_btn.style().polish(self.settings_btn)

    def set_marked_for_removal(self, marked: bool):
        """
        改变控件的视觉外观，以表明它是否被标记为待删除
        """
        self.is_marked_for_removal = marked
        if marked:
            # 使用动态属性来改变样式，方便在QSS中定义
            self.setProperty("markedForRemoval", True)
            self.settings_btn.setIcon(QIcon("assets/icons/revert.svg"))  # 切换为撤销图标
            self.settings_btn.setToolTip("取消移除")
        else:
            self.setProperty("markedForRemoval", False)
            # 只有在移除模式下才恢复为删除图标，否则应该是设置图标
            if self.is_remove_mode:
                self.settings_btn.setIcon(QIcon("assets/icons/delete.svg"))
                self.settings_btn.setToolTip("标记此任务为待移除")

        # 刷新样式以应用或移除属性
        self.style().polish(self)
        self.settings_btn.style().polish(self.settings_btn)

    def mousePressEvent(self, event):
        """记录鼠标按下的位置，用于启动拖拽"""
        if event.button() == Qt.LeftButton:
            handle_rect = self.drag_handle.geometry()
            if handle_rect.contains(event.pos()):
                self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """当鼠标移动时，如果满足拖拽条件，则开始拖拽操作"""
        if not (event.buttons() & Qt.LeftButton): return
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance(): return

        drag = QDrag(self)
        mime_data = QMimeData()
        # 拖拽时使用 instance_id 作为唯一标识
        mime_data.setText(self.task_instance.instance_id)
        drag.setMimeData(mime_data)

        # 创建一个拖拽时的预览图像
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec_(Qt.MoveAction)


class DraggableTaskContainer(QWidget):
    """一个支持拖放排序的容器，用于容纳多个TaskItemWidget"""
    # 当拖放操作导致顺序改变时发出此信号
    order_changed = Signal(list)  # list of instance_ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5)
        self.task_widgets = []

    def add_task_widget(self, task_widget):
        """向容器中添加一个任务项"""
        self.task_widgets.append(task_widget)
        self.layout.addWidget(task_widget)

    def dragEnterEvent(self, event):
        """当有拖拽进入时，接受事件"""
        if event.mimeData().hasText(): event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """当拖拽在内部移动时，接受事件"""
        if event.mimeData().hasText(): event.acceptProposedAction()

    def dropEvent(self, event):
        """当拖拽释放时，重新计算顺序并发出信号"""
        if not event.mimeData().hasText(): return

        dragged_widget = event.source()
        if not dragged_widget or dragged_widget not in self.task_widgets: return

        # 根据释放点的Y坐标计算新的插入位置
        drop_y = event.pos().y()
        insert_index = len(self.task_widgets)
        for i, widget in enumerate(self.task_widgets):
            if drop_y < widget.geometry().center().y():
                insert_index = i
                break

        # 更新内部列表顺序
        self.task_widgets.remove(dragged_widget)
        self.task_widgets.insert(insert_index, dragged_widget)

        # 重新排列UI
        for widget in self.task_widgets: self.layout.removeWidget(widget)
        for widget in self.task_widgets: self.layout.addWidget(widget)

        # 发出新的 instance_id 顺序
        new_order = [w.task_instance.instance_id for w in self.task_widgets]
        self.order_changed.emit(new_order)
        event.acceptProposedAction()


class BasicSettingsPage(QFrame):
    """基本设置页面，用于显示和管理一个资源配置方案下的任务列表"""
    # 当请求任务设置时发出信号
    task_settings_requested = Signal(str, str, str, object, object)

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None
        self.selected_settings_name = None  # 跟踪当前选择的配置方案名称
        self.task_container = None
        self.pending_removal_ids = set()  # 新增：用于存储待删除任务的ID

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()

    def init_ui(self):
        """初始化UI，开始时显示占位符"""
        basic_layout = QVBoxLayout(self)
        basic_layout.setContentsMargins(0, 0, 0, 0)

        self.settings_content = QWidget()
        self.settings_content_layout = QVBoxLayout(self.settings_content)
        self.settings_content_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_content_layout.setSpacing(15)

        self.add_placeholder()
        basic_layout.addWidget(self.settings_content)

    def add_placeholder(self):
        """添加占位符信息，当没有资源被选择时显示"""
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setSpacing(15)

        initial_message = QLabel("请从左侧资源列表中选择一个资源进行设置")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setWordWrap(True)

        self.settings_content_layout.addWidget(initial_message)
        self.settings_content_layout.addStretch()

    def show_resource_settings(self, resource_name: str, settings_name: str):
        """显示所选资源的设置，需要传入配置方案名称"""
        self.selected_resource_name = resource_name
        self.selected_settings_name = settings_name
        self._clear_layout(self.settings_content_layout)
        self.pending_removal_ids.clear()  # 切换显示时，清空待删除列表

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

        # 如果没有任务，显示提示信息
        if not settings.task_order:
            no_tasks_label = QLabel("当前没有已添加的任务, 请点击下方的'添加任务'按钮。")
            no_tasks_label.setAlignment(Qt.AlignCenter)
            self.settings_content_layout.addWidget(no_tasks_label)
            self.settings_content_layout.addStretch(1)
        else:
            # 如果有任务，则创建滚动区域和可拖拽容器来显示它们
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

            self.task_container = DraggableTaskContainer()
            self.task_container.setObjectName('draggableTaskContainer')
            self.task_container.order_changed.connect(self.on_task_order_changed)

            # 核心逻辑：遍历 task_order 来构建UI，确保顺序正确
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
            self.settings_content_layout.addWidget(scroll_area, 1)

    def set_remove_mode(self, enabled: bool):
        """槽函数: 接收来自父组件的信号, 更新所有任务项的模式"""
        if self.task_container:
            for child in self.task_container.findChildren(TaskItemWidget):
                child.set_remove_mode(enabled)

    def on_task_remove_requested(self, instance_id: str):
        """
        修改后的逻辑：不再立即删除，而是标记/取消标记任务
        """
        widget_to_mark = next(
            (w for w in self.task_container.task_widgets if w.task_instance.instance_id == instance_id), None)
        if not widget_to_mark:
            return

        if instance_id in self.pending_removal_ids:
            # 如果已被标记，则取消标记
            self.pending_removal_ids.remove(instance_id)
            widget_to_mark.set_marked_for_removal(False)
            self.logger.debug(f"任务 (ID: {instance_id}) 已被取消移除标记。")
        else:
            # 如果未被标记，则进行标记
            self.pending_removal_ids.add(instance_id)
            widget_to_mark.set_marked_for_removal(True)
            self.logger.debug(f"任务 (ID: {instance_id}) 已被标记为待移除。")

    def commit_removals(self) -> int:
        """
        执行真正的删除操作，由父组件在用户确认后调用。
        返回被删除的任务数量。
        """
        if not self.pending_removal_ids:
            return 0

        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if not settings:
            return 0

        removed_count = 0
        for instance_id in self.pending_removal_ids:
            if instance_id not in settings.task_instances:
                continue

            # 从数据模型中移除
            removed_task = settings.task_instances.pop(instance_id)
            settings.task_order.remove(instance_id)

            # 从UI中移除
            if self.task_container:
                widget_to_remove = next(
                    (w for w in self.task_container.task_widgets if w.task_instance.instance_id == instance_id), None)
                if widget_to_remove:
                    self.task_container.layout.removeWidget(widget_to_remove)
                    self.task_container.task_widgets.remove(widget_to_remove)
                    widget_to_remove.deleteLater()

            self.logger.info(f"任务 '{removed_task.task_name}' (ID: {instance_id}) 已被移除。")
            removed_count += 1

        self.pending_removal_ids.clear()
        return removed_count

    def cancel_removals(self):
        """
        取消所有待删除的标记，恢复UI，由父组件在用户取消后调用。
        """
        if self.task_container:
            for instance_id in self.pending_removal_ids:
                widget_to_restore = next(
                    (w for w in self.task_container.task_widgets if w.task_instance.instance_id == instance_id), None)
                if widget_to_restore:
                    widget_to_restore.set_marked_for_removal(False)

        self.pending_removal_ids.clear()

    def on_task_order_changed(self, new_order_ids: list):
        """处理任务顺序改变，更新数据模型并保存"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if settings:
            settings.task_order = new_order_ids
            global_config.save_all_configs()
            self.logger.info(f"资源 {self.selected_resource_name} 的任务顺序已更新")

    def on_task_enabled_changed(self, instance_id: str, is_enabled: bool):
        """处理任务启用/禁用状态改变，更新数据模型并保存"""
        app_config = global_config.get_app_config()
        settings = next((s for s in app_config.resource_settings if s.name == self.selected_settings_name), None)

        if settings and instance_id in settings.task_instances:
            settings.task_instances[instance_id].enabled = is_enabled
            global_config.save_all_configs()
            status = "启用" if is_enabled else "禁用"
            task_name = settings.task_instances[instance_id].task_name
            self.logger.info(f"任务 '{task_name}' (ID: {instance_id}) 已被{status}。")

    def on_task_settings_requested(self, instance_id: str):
        """处理任务设置请求，找到所有需要的信息并发出信号"""
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

    def show_error_message(self, message):
        """在界面上显示错误信息"""
        self._clear_layout(self.settings_content_layout)
        error_label = QLabel(message)
        error_label.setObjectName("errorText")
        error_label.setAlignment(Qt.AlignCenter)
        self.settings_content_layout.addWidget(error_label)

    def clear_settings(self):
        """清除设置内容并显示占位符"""
        self._clear_layout(self.settings_content_layout)
        self.add_placeholder()
        self.selected_resource_name = None
        self.selected_settings_name = None
        self.task_container = None

    def _clear_layout(self, layout):
        """安全地清除布局中的所有小部件"""
        if layout is None: return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())