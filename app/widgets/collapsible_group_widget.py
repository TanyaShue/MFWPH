# collapsible_group_widget.py
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, Property, QPointF
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QCheckBox, QLabel, QPushButton, QSizePolicy
)
from PySide6.QtGui import QIcon, QPainter, QPixmap, QPolygonF


class CollapsibleArrowButton(QPushButton):
    """自定义的折叠箭头按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCheckable(True)
        self.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.05);
                border-radius: 2px;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 设置画笔
        painter.setPen(Qt.black)
        painter.setBrush(Qt.black)

        # 绘制箭头
        if self.isChecked():
            # 向下箭头 (展开状态)
            points = [
                QPointF(4, 6),
                QPointF(8, 10),
                QPointF(12, 6)
            ]
        else:
            # 向右箭头 (折叠状态)
            points = [
                QPointF(6, 4),
                QPointF(10, 8),
                QPointF(6, 12)
            ]

        polygon = QPolygonF(points)
        painter.drawPolygon(polygon)


class CollapsibleGroupWidget(QFrame):
    """可折叠的设置组组件"""

    # 信号：组启用状态改变
    group_enabled_changed = Signal(bool)
    # 信号：子选项值改变
    sub_option_changed = Signal(str, object)  # option_name, value

    def __init__(self, group_name: str, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.is_expanded = False
        self.sub_widgets = {}
        self._animation_finished_handler = None  # 存储动画完成处理函数

        self.setObjectName("collapsibleGroup")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame#collapsibleGroup {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f8f8f8;
                margin: 2px;
            }
            QFrame#collapsibleGroup:hover {
                border-color: #999;
            }
        """)

        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 头部区域
        self.header_widget = QWidget()
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: transparent;
                min-height: 36px;
            }
        """)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        # 折叠箭头
        self.arrow_button = CollapsibleArrowButton()
        self.arrow_button.toggled.connect(self.toggle_content)
        header_layout.addWidget(self.arrow_button)

        # 组复选框
        self.group_checkbox = QCheckBox(self.group_name)
        self.group_checkbox.setStyleSheet("""
            QCheckBox {
                font-weight: bold;
                font-size: 13px;
            }
        """)
        self.group_checkbox.stateChanged.connect(self._on_group_state_changed)
        header_layout.addWidget(self.group_checkbox)

        # 描述标签（可选）
        self.description_label = QLabel()
        self.description_label.setStyleSheet("""
            QLabel {
                color: #666;
                font-size: 11px;
            }
        """)
        self.description_label.hide()
        header_layout.addWidget(self.description_label)

        header_layout.addStretch()

        self.main_layout.addWidget(self.header_widget)

        # 内容区域
        self.content_widget = QWidget()
        self.content_widget.setObjectName("groupContent")
        self.content_widget.setStyleSheet("""
            QWidget#groupContent {
                background-color: #fff;
                border-top: 1px solid #e0e0e0;
            }
        """)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(24, 8, 8, 8)
        self.content_layout.setSpacing(8)

        # 初始化动画
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

        # 初始状态为折叠
        self.content_widget.setMaximumHeight(0)
        self.content_widget.hide()

        self.main_layout.addWidget(self.content_widget)

    def set_description(self, description: str):
        """设置组描述"""
        if description:
            self.description_label.setText(f"({description})")
            self.description_label.show()
        else:
            self.description_label.hide()

    def add_sub_widget(self, option_name: str, widget: QWidget, actual_control: QWidget = None):
        """添加子选项控件

        Args:
            option_name: 选项名称
            widget: 要添加的容器控件
            actual_control: 实际的控制控件（如 QCheckBox, QLineEdit 等）
        """
        if actual_control:
            self.sub_widgets[option_name] = actual_control
        else:
            self.sub_widgets[option_name] = widget
        self.content_layout.addWidget(widget)

    def toggle_content(self, checked: bool):
        """切换内容区域的显示/隐藏"""
        # 如果动画正在运行，先停止它
        if self.animation.state() == QPropertyAnimation.Running:
            self.animation.stop()

        # 断开之前可能存在的信号连接
        if self._animation_finished_handler:
            try:
                self.animation.finished.disconnect()
            except:
                pass
            self._animation_finished_handler = None

        if checked:
            # 展开
            self.content_widget.show()
            # 先设置一个很大的最大高度来获取实际需要的高度
            self.content_widget.setMaximumHeight(16777215)  # Qt默认的最大值
            actual_height = self.content_widget.sizeHint().height()
            # 设置动画起始和结束值
            self.content_widget.setMaximumHeight(0)
            self.animation.setStartValue(0)
            self.animation.setEndValue(actual_height)

            # 定义展开完成后的处理
            def on_expand_finished():
                # 动画完成后，移除高度限制
                self.content_widget.setMaximumHeight(16777215)

            self._animation_finished_handler = on_expand_finished
            self.animation.finished.connect(self._animation_finished_handler)
            self.animation.start()
            self.is_expanded = True
        else:
            # 折叠
            current_height = self.content_widget.height()
            self.animation.setStartValue(current_height)
            self.animation.setEndValue(0)

            # 定义折叠完成后的处理
            def on_collapse_finished():
                self.content_widget.hide()
                self.content_widget.setMaximumHeight(0)

            self._animation_finished_handler = on_collapse_finished
            self.animation.finished.connect(self._animation_finished_handler)
            self.animation.start()
            self.is_expanded = False

    def _on_group_state_changed(self, state):
        """处理组复选框状态改变"""
        # 直接使用 isChecked() 方法获取状态，更可靠
        is_enabled = self.group_checkbox.isChecked()

        # 【重要修改】移除设置子控件启用状态的逻辑
        # 不再根据组的启用状态来禁用/启用子控件
        # for widget in self.sub_widgets.values():
        #     widget.setEnabled(is_enabled)

        # 发送信号
        self.group_enabled_changed.emit(is_enabled)

    def set_group_enabled(self, enabled: bool):
        """设置组的启用状态"""
        self.group_checkbox.setChecked(enabled)

    def is_group_enabled(self) -> bool:
        """获取组的启用状态"""
        return self.group_checkbox.isChecked()

    def get_sub_widgets(self) -> dict:
        """获取所有子控件的引用"""
        return self.sub_widgets

    def get_sub_values(self) -> dict:
        """获取所有子选项的值"""
        values = {}
        for option_name, widget in self.sub_widgets.items():
            if hasattr(widget, 'currentData'):
                # ComboBox
                values[option_name] = widget.currentData()
            elif hasattr(widget, 'isChecked'):
                # CheckBox
                values[option_name] = widget.isChecked()
            elif hasattr(widget, 'text'):
                # LineEdit
                values[option_name] = widget.text()
        return values