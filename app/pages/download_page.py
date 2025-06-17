"""
美化后的资源下载页面，采用左右分栏布局
"""
from pathlib import Path

import requests
from PySide6.QtCore import QTimer, QCoreApplication, Qt, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QIcon, QFont, QPalette, QPainter, QColor, QBrush, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QPushButton,
                               QHBoxLayout, QProgressBar, QMessageBox, QSizePolicy,
                               QDialog, QListWidget, QListWidgetItem, QStackedWidget,
                               QScrollArea, QTextEdit, QGraphicsOpacityEffect, QGraphicsDropShadowEffect)

from app.models.config.global_config import global_config
from app.utils.update_check import UpdateChecker, UpdateDownloader
from app.utils.update_install import UpdateInstaller
from app.widgets.add_resource_dialog import AddResourceDialog
from app.utils.notification_manager import notification_manager


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


class ResourceListItem(QWidget):
    """自定义资源列表项"""
    clicked = Signal()
    check_update_clicked = Signal()

    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.is_downloading = False
        self.is_selected = False
        self.update_info = None  # 存储更新信息
        self._init_ui()

    def _init_ui(self):
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 左侧图标容器
        icon_container = QWidget()
        icon_container.setFixedSize(44, 44)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignCenter)

        # 资源图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(44, 44)
        self.icon_label.setScaledContents(True)
        self._set_icon(f"assets/resource/{self.resource.resource_update_service_id}/{self.resource.resource_icon}")

        # 图标样式
        self.icon_label.setStyleSheet("""
            QLabel {
                background-color: #f3f4f6;
                border-radius: 10px;
                padding: 8px;
            }
        """)

        icon_layout.addWidget(self.icon_label)
        layout.addWidget(icon_container)

        # 中间信息区域
        info_container = QWidget()
        info_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 2, 0, 2)
        info_layout.setSpacing(2)

        # 资源名称
        self.name_label = QLabel(self.resource.resource_name)
        self.name_label.setObjectName("resourceItemName")
        self.name_label.setStyleSheet("""
            #resourceItemName {
                color: #1f2937;
                font-size: 14px;
                font-weight: 500;
            }
        """)

        # 版本和作者行
        info_row = QHBoxLayout()
        info_row.setSpacing(12)

        # 版本标签
        self.version_label = QLabel(f"{self.resource.resource_version}")
        self.version_label.setObjectName("resourceItemVersion")
        self.version_label.setStyleSheet("color: #6b7280; font-size: 12px;")

        # 作者标签
        if self.resource.resource_author:
            info_row.addWidget(self.version_label)
        else:
            info_row.addWidget(self.version_label)

        info_row.addStretch()

        info_layout.addWidget(self.name_label)
        info_layout.addLayout(info_row)

        layout.addWidget(info_container, 1)

        # 右侧操作区域（使用堆叠布局）
        self.action_stack = QStackedWidget()
        self.action_stack.setFixedWidth(100)

        # 页面0：检查更新按钮
        check_container = QWidget()
        check_layout = QHBoxLayout(check_container)
        check_layout.setContentsMargins(0, 0, 0, 0)

        self.check_button = QPushButton("检查更新")
        self.check_button.setObjectName("resourceCheckButton")
        self.check_button.setFixedSize(88, 32)
        self.check_button.setCursor(Qt.PointingHandCursor)
        self.check_button.clicked.connect(self._on_check_clicked)
        self.check_button.setStyleSheet("""
            #resourceCheckButton {
                background-color: transparent;
                color: #3b82f6;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }
            #resourceCheckButton:hover {
                background-color: #eff6ff;
                border-color: #2563eb;
            }
            #resourceCheckButton:pressed {
                background-color: #dbeafe;
            }
            #resourceCheckButton:disabled {
                color: #9ca3af;
                border-color: #e5e7eb;
                background-color: transparent;
            }
        """)
        check_layout.addWidget(self.check_button)

        # 页面1：更新可用按钮
        update_container = QWidget()
        update_layout = QHBoxLayout(update_container)
        update_layout.setContentsMargins(0, 0, 0, 0)

        self.update_button = QPushButton("立即更新")
        self.update_button.setObjectName("resourceUpdateButton")
        self.update_button.setFixedSize(88, 32)
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.setStyleSheet("""
            #resourceUpdateButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }
            #resourceUpdateButton:hover {
                background-color: #059669;
            }
            #resourceUpdateButton:pressed {
                background-color: #047857;
            }
        """)
        update_layout.addWidget(self.update_button)

        # 页面2：下载进度
        progress_container = QWidget()
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)

        self.progress_bar = CircularProgressBar()
        self.speed_label = QLabel("0 MB/s")
        self.speed_label.setObjectName("downloadSpeed")
        self.speed_label.setStyleSheet("color: #6b7280; font-size: 11px;")

        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.speed_label)
        progress_layout.addStretch()

        # 页面3：状态信息
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel()
        self.status_label.setObjectName("resourceStatus")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFixedWidth(88)
        status_layout.addWidget(self.status_label)

        # 添加所有页面
        self.action_stack.addWidget(check_container)
        self.action_stack.addWidget(update_container)
        self.action_stack.addWidget(progress_container)
        self.action_stack.addWidget(status_container)

        layout.addWidget(self.action_stack)

        # 设置整体样式
        self.setStyleSheet("""
            ResourceListItem {
                background-color: #ffffff;
                border-radius: 12px;
                border: 1px solid #e5e7eb;
            }
            ResourceListItem:hover {
                background-color: #f9fafb;
                border-color: #d1d5db;
            }
        """)

        # 设置鼠标悬停效果
        self.setCursor(Qt.PointingHandCursor)

    def _set_icon(self, path):
        """设置图标"""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            # 如果图标不存在，创建一个默认图标
            pixmap = QPixmap(44, 44)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            # 绘制一个简单的资源图标
            painter.setPen(QPen(QColor(156, 163, 175), 2))  # #9ca3af
            painter.drawRoundedRect(8, 8, 28, 28, 4, 4)
            painter.end()
        self.icon_label.setPixmap(pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_check_clicked(self):
        """检查更新按钮点击"""
        self.check_button.setText("检查中...")
        self.check_button.setEnabled(False)
        self.check_update_clicked.emit()

    def set_update_available(self, new_version, update_type, download_url):
        """设置有更新可用"""
        self.update_info = {
            'version': new_version,
            'type': update_type,
            'url': download_url
        }

        # 更新版本显示
        self.version_label.setText(f"{self.resource.resource_version} → {new_version}")
        self.version_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 500;")

        # 切换到更新按钮
        update_text = "增量更新" if update_type == "incremental" else "完整更新"
        self.update_button.setText(update_text)
        self.action_stack.setCurrentIndex(1)

    def set_checking(self):
        """设置检查中状态"""
        self.check_button.setText("检查中...")
        self.check_button.setEnabled(False)

    def set_downloading(self, progress=0, speed=0):
        """设置下载状态"""
        self.action_stack.setCurrentIndex(2)
        self.progress_bar.setValue(int(progress))
        self.speed_label.setText(f"{speed:.1f} MB/s")

    def set_latest_version(self):
        """设置为最新版本"""
        self.status_label.setText("已是最新")
        self.status_label.setStyleSheet("color: #10b981; font-size: 12px; font-weight: 500;")
        self.action_stack.setCurrentIndex(3)

        # 3秒后恢复到检查按钮
        QTimer.singleShot(3000, self.reset_check_button)

    def set_error(self, error_msg):
        """设置错误状态"""
        self.status_label.setText("检查失败")
        self.status_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        self.action_stack.setCurrentIndex(3)

        # 3秒后恢复到检查按钮
        QTimer.singleShot(3000, self.reset_check_button)

    def reset_check_button(self):
        """重置检查按钮"""
        self.check_button.setText("检查更新")
        self.check_button.setEnabled(True)
        self.action_stack.setCurrentIndex(0)

        # 恢复版本标签
        self.version_label.setText(f"{self.resource.resource_version}")
        self.version_label.setStyleSheet("color: #6b7280; font-size: 12px;")

    def set_selected(self, selected):
        """设置选中状态"""
        self.is_selected = selected
        if selected:
            self.setStyleSheet("""
                ResourceListItem {
                    background-color: #eff6ff;
                    border: 1px solid #3b82f6;
                    border-radius: 12px;
                }
            """)
            # 更新图标容器背景
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: #dbeafe;
                    border-radius: 10px;
                    padding: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                ResourceListItem {
                    background-color: #ffffff;
                    border-radius: 12px;
                    border: 1px solid #e5e7eb;
                }
                ResourceListItem:hover {
                    background-color: #f9fafb;
                    border-color: #d1d5db;
                }
            """)
            # 恢复图标容器背景
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: #f3f4f6;
                    border-radius: 10px;
                    padding: 8px;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 检查是否点击在操作区域
            action_rect = self.action_stack.geometry()
            if not action_rect.contains(event.pos()):
                self.clicked.emit()
        super().mousePressEvent(event)


class ResourceDetailView(QWidget):
    """资源详情视图"""

    def __init__(self):
        super().__init__()
        self.current_resource = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")

        # 内容容器
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(20)

        # 资源信息卡片
        self.info_card = QFrame()
        self.info_card.setObjectName("detailInfoCard")
        self.info_card.setStyleSheet("""
            #detailInfoCard {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
            }
        """)

        # 添加卡片阴影
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 4)
        self.info_card.setGraphicsEffect(shadow)

        info_layout = QVBoxLayout(self.info_card)
        info_layout.setContentsMargins(24, 24, 24, 24)
        info_layout.setSpacing(20)

        # 顶部信息区
        top_info = QHBoxLayout()

        # 大图标
        self.large_icon = QLabel()
        self.large_icon.setFixedSize(64, 64)
        self.large_icon.setScaledContents(True)
        pixmap = QPixmap(f"assets/resource/resource.png")
        if pixmap.isNull():
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(200, 200, 200))
        self.large_icon.setPixmap(pixmap)

        # 标题和作者
        title_layout = QVBoxLayout()
        self.title_label = QLabel("资源名称")
        self.title_label.setObjectName("detailTitle")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setWeight(QFont.Bold)
        self.title_label.setFont(title_font)

        self.author_label = QLabel("作者信息")
        self.author_label.setObjectName("detailAuthor")
        self.author_label.setStyleSheet("color: #666; font-size: 14px;")

        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.author_label)

        top_info.addWidget(self.large_icon)
        top_info.addLayout(title_layout)
        top_info.addStretch()

        info_layout.addLayout(top_info)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #e0e0e0; max-height: 1px;")
        info_layout.addWidget(line)

        # 版本信息
        version_layout = QHBoxLayout()
        version_title = QLabel("版本信息")
        version_title.setObjectName("sectionTitle")
        version_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")

        self.version_label = QLabel("v1.0.0")
        self.version_label.setObjectName("versionLabel")
        self.version_label.setStyleSheet("font-size: 14px; color: #666;")

        version_layout.addWidget(version_title)
        version_layout.addWidget(self.version_label)
        version_layout.addStretch()

        info_layout.addLayout(version_layout)

        # 描述信息
        desc_title = QLabel("资源描述")
        desc_title.setObjectName("sectionTitle")
        desc_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #333;")

        self.desc_label = QLabel("暂无描述")
        self.desc_label.setObjectName("descLabel")
        self.desc_label.setStyleSheet("font-size: 13px; color: #666; line-height: 1.6;")
        self.desc_label.setWordWrap(True)

        info_layout.addWidget(desc_title)
        info_layout.addWidget(self.desc_label)

        content_layout.addWidget(self.info_card)

        # 详细信息区域（占位）
        detail_card = QFrame()
        detail_card.setObjectName("detailCard")
        detail_card.setStyleSheet("""
            #detailCard {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #e0e0e0;
                min-height: 200px;
            }
        """)

        detail_shadow = QGraphicsDropShadowEffect()
        detail_shadow.setBlurRadius(20)
        detail_shadow.setColor(QColor(0, 0, 0, 20))
        detail_shadow.setOffset(0, 4)
        detail_card.setGraphicsEffect(detail_shadow)

        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(24, 24, 24, 24)

        placeholder = QLabel("更多详细信息（待实现）")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #999; font-size: 14px;")
        detail_layout.addWidget(placeholder)

        content_layout.addWidget(detail_card)
        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def set_resource(self, resource):
        """设置要显示的资源"""
        self.current_resource = resource
        self.title_label.setText(resource.resource_name)
        self.author_label.setText(f"作者：{resource.resource_author or '未知'}")
        pixmap = QPixmap(f"assets/resource/{resource.resource_update_service_id}/{resource.resource_icon}")
        if pixmap.isNull():
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(200, 200, 200))
        self.large_icon.setPixmap(pixmap)
        self.version_label.setText(f"{resource.resource_version}")
        self.desc_label.setText(resource.resource_description or "该资源暂无描述信息")


class DownloadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadPage")
        self.threads = []
        self.pending_updates = []
        self.selected_resource = None
        self.resource_items = {}

        self.installer = UpdateInstaller()
        self._init_ui()
        self.load_resources()

    def _init_ui(self):
        """初始化UI元素"""
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧面板
        left_panel = QWidget()
        left_panel.setObjectName("leftPanel")
        left_panel.setFixedWidth(380)
        left_panel.setStyleSheet("""
            #leftPanel {
                background-color: #ffffff;
                border-right: 1px solid #e5e7eb;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 左侧标题
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-bottom: 1px solid #e5e7eb;
            }
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("资源列表")
        title.setObjectName("leftPanelTitle")
        title.setStyleSheet("""
            #leftPanelTitle {
                color: #1f2937;
                font-size: 18px;
                font-weight: 600;
            }
        """)



        header_layout.addWidget(title)
        header_layout.addStretch()

        left_layout.addWidget(header)

        # 资源列表滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用水平滚动条
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #f9fafb;
                border: none;
            }
            QScrollBar:vertical {
                background: #f3f4f6;
                width: 6px;
                border-radius: 3px;
                margin: 4px;
            }
            QScrollBar::handle:vertical {
                background: #d1d5db;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #9ca3af;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 资源列表容器
        self.resources_container = QWidget()
        self.resources_container.setStyleSheet("background-color: transparent;")
        self.resources_layout = QVBoxLayout(self.resources_container)
        self.resources_layout.setContentsMargins(16, 16, 16, 16)
        self.resources_layout.setSpacing(10)

        scroll_area.setWidget(self.resources_container)
        left_layout.addWidget(scroll_area)

        # 底部操作栏
        bottom_bar = QWidget()
        bottom_bar.setFixedHeight(80)
        bottom_bar.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border-top: 1px solid #e5e7eb;
            }
        """)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 16, 16, 16)
        bottom_layout.setSpacing(12)

        # 添加资源按钮
        self.add_btn = QPushButton(" 添加资源")
        self.add_btn.setObjectName("addResourceButton")
        self.add_btn.setIcon(QIcon("assets/icons/add.png"))
        self.add_btn.setFixedHeight(42)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.setStyleSheet("""
            #addResourceButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0 20px;
                font-weight: 500;
                font-size: 14px;
            }
            #addResourceButton:hover {
                background-color: #2563eb;
            }
            #addResourceButton:pressed {
                background-color: #1d4ed8;
            }
            #addResourceButton:disabled {
                background-color: #e5e7eb;
                color: #9ca3af;
            }
        """)
        self.add_btn.clicked.connect(self.show_add_resource_dialog)

        # 检查所有更新按钮
        self.check_all_btn = QPushButton(" 检查全部")
        self.check_all_btn.setObjectName("checkAllButton")
        self.check_all_btn.setIcon(QIcon("assets/icons/refresh.png"))
        self.check_all_btn.setFixedHeight(42)
        self.check_all_btn.setCursor(Qt.PointingHandCursor)
        self.check_all_btn.setStyleSheet("""
            #checkAllButton {
                background-color: #ffffff;
                color: #374151;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 0 20px;
                font-weight: 500;
                font-size: 14px;
            }
            #checkAllButton:hover {
                background-color: #f9fafb;
                border-color: #d1d5db;
            }
            #checkAllButton:pressed {
                background-color: #f3f4f6;
            }
            #checkAllButton:disabled {
                background-color: #f9fafb;
                color: #9ca3af;
                border-color: #e5e7eb;
            }
        """)
        self.check_all_btn.clicked.connect(self.check_all_updates)

        bottom_layout.addWidget(self.add_btn)
        bottom_layout.addWidget(self.check_all_btn)

        left_layout.addWidget(bottom_bar)

        # 右侧内容区域
        right_panel = QWidget()
        right_panel.setObjectName("rightPanel")
        right_panel.setStyleSheet("#rightPanel { background-color: #f9fafb; }")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 内容堆叠
        self.content_stack = QStackedWidget()

        # 空状态
        self.empty_widget = self._create_empty_state()
        self.content_stack.addWidget(self.empty_widget)

        # 详情视图
        self.detail_view = ResourceDetailView()
        self.content_stack.addWidget(self.detail_view)

        right_layout.addWidget(self.content_stack)

        # 添加到主布局
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)

        # 连接信号
        self._connect_signals()

    def _create_empty_state(self):
        """创建空状态页面"""
        widget = QWidget()
        widget.setStyleSheet("background-color: #f9fafb;")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)

        # 图标
        icon_label = QLabel()
        pixmap = QPixmap("assets/icons/empty.png")
        if pixmap.isNull():
            # 创建默认图标
            pixmap = QPixmap(80, 80)
            pixmap.fill(QColor(229, 231, 235))
        icon_label.setPixmap(pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_label.setAlignment(Qt.AlignCenter)

        # 主文字
        text_label = QLabel("请从左侧选择资源查看详情")
        text_label.setObjectName("emptyText")
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet("color: #6b7280; font-size: 16px; font-weight: 500;")

        # 提示文字
        hint_label = QLabel("您可以点击添加资源按钮来添加新的资源")
        hint_label.setAlignment(Qt.AlignCenter)
        hint_label.setStyleSheet("color: #9ca3af; font-size: 14px;")

        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addWidget(hint_label)

        return widget

    def _connect_signals(self):
        """连接信号"""
        self.installer.install_completed.connect(self._handle_install_completed)
        self.installer.install_failed.connect(self._handle_install_failed)
        self.installer.restart_required.connect(self._handle_restart_required)

    def load_resources(self):
        """加载资源列表"""
        # 清空现有资源
        for item in self.resource_items.values():
            item.deleteLater()
        self.resource_items.clear()

        # 清空布局
        while self.resources_layout.count():
            self.resources_layout.takeAt(0)

        # 加载资源
        resources = global_config.get_all_resource_configs()



        for resource in resources:
            item = ResourceListItem(resource)
            item.clicked.connect(lambda r=resource: self._on_resource_selected(r))
            item.check_update_clicked.connect(lambda r=resource: self._check_resource_update(r))

            # 连接更新按钮
            item.update_button.clicked.connect(lambda checked, r=resource, i=item: self._start_update(r, i))

            self.resources_layout.addWidget(item)
            self.resource_items[resource.resource_name] = item

        # 添加弹性空间
        self.resources_layout.addStretch()

        # 如果没有选中的资源，显示空状态
        if not self.selected_resource:
            self.content_stack.setCurrentIndex(0)

    def _on_resource_selected(self, resource):
        """处理资源选中"""
        # 更新选中状态
        for name, item in self.resource_items.items():
            item.set_selected(name == resource.resource_name)

        self.selected_resource = resource
        self.detail_view.set_resource(resource)
        self.content_stack.setCurrentIndex(1)

    def _check_resource_update(self, resource):
        """检查单个资源更新"""
        item = self.resource_items.get(resource.resource_name)
        if not item:
            return

        # 检查更新源
        if not resource.resource_rep_url and not resource.resource_update_service_id:
            item.set_error("无更新源")
            notification_manager.show_warning(
                "该资源未配置更新源",
                resource.resource_name
            )
            return

        # 创建检查线程
        thread = UpdateChecker(resource, single_mode=True)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)

        self.threads.append(thread)
        thread.start()

    def _handle_update_found(self, resource_name, latest_version, current_version, download_url, update_type):
        """处理发现更新"""
        item = self.resource_items.get(resource_name)
        if item:
            item.set_update_available(latest_version, update_type, download_url)

    def _handle_update_not_found(self, resource_name):
        """处理未发现更新"""
        item = self.resource_items.get(resource_name)
        if item:
            item.set_latest_version()

    def _handle_check_failed(self, resource_name, error_message):
        """处理检查失败"""
        item = self.resource_items.get(resource_name)
        if item:
            item.set_error(error_message)

        notification_manager.show_error(
            f"检查更新失败：{error_message}",
            resource_name
        )

    def _start_update(self, resource, item):
        """开始更新资源"""
        if not item.update_info:
            return

        # 切换到下载进度显示
        item.set_downloading()

        # 创建临时目录
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 创建下载线程
        thread = UpdateDownloader(
            resource.resource_name,
            item.update_info['url'],
            temp_dir,
            resource=resource,
            version=item.update_info['version']
        )

        # 连接信号
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_download_completed)
        thread.download_failed.connect(self._handle_download_failed)

        self.threads.append(thread)
        thread.start()

    def _update_download_progress(self, resource_name, progress, speed):
        """更新下载进度"""
        item = self.resource_items.get(resource_name)
        if item:
            item.set_downloading(progress, speed)

    def _handle_download_completed(self, resource_name, file_path, data):
        """处理下载完成"""
        item = self.resource_items.get(resource_name)

        try:
            # 根据数据类型确定是新资源还是更新
            if isinstance(data, dict):
                # 新资源
                self.installer.install_new_resource(resource_name, file_path, data)
            else:
                # 资源更新
                self.installer.install_update(data, file_path)
        except Exception as e:
            if item:
                item.set_error("安装失败")
            notification_manager.show_error(
                f"安装失败：{str(e)}",
                resource_name
            )

    def _handle_download_failed(self, resource_name, error):
        """处理下载失败"""
        item = self.resource_items.get(resource_name)
        if item:
            item.set_error("下载失败")
            # 3秒后恢复到更新按钮状态
            if item.update_info:
                QTimer.singleShot(3000, lambda: item.set_update_available(
                    item.update_info['version'],
                    item.update_info['type'],
                    item.update_info['url']
                ))

        notification_manager.show_error(
            f"下载失败：{error}",
            resource_name
        )

    def check_all_updates(self):
        """检查所有更新"""
        self.check_all_btn.setText("检查中...")
        self.check_all_btn.setEnabled(False)

        # 设置所有资源为检查中状态
        for item in self.resource_items.values():
            if item.resource.resource_rep_url or item.resource.resource_update_service_id:
                item.set_checking()

        # 获取有更新源的资源
        resources = global_config.get_all_resource_configs()
        resources_with_update = [r for r in resources if r.resource_update_service_id or r.resource_rep_url]

        if not resources_with_update:
            self.check_all_btn.setText("检查全部")
            self.check_all_btn.setEnabled(True)
            notification_manager.show_info(
                "没有找到配置了更新源的资源",
                "检查更新"
            )
            return

        # 创建检查线程
        thread = UpdateChecker(resources_with_update)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)
        thread.check_completed.connect(self._handle_batch_check_completed)

        self.threads.append(thread)
        thread.start()

    def _handle_batch_check_completed(self, total_checked, updates_found):
        """处理批量检查完成"""
        self.check_all_btn.setEnabled(True)

        if updates_found == 0:
            self.check_all_btn.setText("检查全部")
            notification_manager.show_success(
                f"已检查 {total_checked} 个资源，所有资源均为最新版本",
                "检查完成"
            )
        else:
            self.check_all_btn.setText(f"检查全部 ({updates_found})")
            notification_manager.show_success(
                f"发现 {updates_found} 个资源有可用更新",
                "检查完成"
            )

    def show_add_resource_dialog(self):
        """显示添加资源对话框"""
        dialog = AddResourceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.add_new_resource(dialog.get_data())

    def add_new_resource(self, data):
        """添加新资源"""
        self.add_btn.setEnabled(False)
        self.add_btn.setText("添加中...")

        # 创建临时目录
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 处理 URL
        url = data["url"]
        if "github.com" in url and not url.endswith(".zip"):
            self._process_github_repo(url, data)
        else:
            self._download_resource(url, data)

    def _process_github_repo(self, repo_url, data):
        """处理 GitHub 仓库 URL"""
        try:
            # 解析 GitHub URL
            parts = repo_url.split('github.com/')[1].split('/')
            if len(parts) < 2:
                self._show_add_error("GitHub地址格式不正确")
                return

            owner, repo = parts[0], parts[1]
            if repo.endswith('.git'):
                repo = repo[:-4]

            # 获取最新发布信息
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            response = requests.get(api_url, timeout=10)

            if response.status_code != 200:
                self._show_add_error(f"API返回错误 ({response.status_code})")
                return

            release_info = response.json()
            latest_version = release_info.get('tag_name', '').lstrip('v')

            # 如果未提供名称，使用仓库名称
            if not data["name"]:
                data["name"] = repo

            # 查找 ZIP 资源
            download_url = None
            for asset in release_info.get('assets', []):
                if asset.get('name', '').endswith('.zip'):
                    download_url = asset.get('browser_download_url')
                    break

            if not download_url:
                self._show_add_error("找不到可下载的资源包")
                return

            # 下载 ZIP
            self._download_resource(download_url, data, latest_version)

        except Exception as e:
            self._show_add_error(str(e))

    def _download_resource(self, url, data, version=None):
        """下载资源"""
        resource_name = data["name"] if data["name"] else "新资源"

        # 创建临时资源项
        temp_resource = type('obj', (object,), {
            'resource_name': resource_name,
            'resource_version': version or '0.0.0',
            'resource_author': data.get('author', ''),
            'resource_description': data.get('description', ''),
            'resource_rep_url': '',
            'resource_update_service_id': ''
        })

        item = ResourceListItem(temp_resource)
        item.set_downloading()
        self.resources_layout.insertWidget(self.resources_layout.count() - 1, item)
        self.resource_items[resource_name] = item

        # 创建下载线程
        temp_dir = Path("assets/temp")
        thread = UpdateDownloader(resource_name, url, temp_dir, data=data, version=version)

        # 连接信号
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_download_completed)
        thread.download_failed.connect(self._handle_download_failed)

        self.threads.append(thread)
        thread.start()

    def _show_add_error(self, error):
        """显示添加错误"""
        self._restore_add_button()
        notification_manager.show_error(
            f"添加资源失败：{error}",
            "操作失败"
        )

    def _restore_add_button(self):
        """恢复添加按钮"""
        self.add_btn.setEnabled(True)
        self.add_btn.setText("添加资源")

    def _handle_install_completed(self, resource_name, version, locked_files):
        """处理安装完成"""
        self.load_resources()
        self._restore_add_button()

        # 更新资源计数
        resources = global_config.get_all_resource_configs()
        notification_manager.show_success(
            f"资源 {resource_name} 已成功更新到版本 {version}",
            "更新成功"
        )

    def _handle_install_failed(self, resource_name, error_message):
        """处理安装失败"""
        self._restore_add_button()
        notification_manager.show_error(
            f"安装失败：{error_message}",
            resource_name
        )

    def _handle_restart_required(self):
        """处理需要重启"""
        reply = QMessageBox.question(
            self,
            "需要重启应用",
            "此更新需要重启应用程序才能完成。\n\n是否立即重启？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            QTimer.singleShot(100, QCoreApplication.quit)
        else:
            notification_manager.show_info(
                "更新已下载但尚未应用，请手动重启应用程序以完成更新",
                "更新延迟"
            )