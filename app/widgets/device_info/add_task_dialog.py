# --- START OF FILE app/widgets/add_task_dialog.py ---

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QScrollArea,
    QWidget, QPushButton, QLabel, QFrame
)

from app.models.config.global_config import global_config


class SelectableTaskWidget(QFrame):
    """
    一个可点击、可选择的任务行控件。
    点击整个控件会切换其选中状态。
    """
    # 信号：当选中状态改变时发出，参数为 (task_name, is_selected)
    selection_changed = Signal(str, bool)

    def __init__(self, task_name, parent=None):
        super().__init__(parent)
        self.task_name = task_name
        self.is_selected = False

        self.setObjectName("selectableTaskWidget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(40)
        self.setCursor(Qt.PointingHandCursor)

        self.init_ui()
        self._update_style()

    def init_ui(self):
        """初始化控件UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        # 任务名称标签
        self.name_label = QLabel(self.task_name)
        layout.addWidget(self.name_label)
        layout.addStretch()

        # 选中状态的图标指示器
        self.check_icon = QLabel()
        self.check_icon.setPixmap(QIcon("assets/icons/check.svg").pixmap(16, 16))
        self.check_icon.setVisible(self.is_selected)
        layout.addWidget(self.check_icon)

    def mousePressEvent(self, event):
        """覆盖鼠标点击事件以切换选中状态"""
        if event.button() == Qt.LeftButton:
            self.is_selected = not self.is_selected
            self._update_style()
            self.selection_changed.emit(self.task_name, self.is_selected)
        super().mousePressEvent(event)

    def _update_style(self):
        """根据选中状态更新控件的样式和图标可见性"""
        self.check_icon.setVisible(self.is_selected)
        # 使用动态属性来帮助QSS样式表进行选择
        self.setProperty("selected", self.is_selected)
        self.style().polish(self)


class AddTaskDialog(QDialog):
    """一个用于向资源重复添加任务的对话框。"""

    def __init__(self, resource_name, device_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"为 {resource_name} 添加任务")
        self.setMinimumWidth(400)
        self.setMinimumHeight(500)
        self.resource_name = resource_name
        self.device_config = device_config
        # 使用集合来高效地跟踪选中的任务名称
        self.selected_tasks = set()
        # 存储所有任务控件的引用，用于全选功能
        self.task_widgets = []
        # 存储所有任务控件的引用，用于全选功能
        self.task_widgets = []

        self.init_ui()
        self.populate_tasks()

    def init_ui(self):
        """初始化对话框UI"""
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)

        info_label = QLabel(f"点击任务行进行选择 (可多选):")
        self.layout.addWidget(info_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("subtleScrollArea")

        self.scroll_content = QWidget()
        self.task_layout = QVBoxLayout(self.scroll_content)
        self.task_layout.setAlignment(Qt.AlignTop)
        self.task_layout.setContentsMargins(10, 10, 10, 10)
        self.task_layout.setSpacing(5)  # 减小行间距

        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        # 创建底部按钮区域布局
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        # 全选按钮
        self.select_all_button = QPushButton("全选")
        self.select_all_button.setObjectName("primaryButton")  # 默认使用主要按钮样式，和确定按钮一样
        self.select_all_button.clicked.connect(self._on_select_all_clicked)
        bottom_layout.addWidget(self.select_all_button)

        # 反馈标签，显示选中数量
        self.feedback_label = QLabel("已选择 0 个任务")
        self.feedback_label.setObjectName("feedbackText")
        self.feedback_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.feedback_label, 1)  # 设置伸缩因子为1，使其占据中间空间

        # 创建标准按钮盒
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # --- 核心改动：获取并设置按钮样式 ---
        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        cancel_button = self.button_box.button(QDialogButtonBox.Cancel)

        # 为按钮设置 objectName 以便应用 QSS 样式
        if ok_button:
            ok_button.setObjectName("primaryButton")  # 设置为主要按钮样式
            ok_button.setText("确定添加")  # 可以自定义文本
        if cancel_button:
            cancel_button.setObjectName("secondaryButton")  # 设置为次要按钮样式
            cancel_button.setText("取消")

        bottom_layout.addWidget(self.button_box)
        self.layout.addLayout(bottom_layout)

    def populate_tasks(self):
        """
        使用自定义的 SelectableTaskWidget 填充所有可用的任务。
        """
        full_resource_config = global_config.get_resource_config(self.resource_name)
        if not full_resource_config or not full_resource_config.resource_tasks:
            self.task_layout.addWidget(QLabel("未找到该资源的可配置任务。"))
            return

        for task in full_resource_config.resource_tasks:
            task_widget = SelectableTaskWidget(task.task_name)
            # 连接子控件的信号到对话框的槽函数
            task_widget.selection_changed.connect(self._on_task_selection_changed)
            self.task_layout.addWidget(task_widget)
            # 保存任务控件的引用
            self.task_widgets.append(task_widget)
            # 保存任务控件的引用
            self.task_widgets.append(task_widget)

    def _on_task_selection_changed(self, task_name: str, is_selected: bool):
        """
        当一个任务行的选中状态改变时，更新我们的跟踪集合和UI反馈。
        """
        if is_selected:
            self.selected_tasks.add(task_name)
        else:
            self.selected_tasks.discard(task_name)  # discard 不会在元素不存在时报错

        count = len(self.selected_tasks)
        self.feedback_label.setText(f"已选择 {count} 个任务")

        # 当没有选择任何任务时，禁用“确定”按钮
        ok_button = self.button_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setEnabled(count > 0)

    def _on_select_all_clicked(self):
        """
        处理全选按钮点击事件。
        根据按钮当前文本决定操作：全选或取消全选。
        """
        current_text = self.select_all_button.text()

        if current_text == "取消全选":
            # 当前是全选状态，需要取消全选
            for task_widget in self.task_widgets:
                task_widget.is_selected = False
                task_widget._update_style()
            # 清空选中集合
            self.selected_tasks.clear()
            # 更新UI反馈
            self.feedback_label.setText("已选择 0 个任务")
            # 禁用确定按钮
            ok_button = self.button_box.button(QDialogButtonBox.Ok)
            if ok_button:
                ok_button.setEnabled(False)
            # 更新按钮文本和样式
            self.select_all_button.setText("全选")
            self.select_all_button.setObjectName("primaryButton")
        else:
            # 当前不是全选状态，需要全选
            for task_widget in self.task_widgets:
                task_widget.is_selected = True
                task_widget._update_style()
            # 添加所有任务到选中集合
            self.selected_tasks = set(task_widget.task_name for task_widget in self.task_widgets)
            # 更新UI反馈
            count = len(self.selected_tasks)
            self.feedback_label.setText(f"已选择 {count} 个任务")
            # 启用确定按钮
            ok_button = self.button_box.button(QDialogButtonBox.Ok)
            if ok_button:
                ok_button.setEnabled(True)
            # 更新按钮文本和样式
            self.select_all_button.setText("取消全选")
            self.select_all_button.setObjectName("secondaryButton")

        # 刷新样式
        self.select_all_button.style().polish(self.select_all_button)

    def get_selected_tasks(self) -> list[str]:
        """
        返回用户在此对话框中最终选择的任务列表。
        """
        # 将集合转换为列表返回
        return list(self.selected_tasks)