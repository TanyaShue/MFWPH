from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QPixmap, QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QComboBox, QCheckBox,
    QLineEdit, QPushButton, QSpinBox, QTextBrowser, QSizePolicy
)

from app.utils.theme_manager import theme_manager


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
        theme_combo = QComboBox()
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
        lang_combo = QComboBox()
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
        """Create the update settings section"""
        layout = self.create_section("更新设置")

        auto_check = QCheckBox("自动检查更新")
        beta_updates = QCheckBox("接收测试版更新")

        # Add warning for beta updates
        beta_warning = QLabel("测试版可能包含不稳定功能，可能影响正常使用")
        beta_warning.setObjectName("warningText")
        beta_warning.setContentsMargins(28, 0, 0, 10)

        check_row = QHBoxLayout()
        check_button = QPushButton("立即检查更新")
        check_button.setObjectName("primaryButton")

        check_row.addWidget(check_button)
        check_row.addStretch()

        layout.addWidget(auto_check)
        layout.addWidget(beta_updates)
        layout.addWidget(beta_warning)
        layout.addLayout(check_row)

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