import json
import os
import sys

from app.models.logging.log_manager import app_logger

from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QScrollArea, QSystemTrayIcon, QMenu
)

from app.components.navigation_button import NavigationButton
from app.models.config.global_config import global_config
from app.pages.device_info_page import DeviceInfoPage
from app.pages.download_page import DownloadPage
from app.pages.home_page import HomePage
from app.pages.scheduled_tasks_page import ScheduledTaskPage
from app.pages.settings_page import SettingsPage
from app.utils.theme_manager import theme_manager
from app.widgets.add_device_dialog import AddDeviceDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MFWPH")
        self.setMinimumSize(800, 600)

        # 跟踪当前激活的页面或设备
        self.current_page = "home"
        self.current_device = None
        self.current_button_id = None  # 跟踪唯一的设备按钮ID

        app_config = global_config.get_app_config()
        if hasattr(app_config, 'window_size') and app_config.window_size:
            try:
                width, height = map(int, app_config.window_size.split('x'))
                self.resize(width, height)
            except (ValueError, AttributeError):
                self.resize(800, 600)
        else:
            self.resize(800, 600)

        if hasattr(app_config, 'window_position') and app_config.window_position:
            try:
                if app_config.window_position.strip().lower() != "center":
                    x, y = map(int, app_config.window_position.split(','))
                    self.move(x, y)
            except (ValueError, AttributeError):
                pass

        self.theme_manager = theme_manager
        self.theme_manager.apply_theme("light")

        # Main container widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Main Content Area (Sidebar + Pages) ---
        main_content_widget = QWidget()
        main_content_layout = QHBoxLayout(main_content_widget)
        main_content_layout.setSpacing(0)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(main_content_widget)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setFixedWidth(60)
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(0)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setAlignment(Qt.AlignTop)
        main_content_layout.addWidget(sidebar)

        # --- Navigation Buttons ---
        self.static_buttons = []
        self.home_btn = NavigationButton("首页", "assets/icons/home.svg")
        self.home_btn.setObjectName("home")
        sidebar_layout.addWidget(self.home_btn)
        self.static_buttons.append(self.home_btn)

        # ... (rest of the sidebar buttons) ...
        separator_top = QFrame()
        separator_top.setFrameShape(QFrame.HLine)
        separator_top.setFrameShadow(QFrame.Sunken)
        separator_top.setObjectName("sidebarSeparator")
        sidebar_layout.addWidget(separator_top)

        self.device_buttons_container = QWidget()
        self.device_buttons_container.setObjectName("sidebarDeviceButtonsContainer")
        self.device_buttons_layout = QVBoxLayout(self.device_buttons_container)
        self.device_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.device_buttons_layout.setSpacing(0)
        self.device_buttons_layout.setAlignment(Qt.AlignTop)

        self.device_scroll_area = QScrollArea()
        self.device_scroll_area.setObjectName("deviceScrollArea")
        self.device_scroll_area.setWidgetResizable(True)
        self.device_scroll_area.setFrameShape(QFrame.NoFrame)
        self.device_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.device_scroll_area.setWidget(self.device_buttons_container)
        sidebar_layout.addWidget(self.device_scroll_area)

        separator_middle = QFrame()
        separator_middle.setFrameShape(QFrame.HLine)
        separator_middle.setFrameShadow(QFrame.Sunken)
        separator_middle.setObjectName("sidebarSeparator")
        sidebar_layout.addWidget(separator_middle)

        self.add_device_btn = NavigationButton("添加设备", "assets/icons/apps-add.svg")
        self.add_device_btn.setCheckable(False)
        self.add_device_btn.clicked.connect(self.open_add_device_dialog)
        sidebar_layout.addWidget(self.add_device_btn)

        self.scheduled_btn = NavigationButton("定时任务", "assets/icons/add-time.svg")
        self.scheduled_btn.setObjectName("scheduled")
        sidebar_layout.addWidget(self.scheduled_btn)
        self.static_buttons.append(self.scheduled_btn)

        self.download_btn = NavigationButton("资源下载", "assets/icons/updata_res.svg")
        self.download_btn.setObjectName("download")
        sidebar_layout.addWidget(self.download_btn)
        self.static_buttons.append(self.download_btn)

        separator_bottom = QFrame()
        separator_bottom.setFrameShape(QFrame.HLine)
        separator_bottom.setFrameShadow(QFrame.Sunken)
        separator_bottom.setObjectName("sidebarSeparator")
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(separator_bottom)

        self.settings_btn = NavigationButton("设置", "assets/icons/settings.svg")
        self.settings_btn.setObjectName("settings")
        sidebar_layout.addWidget(self.settings_btn)
        self.static_buttons.append(self.settings_btn)

        # --- Page Container ---
        self.page_container = QWidget()
        self.page_layout = QVBoxLayout(self.page_container)
        self.page_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.addWidget(self.page_container)

        

        self.pages = {
            "home": HomePage(),
            "scheduled": ScheduledTaskPage(),
            "download": DownloadPage(),
            "settings": SettingsPage()
        }
        self.device_pages = {}

        self.home_btn.clicked.connect(lambda: self.show_page("home"))
        self.download_btn.clicked.connect(lambda: self.show_page("download"))
        self.scheduled_btn.clicked.connect(lambda: self.show_page("scheduled"))
        self.settings_btn.clicked.connect(lambda: self.show_page("settings"))

        self.pages["home"].device_added.connect(self.refresh_device_list)

        self.load_devices()
        self.update_scroll_area_visibility()
        self.init_tray_icon()
        self.show_page("home")

    def init_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("assets/icons/app/logo.png"))
        self.tray_icon.setToolTip("MFWPH")

        show_action = QAction("显示", self)
        quit_action = QAction("退出", self)
        show_action.triggered.connect(self.show_normal)
        quit_action.triggered.connect(self.force_quit)

        tray_menu = QMenu()
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)

        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Left click
            self.show_normal()

    def show_normal(self):
        self.show()
        self.activateWindow()

    def force_quit(self):
        """托盘退出"""
        # 1. 隐藏托盘 (防止图标残留)
        self.tray_icon.hide()

        # 2. 保存配置
        size = self.size()
        window_size = f"{size.width()}x{size.height()}"
        pos = self.pos()
        window_position = f"{pos.x()},{pos.y()}"

        app_config = global_config.get_app_config()
        app_config.window_size = window_size
        app_config.window_position = window_position
        global_config.save_all_configs()

        # 3. 触发全局退出信号 -> 只有这一行！
        # 这会触发 main.py 中的 app.aboutToQuit，从而执行清理和 loop.stop()
        QCoreApplication.instance().quit()

    def closeEvent(self, event):
        """窗口关闭事件"""
        app_config = global_config.get_app_config()

        if app_config.minimize_to_tray_on_close:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "程序已最小化到托盘",
                "点击托盘图标可恢复窗口",
                QSystemTrayIcon.Information,
                2000
            )
            return

        # 正常退出
        size = self.size()
        window_size = f"{size.width()}x{size.height()}"
        pos = self.pos()
        window_position = f"{pos.x()},{pos.y()}"

        app_config.window_size = window_size
        app_config.window_position = window_position
        global_config.save_all_configs()

        # 隐藏托盘
        self.tray_icon.hide()

        # 接受关闭事件
        event.accept()

        # 触发全局退出
        QCoreApplication.instance().quit()

    def load_devices(self):
        while self.device_buttons_layout.count():
            item = self.device_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        devices = global_config.get_app_config().devices
        for i, device in enumerate(devices):
            device_btn = NavigationButton(device.device_name, "assets/icons/browser.svg")
            device_btn.setObjectName("navButton")
            device_btn_id = f"{device.device_name}_{i}"
            device_btn.setProperty("device_btn_id", device_btn_id)
            device_btn.clicked.connect(lambda checked, btn_id=device_btn_id, name=device.device_name:
                                       self.show_device_page(name, btn_id))
            self.device_buttons_layout.addWidget(device_btn)

            if device.device_name not in self.device_pages:
                self.device_pages[device.device_name] = DeviceInfoPage(device.device_name)

        self.update_scroll_area_visibility()

    def update_button_states(self):
        for button in self.static_buttons:
            is_active = (self.current_page == button.objectName())
            button.setChecked(is_active)

        for i in range(self.device_buttons_layout.count()):
            widget = self.device_buttons_layout.itemAt(i).widget()
            if widget:
                is_active = (self.current_page is None and
                             widget.property("device_btn_id") == self.current_button_id)
                widget.setChecked(is_active)

    def show_device_page_by_name(self, device_name: str):
        """
        根据设备名称查找对应的导航按钮并显示其页面。
        这是提供给外部组件（如DeviceCard）调用的公共接口。
        """
        target_button_id = None
        # 遍历设备按钮布局，找到与名称匹配的按钮
        for i in range(self.device_buttons_layout.count()):
            widget = self.device_buttons_layout.itemAt(i).widget()
            # NavigationButton的文本或工具提示就是设备名称
            if widget and widget.toolTip() == device_name:
                target_button_id = widget.property("device_btn_id")
                break  # 找到第一个匹配项后即可退出

        if target_button_id:
            # 如果找到了按钮ID，则调用现有的内部方法来显示页面
            self.show_device_page(device_name, target_button_id)
        else:
            # 如果由于某种原因找不到按钮（例如，UI未同步），则打印警告并返回主页
            print(f"警告: 未能为设备 '{device_name}' 找到对应的导航按钮。将导航至主页。")
            self.show_page("home")

    def show_page(self, page_name):
        self.current_page = page_name
        self.current_device = None
        self.current_button_id = None
        self.update_button_states()
        self.clear_content()
        if page_name in self.pages:
            self.page_layout.addWidget(self.pages[page_name])
            self.pages[page_name].show()

    def show_device_page(self, device_name, button_id):
        self.current_page = None
        self.current_device = device_name
        self.current_button_id = button_id
        self.update_button_states()
        self.clear_content()
        if device_name not in self.device_pages:
            self.device_pages[device_name] = DeviceInfoPage(device_name)

        self.page_layout.addWidget(self.device_pages[device_name])
        self.device_pages[device_name].show()

    def open_add_device_dialog(self):
        dialog = AddDeviceDialog(global_config, self)
        dialog.delete_devices_signal.connect(self.on_device_deleted)

        result = dialog.exec_()
        if result:
            self.load_devices()
            self.pages["home"].device_added.emit()

        self.update_button_states()

    def update_scroll_area_visibility(self):
        devices = global_config.get_app_config().devices
        button_height = 60
        separator_height = 2

        fixed_elements_count = len(self.static_buttons) + 1
        separators_count = 3

        fixed_height = (fixed_elements_count * button_height) + (separators_count * separator_height)
        window_margin = 20

        available_height = self.height() - fixed_height - window_margin
        required_height = len(devices) * button_height

        if len(devices) > 0:
            self.device_scroll_area.setVisible(True)
            effective_height = max(0, available_height)

            if required_height < effective_height:
                self.device_scroll_area.setFixedHeight(required_height)
            else:
                self.device_scroll_area.setFixedHeight(effective_height)
        else:
            self.device_scroll_area.setVisible(False)
            self.device_scroll_area.setFixedHeight(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_scroll_area_visibility()

    def on_device_deleted(self):
        self.refresh_device_list()
        if "home" in self.pages:
            self.pages["home"].load_devices()

    def refresh_device_list(self):
        self.load_devices()

    def clear_content(self):
        while self.page_layout.count():
            item = self.page_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                self.page_layout.removeWidget(widget)

    def show_previous_device_or_home(self, deleted_device_name):
        try:
            if deleted_device_name in self.device_pages:
                self.device_pages[deleted_device_name].deleteLater()
                del self.device_pages[deleted_device_name]

            self.refresh_device_list()
            devices = global_config.get_app_config().devices

            if devices:
                first_device = devices[0]
                first_button_id = f"{first_device.device_name}_0"
                self.show_device_page(first_device.device_name, first_button_id)
            else:
                self.show_page("home")
        except Exception as e:
            print(f"Error navigating after device deletion: {e}")
            self.show_page("home")