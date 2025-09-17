from PySide6.QtCore import (Qt, QRect)
from PySide6.QtGui import QFont, QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget)


class CircularProgressBar(QWidget):
    """圆形进度条控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0
        self.maximum = 100
        self.setFixedSize(32, 32)

    def setValue(self, value):
        self.value = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 定义绘制区域
        rect = QRect(3, 3, 26, 26)

        # 背景圆
        pen = QPen()
        pen.setWidth(3)
        pen.setColor(QColor(229, 231, 235))  # #e5e7eb
        painter.setPen(pen)
        painter.drawEllipse(rect)

        # 进度圆弧
        if self.value > 0:
            pen.setColor(QColor(59, 130, 246))  # #3b82f6
            painter.setPen(pen)

            start_angle = 90 * 16  # 从顶部开始
            span_angle = -int(360 * self.value / self.maximum) * 16
            painter.drawArc(rect, start_angle, span_angle)

        # 中心文字
        painter.setPen(QPen(QColor(75, 85, 99)))  # #4b5563
        painter.setFont(QFont("Arial", 9))
        painter.drawText(rect, Qt.AlignCenter, f"{self.value}%")
