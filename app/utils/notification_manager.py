from enum import Enum
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve,
                            QRect, QPoint, Signal, QObject, Property, QParallelAnimationGroup,
                            QEvent, QSequentialAnimationGroup, QPointF, QRectF, QElapsedTimer)
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QApplication, QPushButton)
from PySide6.QtGui import (QPainter, QBrush, QColor, QPen, QLinearGradient,
                           QPainterPath)


class NotificationLevel(Enum):
    """通知级别枚举 - 优化的配色方案"""
    INFO = ("info",
            QColor(59, 130, 246), QColor(96, 165, 250), QColor(37, 99, 235), QColor(219, 234, 254), "ℹ")
    SUCCESS = ("success",
               QColor(34, 197, 94), QColor(74, 222, 128), QColor(22, 163, 74), QColor(220, 252, 231), "✓")
    WARNING = ("warning",
               QColor(245, 158, 11), QColor(251, 191, 36), QColor(217, 119, 6), QColor(254, 243, 199), "⚠")
    ERROR = ("error",
             QColor(239, 68, 68), QColor(248, 113, 113), QColor(220, 38, 38), QColor(254, 226, 226), "✕")
    PROGRESS = ("progress",
                QColor(139, 92, 246), QColor(167, 139, 250), QColor(109, 40, 217), QColor(237, 233, 254), "◐")


class AnimatedProgressBar(QWidget):
    """自定义动画进度条（从右往左）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 100.0
        self._wave_offset = 0
        self.setFixedHeight(6)
        self.wave_timer = QTimer(self)
        self.wave_timer.timeout.connect(self.update_wave)
        self.wave_timer.start(30)

    def update_wave(self):
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
        if self._progress <= 0: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 3, 3)
        progress_width = int(self.width() * self._progress / 100)
        if progress_width > 0:
            gradient = QLinearGradient(0, 0, progress_width, 0)
            parent_widget = self.parent()
            color1 = getattr(parent_widget, 'light_color', QColor(96, 165, 250))
            color2 = getattr(parent_widget, 'main_color', QColor(59, 130, 246))
            for i in range(5):
                pos = (i / 4.0 + self._wave_offset / 100.0) % 1.0
                gradient.setColorAt(pos, color1 if i % 2 == 0 else color2)
            painter.setBrush(QBrush(gradient))
            path = QPainterPath()
            path.addRoundedRect(0, 0, progress_width, self.height(), 3, 3)
            painter.drawPath(path)


class ProgressBar(QWidget):
    """进度条组件（从左往右）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._wave_offset = 0
        self.setFixedHeight(6)
        self.wave_timer = QTimer(self)
        self.wave_timer.timeout.connect(self.update_wave)
        self.wave_timer.start(30)

    def update_wave(self):
        self._wave_offset = (self._wave_offset + 2) % 100
        self.update()

    @Property(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 30)))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 3, 3)
        progress_width = int(self.width() * self._progress)
        if progress_width > 0:
            gradient = QLinearGradient(0, 0, progress_width, 0)
            parent_widget = self.parent()
            color1 = getattr(parent_widget, 'light_color', QColor(167, 139, 250))
            color2 = getattr(parent_widget, 'main_color', QColor(139, 92, 246))
            for i in range(5):
                pos = (i / 4.0 + self._wave_offset / 100.0) % 1.0
                gradient.setColorAt(pos, color1 if i % 2 == 0 else color2)
            painter.setBrush(QBrush(gradient))
            path = QPainterPath()
            path.addRoundedRect(0, 0, progress_width, self.height(), 3, 3)
            painter.drawPath(path)


class NotificationWidget(QWidget):
    """优化的通知弹窗组件"""
    closed = Signal(object)

    def __init__(self, title, message, level=NotificationLevel.INFO, duration=5000, always_on_top=False, parent=None):
        super().__init__(parent)
        self.level = level
        self.duration = duration
        self._is_closing = False
        self._is_hovered = False
        self._opacity = 1.0  # (新增) 初始化内部opacity变量

        flags = (Qt.Window | Qt.FramelessWindowHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        if always_on_top: flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self.setFixedWidth(320)
        self.setupUI(title, message)
        self.adjustSize()
        self.setupAnimations()

        self.timer = None
        self.progress_timer = None
        self.elapsed_timer = None
        self._time_offset = 0
        self._paused_elapsed = 0

        if self.duration > 0: self.startTimer()

    # (新增) 使用 QProperty 和 setWindowOpacity 控制整体透明度
    @Property(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.setWindowOpacity(value)

    def _setup_base_ui(self, title, message):
        _, main_color, light_color, dark_color, bg_color, icon = self.level.value
        self.main_color, self.light_color, self.dark_color, self.bg_color = main_color, light_color, dark_color, bg_color
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content")
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(16, 16, 16, 12)
        content_layout.setSpacing(0)
        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)
        self.icon_label = QLabel(icon)
        self.icon_label.setFixedSize(42, 42)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet(
            f"color:{main_color.name()};font-size:20px;font-weight:bold;background:{bg_color.name()};border-radius:21px;")
        top_layout.addWidget(self.icon_label)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        if title:
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet("color:#1f2937;font-size:14px;font-weight:600;")
            text_layout.addWidget(self.title_label)
        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color:#6b7280;font-size:13px;line-height:1.5;")
        text_layout.addWidget(self.message_label)
        top_layout.addLayout(text_layout, 1)
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;color:#9ca3af;font-size:18px;border-radius:12px;}}QPushButton:hover{{background:{QColor(0, 0, 0, 20).name()};color:#6b7280;}}")
        top_layout.addWidget(self.close_btn, 0, Qt.AlignTop)
        content_layout.addLayout(top_layout)
        main_layout.addWidget(self.content_widget)
        self.setStyleSheet(
            "QWidget#content{background:rgba(255,255,255,0.95);border:1px solid rgba(0,0,0,0.08);border-radius:16px;}")
        return content_layout

    def setupUI(self, title, message):
        content_layout = self._setup_base_ui(title, message)
        if self.duration > 0:
            content_layout.addSpacing(8)
            self.progress_bar = AnimatedProgressBar()
            content_layout.addWidget(self.progress_bar)

    def setupAnimations(self):
        self.show_animation = QParallelAnimationGroup()

        # (优化) 动画目标改回 self, 作用于新的 opacity 属性
        fade_in = QPropertyAnimation(self, b"opacity")
        fade_in.setDuration(600)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self.show_animation.addAnimation(fade_in)

        self.slide_in_animation = QPropertyAnimation(self, b"pos")
        self.slide_in_animation.setDuration(800)
        self.slide_in_animation.setEasingCurve(QEasingCurve.OutExpo)
        self.show_animation.addAnimation(self.slide_in_animation)

        # (优化) 动画目标改回 self
        self.fade_out_animation = QPropertyAnimation(self, b"opacity")
        self.fade_out_animation.setDuration(400)
        # (优化) 不再设置StartValue, 动画会从当前透明度平滑过渡
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out_animation.finished.connect(self.onFadeOutFinished)

    def startTimer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.close)
        self.timer.setSingleShot(True)
        self.timer.start(self.duration)
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.updateProgress)
        self.progress_timer.start(16)
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self._time_offset = 0

    def updateProgress(self):
        if not self._is_closing and hasattr(self, 'progress_bar') and self.elapsed_timer:
            elapsed = self.elapsed_timer.elapsed() + self._time_offset
            progress = max(0, 100 - (elapsed * 100 / self.duration))
            self.progress_bar.progress = progress
            if progress <= 0 and self.progress_timer: self.progress_timer.stop()

    def showWithAnimation(self, start_pos, end_pos):
        self.move(start_pos)
        self.show()
        self.slide_in_animation.setStartValue(start_pos)
        self.slide_in_animation.setEndValue(end_pos)
        self.show_animation.start()

    def close(self):
        if self._is_closing: return
        self._is_closing = True
        if self.timer and self.timer.isActive(): self.timer.stop()
        if self.progress_timer and self.progress_timer.isActive(): self.progress_timer.stop()
        if hasattr(self, 'progress_bar') and hasattr(self.progress_bar, 'wave_timer'):
            if self.progress_bar.wave_timer and self.progress_bar.wave_timer.isActive(): self.progress_bar.wave_timer.stop()
        self.fade_out_animation.start()

    def onFadeOutFinished(self):
        self.closed.emit(self)
        super().close()

    def enterEvent(self, event):
        self._is_hovered = True
        if self.timer and self.timer.isActive():
            self.timer.stop()
            if self.elapsed_timer: self._paused_elapsed = self.elapsed_timer.elapsed() + self._time_offset
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        if self.timer and not self._is_closing and self.duration > 0:
            if hasattr(self, '_paused_elapsed'):
                remaining = self.duration - self._paused_elapsed
                if remaining > 0:
                    self.timer.start(remaining)
                    self._time_offset = self._paused_elapsed
                    if self.elapsed_timer: self.elapsed_timer.restart()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.close_btn.geometry().contains(event.pos()):
            self.close()
            event.accept()
        else:
            event.ignore()


class ProgressNotificationWidget(NotificationWidget):
    """进度通知组件"""

    def __init__(self, title, message, always_on_top=False, parent=None):
        super().__init__(title, message, NotificationLevel.PROGRESS, 0, always_on_top, parent)
        self._progress = 0.0
        self._auto_close_timer = None

    def setupUI(self, title, message):
        content_layout = self._setup_base_ui(title, message)
        content_layout.addSpacing(8)
        self.progress_bar = ProgressBar()
        content_layout.addWidget(self.progress_bar)

    def updateProgress(self, progress, message=None):
        self._progress = max(0.0, min(1.0, progress))
        if hasattr(self, 'progress_bar'): self.progress_bar.progress = self._progress
        if message is not None and hasattr(self, 'message_label'): self.message_label.setText(message)
        if self._progress >= 1.0:
            if self._auto_close_timer is None:
                self._auto_close_timer = QTimer(self)
                self._auto_close_timer.setSingleShot(True)
                self._auto_close_timer.timeout.connect(self.close)
                self._auto_close_timer.start(1000)
        elif self._auto_close_timer is not None:
            self._auto_close_timer.stop()
            self._auto_close_timer = None

    def startTimer(self):
        pass


class NotificationManager(QObject):
    """优化的通知管理器"""
    _instance = None

    def __new__(cls):
        if cls._instance is None: cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            super().__init__()
            self._initialized = True
            self.notifications = []
            self.progress_notifications = {}
            self.max_visible = 5
            self.spacing = 15
            self.margin = 20
            self.reference_window = None

    def set_reference_window(self, window):
        if self.reference_window:
            try:
                self.reference_window.removeEventFilter(self)
            except RuntimeError:
                pass
        self.reference_window = window
        if window: window.installEventFilter(self)

    def _update_notification_visibility(self):
        if not self.reference_window: return
        is_minimized = self.reference_window.isMinimized()
        for notification in self.notifications:
            try:
                if is_minimized:
                    notification.hide()
                else:
                    notification.show()
            except RuntimeError:
                continue

    def eventFilter(self, obj, event):
        if obj == self.reference_window:
            event_type = event.type()
            if event_type in [QEvent.Move, QEvent.Resize]:
                self.repositionNotifications()
            elif event_type == QEvent.Close:
                self.closeAllNotifications()
            elif event_type == QEvent.WindowActivate:
                self._bring_notifications_to_front()
            elif event_type == QEvent.WindowStateChange:
                self._update_notification_visibility()
        return super().eventFilter(obj, event)

    def _bring_notifications_to_front(self):
        for notification in self.notifications:
            try:
                notification.raise_()
            except RuntimeError:
                continue

    def closeAllNotifications(self):
        for notification in self.notifications.copy():
            try:
                notification.close()
            except RuntimeError:
                pass
        self.notifications.clear()
        self.progress_notifications.clear()

    def get_position_reference(self):
        if self.reference_window and self.reference_window.isVisible():
            return self.reference_window.geometry()
        for widget in QApplication.topLevelWidgets():
            if widget.isWindow() and widget.isVisible() and not isinstance(widget, NotificationWidget):
                if widget.windowTitle(): return widget.geometry()
        screen = QApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    def _create_notification(self, widget_class, *args, **kwargs):
        if len(self.notifications) >= self.max_visible:
            self.notifications[0].close()
        is_always_on_top = bool(
            self.reference_window and (self.reference_window.windowFlags() & Qt.WindowStaysOnTopHint))
        notification = widget_class(*args, **kwargs, always_on_top=is_always_on_top)
        self.notifications.append(notification)
        return notification

    def show(self, message, title="", level=NotificationLevel.INFO, duration=5000):
        notification = self._create_notification(NotificationWidget, title, message, level, duration)
        notification.closed.connect(self.onNotificationClosed)
        self.positionNotification(notification, len(self.notifications) - 1)
        if self.reference_window and self.reference_window.isActiveWindow():
            notification.raise_()

    def show_progress(self, notification_id, message, title="进度", initial_progress=0.0):
        if notification_id in self.progress_notifications:
            notification = self.progress_notifications[notification_id]
            if hasattr(notification, 'updateProgress'):
                notification.updateProgress(initial_progress, message)
            return notification
        notification = self._create_notification(ProgressNotificationWidget, title, message)
        notification.closed.connect(lambda: self.onProgressNotificationClosed(notification_id))
        notification.updateProgress(initial_progress)
        self.progress_notifications[notification_id] = notification
        self.positionNotification(notification, len(self.notifications) - 1)
        if self.reference_window and self.reference_window.isActiveWindow():
            notification.raise_()
        return notification

    def update_progress(self, notification_id, progress, message=None):
        if notification_id in self.progress_notifications:
            self.progress_notifications[notification_id].updateProgress(progress, message)

    def close_progress(self, notification_id):
        if notification_id in self.progress_notifications:
            self.progress_notifications[notification_id].close()

    def onProgressNotificationClosed(self, notification_id):
        if notification_id in self.progress_notifications:
            notification = self.progress_notifications.pop(notification_id)
            self.onNotificationClosed(notification)

    def positionNotification(self, notification, index):
        rect = self.get_position_reference()
        x_end = rect.right() - notification.width() - self.margin
        y_pos = rect.bottom() - self.margin
        for i in range(index + 1):
            if i < len(self.notifications):
                y_pos -= self.notifications[i].height() + self.spacing
        x_start = rect.right()
        notification.showWithAnimation(QPoint(x_start, y_pos), QPoint(x_end, y_pos))

    def onNotificationClosed(self, notification):
        try:
            self.notifications.remove(notification)
        except ValueError:
            return
        QTimer.singleShot(100, self.repositionNotifications)

    def repositionNotifications(self):
        rect = self.get_position_reference()

        # (优化) 在重新定位时，只处理那些没有正在关闭的通知
        valid_notifications = [n for n in self.notifications if n and not n._is_closing]

        y = rect.bottom() - self.margin
        for i, notification in enumerate(valid_notifications):
            try:
                y -= notification.height() + self.spacing
                x = rect.right() - notification.width() - self.margin

                # 如果通知当前位置和目标位置不同，则启动移动画
                target_pos = QPoint(x, y)
                if notification.pos() != target_pos:
                    # 停止任何正在进行的移动动画，避免冲突
                    if hasattr(notification,
                               '_move_animation') and notification._move_animation.state() == QPropertyAnimation.Running:
                        notification._move_animation.stop()

                    move_animation = QPropertyAnimation(notification, b"pos")
                    move_animation.setDuration(500)
                    move_animation.setEasingCurve(QEasingCurve.InOutCubic)
                    move_animation.setEndValue(target_pos)
                    move_animation.start()
                    notification._move_animation = move_animation
            except RuntimeError:
                continue

    def show_info(self, message, title="信息", duration=3000):
        self.show(message, title, NotificationLevel.INFO, duration)

    def show_success(self, message, title="成功", duration=3000):
        self.show(message, title, NotificationLevel.SUCCESS, duration)

    def show_warning(self, message, title="警告", duration=4000):
        self.show(message, title, NotificationLevel.WARNING, duration)

    def show_error(self, message, title="错误", duration=5000):
        self.show(message, title, NotificationLevel.ERROR, duration)


notification_manager = NotificationManager()