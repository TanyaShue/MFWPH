from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QStackedWidget, QComboBox, QLineEdit, QMessageBox
)

from app.models.config.app_config import ResourceSettings, Resource
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.widgets.advanced_settings_page import AdvancedSettingsPage
from app.widgets.basic_settings_page import BasicSettingsPage


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
        self.current_tab = "basic"
        self.resource_header = None
        self.settings_selector = None
        self.edit_button = None
        self.delete_button = None
        self.add_button = None
        self.settings_name_editor = None
        self.is_editing_name = False
        self.logger = None

        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)

        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)

        # 创建资源头部区域
        self.resource_header = QWidget()
        self.resource_header.setVisible(False)
        resource_header_layout = QVBoxLayout(self.resource_header)
        resource_header_layout.setContentsMargins(0, 0, 0, 0)
        resource_header_layout.setSpacing(8)

        # 顶部头部 - 包含资源名称、设置选择器、控制按钮和状态指示器
        top_header_widget = QWidget()
        top_header_layout = QHBoxLayout(top_header_widget)
        top_header_layout.setContentsMargins(0, 0, 0, 0)
        top_header_layout.setSpacing(12)

        # 资源名称标签
        self.resource_name_label = QLabel()
        self.resource_name_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.resource_name_label.setObjectName("sectionTitle")

        # 设置选择器区域
        settings_widget = QWidget()
        settings_layout = QHBoxLayout(settings_widget)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        # 设置下拉框
        self.settings_selector = QComboBox()
        self.settings_selector.setObjectName("settingsSelector")
        self.settings_selector.setMinimumWidth(0)
        self.settings_selector.currentIndexChanged.connect(self.on_settings_changed)

        # 设置名称编辑器（编辑模式时显示）
        self.settings_name_editor = QLineEdit()
        self.settings_name_editor.setObjectName("settingsNameEditor")
        self.settings_name_editor.setMinimumWidth(10)
        self.settings_name_editor.setVisible(False)

        # 添加按钮（小图标按钮）
        self.add_button = QPushButton()
        self.add_button.setIcon(QIcon("assets/icons/add.svg"))
        self.add_button.setToolTip("添加新设置")
        self.add_button.setObjectName("smallIconButton")
        self.add_button.setFixedSize(24, 24)
        self.add_button.clicked.connect(self.add_new_settings)

        # 编辑按钮（小图标按钮）
        self.edit_button = QPushButton()
        self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
        self.edit_button.setToolTip("编辑设置名称")
        self.edit_button.setObjectName("smallIconButton")
        self.edit_button.setFixedSize(24, 24)
        self.edit_button.clicked.connect(self.toggle_edit_mode)

        # 删除按钮（小图标按钮，编辑模式时显示）
        self.delete_button = QPushButton()
        self.delete_button.setIcon(QIcon("assets/icons/delete.svg"))
        self.delete_button.setToolTip("删除当前设置")
        self.delete_button.setObjectName("smallIconButton")
        self.delete_button.setFixedSize(24, 24)
        self.delete_button.setVisible(False)
        self.delete_button.clicked.connect(self.delete_settings)

        # 将控件添加到设置区域
        settings_layout.addWidget(self.settings_selector)
        settings_layout.addWidget(self.settings_name_editor)
        settings_layout.addWidget(self.add_button)
        settings_layout.addWidget(self.edit_button)
        settings_layout.addWidget(self.delete_button)

        # 状态指示器
        self.status_indicator = QWidget()
        status_layout = QHBoxLayout(self.status_indicator)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(5)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(4, 4)

        self.status_text = QLabel()
        self.status_text.setObjectName("statusText")

        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)

        # 组装顶部布局
        top_header_layout.addWidget(self.resource_name_label)
        top_header_layout.addStretch()  # 弹性空间，将设置区域推到中间
        top_header_layout.addWidget(settings_widget)
        top_header_layout.addStretch()  # 弹性空间，将状态指示器推到右侧
        top_header_layout.addWidget(self.status_indicator)

        resource_header_layout.addWidget(top_header_widget)
        self.layout.addWidget(self.resource_header)

        # 内容堆栈
        self.content_stack = QStackedWidget()
        self.content_stack.setMinimumHeight(200)
        self.basic_settings_page = BasicSettingsPage(self.device_config)
        # self.advanced_settings_page = AdvancedSettingsPage(self.device_config)

        self.content_stack.addWidget(self.basic_settings_page)
        # self.content_stack.addWidget(self.advanced_settings_page)
        self.layout.addWidget(self.content_stack)

        # 标签页按钮
        self.tab_buttons_widget = QWidget()
        tab_buttons_layout = QHBoxLayout(self.tab_buttons_widget)
        tab_buttons_layout.setContentsMargins(0, 0, 0, 0)

        self.basic_tab_btn = QPushButton("基本设置")
        self.basic_tab_btn.setObjectName("primaryButton")
        self.basic_tab_btn.setCheckable(True)
        self.basic_tab_btn.setChecked(True)
        self.basic_tab_btn.clicked.connect(lambda: self.switch_tab("basic"))

        # self.advanced_tab_btn = QPushButton("高级设置")
        # self.advanced_tab_btn.setObjectName("secondaryButton")
        # self.advanced_tab_btn.setCheckable(True)
        # self.advanced_tab_btn.clicked.connect(lambda: self.switch_tab("advanced"))

        tab_buttons_layout.addWidget(self.basic_tab_btn)
        # tab_buttons_layout.addWidget(self.advanced_tab_btn)

        self.layout.addWidget(self.tab_buttons_widget)

        self.content_stack.setCurrentWidget(self.basic_settings_page)
        self.tab_buttons_widget.setVisible(False)

    def toggle_edit_mode(self):
        """切换设置名称编辑模式"""
        if not self.selected_resource_name or not self.selected_settings_name:
            return

        if self.is_editing_name:
            # 保存模式 -> 查看模式
            new_name = self.settings_name_editor.text().strip()
            if new_name and new_name != self.selected_settings_name:
                self.rename_settings(self.selected_settings_name, new_name)

            self.settings_name_editor.setVisible(False)
            self.settings_selector.setVisible(True)
            self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
            self.edit_button.setToolTip("编辑设置名称")
            self.is_editing_name = False
            self.delete_button.setVisible(False)
            self.add_button.setVisible(True)
            self.update_settings_selector()
        else:
            # 查看模式 -> 编辑模式
            current_name = self.selected_settings_name
            self.settings_name_editor.setText(current_name)
            self.settings_name_editor.setVisible(True)
            self.settings_selector.setVisible(False)
            self.edit_button.setIcon(QIcon("assets/icons/save.svg"))
            self.edit_button.setToolTip("保存设置名称")
            self.is_editing_name = True
            self.delete_button.setVisible(True)
            self.add_button.setVisible(False)

    def delete_settings(self):
        """删除当前选择的设置"""
        if not self.selected_resource_name or not self.selected_settings_name:
            return

        app_config = global_config.get_app_config()
        if not app_config:
            return

        resource_settings = [s for s in app_config.resource_settings
                             if s.resource_name == self.selected_resource_name]

        if len(resource_settings) <= 1:
            QMessageBox.warning(
                self,
                "无法删除",
                f"无法删除设置 '{self.selected_settings_name}'，因为每个资源至少需要保留一个设置配置。"
            )
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除设置 '{self.selected_settings_name}' 吗？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        for i, settings in enumerate(app_config.resource_settings):
            if settings.name == self.selected_settings_name and settings.resource_name == self.selected_resource_name:
                app_config.resource_settings.pop(i)
                break

        alternative_setting_obj = next(
            (s for s in app_config.resource_settings if s.resource_name == self.selected_resource_name), None)
        if not alternative_setting_obj:
            QMessageBox.critical(self, "错误", f"无法为资源 {self.selected_resource_name} 找到备用设置。")
            return
        alternative_setting_name = alternative_setting_obj.name

        for device in app_config.devices:
            for resource in device.resources:
                if resource.resource_name == self.selected_resource_name and resource.settings_name == self.selected_settings_name:
                    resource.settings_name = alternative_setting_name

        global_config.save_all_configs()

        if self.logger:
            self.logger.info(f"已删除资源 {self.selected_resource_name} 的设置 {self.selected_settings_name}")

        if self.is_editing_name:
            self.is_editing_name = True
            self.toggle_edit_mode()

        self.selected_settings_name = alternative_setting_name
        self.update_settings_selector()
        self.refresh_settings_content()

    def rename_settings(self, old_name, new_name):
        """重命名资源设置"""
        if not self.device_config or not self.selected_resource_name:
            return

        app_config = global_config.get_app_config()
        if not app_config:
            return

        if any(s.name == new_name and s.resource_name == self.selected_resource_name for s in
               app_config.resource_settings):
            QMessageBox.warning(self, "重命名失败", f"设置名称 '{new_name}' 已存在。")
            self.settings_name_editor.setText(old_name)
            return

        settings = next((s for s in app_config.resource_settings
                         if s.name == old_name and s.resource_name == self.selected_resource_name), None)
        if not settings:
            return

        settings.name = new_name

        for device in app_config.devices:
            for resource in device.resources:
                if resource.resource_name == self.selected_resource_name and resource.settings_name == old_name:
                    resource.settings_name = new_name

        global_config.save_all_configs()
        self.selected_settings_name = new_name

        if self.logger:
            self.logger.info(f"已将资源 {self.selected_resource_name} 的设置名称从 {old_name} 修改为 {new_name}")

    def update_settings_selector(self):
        """更新设置选择器下拉框选项"""
        if not self.selected_resource_name:
            self.settings_selector.clear()
            return

        self.settings_selector.blockSignals(True)
        self.settings_selector.clear()

        app_config = global_config.get_app_config()
        if not app_config:
            self.settings_selector.blockSignals(False)
            return

        resource_settings_list = [s for s in app_config.resource_settings
                                  if s.resource_name == self.selected_resource_name]

        for settings in resource_settings_list:
            self.settings_selector.addItem(settings.name, settings.name)

        if self.selected_settings_name:
            index = self.settings_selector.findData(self.selected_settings_name)
            if index >= 0:
                self.settings_selector.setCurrentIndex(index)
            elif self.settings_selector.count() > 0:
                self.settings_selector.setCurrentIndex(0)
                self.selected_settings_name = self.settings_selector.itemData(0)
        elif self.settings_selector.count() > 0:
            self.settings_selector.setCurrentIndex(0)
            self.selected_settings_name = self.settings_selector.itemData(0)

        can_edit_delete = self.settings_selector.count() > 0 and self.selected_settings_name is not None
        self.edit_button.setEnabled(can_edit_delete)
        self.delete_button.setEnabled(can_edit_delete)

        self.settings_selector.blockSignals(False)

    def on_settings_changed(self, index):
        """处理设置选择变化"""
        if index < 0 or not self.settings_selector.itemData(index):
            if self.settings_selector.count() > 0:
                self.selected_settings_name = self.settings_selector.itemData(0)
            else:
                self.selected_settings_name = None
                self.refresh_settings_content()
                return
        else:
            self.selected_settings_name = self.settings_selector.itemData(index)

        if self.selected_resource_name and self.selected_settings_name:
            self.update_device_resource_settings()
            self.refresh_settings_content()

    def update_device_resource_settings(self):
        """更新设备资源使用的设置名称"""
        if not self.device_config or not self.selected_resource_name or not self.selected_settings_name:
            return

        resource_in_device = next((r for r in self.device_config.resources
                                   if r.resource_name == self.selected_resource_name), None)

        if resource_in_device and resource_in_device.settings_name != self.selected_settings_name:
            resource_in_device.settings_name = self.selected_settings_name
            global_config.save_all_configs()
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

        base_name = f"{self.selected_resource_name}_settings_new"
        new_name = base_name
        counter = 1
        while any(s.name == new_name and s.resource_name == self.selected_resource_name
                  for s in app_config.resource_settings):
            new_name = f"{base_name}_{counter}"
            counter += 1

        new_settings = ResourceSettings(
            name=new_name,
            resource_name=self.selected_resource_name,
            selected_tasks=[],
            options=[]
        )
        app_config.resource_settings.append(new_settings)

        device_resource_entry = next((r for r in self.device_config.resources
                                      if r.resource_name == self.selected_resource_name), None)
        if device_resource_entry:
            device_resource_entry.settings_name = new_name

        global_config.save_all_configs()
        self.selected_settings_name = new_name
        self.update_settings_selector()
        self.refresh_settings_content()

        if self.logger:
            self.logger.info(f"为资源 {self.selected_resource_name} 创建了新设置 {new_name}")

    def refresh_settings_content(self):
        """刷新设置内容显示"""
        if not self.selected_resource_name or not self.selected_settings_name:
            self.basic_settings_page.clear_settings()
            # self.advanced_settings_page.clear_settings()
            return

        if self.current_tab == "basic":
            self.basic_settings_page.show_resource_settings(self.selected_resource_name)
        # else:
        #     self.advanced_settings_page.setup_for_resource(self.selected_resource_name)

    def switch_tab(self, tab_name):
        """切换标签页"""
        self.current_tab = tab_name
        if tab_name == "basic":
            self.content_stack.setCurrentWidget(self.basic_settings_page)
            self.basic_tab_btn.setChecked(True)
            self.advanced_tab_btn.setChecked(False)
            self.basic_settings_page.show_resource_settings(self.selected_resource_name)
        # elif tab_name == "advanced":
        #     self.content_stack.setCurrentWidget(self.advanced_settings_page)
        #     self.basic_tab_btn.setChecked(False)
        #     self.advanced_tab_btn.setChecked(True)
        #     self.advanced_settings_page.setup_for_resource(self.selected_resource_name)

    def show_resource_settings(self, resource_name: str):
        """Show settings for the selected resource, ensuring all necessary configurations are linked."""
        self.selected_resource_name = resource_name
        if self.device_config:
            self.logger = log_manager.get_device_logger(self.device_config.device_name)
        else:
            self.logger = log_manager.get_logger("TaskSettingsWidget_NoDevice")  # Fallback logger

        app_config = global_config.get_app_config()
        if not app_config:
            if self.logger: self.logger.error("AppConfig not loaded.")
            self.clear_settings()
            return

        # Ensure all Resource instances in the current app_config are linked (defensive)
        app_config.link_resources_to_config()

        # --- Stage 1: Ensure ResourceSettings exists globally for this resource_name ---
        global_resource_settings_list = [s for s in app_config.resource_settings
                                         if s.resource_name == resource_name]
        effective_settings_name = ""

        if not global_resource_settings_list:
            # No global ResourceSettings for this resource_name. Create a default one.
            default_settings_name = f"{resource_name}_default_settings"
            new_global_settings = ResourceSettings(
                name=default_settings_name,
                resource_name=resource_name,
                selected_tasks=[],
                options=[]
            )
            app_config.resource_settings.append(new_global_settings)
            global_resource_settings_list.append(new_global_settings)
            effective_settings_name = default_settings_name
            if self.logger:
                self.logger.info(
                    f"Created global default ResourceSettings '{default_settings_name}' for resource '{resource_name}'.")

        # --- Stage 2: Ensure a Resource entry in device_config.resources for this resource_name ---
        # And that it's properly linked and points to a valid ResourceSettings.
        device_resource_entry = next((r for r in self.device_config.resources
                                      if r.resource_name == resource_name), None)

        if not device_resource_entry:
            # This device doesn't have this resource listed yet. Add it.
            # It should point to the first available (or newly created default) ResourceSettings.
            if not effective_settings_name:  # Default wasn't just created, pick first from list
                effective_settings_name = global_resource_settings_list[0].name

            device_resource_entry = Resource(
                resource_name=resource_name,
                settings_name=effective_settings_name,
                enable=False  # New resources on a device are initially disabled
            )
            device_resource_entry.set_app_config(app_config)
            self.device_config.resources.append(device_resource_entry)
            if self.logger:
                self.logger.info(
                    f"Added Resource entry for '{resource_name}' to device '{self.device_config.device_name}', using settings '{effective_settings_name}'.")
        else:
            # Device resource entry exists. Ensure its _app_config is set.
            if device_resource_entry._app_config is None:
                device_resource_entry.set_app_config(app_config)

            # Ensure its settings_name points to a valid global ResourceSettings.
            # It might be pointing to an old/deleted setting or be empty.
            current_pointed_settings_valid = any(s.name == device_resource_entry.settings_name and
                                                 s.resource_name == resource_name
                                                 for s in global_resource_settings_list)
            if not device_resource_entry.settings_name or not current_pointed_settings_valid:
                # Invalid or missing settings_name, link to the first available.
                device_resource_entry.settings_name = global_resource_settings_list[0].name
                if self.logger:
                    self.logger.warn(
                        f"Resource '{resource_name}' on device '{self.device_config.device_name}' had invalid/missing settings_name. Reset to '{device_resource_entry.settings_name}'.")
            effective_settings_name = device_resource_entry.settings_name

        # --- Stage 3: UI Update & Save ---
        self.selected_settings_name = effective_settings_name

        self.resource_header.setVisible(True)
        self.resource_name_label.setText(resource_name)
        # Update status indicator using the current enable status from the device_resource_entry
        self.update_resource_status(resource_name, device_resource_entry.enable)

        self.update_settings_selector()
        # Refresh content based on the current tab and selected resource/settings
        self.refresh_settings_content()
        self.tab_buttons_widget.setVisible(True)

        # Save all accumulated changes to app_config
        global_config.save_all_configs()

    def clear_settings(self):
        """Clear the settings content"""
        self.selected_resource_name = None
        self.selected_settings_name = None

        self.resource_header.setVisible(False)
        self.basic_settings_page.clear_settings()
        self.advanced_settings_page.clear_settings()
        self.tab_buttons_widget.setVisible(False)

        self.current_tab = "basic"
        self.content_stack.setCurrentWidget(self.basic_settings_page)
        self.basic_tab_btn.setChecked(True)
        self.advanced_tab_btn.setChecked(False)

        self.settings_selector.blockSignals(True)
        self.settings_selector.clear()
        self.settings_selector.blockSignals(False)

        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)

        if self.is_editing_name:
            self.settings_name_editor.setVisible(False)
            self.settings_selector.setVisible(True)
            self.edit_button.setIcon(QIcon("assets/icons/edit.svg"))
            self.edit_button.setToolTip("编辑设置名称")
            self.is_editing_name = False
            self.delete_button.setVisible(False)
            self.add_button.setVisible(True)

    def update_resource_status(self, resource_name, enabled):
        """更新 UI 中的资源状态"""
        if self.status_dot and self.status_text and self.selected_resource_name == resource_name:
            self.status_dot.setStyleSheet(
                f"background-color: {'#34a853' if enabled else '#ea4335'}; border-radius: 4px;")
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
