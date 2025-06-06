# task_options_widget.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QLineEdit, QSizePolicy
)

from app.components.no_wheel_ComboBox import NoWheelComboBox
from app.models.config.app_config import OptionConfig
from app.models.config.global_config import global_config
from app.models.config.resource_config import SelectOption, BoolOption, InputOption
from app.models.logging.log_manager import log_manager


class TaskOptionsWidget(QFrame):
    """任务选项设置组件，用于显示和配置单个任务的详细选项"""

    # 选项值更新信号
    option_value_changed = Signal(str, str, str, object)  # resource_name, task_name, option_name, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_resource_name = None
        self.current_task_name = None
        self.current_task_config = None
        self.current_device_resource = None
        self.option_widgets = {}
        self.logger = None
        self.init_ui()
        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)
    def init_ui(self):
        """初始化UI"""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # 标题区域
        self.header_widget = QWidget()
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("任务选项设置")
        self.title_label.setObjectName("sectionTitle")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.layout.addWidget(self.header_widget)

        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("separator")
        self.layout.addWidget(separator)

        # 滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)

        # 初始占位符
        self.show_placeholder()

        self.scroll_area.setWidget(self.content_widget)
        self.layout.addWidget(self.scroll_area)

    def show_placeholder(self):
        """显示占位符信息"""
        self._clear_content()

        placeholder = QLabel("请选择一个任务来查看其配置选项")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("placeholderText")
        placeholder.setMinimumHeight(100)

        self.content_layout.addWidget(placeholder)
        self.content_layout.addStretch()

    def show_task_options(self, resource_name, task_name, task_config, device_resource):
        """显示指定任务的选项设置"""
        self.current_resource_name = resource_name
        self.current_task_name = task_name
        self.current_task_config = task_config
        self.current_device_resource = device_resource

        # 设置日志
        if hasattr(device_resource, '_device_config') and device_resource._device_config:
            self.logger = log_manager.get_device_logger(device_resource._device_config.device_name)


        # 清除当前内容
        self._clear_content()

        # 更新标题
        self.title_label.setText(f"{task_name} - 选项设置")

        # 获取资源的完整配置
        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            self._show_error("无法获取资源配置")
            return

        # 检查任务是否有选项
        if not hasattr(task_config, 'option') or not task_config.option:
            self._show_no_options()
            return

        # 获取当前设置中的选项值
        current_options = self._get_current_options()

        # 创建选项控件
        self.option_widgets.clear()

        for option_name in task_config.option:
            # 查找选项配置
            option_config = next(
                (opt for opt in full_resource_config.options if opt.name == option_name),
                None
            )

            if not option_config:
                continue

            # 创建选项组
            option_group = QWidget()
            option_group.setObjectName("optionGroup")
            group_layout = QVBoxLayout(option_group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(5)

            # 创建选项控件
            option_widget = self._create_option_widget(
                option_config,
                option_name,
                current_options
            )

            group_layout.addWidget(option_widget)
            self.content_layout.addWidget(option_group)

        # 添加弹性空间
        self.content_layout.addStretch()

    def _get_current_options(self):
        """获取当前设置中的选项值"""
        if not self.current_device_resource:
            return {}

        # 获取app_config对象
        app_config = global_config.get_app_config()
        if not app_config:
            return {}

        # 获取当前资源使用的ResourceSettings
        settings = next(
            (s for s in app_config.resource_settings
             if s.name == self.current_device_resource.settings_name and
             s.resource_name == self.current_device_resource.resource_name),
            None
        )

        if not settings or not hasattr(settings, 'options'):
            return {}

        # 转换为字典格式
        return {opt.option_name: opt for opt in settings.options}

    def _create_option_widget(self, option, option_name, current_options):
        """创建选项控件"""
        option_widget = QWidget()
        option_widget.setObjectName("optionWidget")
        option_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(8)

        # 选项标签
        option_label = QLabel(option.name)
        option_label.setObjectName("optionLabel")
        option_label.setMinimumWidth(100)

        # 如果有描述，添加提示
        if hasattr(option, 'description') and option.description:
            option_label.setToolTip(option.description)
            info_icon = QLabel("ℹ️")
            info_icon.setFixedWidth(16)
            info_icon.setToolTip(option.description)
            option_layout.addWidget(info_icon)

        option_layout.addWidget(option_label)

        # 根据选项类型创建控件
        if isinstance(option, SelectOption):
            widget = NoWheelComboBox()
            widget.setMinimumWidth(120)

            for choice in option.choices:
                widget.addItem(choice.name, choice.value)

            if option_name in current_options:
                index = widget.findData(current_options[option_name].value)
                if index >= 0:
                    widget.setCurrentIndex(index)

            widget.currentIndexChanged.connect(
                lambda index, w=widget, o_name=option_name:
                self._on_option_changed(o_name, w.currentData())
            )

        elif isinstance(option, BoolOption):
            widget = QCheckBox()
            widget.setObjectName("optionCheckBox")

            if option_name in current_options:
                widget.setChecked(current_options[option_name].value)
            else:
                widget.setChecked(option.default)

            widget.stateChanged.connect(
                lambda state, o_name=option_name, cb=widget:
                self._on_option_changed(o_name, cb.isChecked())
            )

        elif isinstance(option, InputOption):
            widget = QLineEdit()
            widget.setObjectName("optionLineEdit")
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumWidth(120)

            if option_name in current_options:
                widget.setText(str(current_options[option_name].value))
            else:
                widget.setText(str(option.default))

            widget.editingFinished.connect(
                lambda o_name=option_name, le=widget:
                self._on_option_changed(o_name, le.text())
            )

            # 添加占位符文本
            if hasattr(option, 'option_type'):
                if option.option_type == 'number':
                    widget.setPlaceholderText("输入数字...")
                elif option.option_type == 'text':
                    widget.setPlaceholderText("输入文本...")

        else:
            widget = QLabel("不支持的选项类型")
            widget.setObjectName("notSupportedLabel")

        option_layout.addWidget(widget)
        self.option_widgets[option_name] = widget

        return option_widget

    def _on_option_changed(self, option_name, value):
        """处理选项值改变"""
        if not self.current_device_resource:
            return

        # 获取app_config对象
        app_config = global_config.get_app_config()
        if not app_config:
            return

        # 获取当前资源使用的ResourceSettings
        settings = next(
            (s for s in app_config.resource_settings
             if s.name == self.current_device_resource.settings_name and
             s.resource_name == self.current_device_resource.resource_name),
            None
        )

        if not settings:
            return

        # 确保options已初始化
        if not hasattr(settings, 'options') or settings.options is None:
            settings.options = []

        # 处理值的类型转换
        value = self._convert_option_value(option_name, value)

        # 查找或创建选项配置
        option = next(
            (opt for opt in settings.options if opt.option_name == option_name),
            None
        )

        if option:
            prev_value = option.value
            option.value = value
        else:
            # 创建新的选项配置
            new_option = OptionConfig(option_name=option_name, value=value)
            settings.options.append(new_option)
            prev_value = None

        # 保存配置
        global_config.save_all_configs()

        # 发送信号
        self.option_value_changed.emit(
            self.current_resource_name,
            self.current_task_name,
            option_name,
            value
        )

        # 记录日志
        if self.logger:
            value_str = "启用" if isinstance(value, bool) and value else \
                "禁用" if isinstance(value, bool) and not value else \
                    str(value)
            if prev_value is not None:
                self.logger.info(
                    f"任务 [{self.current_task_name}] 的选项 [{option_name}] "
                    f"已更新: {prev_value} → {value_str}"
                )
            else:
                self.logger.info(
                    f"任务 [{self.current_task_name}] 添加了新选项 [{option_name}]，"
                    f"值为: {value_str}"
                )

    def _convert_option_value(self, option_name, value):
        """转换选项值的类型"""
        if not self.current_resource_name:
            return value

        # 获取原始资源配置
        full_resource_config = global_config.get_resource_config(self.current_resource_name)
        if not full_resource_config:
            return value

        # 查找选项配置
        original_option = next(
            (opt for opt in full_resource_config.options if opt.name == option_name),
            None
        )

        if not original_option:
            return value

        # 根据选项类型转换值
        if isinstance(original_option, BoolOption):
            if not isinstance(value, bool):
                value = str(value).lower() in ['true', '1', 'yes', 'y']
        elif hasattr(original_option, 'option_type'):
            if original_option.option_type == 'number':
                try:
                    if '.' in str(value):
                        value = float(value)
                    else:
                        value = int(value)
                except (ValueError, TypeError):
                    if self.logger:
                        self.logger.error(
                            f"选项 {option_name} 的值 '{value}' 无法转换为数字"
                        )

        return value

    def _show_error(self, message):
        """显示错误信息"""
        self._clear_content()

        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setObjectName("errorText")
        error_label.setMinimumHeight(100)

        self.content_layout.addWidget(error_label)
        self.content_layout.addStretch()

    def _show_no_options(self):
        """显示无选项信息"""
        self._clear_content()

        no_options_label = QLabel("该任务没有可配置的选项")
        no_options_label.setAlignment(Qt.AlignCenter)
        no_options_label.setObjectName("noOptionsLabel")
        no_options_label.setMinimumHeight(100)

        self.content_layout.addWidget(no_options_label)
        self.content_layout.addStretch()

    def _clear_content(self):
        """清除内容"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def clear(self):
        """清除所有内容并重置状态"""
        self.current_resource_name = None
        self.current_task_name = None
        self.current_task_config = None
        self.current_device_resource = None
        self.option_widgets.clear()
        self.title_label.setText("任务选项设置")
        self.show_placeholder()