# --- START OF FILE app/widgets/task_options_widget.py ---
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QLineEdit, QSizePolicy, QTextEdit, QSplitter
)

from app.components.no_wheel_ComboBox import NoWheelComboBox
from app.models.config.app_config import OptionConfig, TaskInstance
from app.models.config.global_config import global_config
from app.models.config.resource_config import SelectOption, BoolOption, InputOption, SettingsGroupOption
from app.models.logging.log_manager import log_manager
from app.widgets.collapsible_group_widget import CollapsibleGroupWidget


class TaskOptionsWidget(QFrame):
    """
    任务选项设置组件，用于显示和配置单个任务实例的详细选项。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_resource_name = None
        self.current_instance_id = None  # 使用 instance_id 作为唯一标识符
        self.current_task_name = None
        self.current_task_config = None
        self.current_device_resource = None
        self.option_widgets = {}  # 存储选项控件的引用
        self.logger = None
        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()

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

        # 创建一个垂直分割器，用于划分选项区域和文档区域
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)

        # --- 上半部分：选项滚动区域 ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 5, 0, 5)
        self.content_layout.setSpacing(8)
        self.scroll_area.setWidget(self.content_widget)
        self.splitter.addWidget(self.scroll_area)

        # --- 下半部分：文档显示区域 ---
        self.doc_widget = QWidget()
        doc_layout = QVBoxLayout(self.doc_widget)
        doc_layout.setContentsMargins(5, 5, 5, 5)
        doc_title = QLabel("选项文档")
        doc_title.setObjectName("docTitle")
        self.doc_display = QTextEdit()
        self.doc_display.setReadOnly(True)
        self.doc_display.setObjectName("docDisplay")
        self.doc_display.setPlaceholderText("点击上方的一个选项来查看其详细说明...")
        doc_layout.addWidget(doc_title)
        doc_layout.addWidget(self.doc_display)
        self.doc_widget.setVisible(False)  # 初始隐藏
        self.splitter.addWidget(self.doc_widget)
        self.splitter.setSizes([400, 100])  # 设置初始大小比例

        self.layout.addWidget(self.splitter)
        self.show_placeholder()

    def show_placeholder(self):
        """显示占位符信息，当没有任务被选中时"""
        self._clear_content()
        self.doc_widget.setVisible(False)

        placeholder = QLabel("请选择一个任务来查看其配置选项")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setObjectName("placeholderText")
        placeholder.setMinimumHeight(100)

        self.content_layout.addWidget(placeholder)
        self.content_layout.addStretch()

    def show_task_options(self, resource_name, instance_id, task_name, task_config, device_resource):
        """外部调用的主方法，显示指定任务实例的选项设置"""
        self.current_resource_name = resource_name
        self.current_instance_id = instance_id
        self.current_task_name = task_name
        self.current_task_config = task_config
        self.current_device_resource = device_resource

        if hasattr(device_resource, '_device_config') and device_resource._device_config:
            self.logger = log_manager.get_device_logger(device_resource._device_config.device_name)

        self._clear_content()
        self.doc_widget.setVisible(False)

        self.title_label.setText(f"{task_name} - 选项设置")

        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            self._show_error("无法获取资源配置")
            return

        if not hasattr(task_config, 'option') or not task_config.option:
            self._show_no_options()
            return

        current_instance_options = self._get_current_instance_options()
        self.option_widgets.clear()

        # 遍历任务定义中的每个选项，并为其创建控件
        for option_name in task_config.option:
            option_config = next(
                (opt for opt in full_resource_config.options if opt.name == option_name),
                None
            )
            if not option_config:
                continue

            # 每个选项都放在一个可点击的容器中，以显示文档
            option_container = QFrame()
            option_container.setObjectName("optionContainer")
            container_layout = QVBoxLayout(option_container)
            container_layout.setContentsMargins(10, 8, 10, 8)
            container_layout.setSpacing(5)
            option_container.mousePressEvent = lambda event, o=option_config: self._show_option_doc(o)

            option_widget = self._create_option_widget(
                option_config,
                option_name,
                current_instance_options
            )

            container_layout.addWidget(option_widget)
            self.content_layout.addWidget(option_container)

        self.content_layout.addStretch()

    def _show_option_doc(self, option_config):
        """显示选中选项的文档字符串"""
        if hasattr(option_config, 'doc') and option_config.doc:
            self.doc_display.setText(option_config.doc)
            self.doc_widget.setVisible(True)
        else:
            self.doc_display.setText("此选项没有提供文档说明。")
            self.doc_widget.setVisible(True)

    def _get_current_instance_options(self) -> Dict[str, OptionConfig]:
        """获取当前任务实例已保存的选项值字典"""
        task_instance = self._get_current_task_instance()
        if not task_instance or not hasattr(task_instance, 'options'):
            return {}
        return {opt.option_name: opt for opt in task_instance.options}

    def _get_current_task_instance(self) -> TaskInstance | None:
        """辅助方法，根据当前上下文获取正在编辑的任务实例对象"""
        if not self.current_device_resource or not self.current_instance_id:
            return None
        app_config = global_config.get_app_config()
        if not app_config: return None

        settings = next((s for s in app_config.resource_settings if
                         s.name == self.current_device_resource.settings_name and s.resource_name == self.current_resource_name),
                        None)

        if not settings or not hasattr(settings, 'task_instances'):
            return None

        return settings.task_instances.get(self.current_instance_id)

    def _create_option_widget(self, option, option_name, current_options):
        """根据选项类型（如选择、布尔、输入）创建相应的控件"""
        if isinstance(option, SettingsGroupOption):
            return self._create_settings_group_widget(option, option_name, current_options)

        option_widget = QWidget()
        option_widget.setObjectName("optionWidget")
        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(8)

        option_label = QLabel(option.name)
        option_label.setObjectName("optionLabel")
        option_label.setMinimumWidth(100)
        if hasattr(option, 'description') and option.description:
            option_label.setToolTip(option.description)

        option_layout.addWidget(option_label)
        option_layout.addStretch()

        # 根据选项类型创建不同的输入控件
        if isinstance(option, SelectOption):
            widget = NoWheelComboBox()
            widget.setMinimumWidth(120)
            for choice in option.choices:
                widget.addItem(choice.name, choice.value)

            current_value = option.default
            if option_name in current_options:
                current_value = current_options[option_name].value

            index = widget.findData(current_value)
            if index >= 0:
                widget.setCurrentIndex(index)

            widget.currentIndexChanged.connect(
                lambda index, w=widget, o_name=option_name:
                self._on_option_changed(o_name, w.itemData(index))
            )
        elif isinstance(option, BoolOption):
            widget = QCheckBox()
            widget.setObjectName("optionCheckBox")
            current_value = option.default
            if option_name in current_options:
                current_value = current_options[option_name].value
            widget.setChecked(bool(current_value))
            widget.stateChanged.connect(
                lambda state, o_name=option_name, cb=widget:
                self._on_option_changed(o_name, cb.isChecked())
            )
        elif isinstance(option, InputOption):
            widget = QLineEdit()
            widget.setObjectName("optionLineEdit")
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumWidth(120)
            current_value = option.default
            if option_name in current_options:
                current_value = current_options[option_name].value
            widget.setText(str(current_value))
            widget.editingFinished.connect(
                lambda o_name=option_name, le=widget:
                self._on_option_changed(o_name, le.text())
            )
        else:
            widget = QLabel("不支持的选项类型")
            widget.setObjectName("notSupportedLabel")

        option_layout.addWidget(widget)
        self.option_widgets[option_name] = widget
        return option_widget

    def _create_settings_group_widget(self, option, option_name, current_options):
        """为 SettingsGroupOption 创建可折叠的组控件"""
        group_widget = CollapsibleGroupWidget(option.name)
        if hasattr(option, 'description') and option.description:
            group_widget.set_description(option.description)

        # 设置组的启用状态
        group_enabled = option.default
        if option_name in current_options:
            group_enabled = bool(current_options[option_name].value)
        group_widget.set_group_enabled(group_enabled)

        # 为组内的每个子选项创建控件
        for sub_option in option.settings:
            sub_option_name = f"{option_name}.{sub_option.name}"
            # ... (创建子控件的逻辑与 _create_option_widget 类似) ...
            sub_widget_container = QWidget()
            sub_layout = QHBoxLayout(sub_widget_container)
            sub_layout.setContentsMargins(0, 0, 0, 0)
            sub_layout.setSpacing(8)
            sub_label = QLabel(sub_option.name)
            sub_label.setObjectName("subOptionLabel")
            sub_label.setMinimumWidth(100)
            if hasattr(sub_option, 'description') and sub_option.description:
                sub_label.setToolTip(sub_option.description)
            sub_layout.addWidget(sub_label)
            sub_layout.addStretch()

            current_value = sub_option.default
            if sub_option_name in current_options:
                current_value = current_options[sub_option_name].value

            if isinstance(sub_option, SelectOption):
                widget = NoWheelComboBox()
                widget.setMinimumWidth(120)
                for choice in sub_option.choices: widget.addItem(choice.name, choice.value)
                index = widget.findData(current_value)
                if index >= 0: widget.setCurrentIndex(index)
                widget.currentIndexChanged.connect(
                    lambda i, w=widget, o=sub_option_name: self._on_option_changed(o, w.itemData(i)))
            elif isinstance(sub_option, BoolOption):
                widget = QCheckBox()
                widget.setObjectName("subOptionCheckBox")
                widget.setChecked(bool(current_value))
                widget.stateChanged.connect(
                    lambda s, o=sub_option_name, c=widget: self._on_option_changed(o, c.isChecked()))
            elif isinstance(sub_option, InputOption):
                widget = QLineEdit()
                widget.setObjectName("subOptionLineEdit")
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                widget.setMinimumWidth(120)
                widget.setText(str(current_value))
                widget.editingFinished.connect(lambda o=sub_option_name, l=widget: self._on_option_changed(o, l.text()))
            else:
                widget = QLabel("不支持")
                widget.setObjectName("notSupportedLabel")

            sub_layout.addWidget(widget)
            group_widget.add_sub_widget(sub_option.name, sub_widget_container, widget)
            self.option_widgets[sub_option_name] = widget

        group_widget.group_enabled_changed.connect(
            lambda enabled: self._on_settings_group_changed(option_name, enabled)
        )
        self.option_widgets[option_name] = group_widget
        return group_widget

    def _on_settings_group_changed(self, group_name, enabled):
        """处理设置组启用/禁用状态的改变"""
        self._on_option_changed(group_name, enabled)
        if self.logger:
            status = "已启用" if enabled else "已禁用"
            self.logger.info(f"设置组 [{group_name}] {status}")

    def _on_option_changed(self, option_name, value):
        """核心方法：当任何选项的值改变时，直接修改数据模型并保存"""
        task_instance = self._get_current_task_instance()
        if not task_instance:
            if self.logger: self.logger.error(f"无法找到 instance_id 为 {self.current_instance_id} 的任务实例！")
            return

        if not hasattr(task_instance, 'options') or task_instance.options is None:
            task_instance.options = []

        value = self._convert_option_value(option_name, value)

        # 查找实例的 options 列表中是否已存在该选项
        option_config = next(
            (opt for opt in task_instance.options if opt.option_name == option_name),
            None
        )

        prev_value = None
        if option_config:
            prev_value = option_config.value
            option_config.value = value
        else:
            # 如果不存在，则创建新的 OptionConfig 并添加到实例的列表中
            new_option = OptionConfig(option_name=option_name, value=value)
            task_instance.options.append(new_option)

        global_config.save_all_configs()

        if self.logger:
            # 格式化日志输出，使其更易读
            value_str = "启用" if isinstance(value, bool) and value else "禁用" if isinstance(value,
                                                                                              bool) and not value else str(
                value)
            log_msg = f"任务 [{self.current_task_name}] 的选项 [{option_name}] 已更新为: {value_str}"
            self.logger.info(log_msg)

    def _convert_option_value(self, option_name, value):
        """根据选项的原始定义，将输入值转换为正确的类型（如布尔、数字）"""
        if not self.current_resource_name: return value
        full_resource_config = global_config.get_resource_config(self.current_resource_name)
        if not full_resource_config: return value

        original_option = None
        # 处理嵌套选项（在SettingsGroup中）
        if '.' in option_name:
            group_name, sub_option_name = option_name.split('.', 1)
            group_option = next((opt for opt in full_resource_config.options if opt.name == group_name), None)
            if group_option and isinstance(group_option, SettingsGroupOption):
                original_option = next((opt for opt in group_option.settings if opt.name == sub_option_name), None)
        else:
            original_option = next((opt for opt in full_resource_config.options if opt.name == option_name), None)

        if not original_option: return value

        # 类型转换
        if isinstance(original_option, (BoolOption, SettingsGroupOption)):
            if not isinstance(value, bool):
                return str(value).lower() in ['true', '1', 'yes', 'y']
        elif hasattr(original_option, 'option_type') and original_option.option_type == 'number':
            try:
                return float(value) if '.' in str(value) else int(value)
            except (ValueError, TypeError):
                if self.logger: self.logger.error(f"选项 {option_name} 的值 '{value}' 无法转换为数字")
                return original_option.default  # 转换失败时返回默认值
        return value

    def _show_error(self, message):
        """在界面上显示错误信息"""
        self._clear_content()
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignCenter)
        error_label.setObjectName("errorText")
        error_label.setMinimumHeight(100)
        self.content_layout.addWidget(error_label)
        self.content_layout.addStretch()

    def _show_no_options(self):
        """显示无选项的提示信息"""
        self._clear_content()
        no_options_label = QLabel("该任务没有可配置的选项")
        no_options_label.setAlignment(Qt.AlignCenter)
        no_options_label.setObjectName("noOptionsLabel")
        no_options_label.setMinimumHeight(100)
        self.content_layout.addWidget(no_options_label)
        self.content_layout.addStretch()

    def _clear_content(self):
        """安全地清除滚动区域内的所有内容"""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

    def clear(self):
        """清除所有内容并重置内部状态，通常在切换设备或资源时调用"""
        self.current_resource_name = None
        self.current_instance_id = None
        self.current_task_name = None
        self.current_task_config = None
        self.current_device_resource = None
        self.option_widgets.clear()
        self.title_label.setText("任务选项设置")
        self.show_placeholder()