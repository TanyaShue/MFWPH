from enum import Enum
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve,
                            QRect, QPoint, Signal, QObject, Property, QParallelAnimationGroup,
                            QEvent, QSequentialAnimationGroup, QPointF, QRectF, QElapsedTimer)
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QApplication, QGraphicsOpacityEffect, QPushButton,
                               QGraphicsDropShadowEffect, QGraphicsBlurEffect)
from PySide6.QtGui import (QPainter, QBrush, QColor, QPen, QLinearGradient,
                           QRadialGradient, QPainterPath, QFont, QFontDatabase)
import sys
import math


class NotificationLevel(Enum):
    """通知级别枚举 - 优化的配色方案"""
    INFO = ("info",
            QColor(59, 130, 246),  # 主色 - 更鲜艳的蓝色
            QColor(96, 165, 250),  # 浅色
            QColor(37, 99, 235),  # 深色
            QColor(219, 234, 254),  # 背景色
            "ℹ")  # 更优雅的图标
    SUCCESS = ("success",
               QColor(34, 197, 94),  # 主色 - 更鲜艳的绿色
               QColor(74, 222, 128),  # 浅色
               QColor(22, 163, 74),  # 深色
               QColor(220, 252, 231),  # 背景色
               "✓")
    WARNING = ("warning",
               QColor(245, 158, 11),  # 主色 - 更温暖的橙色
               QColor(251, 191, 36),  # 浅色
               QColor(217, 119, 6),  # 深色
               QColor(254, 243, 199),  # 背景色
               "⚠")
    ERROR = ("error",
             QColor(239, 68, 68),  # 主色 - 更鲜艳的红色
             QColor(248, 113, 113),  # 浅色
             QColor(220, 38, 38),  # 深色
             QColor(254, 226, 226),  # 背景色
             "✕")


class AnimatedProgressBar(QWidget):
    """自定义动画进度条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 100.0
        self._wave_offset = 0
        self.setFixedHeight(6)

        # 波浪动画定时器
        self.wave_timer = QTimer(self)
        self.wave_timer.timeout.connect(self.update_wave)
        self.wave_timer.start(30)

    def update_wave(self):
        """更新波浪动画"""
        self._wave_offset = (self._wave_offset + 2) % 100
        self.update()

    @Property(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value
        self.update()

    def paintEvent(self, event):
        """绘制进度条"""
        if self._progress <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 3, 3)

        # 进度条宽度
        progress_width = int(self.width() * self._progress / 100)

        if progress_width > 0:
            # 创建渐变
            gradient = QLinearGradient(0, 0, progress_width, 0)

            # 获取父级的颜色
            parent_widget = self.parent()
            if hasattr(parent_widget, 'main_color'):
                color1 = parent_widget.light_color
                color2 = parent_widget.main_color
                color3 = parent_widget.dark_color
            else:
                color1 = QColor(96, 165, 250)
                color2 = QColor(59, 130, 246)
                color3 = QColor(37, 99, 235)

            # 添加波浪效果
            for i in range(5):
                pos = (i / 4.0 + self._wave_offset / 100.0) % 1.0
                gradient.setColorAt(pos, color1 if i % 2 == 0 else color2)

            painter.setBrush(QBrush(gradient))

            # 绘制进度条
            path = QPainterPath()
            path.addRoundedRect(0, 0, progress_width, self.height(), 3, 3)
            painter.drawPath(path)

            # 移除光泽效果


class NotificationWidget(QWidget):
    """优化的通知弹窗组件"""

    closed = Signal(object)

    def __init__(self, title, message, level=NotificationLevel.INFO, duration=5000, parent=None):
        super().__init__(parent)
        self.level = level
        self.duration = duration
        self._is_closing = False
        self._is_hovered = False
        self._opacity = 0.0

        # 设置窗口属性
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # 设置尺寸
        self.setFixedWidth(320)

        # 初始化UI
        self.setupUI(title, message)

        # 调整大小
        self.adjustSize()

        # 初始化动画
        self.setupAnimations()

        # 初始化定时器相关变量
        self.timer = None
        self.progress_timer = None
        self.elapsed_timer = None
        self._time_offset = 0
        self._paused_elapsed = 0

        # 启动定时器
        if self.duration > 0:
            self.startTimer()

    def setupUI(self, title, message):
        """设置UI - 优化版"""
        _, main_color, light_color, dark_color, bg_color, icon = self.level.value

        self.main_color = main_color
        self.light_color = light_color
        self.dark_color = dark_color
        self.bg_color = bg_color

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        # 内容容器
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content")

        # 内容布局
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(16, 16, 16, 12)
        content_layout.setSpacing(0)

        # 顶部区域
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        # 图标容器
        icon_container = QWidget()
        icon_container.setFixedSize(42, 42)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                color: {main_color.name()};
                font-size: 20px;
                font-weight: bold;
                background: {bg_color.name()};
                border-radius: 21px;
                padding: 10px;
            }}
        """)
        icon_layout.addWidget(self.icon_label)

        top_layout.addWidget(icon_container)

        # 文本区域
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        # 标题
        if title:
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet("""
                QLabel {
                    color: #1f2937;
                    font-size: 14px;
                    font-weight: 600;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
            """)
            text_layout.addWidget(self.title_label)

        # 消息
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #6b7280;
                font-size: 13px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                line-height: 1.5;
            }
        """)
        text_layout.addWidget(self.message_label)

        top_layout.addLayout(text_layout, 1)

        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: #9ca3af;
                font-size: 18px;
                font-weight: normal;
                border-radius: 12px;
            }}
            QPushButton:hover {{
                background: {QColor(0, 0, 0, 20).name()};
                color: #6b7280;
            }}
        """)
        top_layout.addWidget(self.close_btn, 0, Qt.AlignTop)

        content_layout.addLayout(top_layout)

        # 进度条
        if self.duration > 0:
            content_layout.addSpacing(8)
            self.progress_bar = AnimatedProgressBar()
            content_layout.addWidget(self.progress_bar)

        main_layout.addWidget(self.content_widget)

        # 设置样式 - 移除阴影效果
        self.setStyleSheet(f"""
            QWidget#content {{
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 16px;
            }}
        """)

    def paintEvent(self, event):
        """自定义绘制 - 移除阴影"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 设置整体透明度
        painter.setOpacity(self._opacity)

        # 不再绘制阴影

    @Property(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.update()

    def setupAnimations(self):
        """设置动画效果 - 移除阴影相关动画"""
        # 淡入动画组
        self.show_animation = QParallelAnimationGroup()

        # 透明度动画
        fade_in = QPropertyAnimation(self, b"opacity")
        fade_in.setDuration(600)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.show_animation.addAnimation(fade_in)

        # 滑入动画
        self.slide_in_animation = QPropertyAnimation(self, b"pos")
        self.slide_in_animation.setDuration(800)
        self.slide_in_animation.setEasingCurve(QEasingCurve.OutExpo)
        self.show_animation.addAnimation(self.slide_in_animation)

        # 淡出动画
        self.fade_out_animation = QPropertyAnimation(self, b"opacity")
        self.fade_out_animation.setDuration(400)
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out_animation.finished.connect(self.onFadeOutFinished)

    def startTimer(self):
        """启动定时器"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.close)
        self.timer.setSingleShot(True)
        self.timer.start(self.duration)

        # 进度更新定时器
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.updateProgress)
        self.progress_timer.start(16)  # 60fps

        # 使用 QElapsedTimer 来跟踪时间
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self._time_offset = 0

    def updateProgress(self):
        """更新进度"""
        if not self._is_closing and hasattr(self, 'progress_bar') and self.elapsed_timer:
            elapsed = self.elapsed_timer.elapsed() + self._time_offset
            progress = max(0, 100 - (elapsed * 100 / self.duration))
            self.progress_bar.progress = progress

            if progress <= 0 and self.progress_timer:
                self.progress_timer.stop()

    def showAt(self, x, y):
        """在指定位置显示"""
        # 获取起始位置
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isWindow() and widget.isVisible() and not isinstance(widget, NotificationWidget):
                if widget.windowTitle():
                    parent_window = widget
                    break

        if parent_window:
            start_x = parent_window.geometry().right() + 50
        else:
            screen = QApplication.primaryScreen()
            if screen:
                start_x = screen.geometry().right() + 50
            else:
                start_x = 1920 + 50

        self.move(start_x, y)
        self.show()

        # 设置滑入动画
        self.slide_in_animation.setStartValue(QPoint(start_x, y))
        self.slide_in_animation.setEndValue(QPoint(x, y))

        # 启动显示动画
        self.show_animation.start()

    def close(self):
        """关闭通知"""
        if self._is_closing:
            return

        self._is_closing = True

        # 停止定时器
        if self.timer and self.timer.isActive():
            self.timer.stop()

        if self.progress_timer and self.progress_timer.isActive():
            self.progress_timer.stop()

        if hasattr(self, 'progress_bar') and hasattr(self.progress_bar, 'wave_timer'):
            if self.progress_bar.wave_timer and self.progress_bar.wave_timer.isActive():
                self.progress_bar.wave_timer.stop()

        # 启动淡出动画
        self.fade_out_animation.start()

    def onFadeOutFinished(self):
        """淡出完成"""
        self.closed.emit(self)
        super().close()

    def enterEvent(self, event):
        """鼠标进入"""
        self._is_hovered = True

        # 暂停计时器
        if self.timer and self.timer.isActive():
            self.timer.stop()
            # 记录剩余时间
            if self.elapsed_timer:
                self._paused_elapsed = self.elapsed_timer.elapsed() + self._time_offset

        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开"""
        self._is_hovered = False

        # 恢复计时器
        if self.timer and not self._is_closing and self.duration > 0:
            if hasattr(self, '_paused_elapsed'):
                remaining = self.duration - self._paused_elapsed
                if remaining > 0:
                    self.timer.start(remaining)
                    # 更新时间偏移
                    self._time_offset = self._paused_elapsed
                    if self.elapsed_timer:
                        self.elapsed_timer.restart()

        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """鼠标点击"""
        if event.button() == Qt.LeftButton and event.pos().x() < self.width() - 30:
            # 点击反馈动画
            feedback = QSequentialAnimationGroup()

            # 缩放效果
            scale_down = QPropertyAnimation(self, b"opacity")
            scale_down.setDuration(100)
            scale_down.setStartValue(self._opacity)
            scale_down.setEndValue(self._opacity * 0.8)
            scale_down.setEasingCurve(QEasingCurve.OutCubic)
            feedback.addAnimation(scale_down)

            # 恢复
            scale_up = QPropertyAnimation(self, b"opacity")
            scale_up.setDuration(100)
            scale_up.setStartValue(self._opacity * 0.8)
            scale_up.setEndValue(self._opacity)
            scale_up.setEasingCurve(QEasingCurve.OutCubic)
            feedback.addAnimation(scale_up)

            feedback.finished.connect(self.close)
            feedback.start()


class NotificationManager(QObject):
    """优化的通知管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            super().__init__()
            self._initialized = True
            self.notifications = []
            self.max_visible = 5
            self.spacing = 15
            self.margin = 20
            self.reference_window = None
            self._event_filter_installed = False

    def set_reference_window(self, window):
        """设置参考窗口"""
        if self.reference_window and self._event_filter_installed:
            self.reference_window.removeEventFilter(self)

        self.reference_window = window

        if window:
            window.installEventFilter(self)
            self._event_filter_installed = True

    def eventFilter(self, obj, event):
        """事件过滤器"""
        if obj == self.reference_window:
            if event.type() == QEvent.Move:
                self.repositionNotifications()
            elif event.type() == QEvent.Close:
                self.closeAllNotifications()
        return super().eventFilter(obj, event)

    def closeAllNotifications(self):
        """关闭所有通知"""
        for notification in self.notifications.copy():
            try:
                notification.close()
            except RuntimeError:
                pass
        self.notifications.clear()

    def get_position_reference(self):
        """获取定位参考"""
        if self.reference_window and self.reference_window.isVisible():
            return self.reference_window.geometry()

        for widget in QApplication.topLevelWidgets():
            if widget.isWindow() and widget.isVisible() and not isinstance(widget, NotificationWidget):
                if widget.windowTitle():
                    return widget.geometry()

        screen = QApplication.primaryScreen()
        if screen:
            return screen.availableGeometry()
        return QRect(0, 0, 1920, 1080)

    def show(self, message, title="", level=NotificationLevel.INFO, duration=5000):
        """显示通知"""
        # 如果超过最大数量，关闭最旧的
        if len(self.notifications) >= self.max_visible:
            oldest = self.notifications[0]
            oldest.close()

        notification = NotificationWidget(title, message, level, duration)
        notification.closed.connect(self.onNotificationClosed)

        self.notifications.append(notification)
        self.positionNotification(notification, len(self.notifications) - 1)

    def positionNotification(self, notification, index):
        """定位通知"""
        rect = self.get_position_reference()

        # 计算位置
        x = rect.right() - notification.width() - self.margin
        y = rect.bottom() - self.margin

        # 从底部向上堆叠
        for i in range(index + 1):
            if i < len(self.notifications):
                y -= self.notifications[i].height() + self.spacing

        # 确保不超出屏幕
        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            x = min(x, screen_rect.right() - notification.width() - self.margin)
            y = max(y, screen_rect.top() + self.margin)

        notification.showAt(x, y)

    def onNotificationClosed(self, notification):
        """通知关闭处理"""
        try:
            self.notifications.remove(notification)
        except ValueError:
            return

        # 添加延迟，让关闭动画完成后再重新定位
        QTimer.singleShot(100, self.repositionNotifications)

    def repositionNotifications(self):
        """重新定位所有通知"""
        rect = self.get_position_reference()

        # 清理无效通知
        valid_notifications = []
        for notification in self.notifications:
            try:
                if notification and not notification._is_closing:
                    valid_notifications.append(notification)
            except RuntimeError:
                continue

        self.notifications = valid_notifications

        # 重新定位
        y = rect.bottom() - self.margin

        for i, notification in enumerate(self.notifications):
            try:
                y -= notification.height() + self.spacing
                x = rect.right() - notification.width() - self.margin

                # 确保不超出屏幕
                screen = QApplication.primaryScreen()
                if screen:
                    screen_rect = screen.availableGeometry()
                    x = min(x, screen_rect.right() - notification.width() - self.margin)
                    y = max(y, screen_rect.top() + self.margin)

                # 创建平滑的移动动画
                if hasattr(notification, '_move_animation'):
                    if notification._move_animation and notification._move_animation.state() == QPropertyAnimation.Running:
                        notification._move_animation.stop()

                move_animation = QPropertyAnimation(notification, b"pos")
                move_animation.setDuration(500)
                move_animation.setEasingCurve(QEasingCurve.InOutCubic)
                move_animation.setStartValue(notification.pos())
                move_animation.setEndValue(QPoint(x, y))
                move_animation.start()

                notification._move_animation = move_animation

            except RuntimeError:
                continue

    # 便捷方法
    def show_info(self, message, title="信息", duration=3000):
        self.show(message, title, NotificationLevel.INFO, duration)

    def show_success(self, message, title="成功", duration=3000):
        self.show(message, title, NotificationLevel.SUCCESS, duration)

    def show_warning(self, message, title="警告", duration=4000):
        self.show(message, title, NotificationLevel.WARNING, duration)

    def show_error(self, message, title="错误", duration=5000):
        self.show(message, title, NotificationLevel.ERROR, duration)


# 创建全局通知管理器实例
notification_manager = NotificationManager()

