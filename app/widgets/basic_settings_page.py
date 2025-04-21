from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QScrollArea, QCheckBox, QLineEdit, QPushButton, QSizePolicy
)

from app.components.collapsible_widget import CollapsibleWidget, DraggableContainer
from app.models.config.app_config import Resource, OptionConfig
from app.models.config.global_config import global_config
from app.models.config.resource_config import SelectOption, BoolOption, InputOption
from app.models.logging.log_manager import log_manager
from app.widgets.no_wheel_ComboBox import NoWheelComboBox

class BasicSettingsPage(QFrame):
    """基本设置页面，用于配置资源任务"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.logger=log_manager.get_device_logger(device_config.device_name)
        self.selected_resource_name = None
        self.task_option_widgets = {}

        self.setObjectName("contentCard")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        # 创建基本页面布局
        basic_layout = QVBoxLayout(self)
        basic_layout.setContentsMargins(0, 0, 0, 0)

        # 基本设置内容区域
        self.settings_content = QWidget()
        self.settings_content_layout = QVBoxLayout(self.settings_content)
        self.settings_content_layout.setContentsMargins(0, 0, 0, 0)
        self.settings_content_layout.setSpacing(15)

        # 添加初始占位符信息
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setSpacing(15)

        # 创建自动换行的主消息标签
        initial_message = QLabel("请从左侧资源列表中选择一个资源进行设置")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setWordWrap(True)  # 启用文本自动换行
        initial_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # 水平方向可扩展

        # 创建自动换行的次要消息标签
        sub_message = QLabel("点击资源列表中的设置按钮来配置任务")
        sub_message.setAlignment(Qt.AlignCenter)
        sub_message.setWordWrap(True)  # 启用文本自动换行
        sub_message.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # 水平方向可扩展

        # 设置最小宽度以确保正确的换行行为（可选）
        placeholder_widget.setMinimumWidth(10)

        placeholder_layout.addWidget(initial_message)
        placeholder_layout.addWidget(sub_message)

        # 添加弹性空间，使标签在顶部居中（可选）
        placeholder_layout.addStretch(1)

        self.settings_content_layout.addWidget(placeholder_widget)
        basic_layout.addWidget(self.settings_content)

    def show_resource_settings(self, resource_name):
        """显示所选资源的设置"""
        self.selected_resource_name = resource_name

        # 清除当前设置内容
        self._clear_layout(self.settings_content_layout)

        # 获取资源配置
        full_resource_config = global_config.get_resource_config(resource_name)
        if not full_resource_config:
            # 显示错误信息，如资源配置未找到
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_layout.setAlignment(Qt.AlignCenter)

            error_icon = QLabel()
            error_icon.setPixmap(QIcon("assets/icons/error.svg").pixmap(48, 48))
            error_icon.setAlignment(Qt.AlignCenter)

            error_label = QLabel(f"未找到资源 {resource_name} 的配置信息")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setObjectName("errorText")

            error_layout.addWidget(error_icon)
            error_layout.addWidget(error_label)

            self.settings_content_layout.addWidget(error_widget)
            return

        # 获取设备特定的资源配置
        device_resource = None
        if self.device_config:
            device_resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)

        # 如果设备没有此资源配置，创建一个新的
        if not device_resource and self.device_config:
            try:
                device_resource = Resource(
                    resource_name=resource_name,
                    enable=True,
                    selected_tasks=[],
                    options=[]
                )

                # 将新资源添加到设备的资源列表中
                if not hasattr(self.device_config, 'resources'):
                    self.device_config.resources = []
                self.device_config.resources.append(device_resource)

                # 保存更新后的配置
                global_config.save_all_configs()

                # 记录创建新资源的日志
                device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
                self.logger.info( f"为设备自动创建了资源 {resource_name} 的配置")
            except Exception as e:
                # 如果创建资源时出错，记录并显示警告
                log_manager.log_device_error(
                    self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备",
                    f"自动创建资源配置失败: {str(e)}"
                )

                # 显示原始警告信息
                no_config_widget = QWidget()
                no_config_layout = QVBoxLayout(no_config_widget)
                no_config_layout.setAlignment(Qt.AlignCenter)

                warning_icon = QLabel()
                warning_icon.setPixmap(QIcon("assets/icons/warning.svg").pixmap(48, 48))
                warning_icon.setAlignment(Qt.AlignCenter)

                no_config_label = QLabel(f"设备未配置资源 {resource_name}")
                no_config_label.setAlignment(Qt.AlignCenter)

                action_btn = QPushButton("添加资源配置")
                action_btn.setObjectName("primaryButton")
                action_btn.setFixedWidth(50)
                action_btn.clicked.connect(lambda: self._create_resource_configuration(resource_name))

                no_config_layout.addWidget(warning_icon)
                no_config_layout.addWidget(no_config_label)
                no_config_layout.addSpacing(15)
                no_config_layout.addWidget(action_btn, 0, Qt.AlignCenter)

                self.settings_content_layout.addWidget(no_config_widget)
                return

        # 添加描述（如果有）
        if hasattr(full_resource_config, 'description') and full_resource_config.description:
            description_label = QLabel(full_resource_config.description)
            description_label.setObjectName("resourceDescription")
            description_label.setWordWrap(True)
            description_label.setContentsMargins(0, 0, 0, 10)
            self.settings_content_layout.addWidget(description_label)

        # 拖放任务的说明
        instructions = QLabel("拖放任务可调整执行顺序")
        instructions.setObjectName("instructionText")
        instructions.setAlignment(Qt.AlignCenter)
        self.settings_content_layout.addWidget(instructions)

        # 创建任务的滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        # 禁用水平滚动条
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 创建任务的可拖动容器
        scroll_content = DraggableContainer()
        scroll_content.setObjectName('draggableContainer')
        scroll_content.setMinimumWidth(10)

        scroll_content.layout.setContentsMargins(0, 0, 0, 0)
        scroll_content.drag.connect(lambda order: self.on_drag_tasks(order))

        # 确保内容水平扩展并且可以垂直扩展超出其初始大小
        scroll_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        # 获取任务顺序信息
        task_order_map = {task.task_name: idx for idx, task in enumerate(full_resource_config.resource_tasks)}
        selected_order = {task_name: idx for idx, task_name in enumerate(device_resource.selected_tasks or [])}

        # 按选择状态和顺序排序任务
        sorted_tasks = sorted(
            full_resource_config.resource_tasks,
            key=lambda task: (
                0 if task.task_name in selected_order else 1,
                selected_order.get(task.task_name, task_order_map.get(task.task_name, float('inf')))
            )
        )

        # 创建任务小部件
        self.task_option_widgets = {}  # 存储小部件以便后续引用

        for task in sorted_tasks:
            # 创建可折叠小部件
            options_widget = CollapsibleWidget(task.task_name)
            options_widget.setMinimumHeight(30)  # 设置最小高度

            is_task_selected = task.task_name in selected_order
            options_widget.checkbox.setChecked(is_task_selected)

            options_widget.checkbox.stateChanged.connect(
                lambda state, t_name=task.task_name, cb=options_widget.checkbox:
                self.update_task_selection(device_resource, t_name, cb.isChecked())
            )

            # 如果任务有选项，添加选项小部件
            if hasattr(task, 'option') and task.option:
                for option_name in task.option:
                    for option in full_resource_config.options:
                        if option.name == option_name:
                            option_widget = self._create_option_widget(
                                option, option_name,
                                {opt.option_name: opt for opt in device_resource.options},
                                task.task_name,
                                self.task_option_widgets,
                                device_resource
                            )
                            options_widget.content_layout.addWidget(option_widget)
            else:
                no_options_label = QLabel("该任务没有可配置的选项")
                no_options_label.setObjectName("noOptionsLabel")
                no_options_label.setWordWrap(True)
                options_widget.content_layout.addWidget(no_options_label)

            scroll_content.addWidget(options_widget)

        scroll_area.setWidget(scroll_content)
        self.settings_content_layout.addWidget(scroll_area)

    def clear_settings(self):
        """清除设置内容"""
        self._clear_layout(self.settings_content_layout)

        # 添加初始信息和图标
        placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_widget)
        placeholder_layout.setAlignment(Qt.AlignCenter)
        placeholder_layout.setSpacing(15)

        initial_message = QLabel("请从左侧资源列表中选择一个资源进行设置")
        initial_message.setAlignment(Qt.AlignCenter)
        initial_message.setObjectName("placeholderText")

        sub_message = QLabel("点击资源列表中的设置按钮来配置任务")
        sub_message.setAlignment(Qt.AlignCenter)
        sub_message.setObjectName("subText")

        placeholder_layout.addWidget(initial_message)
        placeholder_layout.addWidget(sub_message)

        self.settings_content_layout.addWidget(placeholder_widget)

        # 清除选中资源名称
        self.selected_resource_name = None

    def _create_resource_configuration(self, resource_name):
        """从按钮点击创建新的资源配置的辅助方法"""
        try:
            # 创建新的资源配置
            device_resource = Resource(
                resource_name=resource_name,
                enable=True,
                selected_tasks=[],
                options=[]
            )

            # 将新资源添加到设备的资源列表中
            if not hasattr(self.device_config, 'resources'):
                self.device_config.resources = []
            self.device_config.resources.append(device_resource)

            # 保存更新后的配置
            global_config.save_all_configs()

            # 记录创建新资源的日志
            device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
            self.logger.info( f"已创建资源 {resource_name} 的配置")

            # 使用新资源刷新设置显示
            self.show_resource_settings(resource_name)
        except Exception as e:
            # 记录任何错误
            log_manager.log_device_error(
                self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备",
                f"创建资源配置失败: {str(e)}"
            )

    def _create_option_widget(self, option, option_name, current_options, task_name, task_options_map, resource_config):
        """基于选项类型创建小部件"""
        option_widget = QWidget()
        option_widget.setObjectName("optionWidget")
        # 确保选项控件适应父容器宽度
        option_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        option_layout = QHBoxLayout(option_widget)
        # 减小边距，使其在较窄的容器中也能显示良好
        option_layout.setContentsMargins(0,0,0,0)
        option_layout.setSpacing(8)  # 减小子元素间的间距

        # Option label with tooltip if description exists
        option_label = QLabel(option.name)
        option_label.setObjectName("optionLabel")
        # 禁止标签自动换行
        option_label.setWordWrap(True)
        # 设置固定最小宽度，防止标签占用太多空间
        option_label.setMinimumWidth(20)

        if hasattr(option, 'description') and option.description:
            option_label.setToolTip(option.description)
            info_icon = QLabel("ℹ️")
            info_icon.setFixedWidth(16)
            info_icon.setToolTip(option.description)
            option_layout.addWidget(info_icon)

        option_layout.addWidget(option_label)

        # Create control based on option type
        if isinstance(option, SelectOption):
            widget = NoWheelComboBox()
            # 设置下拉框适应可用空间的最小宽度
            widget.setMinimumWidth(40)

            for choice in option.choices:
                widget.addItem(choice.name, choice.value)
            if option_name in current_options:
                index = widget.findData(current_options[option_name].value)
                if index >= 0:
                    widget.setCurrentIndex(index)
            widget.currentIndexChanged.connect(
                lambda index, w=widget, o_name=option_name, res_config=resource_config:
                self.update_option_value(res_config, o_name, w.currentData())
            )
        elif isinstance(option, BoolOption):
            widget = QCheckBox()
            widget.setObjectName("optionCheckBox")
            if option_name in current_options:
                widget.setChecked(current_options[option_name].value)
            else:
                widget.setChecked(option.default)
            widget.stateChanged.connect(
                lambda state, o_name=option_name, cb=widget, res_config=resource_config:
                self.update_option_value(res_config, o_name, cb.isChecked())
            )
        elif isinstance(option, InputOption):
            widget = QLineEdit()
            widget.setObjectName("optionLineEdit")
            # 设置输入框适应可用空间
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            # 缩短输入框的最小宽度
            widget.setMinimumWidth(40)

            if option_name in current_options:
                widget.setText(str(current_options[option_name].value))
            else:
                widget.setText(str(option.default))
            widget.editingFinished.connect(
                lambda o_name=option_name, le=widget, res_config=resource_config:
                self.update_option_value(res_config, o_name, le.text())
            )

            # Add placeholder text based on option type
            if hasattr(option, 'option_type'):
                if option.option_type == 'number':
                    # For numeric input
                    widget.setPlaceholderText("输入数字...")
                elif option.option_type == 'text':
                    # For text input
                    widget.setPlaceholderText("输入文本...")
        else:
            widget = QLabel("不支持的选项类型")
            widget.setObjectName("notImportOptionLabel")
            widget.setWordWrap(True)

        option_layout.addWidget(widget)
        task_options_map[(task_name, option_name)] = widget

        return option_widget

    def update_task_selection(self, resource_config, task_name, is_selected):
        """Update task selection status with improved UI feedback"""
        if not resource_config:
            return

        if not hasattr(resource_config, 'selected_tasks') or resource_config.selected_tasks is None:
            resource_config.selected_tasks = []

        if is_selected and task_name not in resource_config.selected_tasks:
            resource_config.selected_tasks.append(task_name)
        elif not is_selected and task_name in resource_config.selected_tasks:
            resource_config.selected_tasks.remove(task_name)

        # Save the updated configuration
        global_config.save_all_configs()

        # Update task count label if present
        for i in range(self.settings_content_layout.count()):
            widget = self.settings_content_layout.itemAt(i).widget()
            if isinstance(widget, QWidget):
                count_label = widget.findChild(QLabel, "countLabel")
                if count_label and resource_config:
                    count_label.setText(f"{len(resource_config.selected_tasks or [])} 个已选择")
                    break

        # Log the change with more details
        status_text = "已选择" if is_selected else "已取消选择"
        device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
        resource_name = resource_config.resource_name if hasattr(resource_config, 'resource_name') else "未知资源"
        self.logger.info( f"资源 [{resource_name}] 的任务 [{task_name}] {status_text}")

    def update_option_value(self, resource_config, option_name, value):
        """Update option value for a resource with improved feedback"""
        if not resource_config:
            return

        if not hasattr(resource_config, 'options') or resource_config.options is None:
            resource_config.options = []

        # 获取实际资源名称
        resource_name = resource_config.resource_name

        # 获取原始完整资源配置，用于确定选项类型
        full_resource_config = global_config.get_resource_config(resource_name)
        original_option = None
        if full_resource_config and hasattr(full_resource_config, 'options'):
            original_option = next((opt for opt in full_resource_config.options if opt.name == option_name), None)

        # Find existing option or create a new one
        option = next((opt for opt in resource_config.options if opt.option_name == option_name), None)

        # 根据原始选项类型处理值
        if original_option:
            if isinstance(original_option, BoolOption):
                # 转换为布尔值
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
                        # 转换失败时记录错误并返回
                        device_name = self.device_config.device_name if hasattr(self.device_config,
                                                                                'device_name') else "未知设备"
                        self.logger.error( f"选项 {option_name} 的值 '{value}' 无法转换为数字")
                        return

        if option:
            # Save the previous value for comparison
            prev_value = option.value
            option.value = value

            # Save the updated configuration
            global_config.save_all_configs()

            # Create a readable string representation for logging
            if isinstance(value, bool):
                value_str = "启用" if value else "禁用"
            else:
                value_str = str(value)

            # Log the change with more details
            device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
            self.logger.info(f"资源 [{resource_name}] 的选项 [{option_name}] 已更新: {prev_value} → {value_str}")
        else:
            # 创建新的选项配置
            from app.models.config.app_config import OptionConfig  # 正确导入OptionConfig类

            # 创建新的选项配置
            new_option = OptionConfig(option_name=option_name, value=value)

            # 添加到资源配置中
            resource_config.options.append(new_option)

            # 保存配置
            global_config.save_all_configs()

            # 创建一个可读的字符串表示用于日志记录
            if isinstance(value, bool):
                value_str = "启用" if value else "禁用"
            else:
                value_str = str(value)

            # 记录日志 - 修复资源名称获取
            device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
            self.logger.info(f"资源 [{resource_name}] 添加了新选项 [{option_name}]，值为: {value_str}")

    def on_drag_tasks(self, current_order):
        """处理任务拖放重新排序"""
        if not self.selected_resource_name or not self.device_config:
            return

        resource_config = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if not resource_config:
            return

        # 更新任务顺序
        resource_config.selected_tasks = [
            task for task in current_order if task in resource_config.selected_tasks
        ]

        # 保存更新后的配置
        global_config.save_all_configs()

        # 记录更改
        device_name = self.device_config.device_name if hasattr(self.device_config, 'device_name') else "未知设备"
        self.logger.info( f"资源 {self.selected_resource_name} 的任务顺序已更新")

    def _clear_layout(self, layout):
        """清除布局中的所有小部件"""
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())