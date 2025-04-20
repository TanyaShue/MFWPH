from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QCheckBox,
    QLineEdit, QPushButton, QSpinBox, QTextBrowser, QSizePolicy, QStackedLayout
)

from app.models.config.global_config import global_config
from app.utils.theme_manager import theme_manager
from app.widgets.no_wheel_QComboBox import NoWheelComboBox

class SettingsPage(QWidget):
    """Settings page with categories on the left and content on the right"""

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.theme_manager = theme_manager
        self.current_theme = "light"
        self.initUI()

    def initUI(self):
        # Main layout
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left sidebar for categories
        self.categories_widget = QListWidget()
        self.categories_widget.setFixedWidth(200)
        self.categories_widget.setObjectName("settingsCategories")
        self.categories_widget.setFrameShape(QFrame.NoFrame)
        self.categories_widget.currentRowChanged.connect(self.scroll_to_section)

        # Add categories
        categories = [
            # "切换配置", "定时执行", "性能设置", "运行设置",
            # "连接设置", "启动设置", "远程控制", "界面设置",
            # "外部通知", "热键设置",
            "界面设置", "更新设置", "关于我们"
        ]

        for category in categories:
            item = QListWidgetItem(category)
            self.categories_widget.addItem(item)

        # Right content area with scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setObjectName("settingsScrollArea")

        # Content widget
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content_widget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(20)
        self.content_layout.setContentsMargins(20, 20, 20, 20)

        # Page title
        self.page_title = QLabel("设置")
        self.page_title.setObjectName("pageTitle")
        self.content_layout.addWidget(self.page_title)

        # Sections for each category
        self.sections = {}

        # Create sections
        # self.create_config_switch_section()
        # self.create_scheduled_tasks_section()
        # self.create_performance_section()
        # self.create_operation_section()
        # self.create_connection_section()
        # self.create_startup_section()
        # self.create_remote_control_section()
        self.create_interface_section()
        # self.create_notifications_section()
        # self.create_hotkey_section()
        self.create_update_section()
        self.create_about_section()  # 新增的"关于我们"部分

        # Add a spacer at the end
        self.content_layout.addStretch()

        # Set the content widget to the scroll area
        self.scroll_area.setWidget(self.content_widget)

        # Add widgets to main layout
        main_layout.addWidget(self.categories_widget)
        main_layout.addWidget(self.scroll_area)

        # Select the first category by default
        self.categories_widget.setCurrentRow(0)

    def create_section(self, title):
        """Create a new section with title and return its content layout"""
        section = QWidget()
        section.setObjectName(f"section_{title}")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)

        section_layout.addWidget(title_label)

        # Content widget
        content = QWidget()
        content.setObjectName("contentCard")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        section_layout.addWidget(content)

        # Add to main content layout
        self.content_layout.addWidget(section)

        # Store section reference
        self.sections[title] = section

        return content_layout

    def create_interface_section(self):
        """Create the interface settings section"""
        layout = self.create_section("界面设置")

        # Theme settings
        theme_row = QHBoxLayout()
        theme_label = QLabel("界面主题")
        theme_label.setObjectName("infoLabel")
        theme_combo = NoWheelComboBox()
        theme_combo.addItem("明亮主题")
        theme_combo.addItem("深色主题")

        if self.current_theme == "dark":
            theme_combo.setCurrentIndex(1)
        else:
            theme_combo.setCurrentIndex(0)

        theme_combo.currentIndexChanged.connect(self.toggle_theme)

        theme_row.addWidget(theme_label)
        theme_row.addWidget(theme_combo)
        theme_row.addStretch()

        # Language settings
        lang_row = QHBoxLayout()
        lang_label = QLabel("界面语言")
        lang_label.setObjectName("infoLabel")
        lang_combo = NoWheelComboBox()
        lang_combo.addItem("简体中文")
        # lang_combo.addItem("English")

        lang_row.addWidget(lang_label)
        lang_row.addWidget(lang_combo)
        lang_row.addStretch()

        # Add note about restart
        note = QLabel("注：语言设置更改将在应用重启后生效")
        note.setObjectName("infoText")

        layout.addLayout(theme_row)
        layout.addLayout(lang_row)
        layout.addWidget(note)

    def create_update_section(self):
        """创建更新设置的界面区域"""
        layout = self.create_section("更新设置")

        # 创建一个公共的状态标签，用于显示各种消息
        self.status_label = QLabel("")
        self.status_label.setObjectName("hintText")
        self.status_label.setMinimumHeight(20)

        # 添加设置警告和清除警告的辅助方法
        def set_warning_message(message):
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #E6A700; font-weight: bold;")

        def clear_message():
            self.status_label.setText("")
            self.status_label.setStyleSheet("")

        # 第一行：自动检查更新、测试版更新及立即检查按钮
        update_row = QHBoxLayout()

        auto_check = QCheckBox("自动检查更新")
        beta_updates = QCheckBox("接收测试版更新")
        check_button = QPushButton("立即检查更新")
        check_button.setObjectName("primaryButton")

        # 从配置初始化复选框状态
        try:
            # 使用不同的变量名存储布尔值
            auto_check_value = global_config.get_app_config().auto_check_update
            auto_check.setChecked(auto_check_value)
        except:
            auto_check.setChecked(False)

        # 获取测试版设置，如果不存在或不合法则默认为False
        try:
            receive_beta = global_config.get_app_config().receive_beta_update
            if not isinstance(receive_beta, bool):  # 如果不是布尔值
                receive_beta = False
        except:
            receive_beta = False

        # 设置测试版复选框状态
        beta_updates.setChecked(receive_beta)

        # 如果启用了测试版，设置警告消息
        if receive_beta:
            set_warning_message("测试版可能包含不稳定功能，可能影响正常使用")

        # 定义复选框状态变化的处理函数
        def on_beta_checkbox_changed(state):
            is_checked = (state == 2)  # 2 = 选中状态 (Qt.Checked)
            global_config.get_app_config().receive_beta_update = is_checked

            if is_checked:
                set_warning_message("测试版可能包含不稳定功能，可能影响正常使用")
            else:
                clear_message()

            global_config.save_all_configs()

        def on_auto_check_changed(state):
            global_config.get_app_config().auto_check_update = (state == 2)
            global_config.save_all_configs()

        # 连接信号与槽
        beta_updates.stateChanged.connect(on_beta_checkbox_changed)
        auto_check.stateChanged.connect(on_auto_check_changed)

        update_row.addWidget(auto_check)
        update_row.addWidget(beta_updates)
        update_row.addStretch()
        update_row.addWidget(check_button)

        layout.addLayout(update_row)

        # 添加状态标签到布局
        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        # 设置更新源部分
        source_row = QHBoxLayout()
        update_source_label = QLabel("更新源:")
        update_source_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.update_source_combo = NoWheelComboBox()
        self.update_source_combo.addItem("github")
        self.update_source_combo.addItem("Mirror酱")
        self.update_source_combo.setObjectName("update_source_combo")

        # 根据当前配置设置默认值
        current_update_method = global_config.get_app_config().update_method
        self.update_source_combo.setCurrentText("Mirror酱" if current_update_method == "MirrorChyan" else "github")

        source_row.addWidget(update_source_label)
        source_row.addWidget(self.update_source_combo)
        source_row.addStretch()

        layout.addLayout(source_row)

        # 为CDK区域预留空间，使用 QStackedLayout 切换显示内容
        layout.addSpacing(15)
        self.cdk_container = QWidget()
        self.cdk_stack = QStackedLayout(self.cdk_container)

        # Page 0：包含CDK输入行
        cdk_page = QWidget()
        cdk_layout = QVBoxLayout(cdk_page)
        cdk_layout.setContentsMargins(0, 0, 0, 0)

        # 创建CDK输入行
        cdk_row = QHBoxLayout()
        cdk_label = QLabel("mirror酱 CDK:")
        cdk_input = QLineEdit()
        cdk_input.setEchoMode(QLineEdit.Password)
        save_button = QPushButton("保存密钥")
        save_button.setObjectName("primaryButton")

        # 尝试获取已有的CDK值
        try:
            current_cdk = global_config.get_app_config().CDK
            if current_cdk:
                cdk_input.setText(current_cdk)
        except:
            pass

        cdk_row.addWidget(cdk_label)
        cdk_row.addWidget(cdk_input, 1)
        cdk_row.addWidget(save_button)
        cdk_layout.addLayout(cdk_row)

        # Page 1：空白占位页面
        placeholder_page = QWidget()
        placeholder_page.setFixedHeight(cdk_page.sizeHint().height())

        # 将两个页面添加到stacked布局中
        self.cdk_stack.addWidget(cdk_page)
        self.cdk_stack.addWidget(placeholder_page)

        # 默认根据更新源显示对应页面
        self.cdk_stack.setCurrentIndex(0 if self.update_source_combo.currentText() == "Mirror酱" else 1)

        layout.addWidget(self.cdk_container)

        # 定义保存CDK功能的槽函数
        def save_cdk():
            global_config.get_app_config().CDK = cdk_input.text()
            global_config.save_all_configs()

            # 临时显示保存成功消息
            self.status_label.setText("密钥保存成功!")
            self.status_label.setStyleSheet("color: #28a745; font-weight: bold;")

            # 3秒后恢复之前的状态
            def restore_previous_state():
                if beta_updates.isChecked():
                    set_warning_message("测试版可能包含不稳定功能，可能影响正常使用")
                else:
                    clear_message()

            QTimer.singleShot(3000, restore_previous_state)

        save_button.clicked.connect(save_cdk)
        cdk_input.returnPressed.connect(save_cdk)

        # 定义更新源改变时的槽函数
        def update_source_changed(new_text):
            is_mirror = (new_text == "Mirror酱")
            self.cdk_stack.setCurrentIndex(0 if is_mirror else 1)
            global_config.get_app_config().update_method = "MirrorChyan" if is_mirror else "github"

            # 确保beta警告的状态正确
            if beta_updates.isChecked():
                set_warning_message("测试版可能包含不稳定功能，可能影响正常使用")

            global_config.save_all_configs()

        self.update_source_combo.currentTextChanged.connect(update_source_changed)

    def create_about_section(self):
        """创建“关于我们”页面，展示应用、项目信息及鸣谢内容"""
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QDesktopServices, QFont, QPixmap
        from PySide6.QtWidgets import QHBoxLayout, QLabel

        layout = self.create_section("关于我们")

        app_info_row = QHBoxLayout()

        # Logo展示
        logo_label = QLabel()
        try:
            logo_pixmap = QPixmap("assets/icons/app/logo.png")
            logo_label.setPixmap(logo_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            # 若加载Logo失败，则显示项目简称
            logo_label.setText("MFWPH")
            logo_label.setFont(QFont("Arial", 16, QFont.Bold))
        logo_label.setFixedSize(50, 50)
        app_info_row.addWidget(logo_label)

        # 应用名称及版本
        app_info = QLabel("<b>MFWPH</b> - MaaFramework Project Helper<br>版本 1.0.0")
        app_info.setObjectName("infoLabel")
        app_info_row.addWidget(app_info)
        app_info_row.addStretch()

        # GitHub链接（点击后会使用默认浏览器打开项目页面）
        github_link = QLabel("<a href='https://github.com/TanyaShue/MFWPH'>访问项目 GitHub</a>")
        github_link.setOpenExternalLinks(True)
        github_link.setCursor(Qt.PointingHandCursor)
        app_info_row.addWidget(github_link)

        layout.addLayout(app_info_row)
        layout.addSpacing(10)


        proj_info_label = QLabel("<b>项目信息</b>")
        proj_info_label.setObjectName("infoLabel")
        layout.addWidget(proj_info_label)

        proj_info_desc = QLabel(
            "本项目基于开源的 <a href='https://github.com/MaaAssistantArknights/MaaFramework'>MaaFramework</a> 框架，旨在辅助自动化脚本的开发与管理。"
        )
        proj_info_desc.setOpenExternalLinks(True)
        proj_info_desc.setObjectName("infoText")
        proj_info_desc.setWordWrap(True)
        layout.addWidget(proj_info_desc)
        layout.addSpacing(15)

        thanks_label = QLabel("<b>开源组件与鸣谢</b>")
        thanks_label.setObjectName("infoLabel")
        layout.addWidget(thanks_label)

        thanks_text = QLabel(
            "感谢以下开源项目为本项目提供支持：<br>"
            "• <a href='https://pypi.org/project/PySide6/'>PySide6</a><br>"
            "• <a href='https://opencv.org/'>OpenCV</a>"
        )
        thanks_text.setOpenExternalLinks(True)
        thanks_text.setObjectName("infoText")
        thanks_text.setWordWrap(True)
        layout.addWidget(thanks_text)
        layout.addSpacing(15)

        copyright_label = QLabel(
            "© 2025 MFWPH 团队<br>"
            "本软件遵循 <a href='https://opensource.org/licenses/MIT'>MIT 许可证</a> 进行发布。"
        )
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setObjectName("infoText")
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)

        return layout

    def scroll_to_section(self, index):
        """Scroll to the selected section"""
        if index < 0 or index >= len(self.sections):
            return

        # Get the section widget based on the index
        section_title = self.categories_widget.item(index).text()
        if section_title in self.sections:
            section = self.sections[section_title]
            # Scroll to the section
            self.scroll_area.ensureWidgetVisible(section)

    def toggle_theme(self, index):
        """Toggle between light and dark themes"""
        if index == 0:  # Light theme
            self.theme_manager.apply_theme("light")
            self.current_theme = "light"
        else:  # Dark theme
            self.theme_manager.apply_theme("dark")
            self.current_theme = "dark"

    def update_source_changed(self, text):
        """处理更新源变更"""
        if text == "Mirror酱":
            global_config.get_app_config().update_method = "MirrorChyan"
        else:
            global_config.get_app_config().update_method = "github"
        global_config.save_all_configs()