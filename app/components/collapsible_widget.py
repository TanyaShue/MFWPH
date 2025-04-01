from PySide6.QtCore import (
    QPropertyAnimation, QEasingCurve, Qt, QMimeData,
    QParallelAnimationGroup, QPoint, Property, Signal, Slot
)
from PySide6.QtGui import QFont, QDrag, QPixmap, QMouseEvent, QCursor, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QPushButton,
    QFrame, QSizePolicy, QApplication, QGraphicsOpacityEffect
)


class CollapsibleWidget(QWidget):
    """可折叠组件：优化了展开/收缩动画，添加了过渡效果和拖动功能"""

    def __init__(self, title="折叠组件", parent=None):
        super().__init__(parent)
        self.is_expanded = False
        self.title_text = title
        # 初始化旋转角度属性
        self._rotation_angle = 0
        self._init_ui()
        self._setup_animations()  # Call setup animations
    def _init_ui(self):
        # 主布局：标题栏 + 内容区
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # ========== 标题栏 ==========
        self.header_widget = QWidget()
        self.header_widget.setObjectName("collapsibleHeader")
        self.header_widget.setFixedHeight(40)  # 设置固定高度
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(5, 0, 5, 0)  # 减小垂直边距
        self.header_layout.setSpacing(5)  # 减小间距

        # 复选框
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(False)

        # 标题标签 - 让它靠近复选框
        self.title_label = QLabel(self.title_text)
        self.title_label.setFont(QFont("Arial", 10, QFont.Bold))

        # 拖动句柄 - 设置为占据所有剩余空间
        self.drag_handle = QLabel("≡")  # 使用 ≡ 作为拖动图标
        self.drag_handle.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.drag_handle.setObjectName("drag_handle")
        self.drag_handle.setCursor(QCursor(Qt.OpenHandCursor))
        self.drag_handle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 左对齐并垂直居中
        self.drag_handle.mousePressEvent = self.drag_handle_mouse_press
        self.drag_handle.mouseMoveEvent = self.drag_handle_mouse_move

        # 展开/折叠按钮 - 靠近右侧
        self.toggle_button = QPushButton()
        self.toggle_button.setIcon(QIcon("assets/icons/dropdown.svg"))
        self.toggle_button.setFixedSize(24, 24)
        self.toggle_button.setObjectName("toggleButton")

        # 布局添加 - 确保标题靠近复选框，按钮靠近右侧
        self.header_layout.addWidget(self.checkbox)
        self.header_layout.addWidget(self.title_label, 0, Qt.AlignLeft)  # 左对齐
        self.header_layout.addWidget(self.drag_handle)  # 这将占据所有剩余空间
        self.header_layout.addWidget(self.toggle_button, 0, Qt.AlignRight)  # 右对齐

        # ========== 内容区 ==========
        self.content_widget = QWidget()
        self.content_widget.setObjectName("collapsibleContent")
        # 添加透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self.content_widget)
        self.opacity_effect.setOpacity(0.0)
        self.content_widget.setGraphicsEffect(self.opacity_effect)

        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(25, 5, 10, 5)
        self.content_layout.setSpacing(5)

        # 初始时内容区"收起"
        self.content_widget.setMaximumHeight(0)

        # 将标题栏和内容区加入主布局
        self.main_layout.addWidget(self.header_widget)
        self.main_layout.addWidget(self.content_widget)

        # 连接点击信号
        self.toggle_button.clicked.connect(self.toggle_content)
        self.title_label.mousePressEvent = lambda event: self.toggle_content()

    def _setup_animations(self):
        # Prepare all animations, setting initial start/end values
        self.height_animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.height_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.height_animation.setDuration(300)

        self.height_animation.setStartValue(0)
        self.height_animation.setEndValue(100) # Placeholder, will be updated

        self.opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.opacity_animation.setDuration(250)
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)

        self.rotate_animation = QPropertyAnimation(self, b"rotation_angle")
        self.rotate_animation.setEasingCurve(QEasingCurve.OutBack)
        self.rotate_animation.setDuration(300)
        self.rotate_animation.setStartValue(0)
        self.rotate_animation.setEndValue(180)

        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.height_animation)
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.addAnimation(self.rotate_animation)

        self.animation_group.finished.connect(self._on_animation_finish)

    # 属性访问器，用于旋转箭头
    def _get_rotation_angle(self):
        return self._rotation_angle

    def _set_rotation_angle(self, angle):
        self._rotation_angle = angle


    rotation_angle = Property(float, _get_rotation_angle, _set_rotation_angle)

    def toggle_content(self):
        content_margins = self.content_layout.contentsMargins()
        content_height = self.content_layout.sizeHint().height() + content_margins.top() + content_margins.bottom()
        if content_height < content_margins.top() + content_margins.bottom() + self.content_layout.spacing():
             content_height = content_margins.top() + content_margins.bottom() + self.content_layout.spacing()


        if self.is_expanded:
            self.animation_group.setDirection(QPropertyAnimation.Backward)
        else:
            self.content_widget.setVisible(True) # Make visible BEFORE animating height
            self.height_animation.setEndValue(content_height)
            self.animation_group.setDirection(QPropertyAnimation.Forward)

        # Toggle state
        self.is_expanded = not self.is_expanded

        if self.animation_group.state() == QPropertyAnimation.Running:
            self.animation_group.stop()
        self.animation_group.start()

    @Slot() # Explicitly mark as a slot
    def _on_animation_finish(self):
        # This slot is called when the animation (either forward or backward) finishes
        if not self.is_expanded: # If state is collapsed
            self.content_widget.setVisible(False) # Hide AFTER collapse animation

    def drag_handle_mouse_press(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
            # Change cursor to grabbing
            self.drag_handle.setCursor(QCursor(Qt.ClosedHandCursor))
        event.accept()

    def drag_handle_mouse_move(self, event: QMouseEvent):
        if not (event.buttons() & Qt.LeftButton):
            # Reset cursor if mouse button released elsewhere
            self.drag_handle.setCursor(QCursor(Qt.OpenHandCursor))
            return
        # If distance threshold not met
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        # Start drag
        drag = QDrag(self)
        mimeData = QMimeData()
        mimeData.setText(f"{self.title_text}_{id(self)}")
        drag.setMimeData(mimeData)

        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, self.header_widget.height() // 2)) # Center hotspot on header

        drag.exec(Qt.MoveAction)
        self.drag_handle.setCursor(QCursor(Qt.OpenHandCursor))


class DraggableContainer(QWidget):
    drag=Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(5) # Reduce spacing slightly if needed
        self.layout.addStretch(1)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setAcceptDrops(True)

        self.drop_indicator = QFrame(self)
        self.drop_indicator.setObjectName("drop_indicator")
        self.drop_indicator.setFixedHeight(3) # Make slightly thicker
        self.drop_indicator.hide()
    def dragMoveEvent(self, event):
        event.acceptProposedAction()
        pos = event.pos()
        insert_index = -1 # Use -1 to indicate insertion before the stretch

        widget_count = self.layout.count() -1 # Exclude stretch
        for i in range(widget_count):
            item = self.layout.itemAt(i)
            widget = item.widget()
            if not widget: # Should not happen with current setup, but good practice
                continue

            geo = widget.geometry()
            drop_pos_relative = pos.y() - geo.y()

            if drop_pos_relative < geo.height() / 2:
                insert_index = i
                break
            else:
                 insert_index = i + 1 # Tentatively set to insert after current widget
        indicator_y = 0
        if insert_index == 0:
            # Insert at the very beginning
             indicator_y = self.layout.contentsMargins().top() # Position at the top margin
        elif insert_index > 0 and insert_index < widget_count:
            # Insert between two widgets
            target_widget = self.layout.itemAt(insert_index).widget()
            if target_widget:
                 indicator_y = target_widget.geometry().top() - (self.layout.spacing() // 2)
        else: # insert_index is widget_count or -1 (meaning insert at the end, before stretch)
             if widget_count > 0:
                 last_widget = self.layout.itemAt(widget_count - 1).widget()
                 if last_widget:
                     indicator_y = last_widget.geometry().bottom() + (self.layout.spacing() // 2)
             else: # No widgets exist yet
                 indicator_y = self.layout.contentsMargins().top()


        # Adjust indicator geometry, ensuring it's within bounds
        indicator_height = self.drop_indicator.height()
        indicator_y = max(0, min(indicator_y - indicator_height // 2, self.height() - indicator_height))

        self.drop_indicator.setGeometry(0, indicator_y, self.width(), indicator_height)
        self.drop_indicator.raise_()
        self.drop_indicator.show()


    def dropEvent(self, event):
        self.drop_indicator.hide()
        mime_text = event.mimeData().text()
        try:
            # Extract the ID part
            dragged_id_str = mime_text.split('_')[-1]
            widget_id = int(dragged_id_str)
        except (IndexError, ValueError):
            event.ignore()
            return

        dragged_widget = self.findChild(QWidget, f"taskItem_{widget_id}", Qt.FindDirectChildrenOnly) # More robust find
        if not dragged_widget:
             for i in range(self.layout.count() - 1): # Exclude stretch
                 widget = self.layout.itemAt(i).widget()
                 if widget and id(widget) == widget_id:
                     dragged_widget = widget
                     break

        if dragged_widget:
            pos = event.pos()
            insert_index = -1 # Default to end (before stretch)

            widget_count = self.layout.count() - 1 # Exclude stretch
            for i in range(widget_count):
                widget = self.layout.itemAt(i).widget()
                if not widget: continue
                geo = widget.geometry()
                if pos.y() < geo.y() + geo.height() / 2:
                    insert_index = i
                    break
            else: # If loop completes without break, insert at the end (before stretch)
                 insert_index = widget_count

            current_index = self.layout.indexOf(dragged_widget)
            if current_index != insert_index and not (current_index == insert_index - 1 and insert_index == widget_count):
                item = self.layout.takeAt(current_index)
                if current_index < insert_index:
                     insert_index -= 1
                self.layout.insertItem(insert_index, item)


            event.acceptProposedAction()
            current_order = self.get_widget_order()
            self.drag.emit([widget.title_text for widget in current_order]) # Emit signal AFTER drop
        else:
            event.ignore()


    def get_widget_order(self):
        widget_list = []
        for i in range(self.layout.count() - 1): # Exclude stretch item
            item = self.layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, CollapsibleWidget):
                widget_list.append(widget)
        return widget_list

    def addWidget(self, widget):
        if isinstance(widget, CollapsibleWidget):
             widget.setObjectName(f"taskItem_{id(widget)}") # Set object name for lookup
        self.layout.insertWidget(self.layout.count() - 1, widget)
    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.drop_indicator.show()
        else:
            event.ignore()


    def dragLeaveEvent(self, event):
        self.drop_indicator.hide()
        event.accept()
