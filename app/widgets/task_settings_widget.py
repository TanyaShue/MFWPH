from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QToolButton, QPushButton, QStackedWidget, QComboBox, QLineEdit, QMessageBox
)

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.advanced_settings_page import AdvancedSettingsPage
from app.widgets.basic_settings_page import BasicSettingsPage
from app.models.config.app_config import ResourceSettings


class TaskSettingsWidget(QFrame):
    """Task settings widget for configuring resource tasks"""

    def __init__(self, device_config, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.selected_resource_name = None
        self.selected_settings_name = None
        self.status_indicator = None
        self.status_dot = None
        self.status_text = None
        self.current_tab = "basic"  # 跟踪当前显示的标签
        self.resource_header = None  # 添加资源标题和状态指示器容器
        self.settings_selector = None  # 添加设置选择器下拉框
        self.edit_button = None  # 添加编辑按钮
        self.delete_button = None  # 添加删除按钮
        self.add_button = None  # 添加新设置按钮
        self.settings_name_editor = None  # 编辑设置名称的输入框
        self.is_editing_name = False  # 跟踪是否正在编辑设置名称
        self.logger = None

        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)

        # 添加资源标题和状态指示器区域
        self.resource_header = QWidget()
        self.resource_header.setVisible(False)  # 初始隐藏，直到选择资源
        resource_header_layout = QVBoxLayout(self.resource_header)
        resource_header_layout.setContentsMargins(0, 0, 0, 0)
        resource_header_layout.setSpacing(8)

        # 顶部区域 - 资源名称和状态
        top_header_widget = QWidget()
        top_header_layout = QHBoxLayout(top_header_widget)
        top_header_layout.setContentsMargins(0, 0, 0, 0)

        # 资源名称标签
        self.resource_name_label = QLabel()
        self.resource_name_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.resource_name_label.setObjectName("sectionTitle")

        # 资源状态指示器
        self.status_indicator = QWidget()
        status_layout = QHBoxLayout(self.status_indicator)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(5)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)

        self.status_text = QLabel()
        self.status_text.setObjectName("statusText")

        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)

        top_header_layout.addWidget(self.resource_name_label)
        top_header_layout.addStretch()
        top_header_layout.addWidget(self.status_indicator)

        # 设置选择器区域
        settings_selector_widget = QWidget()
        settings_selector_layout = QHBoxLayout(settings_selector_widget)
        settings_selector_layout.setContentsMargins(0, 0, 0, 0)
        settings_selector_layout.setSpacing(8)

        # 设置选择标签
        settings_label = QLabel("设置配置:")
        settings_label.setObjectName("settingsLabel")

        # 创建设置选择器下拉框
        self.settings_selector = QComboBox()
        self.settings_selector.setObjectName("settingsSelector")
        self.settings_selector.currentIndexChanged.connect(self.on_settings_changed)

        # 创建设置名称编辑器 (初始隐藏)
        self.settings_name_editor = QLineEdit()
        self.settings_name_editor.setObjectName("settingsNameEditor")
        self.settings_name_editor.setVisible(False)

        # 添加设置按钮
        self.add_button = QPushButton("添加")
        self.add_button.setIcon(QIcon("assets/icons/add.svg"))
        self.add_button.setToolTip("添加新设置")
        self.add_button.setObjectName("iconButton")
        self.add_button.clicked.connect(self.add_new_settings)

        # 编辑按钮
        self.edit_button = QPushButton("编辑")
        self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
        self.edit_button.setToolTip("编辑设置名称")
        self.edit_button.setObjectName("iconButton")
        self.edit_button.clicked.connect(self.toggle_edit_mode)

        # 删除按钮 (初始隐藏)
        self.delete_button = QPushButton("删除")
        self.delete_button.setIcon(QIcon("assets/icons/delete.svg"))
        self.delete_button.setToolTip("删除当前设置")
        self.delete_button.setObjectName("iconButton")
        self.delete_button.setVisible(False)  # 初始隐藏
        self.delete_button.clicked.connect(self.delete_settings)

        settings_selector_layout.addWidget(settings_label)
        settings_selector_layout.addWidget(self.settings_selector)
        settings_selector_layout.addWidget(self.settings_name_editor)
        settings_selector_layout.addWidget(self.add_button)
        settings_selector_layout.addWidget(self.edit_button)
        settings_selector_layout.addWidget(self.delete_button)  # 添加删除按钮到布局
        settings_selector_layout.addStretch()

        # 将小部件添加到资源标题区域
        resource_header_layout.addWidget(top_header_widget)
        resource_header_layout.addWidget(settings_selector_widget)

        self.layout.addWidget(self.resource_header)

        # 创建内容堆栈小部件来容纳基本设置和高级设置
        self.content_stack = QStackedWidget()
        self.content_stack.setFixedHeight(400)
        self.content_stack.setObjectName("contentStack")

        # 创建基本设置页面
        self.basic_settings_page = BasicSettingsPage(self.device_config)

        # 创建高级设置页面
        self.advanced_settings_page = AdvancedSettingsPage(self.device_config)

        # 将页面添加到堆栈小部件
        self.content_stack.addWidget(self.basic_settings_page)
        self.content_stack.addWidget(self.advanced_settings_page)

        # 添加堆栈小部件到主布局
        self.layout.addWidget(self.content_stack)

        # 在底部添加标签切换按钮
        self.tab_buttons_widget = QWidget()
        tab_buttons_layout = QHBoxLayout(self.tab_buttons_widget)
        tab_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.basic_tab_btn = QPushButton("基本设置")
        self.basic_tab_btn.setObjectName("primaryButton")
        self.basic_tab_btn.setCheckable(True)
        self.basic_tab_btn.setChecked(True)
        self.basic_tab_btn.clicked.connect(lambda: self.switch_tab("basic"))

        self.advanced_tab_btn = QPushButton("高级设置")
        self.advanced_tab_btn.setObjectName("secondaryButton")
        self.advanced_tab_btn.setCheckable(True)
        self.advanced_tab_btn.clicked.connect(lambda: self.switch_tab("advanced"))

        tab_buttons_layout.addWidget(self.basic_tab_btn)
        tab_buttons_layout.addWidget(self.advanced_tab_btn)

        self.layout.addWidget(self.tab_buttons_widget)
        self.layout.addStretch()

        # 初始显示基本设置标签页
        self.content_stack.setCurrentWidget(self.basic_settings_page)

        # 隐藏标签切换按钮，直到选择资源
        self.tab_buttons_widget.setVisible(False)

    def toggle_edit_mode(self):
        """切换设置名称编辑模式"""
        if not self.selected_resource_name or not self.selected_settings_name:
            return

        if self.is_editing_name:
            # 保存编辑并返回到选择器模式
            new_name = self.settings_name_editor.text().strip()
            if new_name and new_name != self.selected_settings_name:
                self.rename_settings(self.selected_settings_name, new_name)

            # 切换回下拉框模式
            self.settings_name_editor.setVisible(False)
            self.settings_selector.setVisible(True)
            self.edit_button.setText("编辑")
            self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
            self.edit_button.setToolTip("编辑设置名称")
            self.is_editing_name = False

            # 隐藏删除按钮
            self.delete_button.setVisible(False)

            # 刷新下拉框选项
            self.update_settings_selector()
        else:
            # 切换到编辑模式
            current_name = self.selected_settings_name
            self.settings_name_editor.setText(current_name)
            self.settings_name_editor.setVisible(True)
            self.settings_selector.setVisible(False)
            self.edit_button.setText("保存")
            self.edit_button.setIcon(QIcon("assets/icons/save.svg"))
            self.edit_button.setToolTip("保存设置名称")
            self.is_editing_name = True

            # 显示删除按钮
            self.delete_button.setVisible(True)

    def delete_settings(self):
        """删除当前选择的设置"""
        if not self.selected_resource_name or not self.selected_settings_name:
            return

        app_config = global_config.get_app_config()
        if not app_config:
            return

        # 获取当前资源的所有设置
        resource_settings = [s for s in app_config.resource_settings
                             if s.resource_name == self.selected_resource_name]

        # 如果只有一个设置，不允许删除
        if len(resource_settings) <= 1:
            QMessageBox.warning(
                self,
                "无法删除",
                f"无法删除设置 '{self.selected_settings_name}'，因为每个资源至少需要保留一个设置配置。"
            )
            return

        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除设置 '{self.selected_settings_name}' 吗？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 删除设置
        for i, settings in enumerate(app_config.resource_settings):
            if settings.name == self.selected_settings_name and settings.resource_name == self.selected_resource_name:
                app_config.resource_settings.pop(i)
                break

        # 更新所有引用此设置的资源，改为使用其他设置
        alternative_setting = resource_settings[0].name
        if alternative_setting == self.selected_settings_name and len(resource_settings) > 1:
            alternative_setting = resource_settings[1].name

        for device in app_config.devices:
            for resource in device.resources:
                if resource.resource_name == self.selected_resource_name and resource.settings_name == self.selected_settings_name:
                    resource.settings_name = alternative_setting

        # 保存更改
        global_config.save_all_configs()

        # 记录日志
        if self.logger:
            self.logger.info(f"已删除资源 {self.selected_resource_name} 的设置 {self.selected_settings_name}")

        # 退出编辑模式
        self.is_editing_name = True  # 设置为True，以便正确执行toggle_edit_mode中的逻辑
        self.toggle_edit_mode()

        # 更新选择的设置名称
        self.selected_settings_name = alternative_setting

        # 更新下拉框并选中新设置
        self.update_settings_selector()

        # 刷新页面内容
        self.refresh_settings_content()

    def rename_settings(self, old_name, new_name):
        """重命名资源设置"""
        if not self.device_config or not self.selected_resource_name:
            return

        # 找到需要重命名的设置
        app_config = global_config.get_app_config()
        if not app_config:
            return

        settings = next((s for s in app_config.resource_settings
                         if s.name == old_name and s.resource_name == self.selected_resource_name), None)
        if not settings:
            return

        # 更新设置名称
        settings.name = new_name

        # 更新资源中的引用
        for device in app_config.devices:
            for resource in device.resources:
                if resource.resource_name == self.selected_resource_name and resource.settings_name == old_name:
                    resource.settings_name = new_name

        # 保存更改
        global_config.save_all_configs()

        # 更新当前选中的设置名称
        self.selected_settings_name = new_name

        # 记录日志
        if self.logger:
            self.logger.info(f"已将资源 {self.selected_resource_name} 的设置名称从 {old_name} 修改为 {new_name}")

    def update_settings_selector(self):
        """更新设置选择器下拉框选项"""
        if not self.selected_resource_name:
            return

        self.settings_selector.blockSignals(True)
        self.settings_selector.clear()

        # 获取当前资源的所有设置
        app_config = global_config.get_app_config()
        if not app_config:
            self.settings_selector.blockSignals(False)
            return

        # 筛选出当前资源的设置
        resource_settings = [s for s in app_config.resource_settings
                             if s.resource_name == self.selected_resource_name]

        # 添加到下拉框
        for settings in resource_settings:
            self.settings_selector.addItem(settings.name, settings.name)

        # 如果有选中的设置，恢复选中状态
        if self.selected_settings_name:
            index = self.settings_selector.findData(self.selected_settings_name)
            if index >= 0:
                self.settings_selector.setCurrentIndex(index)
        elif self.settings_selector.count() > 0:
            # 否则选择第一个
            self.selected_settings_name = self.settings_selector.itemData(0)

        self.settings_selector.blockSignals(False)

    def on_settings_changed(self, index):
        """处理设置选择变化"""
        if index < 0:
            return

        # 获取选中的设置名称
        self.selected_settings_name = self.settings_selector.itemData(index)

        # 更新显示的设置内容
        if self.selected_resource_name and self.selected_settings_name:
            # 更新设备资源使用的设置
            self.update_device_resource_settings()

            # 刷新显示的内容
            self.refresh_settings_content()

    def update_device_resource_settings(self):
        """更新设备资源使用的设置名称"""
        if not self.device_config or not self.selected_resource_name or not self.selected_settings_name:
            return

        # 查找当前设备中的资源
        resource = next((r for r in self.device_config.resources
                         if r.resource_name == self.selected_resource_name), None)

        # 如果资源存在且设置名称不同，则更新
        if resource and resource.settings_name != self.selected_settings_name:
            resource.settings_name = self.selected_settings_name

            # 保存更改
            global_config.save_all_configs()

            # 记录日志
            if self.logger:
                self.logger.info(
                    f"设备 {self.device_config.device_name} 的资源 {self.selected_resource_name} 现在使用设置 {self.selected_settings_name}")

    def add_new_settings(self):
        """为当前资源添加新的空设置"""
        if not self.selected_resource_name or not self.device_config:
            return

        app_config = global_config.get_app_config()
        if not app_config:
            return

        # 生成新设置名称（确保唯一）
        base_name = f"{self.selected_resource_name}_settings_new"
        new_name = base_name
        counter = 1

        while any(s.name == new_name and s.resource_name == self.selected_resource_name
                  for s in app_config.resource_settings):
            new_name = f"{base_name}_{counter}"
            counter += 1

        # 创建新的空设置
        new_settings = ResourceSettings(
            name=new_name,
            resource_name=self.selected_resource_name,
            selected_tasks=[],
            options=[]
        )

        # 添加到配置
        app_config.resource_settings.append(new_settings)

        # 更新设备资源引用此设置
        resource = next((r for r in self.device_config.resources
                         if r.resource_name == self.selected_resource_name), None)

        if resource:
            resource.settings_name = new_name

        # 保存更改
        global_config.save_all_configs()

        # 更新当前选择
        self.selected_settings_name = new_name

        # 更新下拉框并选中新设置
        self.update_settings_selector()

        # 刷新页面内容
        self.refresh_settings_content()

        # 记录日志
        if self.logger:
            self.logger.info(f"为资源 {self.selected_resource_name} 创建了新设置 {new_name}")

    def refresh_settings_content(self):
        """刷新设置内容显示"""
        # 刷新基本和高级设置页
        if self.current_tab == "basic":
            self.basic_settings_page.show_resource_settings(self.selected_resource_name)
        else:
            self.advanced_settings_page.setup_for_resource(self.selected_resource_name)

    def switch_tab(self, tab_name):
        """切换标签页"""
        if tab_name == "basic":
            self.content_stack.setCurrentWidget(self.basic_settings_page)
            self.basic_tab_btn.setChecked(True)
            self.advanced_tab_btn.setChecked(False)
            self.current_tab = "basic"
        elif tab_name == "advanced":
            # 确保高级设置页面更新到当前选择的资源
            self.advanced_settings_page.setup_for_resource(self.selected_resource_name)

            self.content_stack.setCurrentWidget(self.advanced_settings_page)
            self.basic_tab_btn.setChecked(False)
            self.advanced_tab_btn.setChecked(True)
            self.current_tab = "advanced"

    def show_resource_settings(self, resource_name):
        """Show settings for the selected resource"""
        self.selected_resource_name = resource_name

        # 获取当前设备的logger
        if self.device_config:
            self.logger = log_manager.get_device_logger(self.device_config.device_name)

        # 显示资源标题和状态指示器
        self.resource_header.setVisible(True)
        self.resource_name_label.setText(resource_name)

        # 从设备配置中获取资源启用状态
        resource_enabled = False
        resource_config = None
        if self.device_config:
            resource_config = next((r for r in self.device_config.resources
                                    if r.resource_name == resource_name), None)
            if resource_config:
                resource_enabled = resource_config.enable
                self.selected_settings_name = resource_config.settings_name

        # 更新状态指示器
        self.update_resource_status(resource_name, resource_enabled)

        # 更新设置选择器
        self.update_settings_selector()

        # 更新基本设置页面
        self.basic_settings_page.show_resource_settings(resource_name)

        # 显示标签切换按钮
        self.tab_buttons_widget.setVisible(True)

        # 如果当前是高级设置标签，也更新高级设置页面
        if self.current_tab == "advanced":
            self.advanced_settings_page.setup_for_resource(resource_name)

    def clear_settings(self):
        """Clear the settings content"""
        self.selected_resource_name = None
        self.selected_settings_name = None

        # 隐藏资源标题和状态指示器
        self.resource_header.setVisible(False)

        # 清除基本设置页面
        self.basic_settings_page.clear_settings()

        # 清除高级设置页面
        self.advanced_settings_page.clear_settings()

        # 隐藏标签切换按钮
        self.tab_buttons_widget.setVisible(False)

        # 重置当前标签页并显示基本设置
        self.current_tab = "basic"
        self.content_stack.setCurrentWidget(self.basic_settings_page)
        self.basic_tab_btn.setChecked(True)
        self.advanced_tab_btn.setChecked(False)

        # 清空设置选择器
        self.settings_selector.clear()

        # 重置编辑模式
        if self.is_editing_name:
            self.settings_name_editor.setVisible(False)
            self.settings_selector.setVisible(True)
            self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
            self.edit_button.setText("编辑")
            self.is_editing_name = False
            self.delete_button.setVisible(False)  # 隐藏删除按钮

    def update_resource_status(self, resource_name, enabled):
        """更新 UI 中的资源状态"""
        if self.selected_resource_name == resource_name:
            # 更新状态点的颜色
            self.status_dot.setStyleSheet(
                f"background-color: {'#34a853' if enabled else '#ea4335'}; border-radius: 4px;")

            # 更新状态文本
            self.status_text.setText(f"{'已启用' if enabled else '已禁用'}")
            self.status_text.setStyleSheet(f"color: {'#34a853' if enabled else '#ea4335'}; font-size: 12px;")

    def _clear_layout(self, layout):
        """Clear all widgets from a layout"""
        if layout is None:
            return

        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())
