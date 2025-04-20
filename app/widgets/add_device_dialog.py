from PySide6.QtCore import Qt, QTime, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QLineEdit, QPushButton,
                               QWidget, QCheckBox, QGroupBox, QScrollArea,
                               QTimeEdit, QMessageBox, QStackedWidget)
from maa.toolkit import Toolkit
# Import the necessary enums from maa.define
from maa.define import (MaaAdbScreencapMethodEnum, MaaAdbInputMethodEnum,
                        MaaWin32ScreencapMethodEnum, MaaWin32InputMethodEnum)

from app.models.config.app_config import DeviceConfig, AdbDevice, Win32Device, DeviceType
from app.models.logging.log_manager import log_manager
from app.widgets.no_wheel_QComboBox import NoWheelComboBox

logger = log_manager.get_app_logger()


class DeviceSearchThread(QThread):
    """用于后台搜索设备的线程"""
    devices_found = Signal(list)
    search_error = Signal(str)

    def __init__(self, search_type):
        super().__init__()
        self.search_type = search_type

    def run(self):
        try:
            devices = None
            if self.search_type == DeviceType.ADB:
                devices = Toolkit.find_adb_devices()
            elif self.search_type == DeviceType.WIN32:
                devices = Toolkit.find_desktop_windows()
                devices = [device for device in devices if device.window_name != '']
            logger.debug(f"搜索发现:{len(devices)}个设备:{devices}")
            self.devices_found.emit(devices)
        except Exception as e:
            self.search_error.emit(str(e))


class AddDeviceDialog(QDialog):
    delete_devices_signal = Signal()

    def __init__(self, global_config, parent=None, edit_mode=False, device_config=None):
        super().__init__(parent)
        self.global_config = global_config
        self.found_devices = []
        self.search_thread = None
        self.edit_mode = edit_mode
        self.device_config = device_config
        self.schedule_time_widgets = []  # 存储各个时间组件
        self.time_container_layouts = []  # 存储各行容器的布局

        self.setObjectName("addDeviceDialog")
        self.setWindowTitle("编辑设备" if edit_mode else "添加设备")
        self.setMinimumSize(500, 500)

        self.init_ui()

        # 根据模式填充数据或添加默认时间组件
        if edit_mode and device_config:
            self.fill_device_data()
        else:
            self.add_time_selection_widget()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setObjectName("addDeviceScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_layout = QVBoxLayout(scroll_content)

        # 设备类型选择区域
        device_type_group = QGroupBox("设备类型")
        device_type_group.setObjectName("addDeviceGroupBox")
        device_type_layout = QHBoxLayout()
        device_type_layout.addWidget(QLabel("控制器类型:"))
        self.controller_type_combo = NoWheelComboBox()
        self.controller_type_combo.addItem("ADB设备", DeviceType.ADB)
        self.controller_type_combo.addItem("Win32窗口", DeviceType.WIN32)
        self.controller_type_combo.currentIndexChanged.connect(self.controller_type_changed)
        device_type_layout.addWidget(self.controller_type_combo)
        device_type_layout.addStretch()
        device_type_group.setLayout(device_type_layout)
        scroll_layout.addWidget(device_type_group)

        # 设备搜索区域
        self.search_group = QGroupBox("设备搜索")
        self.search_group.setObjectName("addDeviceGroupBox")
        search_layout = QVBoxLayout()
        search_btn_layout = QHBoxLayout()
        self.search_btn = QPushButton("搜索设备")
        self.search_btn.setIcon(QIcon("assets/icons/search.svg"))
        self.search_btn.clicked.connect(self.search_devices)
        self.search_status = QLabel("未搜索")
        search_btn_layout.addWidget(self.search_btn)
        search_btn_layout.addWidget(self.search_status)
        search_btn_layout.addStretch()
        device_select_layout = QHBoxLayout()
        device_select_layout.addWidget(QLabel("发现的设备:"))
        self.device_combo = NoWheelComboBox()
        self.device_combo.setMinimumWidth(250)
        self.device_combo.currentIndexChanged.connect(self.device_selected)
        device_select_layout.addWidget(self.device_combo)
        search_layout.addLayout(search_btn_layout)
        search_layout.addLayout(device_select_layout)
        self.search_group.setLayout(search_layout)
        scroll_layout.addWidget(self.search_group)

        # 设备基本信息 - 使用堆叠部件以便切换不同类型的控制器配置
        self.info_group = QGroupBox("设备信息")
        self.info_group.setObjectName("addDeviceGroupBox")
        info_layout = QVBoxLayout()

        # 设备名称 - 对所有设备类型都适用
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("设备名称:"))
        self.name_edit = QLineEdit()
        name_layout.addWidget(self.name_edit)
        info_layout.addLayout(name_layout)

        # 控制器配置堆叠部件
        self.controller_stack = QStackedWidget()

        # ADB设备配置页
        adb_widget = QWidget()
        adb_form = QFormLayout(adb_widget)
        self.adb_path_edit = QLineEdit()
        self.adb_address_edit = QLineEdit()

        # 替换文本框为下拉框: ADB设备截图方法
        self.screenshot_method_combo = NoWheelComboBox()
        self._populate_adb_screencap_combo()

        # 替换文本框为下拉框: ADB设备输入方法
        self.input_method_combo = NoWheelComboBox()
        self._populate_adb_input_combo()

        self.config_edit = QLineEdit()
        self.agent_path_edit = QLineEdit()

        adb_form.addRow("ADB 路径:", self.adb_path_edit)
        adb_form.addRow("ADB 地址:", self.adb_address_edit)
        adb_form.addRow("截图方法:", self.screenshot_method_combo)
        adb_form.addRow("输入方法:", self.input_method_combo)
        adb_form.addRow("Agent 路径:", self.agent_path_edit)
        adb_form.addRow("配置:", self.config_edit)
        self.controller_stack.addWidget(adb_widget)

        # Win32设备配置页
        win32_widget = QWidget()
        win32_form = QFormLayout(win32_widget)
        self.hwnd_edit = QLineEdit()

        # 替换文本框为下拉框: Win32设备截图方法
        self.win32_screenshot_method_combo = NoWheelComboBox()
        self._populate_win32_screencap_combo()

        # 替换文本框为下拉框: Win32设备输入方法
        self.win32_input_method_combo = NoWheelComboBox()
        self._populate_win32_input_combo()

        win32_form.addRow("窗口句柄 (hWnd):", self.hwnd_edit)
        win32_form.addRow("截图方法:", self.win32_screenshot_method_combo)
        win32_form.addRow("输入方法:", self.win32_input_method_combo)
        self.controller_stack.addWidget(win32_widget)

        info_layout.addWidget(self.controller_stack)
        self.info_group.setLayout(info_layout)
        scroll_layout.addWidget(self.info_group)

        # 高级设置
        advanced_group = QGroupBox("高级设置")
        advanced_group.setObjectName("addDeviceGroupBox")
        advanced_layout = QVBoxLayout()

        # 定时启动区域
        self.schedule_layout = QVBoxLayout()
        schedule_header = QHBoxLayout()
        self.schedule_enabled = QCheckBox("启用定时启动")
        self.schedule_enabled.toggled.connect(self.toggle_schedule_widgets)
        schedule_header.addWidget(self.schedule_enabled)
        self.add_time_btn = QPushButton()
        self.add_time_btn.setIcon(QIcon("assets/icons/add-time.svg"))
        self.add_time_btn.setFixedSize(24, 24)
        self.add_time_btn.clicked.connect(self.add_time_selection_widget)
        self.add_time_btn.setToolTip("添加启动时间")
        schedule_header.addWidget(self.add_time_btn)
        schedule_header.addStretch()
        self.schedule_layout.addLayout(schedule_header)

        # 使用一个容器控件管理所有时间组件
        self.time_container_widget = QWidget()
        self.time_rows_container = QVBoxLayout(self.time_container_widget)
        self.schedule_layout.addWidget(self.time_container_widget)

        # 初始化第一行容器
        self.add_new_time_container()

        advanced_layout.addLayout(self.schedule_layout)

        # 命令设置
        command_layout = QFormLayout()
        self.pre_command_edit = QLineEdit()
        self.post_command_edit = QLineEdit()
        command_layout.addRow("启动前命令:", self.pre_command_edit)
        command_layout.addRow("启动后命令:", self.post_command_edit)
        advanced_layout.addSpacing(10)
        advanced_layout.addLayout(command_layout)

        advanced_group.setLayout(advanced_layout)
        scroll_layout.addWidget(advanced_group)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # 底部按钮
        buttons_layout = QHBoxLayout()
        # 如果是编辑模式，添加删除按钮
        if self.edit_mode:
            delete_btn = QPushButton("删除")
            delete_btn.clicked.connect(self.delete_device)
            buttons_layout.addWidget(delete_btn)
        buttons_layout.addStretch()
        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        save_btn.clicked.connect(self.save_device)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        main_layout.addLayout(buttons_layout)

    def _populate_adb_screencap_combo(self):
        """填充ADB截图方法下拉框"""
        # 添加各个枚举值作为选项
        self.screenshot_method_combo.addItem("默认 (Default)", MaaAdbScreencapMethodEnum.Default)
        self.screenshot_method_combo.addItem("全部 (All)", MaaAdbScreencapMethodEnum.All)
        self.screenshot_method_combo.addItem("EncodeToFileAndPull", MaaAdbScreencapMethodEnum.EncodeToFileAndPull)
        self.screenshot_method_combo.addItem("Encode", MaaAdbScreencapMethodEnum.Encode)
        self.screenshot_method_combo.addItem("RawWithGzip", MaaAdbScreencapMethodEnum.RawWithGzip)
        self.screenshot_method_combo.addItem("RawByNetcat", MaaAdbScreencapMethodEnum.RawByNetcat)
        self.screenshot_method_combo.addItem("MinicapDirect", MaaAdbScreencapMethodEnum.MinicapDirect)
        self.screenshot_method_combo.addItem("MinicapStream", MaaAdbScreencapMethodEnum.MinicapStream)
        self.screenshot_method_combo.addItem("EmulatorExtras", MaaAdbScreencapMethodEnum.EmulatorExtras)

    def _populate_adb_input_combo(self):
        """填充ADB输入方法下拉框"""
        # 添加各个枚举值作为选项
        self.input_method_combo.addItem("默认 (Default)", MaaAdbInputMethodEnum.Default)
        self.input_method_combo.addItem("全部 (All)", MaaAdbInputMethodEnum.All)
        self.input_method_combo.addItem("AdbShell", MaaAdbInputMethodEnum.AdbShell)
        self.input_method_combo.addItem("MinitouchAndAdbKey", MaaAdbInputMethodEnum.MinitouchAndAdbKey)
        self.input_method_combo.addItem("Maatouch", MaaAdbInputMethodEnum.Maatouch)
        self.input_method_combo.addItem("EmulatorExtras", MaaAdbInputMethodEnum.EmulatorExtras)

    def _populate_win32_screencap_combo(self):
        """填充Win32截图方法下拉框"""
        # Win32截图方法不使用位运算组合，而是直接选择一种方法
        self.win32_screenshot_method_combo.addItem("GDI", MaaWin32ScreencapMethodEnum.GDI)
        self.win32_screenshot_method_combo.addItem("FramePool", MaaWin32ScreencapMethodEnum.FramePool)
        self.win32_screenshot_method_combo.addItem("DXGI_DesktopDup", MaaWin32ScreencapMethodEnum.DXGI_DesktopDup)

    def _populate_win32_input_combo(self):
        """填充Win32输入方法下拉框"""
        # Win32输入方法只有两种选择
        self.win32_input_method_combo.addItem("Seize", 1)  # 对应枚举值为1
        self.win32_input_method_combo.addItem("SendMessage", 2)  # 对应枚举值为2

    def _find_combo_index_by_value(self, combo, value):
        """根据值查找下拉框中的索引位置"""
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                return i
        # 如果找不到匹配的值，则返回默认值的索引
        for i in range(combo.count()):
            if 'Default' in combo.itemText(i):
                return i
        return 0  # 如果没有默认值，则返回第一个选项

    def controller_type_changed(self, index):
        """当控制器类型变更时的处理函数"""
        self.controller_stack.setCurrentIndex(index)

    def toggle_schedule_widgets(self, enabled):
        """统一控制定时启动区域的使能状态"""
        self.add_time_btn.setEnabled(enabled)
        self.time_container_widget.setEnabled(enabled)

    def add_new_time_container(self):
        """创建并添加一行时间组件的容器"""
        container_widget = QWidget()
        container_layout = QHBoxLayout(container_widget)
        container_layout.setContentsMargins(0, 5, 0, 0)
        container_layout.setSpacing(5)
        container_layout.setAlignment(Qt.AlignLeft)
        self.time_rows_container.addWidget(container_widget)
        self.time_container_layouts.append(container_layout)
        return container_layout

    def add_time_selection_widget(self):
        """添加一个时间选择组件到当前行容器中"""
        if self.schedule_time_widgets and len(self.schedule_time_widgets) % 4 == 0:
            current_container = self.add_new_time_container()
        else:
            current_container = self.time_container_layouts[-1]
        time_widget = QWidget()
        time_layout = QHBoxLayout(time_widget)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(2)
        time_edit = QTimeEdit()
        time_edit.setObjectName("time_edit")
        time_edit.setTime(QTime(8, 0))
        del_btn = QPushButton()
        del_btn.setIcon(QIcon("assets/icons/delete.svg"))
        del_btn.setFixedSize(20, 20)
        del_btn.clicked.connect(lambda: self.remove_time_widget(time_widget))
        del_btn.setToolTip("删除此启动时间")
        time_layout.addWidget(time_edit)
        time_layout.addWidget(del_btn)
        time_widget.setFixedWidth(100)
        current_container.addWidget(time_widget)
        self.schedule_time_widgets.append(time_widget)
        if len(self.schedule_time_widgets) == 1:
            del_btn.setEnabled(False)
            self.first_time_del_btn = del_btn
        elif len(self.schedule_time_widgets) > 1 and hasattr(self, 'first_time_del_btn'):
            self.first_time_del_btn.setEnabled(True)
        return time_widget

    def remove_time_widget(self, widget):
        """移除指定的时间选择组件，并重新整理布局"""
        if len(self.schedule_time_widgets) > 1:
            self.schedule_time_widgets.remove(widget)
            for container in self.time_container_layouts:
                for i in range(container.count()):
                    if container.itemAt(i).widget() == widget:
                        container.removeWidget(widget)
                        widget.deleteLater()
                        break
            self.reorganize_time_widgets()
            if len(self.schedule_time_widgets) == 1:
                last_widget = self.schedule_time_widgets[0]
                del_btn = last_widget.findChild(QPushButton)
                if del_btn:
                    del_btn.setEnabled(False)
                    self.first_time_del_btn = del_btn

    def reorganize_time_widgets(self):
        """清除所有旧容器后，重新按照每行最多4个组件组织时间组件"""
        for container in self.time_container_layouts:
            container_widget = container.parentWidget()
            self.time_rows_container.removeWidget(container_widget)
            container_widget.deleteLater()
        self.time_container_layouts = []
        current_container = self.add_new_time_container()
        for i, widget in enumerate(self.schedule_time_widgets):
            if i and i % 4 == 0:
                current_container = self.add_new_time_container()
            current_container.addWidget(widget)

    def fill_device_data(self):
        """将已有设备数据填充到表单中"""
        if not self.device_config:
            return

        # 设置设备名称
        self.name_edit.setText(self.device_config.device_name)

        # 设置控制器类型
        device_type = self.device_config.device_type
        if device_type == DeviceType.ADB:
            self.controller_type_combo.setCurrentIndex(0)
            controller = self.device_config.controller_config

            # 填充ADB设备信息
            self.adb_path_edit.setText(controller.adb_path)
            self.adb_address_edit.setText(controller.address)

            # 设置截图方法下拉框
            screencap_method = controller.screencap_methods
            index = self._find_combo_index_by_value(self.screenshot_method_combo, screencap_method)
            self.screenshot_method_combo.setCurrentIndex(index)

            # 设置输入方法下拉框
            input_method = controller.input_methods
            index = self._find_combo_index_by_value(self.input_method_combo, input_method)
            self.input_method_combo.setCurrentIndex(index)

            # 填充新增的agent_path
            if hasattr(controller, 'agent_path') and controller.agent_path:
                self.agent_path_edit.setText(controller.agent_path)

            import json
            config_str = json.dumps(controller.config)
            self.config_edit.setText(config_str)
        elif device_type == DeviceType.WIN32:
            self.controller_type_combo.setCurrentIndex(1)
            controller = self.device_config.controller_config

            # 填充Win32设备信息
            self.hwnd_edit.setText(str(controller.hWnd))

            # 设置Win32截图方法下拉框
            screencap_method = controller.screencap_method
            index = self._find_combo_index_by_value(self.win32_screenshot_method_combo, screencap_method)
            self.win32_screenshot_method_combo.setCurrentIndex(index)

            # 设置Win32输入方法下拉框
            input_method = controller.input_method
            index = self._find_combo_index_by_value(self.win32_input_method_combo, input_method)
            self.win32_input_method_combo.setCurrentIndex(index)

        # 填充高级设置
        self.schedule_enabled.setChecked(self.device_config.schedule_enabled)
        self.toggle_schedule_widgets(self.device_config.schedule_enabled)

        # 清除已有的时间组件和容器
        if self.schedule_time_widgets:
            for widget in self.schedule_time_widgets:
                parent = widget.parentWidget().layout()
                parent.removeWidget(widget)
                widget.deleteLater()
            self.schedule_time_widgets.clear()
        for container in self.time_container_layouts:
            container_widget = container.parentWidget()
            self.time_rows_container.removeWidget(container_widget)
            container_widget.deleteLater()
        self.time_container_layouts = []
        self.add_new_time_container()

        # 添加已有的定时启动时间，若没有则添加一个默认
        if self.device_config.schedule_time:
            for time_str in self.device_config.schedule_time:
                parts = time_str.split(":")
                if len(parts) == 2:
                    time_widget = self.add_time_selection_widget()
                    time_edit = time_widget.findChild(QTimeEdit)
                    if time_edit:
                        time_edit.setTime(QTime(int(parts[0]), int(parts[1])))
        else:
            self.add_time_selection_widget()

        # 填充命令
        if hasattr(self.device_config, 'start_command'):
            self.pre_command_edit.setText(self.device_config.start_command)
        if hasattr(self.device_config, 'stop_command'):
            self.post_command_edit.setText(self.device_config.stop_command)

    def search_devices(self):
        self.search_btn.setEnabled(False)
        self.search_status.setText("正在搜索...")
        self.search_thread = DeviceSearchThread(self.controller_type_combo.currentData())
        self.search_thread.devices_found.connect(self.on_devices_found)
        self.search_thread.search_error.connect(self.on_search_error)
        self.search_thread.finished.connect(self.on_search_completed)
        self.search_thread.start()

    def on_devices_found(self, devices):
        self.device_combo.clear()
        self.found_devices = devices
        if devices:
            for device in devices:
                text = getattr(device, "address", None) or getattr(device, "window_name", "")
                self.device_combo.addItem(text)
            self.search_status.setText(f"找到 {len(devices)} 个设备")
        else:
            self.device_combo.addItem("未找到设备")
            self.search_status.setText("未找到设备")

    def on_search_error(self, error_msg):
        self.device_combo.clear()
        self.device_combo.addItem("搜索出错")
        self.search_status.setText(f"搜索出错: {error_msg}")

    def on_search_completed(self):
        self.search_btn.setEnabled(True)
        self.search_thread = None

    def device_selected(self, index):
        # 获取当前选择的控制器类型
        controller_type = self.controller_type_combo.currentData()

        if 0 <= index < len(self.found_devices):
            device = self.found_devices[index]

            # 设置通用字段
            if not self.name_edit.text():
                if controller_type == DeviceType.ADB:
                    self.name_edit.setText(f"设备 {device.address}")
                elif controller_type == DeviceType.WIN32:
                    window_title = getattr(device, 'title', f"窗口 {device.hwnd}")
                    self.name_edit.setText(window_title)

            # 根据控制器类型填充相应字段
            if controller_type == DeviceType.ADB:
                # 填充ADB设备字段
                self.adb_address_edit.setText(device.address)
                self.adb_path_edit.setText(str(device.adb_path))

                self.config_edit.setText(str(device.config))
            elif controller_type == DeviceType.WIN32:
                # 填充Win32设备字段
                self.hwnd_edit.setText(str(device.hwnd))

    def save_device(self):
        """保存设备信息"""
        # 检查必填字段
        if not self.name_edit.text():
            QMessageBox.warning(self, "输入错误", "设备名称不能为空")
            return

        try:
            import json

            # 获取当前选择的控制器类型
            controller_type = self.controller_type_combo.currentData()

            # 根据控制器类型获取和验证输入
            if controller_type == DeviceType.ADB:
                if not self.adb_address_edit.text():
                    QMessageBox.warning(self, "输入错误", "ADB地址不能为空")
                    return

                # 尝试解析配置文本为字典，如果解析失败则使用空字典
                try:
                    config_text = self.config_edit.text()
                    config_dict = json.loads(config_text) if config_text.strip() != "" else {}
                except json.JSONDecodeError as e:
                    print("配置数据格式错误，无法解析为字典。", e)
                    config_dict = {}

                # 获取下拉框中选择的枚举值
                screencap_method = self.screenshot_method_combo.currentData()
                input_method = self.input_method_combo.currentData()

                # 创建ADB控制器配置
                controller_config = AdbDevice(
                    name=self.name_edit.text(),
                    adb_path=self.adb_path_edit.text(),
                    address=self.adb_address_edit.text(),
                    screencap_methods=screencap_method,
                    input_methods=input_method,
                    agent_path=self.agent_path_edit.text() or None,
                    config=config_dict
                )
            else:  # WIN32
                if not self.hwnd_edit.text():
                    QMessageBox.warning(self, "输入错误", "窗口句柄不能为空")
                    return

                # 获取下拉框中选择的枚举值
                screencap_method = self.win32_screenshot_method_combo.currentData()
                input_method = self.win32_input_method_combo.currentData()

                # 创建Win32控制器配置
                controller_config = Win32Device(
                    hWnd=int(self.hwnd_edit.text() or "0"),
                    screencap_method=screencap_method,
                    input_method=input_method,
                    notification_handler=None
                )

            # 收集所有定时启动时间
            schedule_times = []
            for widget in self.schedule_time_widgets:
                time_edit = widget.findChild(QTimeEdit)
                if time_edit:
                    schedule_times.append(time_edit.time().toString("hh:mm"))

            if self.edit_mode and self.device_config:
                # 更新设备配置
                self.device_config.device_name = self.name_edit.text()
                self.device_config.device_type = controller_type
                self.device_config.controller_config = controller_config
                self.device_config.schedule_enabled = self.schedule_enabled.isChecked()
                self.device_config.schedule_time = schedule_times
                self.device_config.start_command = self.pre_command_edit.text()
                if hasattr(self.device_config, 'stop_command'):
                    self.device_config.stop_command = self.post_command_edit.text()
            else:
                # 创建新设备配置
                new_config = DeviceConfig(
                    device_name=self.name_edit.text(),
                    device_type=controller_type,
                    controller_config=controller_config,
                    schedule_enabled=self.schedule_enabled.isChecked(),
                    schedule_time=schedule_times,
                    start_command=self.pre_command_edit.text()
                )
                self.global_config.app_config.devices.append(new_config)

            self.global_config.save_all_configs()
            self.accept()

        except Exception as e:
            print(f"保存设备时出错: {e}")
            QMessageBox.critical(self, "错误", f"保存设备时出错: {e}")

    def delete_device(self):
        """删除该设备"""
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除该设备吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                # 从全局配置中删除该设备，假设设备以 device_name 为唯一标识
                self.global_config.app_config.devices = [
                    device for device in self.global_config.app_config.devices
                    if device.device_name != self.device_config.device_name
                ]
                self.global_config.save_all_configs()
                self.delete_devices_signal.emit()
                self.accept()
            except Exception as e:
                print("删除设备时出错: ", e)