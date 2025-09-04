# task_options_widget.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QLineEdit, QSizePolicy, QTextEdit, QSplitter
)

from app.components.no_wheel_ComboBox import NoWheelComboBox
from app.models.config.app_config import OptionConfig
from app.models.config.global_config import global_config
from app.models.config.resource_config import SelectOption, BoolOption, InputOption, SettingsGroupOption
from app.models.logging.log_manager import log_manager
from app.widgets.collapsible_group_widget import CollapsibleGroupWidget


class TaskOptionsWidget(QFrame):
    """
    任务选项设置组件，用于显示和配置单个任务的详细选项。
    界面分为上下两部分：
    - 上半部分：显示任务的可配置选项列表。
    - 下半部分：显示当前选中选项的详细文档说明。
    """

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

        # 创建一个垂直分割器，用于划分选项区域和文档区域
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False) # 防止子组件被完全折叠

        # --- 上半部分：选项滚动区域 ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 内容容器
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 5, 0, 5) # 调整边距
        self.content_layout.setSpacing(8) # 调整间距

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
        self.doc_widget.setVisible(False)  # 默认隐藏

        self.splitter.addWidget(self.doc_widget)

        # 设置分割器的初始尺寸比例 (例如，80%给选项，20%给文档)
        self.splitter.setSizes([400, 100])

        self.layout.addWidget(self.splitter)
        self.show_placeholder()

    def show_placeholder(self):
        """显示占位符信息"""
        self._clear_content()
        self.doc_widget.setVisible(False)  # 隐藏文档区域

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

        if hasattr(device_resource, '_device_config') and device_resource._device_config:
            self.logger = log_manager.get_device_logger(device_resource._device_config.device_name)

        self._clear_content()
        self.doc_widget.setVisible(False) # 切换任务时先隐藏文档

        self.title_label.setText(f"{task_name} - 选项设置")

        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            self._show_error("无法获取资源配置")
            return

        if not hasattr(task_config, 'option') or not task_config.option:
            self._show_no_options()
            return

        current_options = self._get_current_options()
        self.option_widgets.clear()

        for option_name in task_config.option:
            option_config = next(
                (opt for opt in full_resource_config.options if opt.name == option_name),
                None
            )
            if not option_config:
                continue

            # 为每个选项创建一个独立的容器，用于样式化和点击事件
            option_container = QFrame()
            option_container.setObjectName("optionContainer")
            container_layout = QVBoxLayout(option_container)
            container_layout.setContentsMargins(10, 8, 10, 8)
            container_layout.setSpacing(5)

            # 【重要】让容器可点击，以显示文档
            option_container.mousePressEvent = lambda event, o=option_config: self._show_option_doc(o)

            # 创建选项控件 (包括普通选项和设置组)
            option_widget = self._create_option_widget(
                option_config,
                option_name,
                current_options
            )

            container_layout.addWidget(option_widget)
            self.content_layout.addWidget(option_container)

        self.content_layout.addStretch()

    def _show_option_doc(self, option_config):
        """
        显示选中选项的文档。
        这个方法由每个选项容器的 mousePressEvent 调用。
        """
        # 检查选项配置对象是否存在 `doc` 属性且不为空
        if hasattr(option_config, 'doc') and option_config.doc:
            self.doc_display.setText(option_config.doc)
            self.doc_widget.setVisible(True)
        else:
            self.doc_widget.setVisible(False)

    def _get_current_options(self):
        """获取当前设置中的选项值"""
        if not self.current_device_resource:
            return {}
        app_config = global_config.get_app_config()
        if not app_config:
            return {}
        settings = next(
            (s for s in app_config.resource_settings
             if s.name == self.current_device_resource.settings_name and
             s.resource_name == self.current_device_resource.resource_name),
            None
        )
        if not settings or not hasattr(settings, 'options'):
            return {}
        return {opt.option_name: opt for opt in settings.options}

    def _create_option_widget(self, option, option_name, current_options):
        """
        创建选项控件，此方法现在返回控件本身，而不是一个完整的行。
        行容器在 show_task_options 中创建。
        """
        if isinstance(option, SettingsGroupOption):
            return self._create_settings_group_widget(option, option_name, current_options)

        option_widget = QWidget()
        option_widget.setObjectName("optionWidget")
        option_layout = QHBoxLayout(option_widget)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(8)

        # 选项标签
        option_label = QLabel(option.name)
        option_label.setObjectName("optionLabel")
        option_label.setMinimumWidth(100)
        if hasattr(option, 'description') and option.description:
            option_label.setToolTip(option.description)

        option_layout.addWidget(option_label)
        option_layout.addStretch()

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

    def _create_settings_group_widget(self, option, option_name, current_options):
        """创建设置组控件"""
        group_widget = CollapsibleGroupWidget(option.name)
        if hasattr(option, 'description') and option.description:
            group_widget.set_description(option.description)

        group_enabled = option.default
        if option_name in current_options:
            group_enabled = current_options[option_name].value
        group_widget.set_group_enabled(group_enabled)

        for sub_option in option.settings:
            sub_option_name = f"{option_name}.{sub_option.name}"
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

            if isinstance(sub_option, SelectOption):
                widget = NoWheelComboBox()
                widget.setMinimumWidth(120)
                for choice in sub_option.choices:
                    widget.addItem(choice.name, choice.value)
                if sub_option_name in current_options:
                    index = widget.findData(current_options[sub_option_name].value)
                    if index >= 0: widget.setCurrentIndex(index)
                else:
                    index = widget.findData(sub_option.default)
                    if index >= 0: widget.setCurrentIndex(index)
                widget.currentIndexChanged.connect(
                    lambda index, w=widget, o_name=sub_option_name:
                    self._on_option_changed(o_name, w.currentData())
                )

            elif isinstance(sub_option, BoolOption):
                widget = QCheckBox()
                widget.setObjectName("subOptionCheckBox")
                if sub_option_name in current_options:
                    widget.setChecked(current_options[sub_option_name].value)
                else:
                    widget.setChecked(sub_option.default)
                widget.stateChanged.connect(
                    lambda state, o_name=sub_option_name, cb=widget:
                    self._on_option_changed(o_name, cb.isChecked())
                )

            elif isinstance(sub_option, InputOption):
                widget = QLineEdit()
                widget.setObjectName("subOptionLineEdit")
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                widget.setMinimumWidth(120)
                if sub_option_name in current_options:
                    widget.setText(str(current_options[sub_option_name].value))
                else:
                    widget.setText(str(sub_option.default))
                widget.editingFinished.connect(
                    lambda o_name=sub_option_name, le=widget:
                    self._on_option_changed(o_name, le.text())
                )
            else:
                widget = QLabel("不支持的选项类型")
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
        """处理设置组启用状态改变"""
        self._on_option_changed(group_name, enabled)
        if self.logger:
            status = "已启用" if enabled else "已禁用"
            self.logger.info(f"设置组 [{group_name}] {status}")

    def _on_option_changed(self, option_name, value):
        """处理选项值改变"""
        if not self.current_device_resource:
            return
        app_config = global_config.get_app_config()
        if not app_config:
            return
        settings = next(
            (s for s in app_config.resource_settings
             if s.name == self.current_device_resource.settings_name and
             s.resource_name == self.current_device_resource.resource_name),
            None
        )
        if not settings:
            return

        if not hasattr(settings, 'options') or settings.options is None:
            settings.options = []

        value = self._convert_option_value(option_name, value)
        option = next(
            (opt for opt in settings.options if opt.option_name == option_name),
            None
        )

        if option:
            prev_value = option.value
            option.value = value
        else:
            new_option = OptionConfig(option_name=option_name, value=value)
            settings.options.append(new_option)
            prev_value = None

        global_config.save_all_configs()
        self.option_value_changed.emit(
            self.current_resource_name,
            self.current_task_name,
            option_name,
            value
        )

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
        full_resource_config = global_config.get_resource_config(self.current_resource_name)
        if not full_resource_config:
            return value

        original_option = None
        if '.' in option_name:
            group_name, sub_option_name = option_name.split('.', 1)
            group_option = next(
                (opt for opt in full_resource_config.options if opt.name == group_name),
                None
            )
            if group_option and isinstance(group_option, SettingsGroupOption):
                original_option = next(
                    (opt for opt in group_option.settings if opt.name == sub_option_name),
                    None
                )
        else:
            original_option = next(
                (opt for opt in full_resource_config.options if opt.name == option_name),
                None
            )
        if not original_option:
            return value

        if isinstance(original_option, (BoolOption, SettingsGroupOption)):
            if not isinstance(value, bool):
                return str(value).lower() in ['true', '1', 'yes', 'y']
        elif hasattr(original_option, 'option_type') and original_option.option_type == 'number':
            try:
                return float(value) if '.' in str(value) else int(value)
            except (ValueError, TypeError):
                if self.logger:
                    self.logger.error(f"选项 {option_name} 的值 '{value}' 无法转换为数字")
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
            if item:
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
