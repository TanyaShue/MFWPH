from enum import Enum
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve,
                            QRect, QPoint, Signal, QObject, Property, QParallelAnimationGroup,
                            QEvent, QSequentialAnimationGroup, QRectF)
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout,
                               QApplication, QGraphicsOpacityEffect, QPushButton,
                               QGraphicsDropShadowEffect, QGraphicsBlurEffect)
from PySide6.QtGui import QPainter, QBrush, QColor, QPen, QFont, QPalette, QLinearGradient, QRadialGradient, \
    QPainterPath
import sys
import weakref


class NotificationLevel(Enum):
    """通知级别枚举"""
    INFO = ("info",
            QColor(94, 129, 244),  # 主色
            QColor(129, 155, 248),  # 浅色
            QColor(59, 91, 219),  # 深色
            "●")  # 点图标
    SUCCESS = ("success",
               QColor(52, 211, 153),  # 主色
               QColor(110, 231, 183),  # 浅色
               QColor(16, 185, 129),  # 深色
               "✓")
    WARNING = ("warning",
               QColor(251, 191, 36),  # 主色
               QColor(252, 211, 77),  # 浅色
               QColor(245, 158, 11),  # 深色
               "!")
    ERROR = ("error",
             QColor(248, 113, 113),  # 主色
             QColor(252, 165, 165),  # 浅色
             QColor(239, 68, 68),  # 深色
             "×")




class NotificationWidget(QWidget):
    """单个通知弹窗组件"""

    closed = Signal(object)  # 传递自身引用

    def __init__(self, title, message, level=NotificationLevel.INFO, duration=2000, parent=None):
        super().__init__(parent)
        self.level = level
        self.duration = duration
        self._is_closing = False
        self._is_hovered = False
        self._progress = 100
        self._glow_opacity = 0

        # 设置窗口属性
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        # 设置尺寸
        self.setFixedSize(260, 74)  # 稍微增加高度以容纳进度条

        # 初始化UI
        self.setupUI(title, message)

        # 添加阴影效果
        self.setupShadow()

        # 初始化动画
        self.setupAnimations()

        # 启动定时器
        self.startTimer()

        # 启动呼吸灯效果
        self.startGlowAnimation()

    def setupUI(self, title, message):
        """设置UI"""
        # 获取级别信息
        _, main_color, light_color, dark_color, icon = self.level.value

        # 添加调试输出
        if self.level == NotificationLevel.WARNING:
            print(f"WARNING颜色值:")
            print(f"  主色: {main_color.name()}, Alpha: {main_color.alpha()}")
            print(f"  浅色: {light_color.name()}, Alpha: {light_color.alpha()}")
            print(f"  深色: {dark_color.name()}, Alpha: {dark_color.alpha()}")

        # Helper function to convert QColor to rgba() string
        def to_rgba_string(qcolor):
            return f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {qcolor.alpha()})"

        # Convert colors to rgba strings for stylesheet
        light_rgba_str = to_rgba_string(light_color)
        main_rgba_str = to_rgba_string(main_color)
        dark_rgba_str = to_rgba_string(dark_color)
        lighter_main_rgba_str = to_rgba_string(main_color.lighter(120)) # For icon gradient

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 内容区域 - 设置整体背景和圆角
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content")
        self.content_widget.setStyleSheet("""
            QWidget#content {
                background-color: rgba(255, 255, 255, 0.95);
                border-radius: 12px;
            }
        """)

        # 创建内容布局
        content_layout = QHBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 左侧渐变装饰条 - 作为内部元素
        self.gradient_bar = QWidget()
        self.gradient_bar.setFixedWidth(6)  # 加宽装饰条
        # Use rgba strings here
        self.gradient_bar.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {light_rgba_str},
                    stop:0.5 {main_rgba_str},
                    stop:1 {dark_rgba_str});
                border-top-left-radius: 12px;
                border-bottom-left-radius: 12px;
            }}
        """)
        content_layout.addWidget(self.gradient_bar)

        # 主内容区域
        main_content = QWidget()
        main_content.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)

        # 主内容布局
        main_h_layout = QHBoxLayout(main_content)
        main_h_layout.setContentsMargins(10, 10, 12, 10)
        main_h_layout.setSpacing(10)

        # 图标
        icon_widget = QWidget()
        icon_widget.setFixedSize(36, 36)
        # Use rgba strings here
        icon_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {lighter_main_rgba_str},
                    stop:1 {main_rgba_str});
                border-radius: 10px;
            }}
        """)

        icon_layout = QVBoxLayout(icon_widget)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_layout.addWidget(icon_label)

        main_h_layout.addWidget(icon_widget)

        # 文本区域
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_layout.setContentsMargins(0, 2, 0, 2)
        text_layout.setSpacing(3)

        # 标题
        if title:
            self.title_label = QLabel(title)
            self.title_label.setStyleSheet("""
                QLabel {
                    color: #1a202c;
                    font-size: 13px;
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
                color: #4a5568;
                font-size: 11px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                line-height: 1.4;
            }
        """)
        text_layout.addWidget(self.message_label)
        text_layout.addStretch()

        main_h_layout.addWidget(text_widget, 1)
        content_layout.addWidget(main_content)

        main_layout.addWidget(self.content_widget)

        # 保存颜色
        self.main_color = main_color
        self.light_color = light_color
        self.dark_color = dark_color

    def paintEvent(self, event):
        """自定义绘制"""
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 首先绘制一个完整的圆角矩形作为裁剪区域，确保内容不会超出圆角
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.content_widget.rect()), 12, 12)
        painter.setClipPath(path)

        # 绘制发光效果
        if self._glow_opacity > 0:
            glow_color = QColor(self.main_color)
            glow_color.setAlpha(int(30 * self._glow_opacity))

            # 外发光
            for i in range(3):
                pen = QPen(glow_color, 2 - i * 0.5)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(self.rect().adjusted(i, i, -i, -i), 12, 12)

        # 重置裁剪
        painter.setClipping(False)

        # 绘制进度条
        if self.duration > 0 and not self._is_closing:
            # 进度条背景 - 更深的颜色
            painter.setPen(Qt.NoPen)
            bg_color = QColor(0, 0, 0, 80)  # 增加不透明度
            painter.setBrush(QBrush(bg_color))
            painter.drawRoundedRect(12, 65, 236, 4, 2, 2)

            # 进度条前景
            if self._progress > 0:
                # 渐变进度条
                progress_width = int(236 * self._progress / 100)
                gradient = QLinearGradient(12, 67, 12 + progress_width, 67)
                gradient.setColorAt(0, self.light_color)
                gradient.setColorAt(0.5, self.main_color)
                gradient.setColorAt(1, self.dark_color)
                painter.setBrush(QBrush(gradient))
                painter.drawRoundedRect(12, 65, progress_width, 4, 2, 2)

    def setupShadow(self):
        """设置阴影效果"""
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.content_widget.setGraphicsEffect(shadow)

    def setupAnimations(self):
        """设置动画效果"""
        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0)

        # 淡入动画
        self.fade_in_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_animation.setDuration(500)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.OutCubic)

        # 滑入动画 - 带弹性效果
        self.slide_in_animation = QPropertyAnimation(self, b"pos")
        self.slide_in_animation.setDuration(600)
        self.slide_in_animation.setEasingCurve(QEasingCurve.OutBack)

        # 组合动画
        self.show_animation = QParallelAnimationGroup()
        self.show_animation.addAnimation(self.fade_in_animation)
        self.show_animation.addAnimation(self.slide_in_animation)

        # 淡出动画
        self.fade_out_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out_animation.setDuration(300)
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.finished.connect(self.onFadeOutFinished)

    def startGlowAnimation(self):
        """启动呼吸灯动画"""
        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self.updateGlow)
        self.glow_timer.start(50)
        self._glow_increasing = True

    def updateGlow(self):
        """更新发光效果"""
        if self._is_hovered:
            # 悬停时保持最亮
            self._glow_opacity = 1.0
        else:
            # 呼吸效果
            if self._glow_increasing:
                self._glow_opacity += 0.03
                if self._glow_opacity >= 0.6:
                    self._glow_increasing = False
            else:
                self._glow_opacity -= 0.03
                if self._glow_opacity <= 0:
                    self._glow_increasing = True

        self.update()

    def startTimer(self):
        """启动定时器"""
        if self.duration > 0:
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.close)
            self.timer.setSingleShot(True)
            self.timer.start(self.duration)

            # 进度条动画
            self.progress_timer = QTimer(self)
            self.progress_timer.timeout.connect(self.updateProgress)
            self.progress_timer.start(20)

    def updateProgress(self):
        """更新进度条"""
        if self.duration > 0 and not self._is_closing:
            self._progress -= (100 * 20 / self.duration)
            if self._progress < 0:
                self._progress = 0
            self.update()

    def showAt(self, x, y):
        """在指定位置显示通知"""
        # 获取参考窗口位置
        parent_window = None
        for widget in QApplication.topLevelWidgets():
            if widget.isWindow() and widget.isVisible() and not isinstance(widget, NotificationWidget):
                if widget.windowTitle():
                    parent_window = widget
                    break

        if parent_window:
            start_x = parent_window.geometry().right() + 10
        else:
            screen = QApplication.primaryScreen()
            if screen:
                start_x = screen.geometry().right() + 10
            else:
                start_x = 1920 + 10

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
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()
        if hasattr(self, 'glow_timer'):
            self.glow_timer.stop()

        # 启动淡出动画
        self.fade_out_animation.start()

    def onFadeOutFinished(self):
        """淡出完成后的处理"""
        self.closed.emit(self)
        super().close()

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            # 添加点击动画效果
            click_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
            click_animation.setDuration(100)
            click_animation.setStartValue(1.0)
            click_animation.setEndValue(0.8)

            # 创建序列动画
            seq = QSequentialAnimationGroup()
            seq.addAnimation(click_animation)

            # 反向动画
            reverse_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
            reverse_animation.setDuration(100)
            reverse_animation.setStartValue(0.8)
            reverse_animation.setEndValue(1.0)
            seq.addAnimation(reverse_animation)

            seq.finished.connect(self.close)
            seq.start()

    def enterEvent(self, event):
        """鼠标进入事件"""
        self._is_hovered = True

        # 停止定时器
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'progress_timer'):
            self.progress_timer.stop()

        # 增强阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(35)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 50))
        self.content_widget.setGraphicsEffect(shadow)

        # 轻微放大效果
        self.hover_scale = QPropertyAnimation(self, b"geometry")
        self.hover_scale.setDuration(200)
        self.hover_scale.setEasingCurve(QEasingCurve.OutCubic)
        current_geo = self.geometry()
        expanded_geo = current_geo.adjusted(-2, -2, 2, 2)
        self.hover_scale.setStartValue(current_geo)
        self.hover_scale.setEndValue(expanded_geo)
        self.hover_scale.start()

        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self._is_hovered = False

        # 重新启动定时器
        if hasattr(self, 'timer') and not self._is_closing:
            remaining_time = int(self.duration * self._progress / 100)
            if remaining_time > 0:
                self.timer.start(remaining_time)
                if hasattr(self, 'progress_timer'):
                    self.progress_timer.start(20)

        # 恢复阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.content_widget.setGraphicsEffect(shadow)

        # 恢复大小
        if hasattr(self, 'hover_scale'):
            self.hover_scale.stop()
            restore_scale = QPropertyAnimation(self, b"geometry")
            restore_scale.setDuration(200)
            restore_scale.setEasingCurve(QEasingCurve.OutCubic)
            current_geo = self.geometry()
            original_geo = current_geo.adjusted(2, 2, -2, -2)
            restore_scale.setStartValue(current_geo)
            restore_scale.setEndValue(original_geo)
            restore_scale.start()

        super().leaveEvent(event)


class NotificationManager(QObject):
    """通知管理器"""

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
            self.spacing = 10
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
        notifications_copy = self.notifications.copy()
        for notification in notifications_copy:
            try:
                notification.close()
            except RuntimeError:
                pass
        self.notifications.clear()

    def get_position_reference(self):
        """获取定位参考区域"""
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
        notification = NotificationWidget(title, message, level, duration)
        notification.closed.connect(self.onNotificationClosed)

        if len(self.notifications) >= self.max_visible:
            oldest = self.notifications[0]
            oldest.close()
            self.notifications.pop(0)

        self.notifications.append(notification)
        self.repositionNotifications()
        self.positionNotification(notification, len(self.notifications) - 1)

    def positionNotification(self, notification, index):
        """定位并显示通知"""
        rect = self.get_position_reference()

        x = rect.right() - notification.width() - self.margin
        y = rect.bottom() - (notification.height() + self.spacing) * (index + 1) - self.margin

        screen = QApplication.primaryScreen()
        if screen:
            screen_rect = screen.availableGeometry()
            x = min(x, screen_rect.right() - notification.width() - self.margin)
            y = max(y, screen_rect.top() + self.margin)

        notification.showAt(x, y)

    def onNotificationClosed(self, notification):
        """通知关闭时的处理"""
        try:
            self.notifications.remove(notification)
        except ValueError:
            return
        self.repositionNotifications()

    def repositionNotifications(self):
        """重新定位所有通知"""
        rect = self.get_position_reference()

        valid_notifications = []
        for notification in self.notifications:
            try:
                if notification and not notification._is_closing:
                    valid_notifications.append(notification)
            except RuntimeError:
                continue

        self.notifications = valid_notifications

        for i, notification in enumerate(self.notifications):
            try:
                x = rect.right() - notification.width() - self.margin
                y = rect.bottom() - (notification.height() + self.spacing) * (i + 1) - self.margin

                screen = QApplication.primaryScreen()
                if screen:
                    screen_rect = screen.availableGeometry()
                    x = min(x, screen_rect.right() - notification.width() - self.margin)
                    y = max(y, screen_rect.top() + self.margin)

                if hasattr(notification, '_move_animation') and notification._move_animation:
                    if notification._move_animation.state() == QPropertyAnimation.Running:
                        notification._move_animation.stop()

                move_animation = QPropertyAnimation(notification, b"pos")
                move_animation.setDuration(400)
                move_animation.setEasingCurve(QEasingCurve.OutBack)
                move_animation.setStartValue(notification.pos())
                move_animation.setEndValue(QPoint(x, y))
                move_animation.start()

                notification._move_animation = move_animation
            except RuntimeError:
                continue

    # 便捷方法
    def show_info(self, message, title="信息", duration=2000):
        self.show(message, title, NotificationLevel.INFO, duration)

    def show_success(self, message, title="成功", duration=2000):
        self.show(message, title, NotificationLevel.SUCCESS, duration)

    def show_warning(self, message, title="警告", duration=2000):
        self.show(message, title, NotificationLevel.WARNING, duration)

    def show_error(self, message, title="错误", duration=2000):
        self.show(message, title, NotificationLevel.ERROR, duration)


# 创建全局通知管理器实例
notification_manager = NotificationManager()