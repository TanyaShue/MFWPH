from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                               QLabel, QLineEdit, QPushButton,
                               QWidget, QGroupBox, QScrollArea,
                               QMessageBox, QStackedWidget)
from maa.define import (MaaAdbScreencapMethodEnum, MaaAdbInputMethodEnum,
                        MaaWin32ScreencapMethodEnum)
from maa.toolkit import Toolkit

from app.models.config.app_config import DeviceConfig, AdbDevice, Win32Device, DeviceType
from app.models.logging.log_manager import log_manager
from app.components.no_wheel_ComboBox import NoWheelComboBox
import re
import ast

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
                logger.debug(f"hr: {devices}")
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
        self.setMinimumSize(550, 550)  # 稍微增加了窗口大小，提供更好的视觉体验

        self.init_ui()
        self.fill_device_data()

        # 连接名称输入框的焦点事件，用于自动处理特殊字符
        self.name_edit.focusOutEvent = self.name_edit_focus_out

    def init_ui(self):
        # 设置主布局和边距
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)  # 增加窗口边距
        main_layout.setSpacing(12)  # 设置垂直间距

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setObjectName("addDeviceScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.NoFrame)  # 移除边框，使界面更简洁

        scroll_content = QWidget()
        scroll_content.setObjectName("scroll_content")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 10, 0)  # 内容区右侧预留滚动条空间
        scroll_layout.setSpacing(15)  # 组之间间距增加

        # 定义统一的标签宽度和字段宽度
        LABEL_WIDTH = 100  # 所有标签统一宽度
        FIELD_WIDTH = 300  # 所有输入字段统一宽度

        # 设备类型选择区域
        device_type_group = QGroupBox("设备类型")
        device_type_group.setObjectName("addDeviceGroupBox")
        device_type_layout = QFormLayout(device_type_group)
        device_type_layout.setContentsMargins(15, 15, 15, 15)  # 组内边距增加
        device_type_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        device_type_layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸

        # 创建标签并设置固定宽度
        type_label = QLabel("控制器类型:")
        type_label.setFixedWidth(LABEL_WIDTH)

        # 创建控制器类型下拉框并设置固定宽度
        self.controller_type_combo = NoWheelComboBox()
        self.controller_type_combo.setFixedWidth(FIELD_WIDTH)
        self.controller_type_combo.addItem("ADB设备(模拟器或手机连接)", DeviceType.ADB)
        self.controller_type_combo.addItem("Win32窗口(window窗口)", DeviceType.WIN32)
        self.controller_type_combo.currentIndexChanged.connect(self.controller_type_changed)

        device_type_layout.addRow(type_label, self.controller_type_combo)
        scroll_layout.addWidget(device_type_group)

        # 设备搜索区域
        self.search_group = QGroupBox("设备搜索")
        self.search_group.setObjectName("addDeviceGroupBox")
        search_layout = QVBoxLayout(self.search_group)
        search_layout.setContentsMargins(15, 15, 15, 15)
        search_layout.setSpacing(10)

        # 搜索按钮和状态布局 - 使用FormLayout保持对齐
        search_btn_form = QFormLayout()
        search_btn_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        search_btn_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        # 创建搜索标签并设置固定宽度
        search_label = QLabel("搜索设备:")
        search_label.setFixedWidth(LABEL_WIDTH)

        # 创建搜索按钮和状态的容器
        search_btn_container = QWidget()
        search_btn_layout = QHBoxLayout(search_btn_container)
        search_btn_layout.setContentsMargins(0, 0, 0, 0)
        search_btn_layout.setSpacing(10)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setIcon(QIcon("assets/icons/search.svg"))
        self.search_btn.setObjectName("secondaryButton")
        self.search_btn.setFixedWidth(100)  # 设置固定按钮宽度
        self.search_btn.clicked.connect(self.search_devices)

        self.search_status = QLabel("未搜索")
        self.search_status.setStyleSheet("color: #666;")  # 状态文本颜色调整，增加可辨识度

        search_btn_layout.addWidget(self.search_btn)
        search_btn_layout.addWidget(self.search_status)
        search_btn_layout.addStretch()

        # 添加到表单布局，确保对齐
        search_btn_form.addRow(search_label, search_btn_container)
        search_layout.addLayout(search_btn_form)

        # 设备选择布局 - 使用FormLayout确保标签对齐
        device_select_layout = QFormLayout()
        device_select_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        device_select_layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸

        # 创建标签并设置固定宽度
        device_label = QLabel("发现的设备:")
        device_label.setFixedWidth(LABEL_WIDTH)

        self.device_combo = NoWheelComboBox()
        self.device_combo.setFixedWidth(FIELD_WIDTH)  # 固定宽度，确保与其他输入字段对齐
        self.device_combo.currentIndexChanged.connect(self.device_selected)

        device_select_layout.addRow(device_label, self.device_combo)
        search_layout.addLayout(device_select_layout)

        scroll_layout.addWidget(self.search_group)

        # 设备基本信息 - 使用堆叠部件以便切换不同类型的控制器配置
        self.info_group = QGroupBox("设备信息")
        self.info_group.setObjectName("addDeviceGroupBox")
        info_layout = QVBoxLayout(self.info_group)
        info_layout.setContentsMargins(15, 15, 15, 15)
        info_layout.setSpacing(12)

        # 设备名称 - 对所有设备类型都适用
        name_form = QFormLayout()
        name_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        name_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸

        # 创建标签并设置固定宽度
        name_label = QLabel("设备名称:")
        name_label.setFixedWidth(LABEL_WIDTH)

        self.name_edit = QLineEdit()
        self.name_edit.setFixedWidth(FIELD_WIDTH)
        self.name_edit.setToolTip("设备名称不能包含特殊符号和空格，这些字符将被替换为下划线")

        name_form.addRow(name_label, self.name_edit)
        info_layout.addLayout(name_form)

        # 控制器配置堆叠部件
        self.controller_stack = QStackedWidget()

        # ADB设备配置页
        adb_widget = QWidget()
        adb_form = QFormLayout(adb_widget)
        adb_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        adb_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸
        adb_form.setSpacing(10)
        adb_form.setContentsMargins(0, 5, 0, 5)  # 减少边距，因为已经在父容器中设置

        # 创建ADB路径标签和输入框
        adb_path_label = QLabel("ADB 路径:")
        adb_path_label.setFixedWidth(LABEL_WIDTH)
        self.adb_path_edit = QLineEdit()
        self.adb_path_edit.setFixedWidth(FIELD_WIDTH)

        # 创建ADB地址标签和输入框
        adb_addr_label = QLabel("ADB 地址:")
        adb_addr_label.setFixedWidth(LABEL_WIDTH)
        self.adb_address_edit = QLineEdit()
        self.adb_address_edit.setFixedWidth(FIELD_WIDTH)

        # 创建截图方法标签和下拉框
        screenshot_label = QLabel("截图方法:")
        screenshot_label.setFixedWidth(LABEL_WIDTH)
        self.screenshot_method_combo = NoWheelComboBox()
        self.screenshot_method_combo.setFixedWidth(FIELD_WIDTH)
        self._populate_adb_screencap_combo()

        # 创建输入方法标签和下拉框
        input_label = QLabel("输入方法:")
        input_label.setFixedWidth(LABEL_WIDTH)
        self.input_method_combo = NoWheelComboBox()
        self.input_method_combo.setFixedWidth(FIELD_WIDTH)
        self._populate_adb_input_combo()

        # 创建Agent路径标签和输入框
        agent_label = QLabel("Agent 路径:")
        agent_label.setFixedWidth(LABEL_WIDTH)
        self.agent_path_edit = QLineEdit()
        self.agent_path_edit.setFixedWidth(FIELD_WIDTH)

        # 创建配置标签和输入框
        config_label = QLabel("配置:")
        config_label.setFixedWidth(LABEL_WIDTH)
        self.config_edit = QLineEdit()
        self.config_edit.setFixedWidth(FIELD_WIDTH)

        # 添加表单行，使用显式标签确保对齐
        adb_form.addRow(adb_path_label, self.adb_path_edit)
        adb_form.addRow(adb_addr_label, self.adb_address_edit)
        adb_form.addRow(screenshot_label, self.screenshot_method_combo)
        adb_form.addRow(input_label, self.input_method_combo)
        adb_form.addRow(agent_label, self.agent_path_edit)
        adb_form.addRow(config_label, self.config_edit)
        self.controller_stack.addWidget(adb_widget)

        # Win32设备配置页
        win32_widget = QWidget()
        win32_form = QFormLayout(win32_widget)
        win32_form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        win32_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸
        win32_form.setSpacing(10)
        win32_form.setContentsMargins(0, 5, 0, 5)  # 减少边距

        # 创建窗口句柄标签和输入框
        hwnd_label = QLabel("窗口句柄 (hWnd):")
        hwnd_label.setFixedWidth(LABEL_WIDTH)
        self.hwnd_edit = QLineEdit()
        self.hwnd_edit.setFixedWidth(FIELD_WIDTH)

        # 创建Win32截图方法标签和下拉框
        win32_screenshot_label = QLabel("截图方法:")
        win32_screenshot_label.setFixedWidth(LABEL_WIDTH)
        self.win32_screenshot_method_combo = NoWheelComboBox()
        self.win32_screenshot_method_combo.setFixedWidth(FIELD_WIDTH)
        self._populate_win32_screencap_combo()

        # 创建Win32输入方法标签和下拉框
        win32_input_label = QLabel("输入方法:")
        win32_input_label.setFixedWidth(LABEL_WIDTH)
        self.win32_input_method_combo = NoWheelComboBox()
        self.win32_input_method_combo.setFixedWidth(FIELD_WIDTH)
        self._populate_win32_input_combo()

        # 添加表单行，使用显式标签确保对齐
        win32_form.addRow(hwnd_label, self.hwnd_edit)
        win32_form.addRow(win32_screenshot_label, self.win32_screenshot_method_combo)
        win32_form.addRow(win32_input_label, self.win32_input_method_combo)
        self.controller_stack.addWidget(win32_widget)

        info_layout.addWidget(self.controller_stack)
        scroll_layout.addWidget(self.info_group)

        # 高级设置
        advanced_group = QGroupBox("高级设置")
        advanced_group.setObjectName("addDeviceGroupBox")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setContentsMargins(15, 15, 15, 15)
        advanced_layout.setSpacing(10)

        # 命令设置
        command_layout = QFormLayout()
        command_layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # 标签左对齐
        command_layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)  # 保持字段尺寸
        command_layout.setSpacing(10)

        # 创建启动前命令标签和输入框
        pre_command_label = QLabel("启动前命令:")
        pre_command_label.setFixedWidth(LABEL_WIDTH)
        self.pre_command_edit = QLineEdit()
        self.pre_command_edit.setFixedWidth(FIELD_WIDTH)

        # 创建启动后命令标签和输入框
        post_command_label = QLabel("启动后命令:")
        post_command_label.setFixedWidth(LABEL_WIDTH)
        self.post_command_edit = QLineEdit()
        self.post_command_edit.setFixedWidth(FIELD_WIDTH)

        # 添加表单行，使用显式标签确保对齐
        command_layout.addRow(pre_command_label, self.pre_command_edit)
        command_layout.addRow(post_command_label, self.post_command_edit)
        advanced_layout.addLayout(command_layout)

        scroll_layout.addWidget(advanced_group)
        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # 底部按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 10, 0, 0)  # 顶部增加间距
        buttons_layout.setSpacing(10)  # 按钮间距

        # 如果是编辑模式，添加删除按钮
        if self.edit_mode:
            delete_btn = QPushButton("删除")
            delete_btn.setIcon(QIcon("assets/icons/delete.svg"))  # 假设有删除图标
            delete_btn.setMinimumWidth(100)  # 设置统一按钮宽度
            delete_btn.clicked.connect(self.delete_device)
            buttons_layout.addWidget(delete_btn)

        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("保存")
        save_btn.setMinimumWidth(100)
        save_btn.setObjectName("primaryButton")  # 假设有主按钮样式
        save_btn.clicked.connect(self.save_device)

        buttons_layout.addWidget(cancel_btn)
        buttons_layout.addWidget(save_btn)

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

    def name_edit_focus_out(self, event):
        """当设备名称输入框失去焦点时自动处理特殊符号和空格"""
        current_text = self.name_edit.text()
        sanitized_text = self._sanitize_device_name(current_text)
        if current_text != sanitized_text:
            self.name_edit.setText(sanitized_text)
        super(QLineEdit, self.name_edit).focusOutEvent(event) if hasattr(super(QLineEdit, self.name_edit),
                                                                         'focusOutEvent') else None

    def _sanitize_device_name(self, name):
        """处理设备名称，将特殊符号和空格替换为下划线"""
        # 使用正则表达式替换特殊字符和空格，只保留字母、数字、中文和下划线(不包括空格)
        sanitized_name = re.sub(r'[^\w\u4e00-\u9fa5]|[\s]', '_', name)
        return sanitized_name

    def controller_type_changed(self, index):
        """当控制器类型变更时的处理函数"""
        self.controller_stack.setCurrentIndex(index)

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

        # 填充命令
        if hasattr(self.device_config, 'start_command'):
            self.pre_command_edit.setText(self.device_config.start_command)
        if hasattr(self.device_config, 'stop_command'):
            self.post_command_edit.setText(self.device_config.stop_command)

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

    def search_devices(self):
        """搜索设备"""
        self.search_btn.setEnabled(False)
        self.search_status.setText("正在搜索...")
        self.search_thread = DeviceSearchThread(self.controller_type_combo.currentData())
        self.search_thread.devices_found.connect(self.on_devices_found)
        self.search_thread.search_error.connect(self.on_search_error)
        self.search_thread.finished.connect(self.on_search_completed)
        self.search_thread.start()

    def on_devices_found(self, devices):
        """处理找到的设备"""
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
        """处理搜索错误"""
        self.device_combo.clear()
        self.device_combo.addItem("搜索出错")
        self.search_status.setText(f"搜索出错: {error_msg}")

    def on_search_completed(self):
        """搜索完成后恢复按钮状态"""
        self.search_btn.setEnabled(True)
        self.search_thread = None

    def device_selected(self, index):
        """处理设备选择"""
        # 获取当前选择的控制器类型
        controller_type = self.controller_type_combo.currentData()

        if 0 <= index < len(self.found_devices):
            device = self.found_devices[index]

            # 设置通用字段
            if not self.name_edit.text():
                if controller_type == DeviceType.ADB:
                    # 自动生成的设备名称也需要处理特殊符号
                    device_name = f"设备 {device.address}"
                    self.name_edit.setText(self._sanitize_device_name(device_name))
                elif controller_type == DeviceType.WIN32:
                    window_title = getattr(device, 'title', f"窗口 {device}")
                    # 自动生成的窗口名称也需要处理特殊符号
                    self.name_edit.setText(self._sanitize_device_name(window_title))

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

            # 获取设备名称并进行处理
            device_name = self.name_edit.text()
            sanitized_device_name = self._sanitize_device_name(device_name)

            # 直接更新设备名称文本框，不使用弹窗提示
            if device_name != sanitized_device_name:
                self.name_edit.setText(sanitized_device_name)

            # 获取当前选择的控制器类型
            controller_type = self.controller_type_combo.currentData()

            # 根据控制器类型获取和验证输入
            if controller_type == DeviceType.ADB:
                adb_address = self.adb_address_edit.text()
                if not adb_address:
                    QMessageBox.warning(self, "输入错误", "ADB地址不能为空")
                    return

                # if self.adb_address_exists(adb_address):
                #     QMessageBox.warning(self, "设备已存在", "该设备已被加入，请勿重复添加")
                #     return

                # 尝试解析配置文本为字典，如果解析失败则使用空字典
                try:
                    config_text = self.config_edit.text()
                    config_dict = ast.literal_eval(config_text)
                    # config_dict = json.loads(config_text) if config_text.strip() != "" else {}
                except Exception as e:
                    print("配置数据格式错误，无法解析为字典。", e)
                    config_dict = {}

                # 获取下拉框中选择的枚举值
                screencap_method = self.screenshot_method_combo.currentData()
                input_method = self.input_method_combo.currentData()

                # 创建ADB控制器配置
                controller_config = AdbDevice(
                    name=sanitized_device_name,  # 使用处理过的设备名称
                    adb_path=self.adb_path_edit.text(),
                    address=adb_address,
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

            if self.edit_mode and self.device_config:
                # 更新设备配置
                self.device_config.device_name = sanitized_device_name  # 使用处理过的设备名称
                self.device_config.device_type = controller_type
                self.device_config.controller_config = controller_config
                self.device_config.start_command = self.pre_command_edit.text()
                if hasattr(self.device_config, 'stop_command'):
                    self.device_config.stop_command = self.post_command_edit.text()
            else:
                # 创建新设备配置
                new_config = DeviceConfig(
                    device_name=sanitized_device_name,  # 使用处理过的设备名称
                    device_type=controller_type,
                    controller_config=controller_config,
                    start_command=self.pre_command_edit.text()
                )
                self.global_config.app_config.devices.append(new_config)

            self.global_config.save_all_configs()
            self.accept()

        except Exception as e:
            print(f"保存设备时出错: {e}")
            QMessageBox.critical(self, "错误", f"保存设备时出错: {e}")

    def adb_address_exists(self, new_address):
        devices = self.global_config.app_config.devices
        return any(new_address == dev.controller_config.address for dev in devices)

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