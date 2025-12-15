from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QSizePolicy,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    Theme,
    setTheme,
)

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import global_config


class HomeInterface(QWidget):
    """
    全新 Fluent 风格首页：
    - 顶部操作卡：标题、说明、添加/刷新按钮
    - 统计卡：设备数量及类型分布
    - 设备卡：CardWidget 组合 Fluent 组件呈现
    """

    addDeviceRequested = Signal()
    deviceActivated = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent=parent)
        setTheme(Theme.LIGHT)
        self.setObjectName("homeInterface")
        self._build_ui()
        self.refresh_devices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        layout.addWidget(self._build_header_card())
        layout.addLayout(self._build_stat_cards())

        self.scroll_area = ScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setHorizontalSpacing(12)
        self.cards_layout.setVerticalSpacing(12)
        self.cards_layout.setAlignment(Qt.AlignTop)

        self.scroll_area.setWidget(self.cards_container)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.scroll_area, stretch=1)

    def _build_header_card(self) -> CardWidget:
        card = CardWidget(self)
        card.setObjectName("headerCard")
        card.setFixedHeight(120)

        cl = QHBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(6)
        title = StrongBodyLabel("控制中心")
        subtitle = BodyLabel("纯 Fluent 组件重写首页，快速浏览与进入设备。")
        subtitle.setProperty("textColor", "secondary")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        cl.addLayout(title_box, stretch=1)

        refresh_btn = PushButton("刷新")
        refresh_btn.setIcon(QIcon(FIF.SYNC.icon()))
        refresh_btn.clicked.connect(self.refresh_devices)

        add_btn = PrimaryPushButton("添加设备")
        add_btn.setIcon(QIcon(FIF.ADD.icon()))
        add_btn.clicked.connect(self.addDeviceRequested.emit)

        cl.addWidget(refresh_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
        cl.addWidget(add_btn, alignment=Qt.AlignRight | Qt.AlignVCenter)
        return card

    def _build_stat_cards(self) -> QHBoxLayout:
        hl = QHBoxLayout()
        hl.setSpacing(12)

        self.total_card = self._stat_card("全部设备", FIF.LAYOUT)
        self.adb_card = self._stat_card("ADB", FIF.PHONE)
        self.win_card = self._stat_card("Win32", FIF.APPLICATION)

        hl.addWidget(self.total_card)
        hl.addWidget(self.adb_card)
        hl.addWidget(self.win_card)
        hl.addStretch()
        return hl

    def _stat_card(self, title: str, icon: FIF) -> CardWidget:
        card = CardWidget(self)
        card.setFixedHeight(82)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        cl = QHBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(icon.icon().pixmap(26, 26))
        icon_label.setFixedSize(28, 28)
        cl.addWidget(icon_label, alignment=Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.addWidget(BodyLabel(title))
        value_label = StrongBodyLabel("0")
        value_label.setProperty("textColor", "primary")
        text_box.addWidget(value_label)
        cl.addLayout(text_box)

        cl.addStretch()
        card.value_label = value_label  # 直接挂载供刷新使用
        return card

    def refresh_devices(self):
        self._clear_cards()
        devices: List[DeviceConfig] = getattr(global_config.get_app_config(), "devices", []) or []
        self._update_stats(devices)

        if not devices:
            self._show_empty_state()
            return

        for idx, device in enumerate(devices):
            card = self._create_device_card(device)
            row, col = divmod(idx, 2)
            self.cards_layout.addWidget(card, row, col)

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _show_empty_state(self):
        card = CardWidget(self.cards_container)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(8)
        cl.addWidget(StrongBodyLabel("暂无设备"), alignment=Qt.AlignLeft)
        cl.addWidget(
            BodyLabel("点击右上角“添加设备”创建或导入设备配置。"),
            alignment=Qt.AlignLeft,
        )

        add_btn = PrimaryPushButton("立即添加")
        add_btn.setIcon(QIcon(FIF.ADD.icon()))
        add_btn.clicked.connect(self.addDeviceRequested.emit)
        cl.addWidget(add_btn, alignment=Qt.AlignLeft)

        self.cards_layout.addWidget(card, 0, 0)

    def _create_device_card(self, device: DeviceConfig) -> CardWidget:
        card = CardWidget(self.cards_container)
        card.setFixedHeight(190)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(FIF.ROBOT.icon().pixmap(28, 28))
        icon_label.setFixedSize(32, 32)
        header.addWidget(icon_label, alignment=Qt.AlignTop)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(StrongBodyLabel(device.device_name))
        subtitle = BodyLabel(self._device_type_text(device.device_type))
        subtitle.setProperty("textColor", "secondary")
        title_box.addWidget(subtitle)
        header.addLayout(title_box, stretch=1)

        status = BodyLabel(self._controller_label(device))
        status.setProperty("textColor", "secondary")
        header.addWidget(status, alignment=Qt.AlignRight | Qt.AlignTop)
        cl.addLayout(header)

        info = QGridLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setHorizontalSpacing(12)
        info.setVerticalSpacing(6)

        resources = getattr(device, "resources", []) or []
        info.addWidget(BodyLabel("资源数量"), 0, 0)
        info.addWidget(StrongBodyLabel(str(len(resources))), 0, 1)

        start_cmd = getattr(device, "start_command", "") or "未配置启动命令"
        info.addWidget(BodyLabel("启动方式"), 1, 0)
        info.addWidget(BodyLabel(start_cmd), 1, 1)

        auto_start = getattr(device, "auto_start_emulator", False)
        auto_close = getattr(device, "auto_close_emulator", False)
        info.addWidget(BodyLabel("自动启动模拟器"), 2, 0)
        info.addWidget(BodyLabel("是" if auto_start else "否"), 2, 1)
        info.addWidget(BodyLabel("自动关闭模拟器"), 3, 0)
        info.addWidget(BodyLabel("是" if auto_close else "否"), 3, 1)

        cl.addLayout(info)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        go_btn = PrimaryPushButton("进入设备")
        go_btn.clicked.connect(lambda: self.deviceActivated.emit(device.device_name))
        actions.addWidget(go_btn)

        copy_btn = PushButton("复制配置")
        copy_btn.clicked.connect(lambda: self._copy_hint(card))
        actions.addWidget(copy_btn)

        actions.addStretch()
        cl.addLayout(actions)

        return card

    def _controller_label(self, device: DeviceConfig) -> str:
        if device.device_type == DeviceType.ADB:
            controller = getattr(device.controller_config, "address", "")
            return controller or "ADB 设备"
        if device.device_type == DeviceType.WIN32:
            hwnd = getattr(device.controller_config, "hWnd", None)
            return f"Win32 - hWnd {hwnd}" if hwnd else "Win32 设备"
        return "未知类型"

    @staticmethod
    def _device_type_text(device_type: DeviceType) -> str:
        if device_type == DeviceType.ADB:
            return "Android / ADB"
        if device_type == DeviceType.WIN32:
            return "Windows 窗口"
        return "未识别设备"

    def _copy_hint(self, parent: QWidget):
        InfoBar.info(
            title="提示",
            content="后续可接入复制或导出配置逻辑。",
            duration=3000,
            parent=parent,
            position=InfoBarPosition.BOTTOM_RIGHT,
        )

    def _update_stats(self, devices: List[DeviceConfig]):
        total = len(devices)
        adb = len([d for d in devices if d.device_type == DeviceType.ADB])
        win = len([d for d in devices if d.device_type == DeviceType.WIN32])
        self.total_card.value_label.setText(str(total))
        self.adb_card.value_label.setText(str(adb))
        self.win_card.value_label.setText(str(win))


