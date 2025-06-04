"""
PySide6 配置系统实现
用于解析配置并生成对应的pipeline_override
"""

import json
from typing import Dict, Any, List, Union
from dataclasses import dataclass
from copy import deepcopy
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QSpinBox, QCheckBox, QRadioButton, QButtonGroup,
    QComboBox, QPushButton, QGroupBox, QListWidget,
    QListWidgetItem, QToolBox, QSlider
)
from PySide6.QtCore import Qt, Signal


@dataclass
class OptionConfig:
    """单个选项的配置"""
    key: str
    display_name: str
    widget_type: str
    default_value: Any
    config: Dict[str, Any]


class OptionWidget(QWidget):
    """选项控件基类"""
    value_changed = Signal(str, object)  # key, value

    def __init__(self, option_config: OptionConfig):
        super().__init__()
        self.option_config = option_config
        self.key = option_config.key

    def get_value(self) -> Any:
        """获取当前值"""
        raise NotImplementedError

    def set_value(self, value: Any):
        """设置值"""
        raise NotImplementedError

    def get_pipeline_override(self) -> Dict[str, Any]:
        """获取对应的pipeline_override"""
        raise NotImplementedError


class LineEditOption(OptionWidget):
    """文本输入选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QHBoxLayout(self)

        label = QLabel(option_config.display_name)
        self.line_edit = QLineEdit()
        self.line_edit.setText(str(option_config.default_value))

        if placeholder := option_config.config.get('placeholder'):
            self.line_edit.setPlaceholderText(placeholder)

        self.line_edit.textChanged.connect(
            lambda text: self.value_changed.emit(self.key, text)
        )

        layout.addWidget(label)
        layout.addWidget(self.line_edit)

    def get_value(self) -> str:
        return self.line_edit.text()

    def set_value(self, value: str):
        self.line_edit.setText(str(value))

    def get_pipeline_override(self) -> Dict[str, Any]:
        """直接替换{value}占位符"""
        value = self.get_value()
        pipeline = deepcopy(self.option_config.config.get('pipeline_override', {}))
        return self._replace_value_placeholder(pipeline, value)

    def _replace_value_placeholder(self, obj: Any, value: str) -> Any:
        """递归替换{value}占位符"""
        if isinstance(obj, dict):
            return {k: self._replace_value_placeholder(v, value) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_value_placeholder(item, value) for item in obj]
        elif isinstance(obj, str) and '{value}' in obj:
            return obj.replace('{value}', value)
        return obj


class SpinBoxOption(OptionWidget):
    """数字输入选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QHBoxLayout(self)

        label = QLabel(option_config.display_name)
        self.spin_box = QSpinBox()

        # 设置范围
        if min_val := option_config.config.get('min_value'):
            self.spin_box.setMinimum(min_val)
        if max_val := option_config.config.get('max_value'):
            self.spin_box.setMaximum(max_val)

        # 设置默认值
        default_val = option_config.default_value if option_config.default_value is not None else 0
        self.spin_box.setValue(int(default_val))

        self.spin_box.valueChanged.connect(
            lambda val: self.value_changed.emit(self.key, val)
        )

        layout.addWidget(label)
        layout.addWidget(self.spin_box)

    def get_value(self) -> int:
        return self.spin_box.value()

    def set_value(self, value: int):
        self.spin_box.setValue(int(value))

    def get_pipeline_override(self) -> Dict[str, Any]:
        value = str(self.get_value())
        pipeline = deepcopy(self.option_config.config.get('pipeline_override', {}))
        return LineEditOption._replace_value_placeholder(self, pipeline, value)


class CheckBoxOption(OptionWidget):
    """复选框选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QHBoxLayout(self)

        self.checkbox = QCheckBox(option_config.display_name)
        default_val = bool(option_config.default_value) if option_config.default_value is not None else False
        self.checkbox.setChecked(default_val)

        self.checkbox.stateChanged.connect(
            lambda state: self.value_changed.emit(self.key, state == Qt.Checked)
        )

        layout.addWidget(self.checkbox)

    def get_value(self) -> bool:
        return self.checkbox.isChecked()

    def set_value(self, value: bool):
        self.checkbox.setChecked(bool(value))

    def get_pipeline_override(self) -> Dict[str, Any]:
        value_key = 'true' if self.get_value() else 'false'
        values = self.option_config.config.get('values', {})
        if value_config := values.get(value_key):
            return value_config.get('pipeline_override', {})
        return {}


class ComboBoxOption(OptionWidget):
    """下拉框选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QHBoxLayout(self)

        label = QLabel(option_config.display_name)
        self.combo_box = QComboBox()

        self.values = option_config.config.get('values', {})
        for key, value_config in self.values.items():
            self.combo_box.addItem(value_config.get('display', key), key)

        # 设置默认值
        if default := option_config.default_value:
            index = self.combo_box.findData(default)
            if index >= 0:
                self.combo_box.setCurrentIndex(index)

        self.combo_box.currentIndexChanged.connect(
            lambda: self.value_changed.emit(self.key, self.get_value())
        )

        layout.addWidget(label)
        layout.addWidget(self.combo_box)

    def get_value(self) -> str:
        return self.combo_box.currentData()

    def set_value(self, value: str):
        index = self.combo_box.findData(value)
        if index >= 0:
            self.combo_box.setCurrentIndex(index)

    def get_pipeline_override(self) -> Dict[str, Any]:
        current_value = self.get_value()
        if value_config := self.values.get(current_value):
            return value_config.get('pipeline_override', {})
        return {}


class CheckListOption(OptionWidget):
    """复选列表选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QVBoxLayout(self)

        label = QLabel(option_config.display_name)
        layout.addWidget(label)

        self.list_widget = QListWidget()
        self.items = option_config.config.get('items', {})

        # 添加列表项
        default_values = option_config.default_value if isinstance(option_config.default_value, list) else []
        for key, item_config in self.items.items():
            item = QListWidgetItem(item_config.get('display', key))
            item.setData(Qt.UserRole, key)
            item.setCheckState(Qt.Checked if key in default_values else Qt.Unchecked)
            self.list_widget.addItem(item)

        self.list_widget.itemChanged.connect(
            lambda: self.value_changed.emit(self.key, self.get_value())
        )

        layout.addWidget(self.list_widget)

    def get_value(self) -> List[str]:
        checked_items = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.Checked:
                checked_items.append(item.data(Qt.UserRole))
        return checked_items

    def set_value(self, values: List[str]):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            key = item.data(Qt.UserRole)
            item.setCheckState(Qt.Checked if key in values else Qt.Unchecked)

    def get_pipeline_override(self) -> Dict[str, Any]:
        """合并所有选中项的pipeline_override"""
        merged_pipeline = {}
        for key in self.get_value():
            if item_config := self.items.get(key):
                if pipeline := item_config.get('pipeline_override'):
                    merged_pipeline = self._deep_merge(merged_pipeline, pipeline)
        return merged_pipeline

    @staticmethod
    def _deep_merge(dict1: Dict, dict2: Dict) -> Dict:
        """深度合并两个字典"""
        result = deepcopy(dict1)
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = CheckListOption._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result


class GroupOption(OptionWidget):
    """分组选项"""

    def __init__(self, option_config: OptionConfig):
        super().__init__(option_config)
        layout = QVBoxLayout(self)

        self.group_box = QGroupBox(option_config.display_name)
        group_layout = QVBoxLayout(self.group_box)

        self.child_widgets = {}
        children = option_config.config.get('children', {})

        # 创建子控件
        for key, child_config in children.items():
            child_option = OptionConfig(
                key=f"{option_config.key}.{key}",
                display_name=child_config.get('display_name', key),
                widget_type=child_config.get('widget_type'),
                default_value=child_config.get('default_value'),
                config=child_config
            )

            widget = create_option_widget(child_option)
            if widget:
                widget.value_changed.connect(self._on_child_value_changed)
                self.child_widgets[key] = widget
                group_layout.addWidget(widget)

        layout.addWidget(self.group_box)

    def _on_child_value_changed(self, key: str, value: Any):
        self.value_changed.emit(self.key, self.get_value())

    def get_value(self) -> Dict[str, Any]:
        return {key: widget.get_value() for key, widget in self.child_widgets.items()}

    def set_value(self, values: Dict[str, Any]):
        for key, value in values.items():
            if widget := self.child_widgets.get(key):
                widget.set_value(value)

    def get_pipeline_override(self) -> Dict[str, Any]:
        """合并所有子控件的pipeline_override"""
        merged_pipeline = {}
        for widget in self.child_widgets.values():
            child_pipeline = widget.get_pipeline_override()
            merged_pipeline = CheckListOption._deep_merge(merged_pipeline, child_pipeline)
        return merged_pipeline


# 工厂函数
def create_option_widget(option_config: OptionConfig) -> OptionWidget:
    """根据配置创建对应的控件"""
    widget_map = {
        'line_edit': LineEditOption,
        'spin_box': SpinBoxOption,
        'check_box': CheckBoxOption,
        'combo_box': ComboBoxOption,
        'check_list': CheckListOption,
        'group': GroupOption,
        # 可以继续添加其他控件类型
    }

    widget_class = widget_map.get(option_config.widget_type)
    if widget_class:
        return widget_class(option_config)
    return None


class OptionsManager:
    """选项管理器"""

    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data
        self.options = config_data.get('options', {})
        self.widgets = {}

    def create_widgets(self) -> Dict[str, OptionWidget]:
        """创建所有选项控件"""
        for key, option_config in self.options.items():
            widget_type = option_config.get('widget_type')

            # 根据控件类型选择正确的默认值字段
            if widget_type == 'check_list':
                default_value = option_config.get('default_values', [])
            else:
                default_value = option_config.get('default_value')

            config = OptionConfig(
                key=key,
                display_name=option_config.get('display_name', key),
                widget_type=widget_type,
                default_value=default_value,
                config=option_config
            )

            if widget := create_option_widget(config):
                self.widgets[key] = widget

        return self.widgets

    def get_pipeline_override_for_task(self, task_name: str) -> Dict[str, Any]:
        """获取指定任务的所有pipeline_override"""
        # 找到任务配置
        task_config = None
        for task in self.config_data.get('resource_tasks', []):
            if task['task_name'] == task_name:
                task_config = task
                break

        if not task_config:
            return {}

        # 合并所有相关选项的pipeline_override
        merged_pipeline = {}
        for option_key in task_config.get('options', []):
            if widget := self.widgets.get(option_key):
                option_pipeline = widget.get_pipeline_override()
                merged_pipeline = CheckListOption._deep_merge(merged_pipeline, option_pipeline)

        return merged_pipeline

    def get_all_pipeline_overrides(self) -> Dict[str, Any]:
        """获取所有选项的pipeline_override"""
        merged_pipeline = {}
        for widget in self.widgets.values():
            option_pipeline = widget.get_pipeline_override()
            merged_pipeline = CheckListOption._deep_merge(merged_pipeline, option_pipeline)
        return merged_pipeline

    def get_values(self) -> Dict[str, Any]:
        """获取所有选项的当前值"""
        return {key: widget.get_value() for key, widget in self.widgets.items()}

    def set_values(self, values: Dict[str, Any]):
        """设置选项值"""
        for key, value in values.items():
            if widget := self.widgets.get(key):
                widget.set_value(value)


# 使用示例
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QScrollArea

    # 示例配置
    config = {
        "resource_name": "阴阳师",
        "resource_version": "v1.1.6-beta.2",
        "resource_tasks": [
            {
                "task_name": "自动御魂",
                "task_entry": "自动御魂",
                "options": ["soul_boost", "challenge_count"]
            }
        ],
        "options": {
            "soul_boost": {
                "display_name": "御魂加成",
                "widget_type": "check_box",
                "default_value": False,
                "values": {
                    "true": {
                        "pipeline_override": {
                            "寮3026_copy1": {"enabled": True}
                        }
                    },
                    "false": {
                        "pipeline_override": {
                            "寮3026_copy1": {"enabled": False}
                        }
                    }
                }
            },
            "challenge_count": {
                "display_name": "自动挑战次数",
                "widget_type": "spin_box",
                "default_value": 10,
                "min_value": 1,
                "max_value": 999,
                "pipeline_override": {
                    "自动御魂3": {
                        "custom_action_param": {
                            "expected_number": "{value}"
                        }
                    }
                }
            }
        }
    }

    app = QApplication(sys.argv)

    # 创建主窗口
    window = QMainWindow()
    window.setWindowTitle("游戏配置管理")

    # 创建选项管理器
    manager = OptionsManager(config)
    widgets = manager.create_widgets()

    # 创建界面
    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)

    for widget in widgets.values():
        layout.addWidget(widget)

    # 添加获取配置按钮
    btn = QPushButton("获取当前Pipeline配置")
    btn.clicked.connect(lambda: print(json.dumps(
        manager.get_all_pipeline_overrides(),
        ensure_ascii=False,
        indent=2
    )))
    layout.addWidget(btn)

    # 设置滚动区域
    scroll = QScrollArea()
    scroll.setWidget(central_widget)
    window.setCentralWidget(scroll)

    window.resize(600, 800)
    window.show()

    sys.exit(app.exec())