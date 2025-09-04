# --- START OF FILE app/dialogs/add_task_dialog.py ---

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QDialogButtonBox, QScrollArea,
    QWidget, QPushButton, QLabel
)

from app.models.config.global_config import global_config


class AddTaskDialog(QDialog):
    """一个用于向资源重复添加任务的对话框。"""

    def __init__(self, resource_name, device_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"为 {resource_name} 添加任务")
        self.setMinimumWidth(350)
        self.resource_name = resource_name
        self.device_config = device_config
        # 这个列表现在可以包含重复的任务名称
        self.newly_selected_tasks = []

        self.init_ui()
        self.populate_tasks()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(10)

        info_label = QLabel(f"为资源 '{self.resource_name}' 选择要添加的任务:\n(可以重复添加同一个任务)")
        self.layout.addWidget(info_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("subtleScrollArea")

        self.scroll_content = QWidget()
        self.task_layout = QVBoxLayout(self.scroll_content)
        self.task_layout.setAlignment(Qt.AlignTop)
        self.task_layout.setContentsMargins(10, 10, 10, 10)
        self.task_layout.setSpacing(8)

        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        # 添加一个标签来反馈用户的添加操作
        self.feedback_label = QLabel("尚未添加任何任务")
        self.feedback_label.setObjectName("feedbackText")
        self.feedback_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.feedback_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def populate_tasks(self):
        """
        填充所有可用的任务, 每个任务后面都有一个添加按钮.
        """
        full_resource_config = global_config.get_resource_config(self.resource_name)
        if not full_resource_config or not full_resource_config.resource_tasks:
            self.task_layout.addWidget(QLabel("未找到该资源的可配置任务。"))
            return

        for task in full_resource_config.resource_tasks:
            task_name = task.task_name

            # 为每一行创建一个容器
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)

            # 任务名称
            name_label = QLabel(task_name)

            # 添加按钮
            add_button = QPushButton("添加")
            add_button.setIcon(QIcon("assets/icons/add.svg"))
            add_button.setObjectName("primaryButton")
            add_button.setFixedWidth(80)

            # 连接按钮点击事件, 使用 lambda 传递任务名称
            add_button.clicked.connect(lambda checked=False, t=task_name: self._on_add_task_clicked(t))

            row_layout.addWidget(name_label)
            row_layout.addStretch()
            row_layout.addWidget(add_button)

            self.task_layout.addWidget(row_widget)

    def _on_add_task_clicked(self, task_name):
        """
        当用户点击某个任务的'添加'按钮时调用.
        """
        self.newly_selected_tasks.append(task_name)
        self.feedback_label.setText(f"已添加任务: {task_name}\n总共待添加 {len(self.newly_selected_tasks)} 个任务。")

    def get_selected_tasks(self):
        """
        返回用户在此对话框中选择要添加的任务列表.
        """
        return self.newly_selected_tasks

# --- END OF FILE app/dialogs/add_task_dialog.py ---