from PySide6.QtWidgets import QWidget
from qfluentwidgets import (
    FluentWindow,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    setTheme,
    Theme,
)

from app.models.config.global_config import global_config
from app_refact.home_interface import HomeInterface


class AppWindow(FluentWindow):
    """极简版：只展示 FluentWindow 自带侧边栏与占位页，不含托盘/保存逻辑。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MFWPH")
        self.setMinimumSize(900, 650)

        setTheme(Theme.LIGHT)

        # 简单加载配置（仅为获取设备列表）
        global_config.load_all_resources_from_directory("assets/resource/")
        global_config.load_app_config("assets/config/app_config.json")

        # 使用 FluentWindow 内置 navigationInterface
        self.navigationInterface.setExpandWidth(220)
        self.navigationInterface.setMinimumWidth(72)

        self.home_interface = HomeInterface()
        self.home_interface.addDeviceRequested.connect(self._on_add_device_requested)
        self.home_interface.deviceActivated.connect(self._on_device_activated)

        self._build_nav_items()

    def _build_nav_items(self):
        devices = getattr(global_config.get_app_config(), "devices", [])

        # 首页使用重构后的 Fluent 卡片页面
        self.addSubInterface(self.home_interface, FIF.HOME, "首页", position=NavigationItemPosition.TOP)
        self._add_placeholder("scheduled", FIF.CLOSE, "定时任务", NavigationItemPosition.TOP)
        self._add_placeholder("download", FIF.DOWNLOAD, "资源下载", NavigationItemPosition.TOP)

        self.navigationInterface.addSeparator()
        for device in devices:
            route_key = f"device::{device.device_name}"
            self._add_placeholder(route_key, FIF.CLOSE, device.device_name, NavigationItemPosition.SCROLL)
        self.navigationInterface.addSeparator()

        self._add_placeholder("settings", FIF.SETTING, "设置", NavigationItemPosition.BOTTOM)

    def _add_placeholder(self, route_key: str, icon, text: str, position: NavigationItemPosition):
        page = QWidget()
        page.setObjectName(route_key)
        self.addSubInterface(page, icon, text, position=position)

    def _on_add_device_requested(self):
        InfoBar.info(
            title="即将支持",
            content="此重构版本仅演示首页，可在集成添加设备逻辑后跳转。",
            parent=self.home_interface,
            position=InfoBarPosition.TOP,
            duration=3000,
        )

    def _on_device_activated(self, device_name: str):
        InfoBar.success(
            title="设备打开",
            content=f"将在后续版本跳转到 {device_name} 的详情页。",
            parent=self.home_interface,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500,
        )


