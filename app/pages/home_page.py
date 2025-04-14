import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QPushButton, QSplitter,
    QSizePolicy
)
from qasync import asyncSlot

from app.components.device_card import DeviceCard
from app.components.log_display import LogDisplay
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.tasker_manager import task_manager

class HomePage(QWidget):
    """Home page with device cards and collapsible log display"""

    device_added = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.global_config = global_config
        self.devices = []
        self.init_ui()

        # Connect signals
        self.connect_signals()

        # Log startup message
        self.log_startup_message()

    def log_startup_message(self):
        """记录应用启动日志，包含日志处理相关信息"""
        app_logger = log_manager.get_app_logger()
        app_logger.info("MFWPH已启动")
        app_logger.info(f"日志存储路径: {os.path.abspath(log_manager.log_dir)}")

        # 如果刚才进行了日志备份，记录一条信息
        backup_dir = log_manager.backup_dir
        backup_files = [f for f in os.listdir(backup_dir) if f.startswith("logs_backup_")]
        if backup_files:
            # 获取最新的备份文件
            latest_backup = max(backup_files)
            app_logger.info(f"启动时发现日志超过10MB，已备份至: {os.path.join('backup', latest_backup)}")

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)  # 减少顶部边距
        main_layout.setSpacing(10)  # 减少间距
        self.setObjectName("settingsPage")
        # 创建内容区域小部件
        content_widget = QWidget()
        content_widget.setObjectName("content_widget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)  # 减少间距

        # 带有徽标和应用标题的标题 - 更紧凑
        header_widget = QWidget()
        header_widget.setObjectName("titleContainer")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 10, 10, 10)  # 减少边距

        # 应用徽标
        logo_label = QLabel()
        logo_pixmap = QPixmap("assets/images/logo.png")
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # 如果找不到图像，则使用备用文本
            logo_label.setText("📱")
            logo_label.setFont(QFont("Segoe UI", 20))

        header_layout.addWidget(logo_label)

        # 应用标题和副标题
        title_container = QVBoxLayout()
        title_container.setSpacing(0)

        title_label = QLabel("MFWPH")
        title_label.setObjectName("pageTitle")

        subtitle_label = QLabel("设备管理系统")
        subtitle_label.setObjectName("statusText")

        title_container.addWidget(title_label)
        title_container.addWidget(subtitle_label)

        header_layout.addLayout(title_container)
        header_layout.addStretch()

        # 添加设备按钮
        add_device_btn = QPushButton("添加设备")
        add_device_btn.setObjectName("primaryButton")
        add_device_btn.setIcon(QIcon("assets/icons/add.svg"))
        add_device_btn.clicked.connect(self.add_device)
        header_layout.addWidget(add_device_btn)

        # 切换日志按钮
        self.toggle_logs_btn = QPushButton("显示日志")
        self.toggle_logs_btn.setObjectName("secondaryButton")
        self.toggle_logs_btn.setIcon(QIcon("assets/icons/log.svg"))
        self.toggle_logs_btn.setCheckable(True)
        self.toggle_logs_btn.clicked.connect(self.toggle_logs)
        header_layout.addWidget(self.toggle_logs_btn)

        content_layout.addWidget(header_widget)

        # 可滚动区域中的设备卡网格 - 位置更靠近顶部
        scroll_area = QScrollArea()
        scroll_area.setObjectName("deviceScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 设备卡容器
        self.cards_container = QWidget()
        self.cards_container.setObjectName("deviceButtonsContainer")
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(5, 0, 5, 10)  # 减少边距
        self.cards_layout.setSpacing(15)  # 略微减少间距

        # 设置列伸展因子以使卡片均匀分布
        self.cards_layout.setColumnStretch(0, 1)
        self.cards_layout.setColumnStretch(1, 1)
        self.cards_layout.setColumnStretch(2, 1)

        scroll_area.setWidget(self.cards_container)
        content_layout.addWidget(scroll_area, 1)  # 给它一个伸展因子来占用可用空间

        # 现在为内容区域和日志创建主分割器
        self.content_splitter = QSplitter(Qt.Vertical)
        # self.content_splitter.setObjectName("leftSplitter")
        self.content_splitter.setHandleWidth(1)  # 更细的手柄
        self.content_splitter.setChildrenCollapsible(True)

        # 将内容小部件添加到分割器
        self.content_splitter.addWidget(content_widget)

        # 创建并将日志显示添加到分割器
        self.log_display = LogDisplay(self)
        self.log_display.setObjectName("logFrame")
        self.log_display.setMinimumHeight(100)
        self.content_splitter.addWidget(self.log_display)

        # 设置初始大小 - 日志区域完全折叠
        self.content_splitter.setSizes([1, 0])

        # 将分割器添加到主布局
        main_layout.addWidget(self.content_splitter)

        # 加载设备
        self.load_devices()

        # 更新日志显示中的设备列表
        if hasattr(self.log_display, 'update_device_list'):
            self.log_display.update_device_list(self.devices)

    def connect_signals(self):
        """连接来自日志管理器和其他信号"""
        log_manager.app_log_updated.connect(self.on_app_log_updated)

        # 连接来自全局配置的设备更改
        if hasattr(global_config, 'device_added'):
            global_config.device_added.connect(self.on_device_config_changed)
        if hasattr(global_config, 'device_removed'):
            global_config.device_removed.connect(self.on_device_config_changed)
        if hasattr(global_config, 'device_updated'):
            global_config.device_updated.connect(self.on_device_config_changed)

    def load_devices(self):
        """加载所有已配置设备的设备卡"""
        # 清除当前卡片
        self.clear_device_cards()

        # 从配置获取设备
        devices_config = self.global_config.get_devices_config()
        if devices_config and hasattr(devices_config, 'devices'):
            self.devices = devices_config.devices

            # 更新设备数量
            # self.device_count_label.setText(f"{len(self.devices)} 台设备")

            # 创建卡片
            for idx, device in enumerate(self.devices):
                # 根据索引计算行和列
                row = idx // 3  # 每行3张卡片
                col = idx % 3

                card = DeviceCard(device, self)
                self.cards_layout.addWidget(card, row, col)

            # 更新日志显示中的设备列表
            if hasattr(self.log_display, 'update_device_list'):
                self.log_display.update_device_list(self.devices)
        # else:
            # 没有设备
            # self.device_count_label.setText("0 台设备")

    def clear_device_cards(self):
        """从网格中清除所有设备卡"""
        # 从网格中删除所有小部件
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def on_device_config_changed(self, *args):
        """处理设备配置更改"""
        # 重新加载所有设备
        self.load_devices()

    def on_app_log_updated(self):
        """处理应用日志更新"""
        # 如果日志显示可见，更新它
        if self.content_splitter.sizes()[1] > 0 and self.log_display.isVisible():
            self.log_display.request_logs_update()

    def toggle_logs(self, checked):
        """切换日志显示区域的可见性"""
        sizes = self.content_splitter.sizes()
        total_height = sum(sizes)

        if checked:
            # 显示日志 - 设置为总高度的约1/3
            self.content_splitter.setSizes([int(total_height * 2 / 3), int(total_height * 1 / 3)])
            self.toggle_logs_btn.setText("隐藏日志")
            self.log_display.setVisible(True)
            # 请求日志更新
            self.log_display.request_logs_update()
        else:
            # 隐藏日志 - 重要：首先设置大小，然后隐藏
            self.content_splitter.setSizes([total_height, 0])
            self.toggle_logs_btn.setText("显示日志")

    def add_device(self):
        """打开对话框以添加新设备"""
        # 查找主窗口
        main_window = self.window()

        # 检查它是否具有添加设备方法
        if main_window and hasattr(main_window, 'add_device'):
            main_window.add_device()

    def show_all_logs(self):
        """显示所有日志并使日志区域可见"""
        # 确保日志可见
        if self.content_splitter.sizes()[1] == 0:
            self.toggle_logs_btn.setChecked(True)
            self.toggle_logs(True)

        # 设置日志显示以显示所有日志
        self.log_display.device_selector.setCurrentIndex(0)