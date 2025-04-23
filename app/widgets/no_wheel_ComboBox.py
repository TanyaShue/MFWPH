from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox


class NoWheelComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # 忽略鼠标中键滚动事件
        event.ignore()
