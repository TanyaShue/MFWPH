# app/widgets/resource_config_widget.py

from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QComboBox, QLineEdit, QStackedWidget
)

from app.models.config.app_config import ResourceSettings
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class ResourceConfigWidget(QFrame):
    """
    用于选择和管理资源配置方案 (settings) 和资源包 (resource_pack) 的小部件。
    采用无弹窗、状态化的确认机制，以提供更流畅的用户体验。
    """
    # 当配置方案切换时发出信号 (资源名称, 新的配置方案名称)
    settings_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.device_config = None
        self.selected_resource_name = None
        self.selected_settings_name = None
        self.logger = None

        # 状态标记
        self.is_editing_name = False
        self.is_confirming_delete = False

        self.setObjectName("taskSettingsFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # 创建主内容区域和占位符区域
        self.main_content_widget = QWidget()
        self.placeholder_widget = self._create_placeholder_widget()
        self._init_main_content_ui()

        self.stack.addWidget(self.main_content_widget)
        self.stack.addWidget(self.placeholder_widget)
        # 初始显示占位符
        self.stack.setCurrentWidget(self.placeholder_widget)

    def _create_placeholder_widget(self) -> QWidget:
        """创建一个居中的占位提示标签"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel("请从左侧选择一个资源以进行配置")
        label.setObjectName("placeholderText")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        return widget

    def _init_main_content_ui(self):
        """初始化主内容界面的所有控件"""
        layout = QVBoxLayout(self.main_content_widget)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(15)

        # 顶部：资源名称和状态指示器
        top_layout = QHBoxLayout()
        self.resource_name_label = QLabel("资源配置")
        self.resource_name_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.resource_name_label.setObjectName("sectionTitle")
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
        top_layout.addWidget(self.resource_name_label)
        top_layout.addStretch()
        top_layout.addWidget(self.status_indicator)
        layout.addLayout(top_layout)

        # 配置方案行：使用 QHBoxLayout 实现紧凑的单行布局
        settings_row_layout = QHBoxLayout()
        settings_row_layout.setSpacing(8)

        settings_label = QLabel("配置:")

        # 使用 QStackedWidget 优雅地在下拉框和输入框之间切换
        self.editor_stack = QStackedWidget()
        self.settings_selector = QComboBox()
        self.settings_selector.setObjectName("settingsSelector")
        self.settings_selector.setMinimumWidth(200)
        self.settings_selector.currentIndexChanged.connect(self.on_settings_changed)

        self.settings_name_editor = QLineEdit()
        self.settings_name_editor.setObjectName("settingsNameEditor")
        self.settings_name_editor.setMinimumWidth(200)
        self.settings_name_editor.returnPressed.connect(self.handle_edit_save_action)

        self.editor_stack.addWidget(self.settings_selector)
        self.editor_stack.addWidget(self.settings_name_editor)

        # 控制按钮：仅使用图标以节省空间
        self.add_cancel_button = QPushButton()
        self.edit_save_button = QPushButton()
        self.delete_confirm_button = QPushButton()

        for btn in [self.add_cancel_button, self.edit_save_button, self.delete_confirm_button]:
            btn.setIconSize(QSize(16, 16))
            btn.setFixedSize(QSize(28, 28))
            btn.setText("")

        self.add_cancel_button.clicked.connect(self.handle_add_or_cancel_action)
        self.edit_save_button.clicked.connect(self.handle_edit_save_action)
        self.delete_confirm_button.clicked.connect(self.handle_delete_confirm_action)

        # 将所有控件添加到单行布局中
        settings_row_layout.addWidget(settings_label)
        settings_row_layout.addWidget(self.editor_stack, 1)  # 1 表示此控件可拉伸
        settings_row_layout.addSpacing(5)
        settings_row_layout.addWidget(self.add_cancel_button)
        settings_row_layout.addWidget(self.edit_save_button)
        settings_row_layout.addWidget(self.delete_confirm_button)

        layout.addLayout(settings_row_layout)

        # 资源包选择行
        pack_layout = QHBoxLayout()
        pack_label = QLabel("资源包:")
        self.pack_selector = QComboBox()
        self.pack_selector.setObjectName("packSelector")
        self.pack_selector.setMinimumWidth(200)
        self.pack_selector.currentIndexChanged.connect(self.on_pack_changed)
        pack_layout.addWidget(pack_label)
        pack_layout.addWidget(self.pack_selector)
        pack_layout.addStretch()
        layout.addLayout(pack_layout)
        layout.addStretch()

        self._update_ui_state()

    def handle_add_or_cancel_action(self):
        """处理 "添加方案" 或 "取消" 按钮的点击事件"""
        if self.is_editing_name or self.is_confirming_delete:
            self._reset_ui_state()  # 如果在编辑或确认删除状态，则行为是“取消”
        else:
            self.add_new_settings()  # 否则行为是“添加”

    def handle_edit_save_action(self):
        """处理 "编辑名称" 或 "保存" 按钮的点击事件"""
        if self.is_editing_name:
            # “保存”逻辑
            new_name = self.settings_name_editor.text().strip()
            if new_name and new_name != self.selected_settings_name:
                self.rename_settings(self.selected_settings_name, new_name)
            self._reset_ui_state()
        else:
            # “编辑”逻辑
            self.is_editing_name = True
            self.is_confirming_delete = False
            self.settings_name_editor.setText(self.selected_settings_name)
            self.settings_name_editor.selectAll()
            self._update_ui_state()
            self.settings_name_editor.setFocus()

    def handle_delete_confirm_action(self):
        """处理 "删除方案" 或 "确认删除" 按钮的点击事件"""
        app_config = global_config.get_app_config()
        settings_count = sum(1 for s in app_config.resource_settings if s.resource_name == self.selected_resource_name)
        if settings_count <= 1 and not self.is_confirming_delete:
            self.logger.warning(f"无法删除资源 '{self.selected_resource_name}' 的最后一个配置。")
            return

        if self.is_confirming_delete:
            # “确认删除”逻辑
            self.delete_settings()
            self._reset_ui_state()
        else:
            # “删除”逻辑（进入待确认状态）
            self.is_confirming_delete = True
            self.is_editing_name = False
            self._update_ui_state()

    def _reset_ui_state(self):
        """重置所有状态标记并更新UI到默认状态"""
        self.is_editing_name = False
        self.is_confirming_delete = False
        self.update_settings_selector()  # 重新加载并选中正确的项
        self._update_ui_state()

    def _update_ui_state(self):
        """根据当前状态（is_editing_name, is_confirming_delete）集中更新所有UI元素"""
        if self.is_editing_name:
            # --- 编辑状态 ---
            self.editor_stack.setCurrentWidget(self.settings_name_editor)
            self.pack_selector.setEnabled(False)

            self.add_cancel_button.setIcon(QIcon("assets/icons/cancel.svg"))
            self.add_cancel_button.setToolTip("放弃修改")
            self.add_cancel_button.setObjectName("secondaryButton")
            self.add_cancel_button.setVisible(True)

            self.edit_save_button.setIcon(QIcon("assets/icons/save.svg"))
            self.edit_save_button.setToolTip("保存新的方案名称")
            self.edit_save_button.setObjectName("primaryButton")
            self.edit_save_button.setVisible(True)

            self.delete_confirm_button.setVisible(False)

        elif self.is_confirming_delete:
            # --- 确认删除状态 ---
            self.editor_stack.setCurrentWidget(self.settings_selector)
            self.settings_selector.setEnabled(False)
            self.pack_selector.setEnabled(False)

            self.add_cancel_button.setIcon(QIcon("assets/icons/cancel.svg"))
            self.add_cancel_button.setToolTip("取消删除操作")
            self.add_cancel_button.setObjectName("secondaryButton")
            self.add_cancel_button.setVisible(True)

            self.edit_save_button.setVisible(False)

            self.delete_confirm_button.setIcon(QIcon("assets/icons/delete.svg"))
            self.delete_confirm_button.setToolTip("确认删除，此操作不可恢复！")
            self.delete_confirm_button.setObjectName("dangerButton")
            self.delete_confirm_button.setVisible(True)
            self.delete_confirm_button.setEnabled(True)

        else:
            # --- 默认状态 ---
            self.editor_stack.setCurrentWidget(self.settings_selector)
            self.settings_selector.setEnabled(True)
            self.pack_selector.setEnabled(True)

            self.add_cancel_button.setVisible(True)
            self.edit_save_button.setVisible(True)
            self.delete_confirm_button.setVisible(True)

            self.add_cancel_button.setIcon(QIcon("assets/icons/add.svg"))
            self.add_cancel_button.setToolTip("添加一个新的配置")
            self.add_cancel_button.setObjectName("primaryButton")
            self.add_cancel_button.setEnabled(True)

            self.edit_save_button.setIcon(QIcon("assets/icons/edit.svg"))
            self.edit_save_button.setToolTip("编辑当前方案的名称")
            self.edit_save_button.setObjectName("secondaryButton")
            self.edit_save_button.setEnabled(self.settings_selector.count() > 0)

            self.delete_confirm_button.setIcon(QIcon("assets/icons/delete.svg"))
            self.delete_confirm_button.setToolTip("删除当前选中的配置")
            self.delete_confirm_button.setObjectName("secondaryButton")
            # 只有当配置方案多于一个时，才允许删除
            self.delete_confirm_button.setEnabled(self.settings_selector.count() > 1)

        # 强制刷新所有按钮的样式
        for btn in [self.add_cancel_button, self.edit_save_button, self.delete_confirm_button]:
            btn.style().polish(btn)

    def show_for_resource(self, device_config, resource_name):
        """
        外部调用的主方法，用于显示指定资源的配置界面。
        """
        self.device_config = device_config
        self.selected_resource_name = resource_name
        self.logger = log_manager.get_device_logger(device_config.device_name)

        device_resource = next((r for r in self.device_config.resources if r.resource_name == resource_name), None)
        if device_resource:
            self.selected_settings_name = device_resource.settings_name
            self.update_resource_status(resource_name, device_resource.enable)
        else:
            self.selected_settings_name = None

        self.stack.setCurrentWidget(self.main_content_widget)
        self.resource_name_label.setText(resource_name)

        self._reset_ui_state()

        # 更新资源包选择器
        self.update_pack_selector()

    def update_settings_selector(self):
        """更新配置方案下拉框的内容和当前选项"""
        if not self.selected_resource_name:
            self.settings_selector.clear()
            return

        self.settings_selector.blockSignals(True)
        current_selection = self.selected_settings_name
        self.settings_selector.clear()

        app_config = global_config.get_app_config()
        resource_settings_list = [s for s in app_config.resource_settings if
                                  s.resource_name == self.selected_resource_name]

        for settings in resource_settings_list:
            self.settings_selector.addItem(settings.name, settings.name)

        index = self.settings_selector.findData(current_selection)
        if index >= 0:
            self.settings_selector.setCurrentIndex(index)
        elif self.settings_selector.count() > 0:
            self.settings_selector.setCurrentIndex(0)
            self.selected_settings_name = self.settings_selector.itemData(0)

        self.settings_selector.blockSignals(False)
        self._update_ui_state()

        if self.settings_selector.currentIndex() >= 0:
            self.on_settings_changed(self.settings_selector.currentIndex())

    def on_settings_changed(self, index):
        """当配置方案下拉框选项改变时触发"""
        if index < 0 or not self.settings_selector.itemData(index): return
        if self.is_editing_name or self.is_confirming_delete: return

        new_settings_name = self.settings_selector.itemData(index)
        self.selected_settings_name = new_settings_name

        resource_in_device = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if resource_in_device and resource_in_device.settings_name != new_settings_name:
            resource_in_device.settings_name = new_settings_name
            global_config.save_all_configs()
            self.logger.info(
                f"设备 {self.device_config.device_name} 的资源 {self.selected_resource_name} 现在使用设置 {new_settings_name}")
        self.settings_changed.emit(self.selected_resource_name, new_settings_name)
        self._update_ui_state()

    def delete_settings(self):
        """删除当前选定的配置方案"""
        app_config = global_config.get_app_config()
        # 从全局配置中移除该方案
        app_config.resource_settings = [s for s in app_config.resource_settings if not (
                s.name == self.selected_settings_name and s.resource_name == self.selected_resource_name)]

        # 找到一个备用方案，用于更新其他正在使用被删除方案的设备
        alternative_setting = next(
            (s for s in app_config.resource_settings if s.resource_name == self.selected_resource_name), None)
        new_setting_name = alternative_setting.name if alternative_setting else None

        # 更新所有设备，将使用旧方案的指向新方案
        for device in app_config.devices:
            for res in device.resources:
                if res.resource_name == self.selected_resource_name and res.settings_name == self.selected_settings_name:
                    res.settings_name = new_setting_name

        global_config.save_all_configs()
        self.logger.info(f"已删除资源 '{self.selected_resource_name}' 的配置 '{self.selected_settings_name}'")
        self.selected_settings_name = new_setting_name

    def rename_settings(self, old_name, new_name):
        """重命名配置方案"""
        app_config = global_config.get_app_config()
        # 检查新名称是否已存在
        if any(s.name == new_name and s.resource_name == self.selected_resource_name for s in
               app_config.resource_settings):
            self.logger.warning(f"设置名称 '{new_name}' 已存在，重命名失败。")
            return

        # 更新全局配置
        settings = next((s for s in app_config.resource_settings if
                         s.name == old_name and s.resource_name == self.selected_resource_name), None)
        if settings: settings.name = new_name

        # 更新所有设备的引用
        for device in app_config.devices:
            for res in device.resources:
                if res.resource_name == self.selected_resource_name and res.settings_name == old_name:
                    res.settings_name = new_name

        global_config.save_all_configs()
        self.selected_settings_name = new_name
        self.logger.info(f"已将资源 '{self.selected_resource_name}' 的设置名称从 '{old_name}' 修改为 '{new_name}'")

    def add_new_settings(self):
        """添加一个新的配置方案"""
        app_config = global_config.get_app_config()
        base_name = "新方案"
        new_name = base_name
        counter = 1
        # 自动生成一个不重复的名称
        while any(s.name == new_name and s.resource_name == self.selected_resource_name for s in
                  app_config.resource_settings):
            new_name = f"{base_name}_{counter}"
            counter += 1

        new_settings = ResourceSettings(name=new_name, resource_name=self.selected_resource_name, task_instances={},
                                        task_order=[])
        app_config.resource_settings.append(new_settings)
        self.selected_settings_name = new_name

        # 将当前设备对此资源的设置指向这个新方案
        device_resource = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if device_resource: device_resource.settings_name = new_name

        global_config.save_all_configs()
        self.update_settings_selector()
        self.logger.info(f"为资源 {self.selected_resource_name} 创建了新设置 {new_name}")

    def clear(self):
        """清空组件内容并重置状态"""
        self.stack.setCurrentWidget(self.placeholder_widget)
        self._reset_ui_state()
        self.device_config = None
        self.selected_resource_name = None
        self.selected_settings_name = None
        self.settings_selector.clear()
        self.pack_selector.clear()

    def update_pack_selector(self):
        """更新资源包下拉框的内容"""
        self.pack_selector.blockSignals(True)
        self.pack_selector.clear()
        resource_config = global_config.get_resource_config(self.selected_resource_name)

        if not resource_config or not hasattr(resource_config, 'resource_pack') or not resource_config.resource_pack:
            self.pack_selector.addItem("无可用资源包")
            self.pack_selector.setEnabled(False)
        else:
            self.pack_selector.setEnabled(True)
            for pack in resource_config.resource_pack:
                pack_name = pack.get('name', '未命名资源包')
                self.pack_selector.addItem(pack_name, pack_name)

            # 选中当前设备配置的资源包
            device_resource = next(
                (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
            if device_resource and hasattr(device_resource, 'resource_pack') and device_resource.resource_pack:
                index = self.pack_selector.findData(device_resource.resource_pack)
                if index >= 0: self.pack_selector.setCurrentIndex(index)
        self.pack_selector.blockSignals(False)

    def on_pack_changed(self, index):
        """当资源包选项改变时，更新设备配置并保存"""
        if index < 0: return
        pack_name = self.pack_selector.itemData(index)
        device_resource = next(
            (r for r in self.device_config.resources if r.resource_name == self.selected_resource_name), None)
        if device_resource:
            if not hasattr(device_resource, 'resource_pack') or device_resource.resource_pack != pack_name:
                device_resource.resource_pack = pack_name
                global_config.save_all_configs()
                self.logger.info(f"资源 [{self.selected_resource_name}] 已切换到资源包 [{pack_name}]")

    def update_resource_status(self, resource_name, enabled):
        """根据资源启用状态更新UI上的状态指示器"""
        if self.status_dot and self.status_text and self.selected_resource_name == resource_name:
            color = '#34a853' if enabled else '#ea4335'
            self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
            self.status_text.setText("已启用" if enabled else "已禁用")
            self.status_text.setStyleSheet(f"color: {color}; font-size: 12px;")