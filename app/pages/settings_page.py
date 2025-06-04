import os
import sys
from pathlib import Path

import requests
from PySide6.QtCore import QTimer, QThread, Signal, QCoreApplication, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QCheckBox,
    QLineEdit, QPushButton, QSizePolicy, QStackedLayout, QMessageBox,
    QProgressDialog
)

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.utils.theme_manager import theme_manager
from app.utils.update_check import UpdateDownloader
from app.utils.update_install import UpdateInstaller
from app.components.no_wheel_ComboBox import NoWheelComboBox

logger = log_manager.get_app_logger()


class AppUpdateChecker(QThread):
    """主程序更新检查线程"""
    update_found = Signal(str, str, str)  # latest_version, current_version, download_url
    update_not_found = Signal()
    check_failed = Signal(str)  # error_message

    def __init__(self):
        super().__init__()
        self.github_api_url = "https://api.github.com"
        self.repo_owner = "TanyaShue"
        self.repo_name = "MFWPH"
        self.asset_name = "MFWPH_RELEASE.zip"

    def run(self):
        try:
            # 获取最新发布版本
            api_url = f"{self.github_api_url}/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            headers = {"Accept": "application/vnd.github.v3+json"}

            response = requests.get(api_url, headers=headers, timeout=10)

            if response.status_code == 403:
                self.check_failed.emit("请求被拒绝：可能超出了 GitHub API 请求速率限制")
                return

            if response.status_code != 200:
                self.check_failed.emit(f"GitHub API 返回错误 ({response.status_code})")
                return

            release_info = response.json()
            latest_version = release_info.get('tag_name', '').lstrip('v')

            # 获取当前版本
            current_version = self.get_current_version()

            # 查找特定的安装包
            download_url = None
            for asset in release_info.get('assets', []):
                if asset.get('name') == self.asset_name:
                    download_url = asset.get('browser_download_url')
                    break

            if not download_url:
                self.check_failed.emit(f"未找到安装包文件: {self.asset_name}")
                return

            # 比较版本
            if latest_version and latest_version != current_version:
                self.update_found.emit(latest_version, current_version, download_url)
            else:
                self.update_not_found.emit()

        except requests.exceptions.Timeout:
            self.check_failed.emit("连接超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            self.check_failed.emit("网络连接失败")
        except Exception as e:
            self.check_failed.emit(f"检查更新时出错: {str(e)}")

    def get_current_version(self):
        """获取当前版本"""
        # 检查是否是打包后的可执行文件
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
        else:
            base_path = os.getcwd()

        version_file_path = os.path.join(base_path, 'versioninfo.txt')

        try:
            if os.path.exists(version_file_path):
                with open(version_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('version='):
                            return line.split('=', 1)[1]
        except Exception as e:
            logger.error(f"读取版本信息失败: {e}")

        return "未知版本"


class SettingsPage(QWidget):
    """Settings page with categories on the left and content on the right"""

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.theme_manager = theme_manager
        self.current_theme = "light"
        self.update_checker_thread = None
        self.download_thread = None
        self.installer = UpdateInstaller()
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
        self.create_interface_section()
        self.create_update_section()
        self.create_about_section()

        # Add a spacer at the end
        self.content_layout.addStretch()

        # Set the content widget to the scroll area
        self.scroll_area.setWidget(self.content_widget)

        # Add widgets to main layout
        main_layout.addWidget(self.categories_widget)
        main_layout.addWidget(self.scroll_area)

        # Select the first category by default
        self.categories_widget.setCurrentRow(0)

        # Connect installer signals
        self.installer.restart_required.connect(self.handle_restart_required)

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
        theme_combo.addItem("深色主题(实验内容,不够完善)")

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

        # 立即检查更新按钮
        self.check_button = QPushButton("立即检查更新")
        self.check_button.setObjectName("primaryButton")
        self.check_button.clicked.connect(self.check_app_update)

        # 从配置初始化复选框状态
        try:
            auto_check_value = global_config.get_app_config().auto_check_update
            auto_check.setChecked(auto_check_value)
        except:
            auto_check.setChecked(False)

        # 获取测试版设置
        try:
            receive_beta = global_config.get_app_config().receive_beta_update
            if not isinstance(receive_beta, bool):
                receive_beta = False
        except:
            receive_beta = False

        beta_updates.setChecked(receive_beta)

        if receive_beta:
            set_warning_message("测试版可能包含不稳定功能，可能影响正常使用")

        # 定义复选框状态变化的处理函数
        def on_beta_checkbox_changed(state):
            is_checked = (state == 2)
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
        update_row.addWidget(self.check_button)

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

        # CDK 输入区域
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

    def check_app_update(self):
        """检查主程序更新"""
        # 禁用按钮并更改文本
        self.check_button.setEnabled(False)
        self.check_button.setText("检查中...")

        # 创建并启动检查线程
        self.update_checker_thread = AppUpdateChecker()
        self.update_checker_thread.update_found.connect(self.handle_update_found)
        self.update_checker_thread.update_not_found.connect(self.handle_update_not_found)
        self.update_checker_thread.check_failed.connect(self.handle_check_failed)
        self.update_checker_thread.start()

    def handle_update_found(self, latest_version, current_version, download_url):
        """处理发现更新"""
        # 恢复按钮
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")

        # 显示更新对话框
        reply = QMessageBox.question(
            self,
            "发现新版本",
            f"发现新版本 {latest_version}！\n"
            f"当前版本：{current_version}\n\n"
            f"是否立即下载并安装更新？\n"
            f"注意：更新将需要重启应用程序。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            self.download_and_install_update(download_url, latest_version)

    def handle_update_not_found(self):
        """处理未发现更新"""
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")

        # 显示当前版本信息
        current_version = self.update_checker_thread.get_current_version()
        QMessageBox.information(
            self,
            "检查更新",
            f"您的应用程序已是最新版本！\n当前版本：{current_version}"
        )

    def handle_check_failed(self, error_message):
        """处理检查失败"""
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")

        QMessageBox.warning(
            self,
            "检查更新失败",
            f"无法检查更新：\n{error_message}"
        )

    def download_and_install_update(self, download_url, version):
        """下载并安装更新"""
        # 创建进度对话框
        self.progress_dialog = QProgressDialog("正在下载更新...", "取消", 0, 100, self)
        self.progress_dialog.setWindowTitle("下载更新")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()

        # 创建临时目录
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 创建下载线程
        self.download_thread = UpdateDownloader(
            "MFWPH主程序",
            download_url,
            temp_dir,
            version=version
        )

        # 连接信号
        self.download_thread.progress_updated.connect(self.update_download_progress)
        self.download_thread.download_completed.connect(self.handle_download_completed)
        self.download_thread.download_failed.connect(self.handle_download_failed)

        # 连接取消按钮
        self.progress_dialog.canceled.connect(self.download_thread.cancel)

        # 启动下载
        self.download_thread.start()

    def update_download_progress(self, resource_name, progress, speed):
        """更新下载进度"""
        self.progress_dialog.setValue(int(progress))
        self.progress_dialog.setLabelText(f"正在下载更新... {int(progress)}% ({speed:.2f} MB/s)")

    def handle_download_completed(self, resource_name, file_path, data):
        """处理下载完成"""
        self.progress_dialog.close()

        # 显示安装确认
        reply = QMessageBox.question(
            self,
            "下载完成",
            "更新已下载完成。\n\n"
            "安装更新将需要重启应用程序。\n"
            "是否立即安装？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # 使用独立更新程序安装
            try:
                self.installer._launch_updater(file_path, "full")
                QMessageBox.information(
                    self,
                    "正在更新",
                    "更新程序已启动，应用程序将自动重启以完成更新。"
                )
                # 延迟后退出应用
                QTimer.singleShot(1000, QCoreApplication.quit)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "更新失败",
                    f"无法启动更新程序：\n{str(e)}"
                )

    def handle_download_failed(self, resource_name, error):
        """处理下载失败"""
        self.progress_dialog.close()
        QMessageBox.critical(
            self,
            "下载失败",
            f"更新下载失败：\n{error}"
        )

    def handle_restart_required(self):
        """处理需要重启的情况"""
        QTimer.singleShot(100, QCoreApplication.quit)

    def create_about_section(self):
        """创建"关于我们"页面，展示应用、项目信息及鸣谢内容"""
        layout = self.create_section("关于我们")

        app_info_row = QHBoxLayout()

        # Logo展示
        logo_label = QLabel()
        try:
            logo_pixmap = QPixmap("assets/icons/app/logo.png")
            logo_label.setPixmap(logo_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception as e:
            logo_label.setText("MFWPH")
            logo_label.setFont(QFont("Arial", 16, QFont.Bold))
        logo_label.setFixedSize(50, 50)
        app_info_row.addWidget(logo_label)

        # 获取版本信息
        version_info = self.get_version_info()

        # 应用名称及版本
        app_info = QLabel(f"<b>MFWPH</b> - MaaFramework Project Helper<br>版本 {version_info}")
        app_info.setObjectName("infoLabel")
        app_info_row.addWidget(app_info)
        app_info_row.addStretch()

        # GitHub链接
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

    def get_version_info(self):
        """从versioninfo.txt文件中获取版本信息"""
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
        else:
            base_path = os.getcwd()

        version_file_path = os.path.join(base_path, 'versioninfo.txt')

        try:
            if os.path.exists(version_file_path):
                with open(version_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('version='):
                            version = line.split('=', 1)[1]
                            return version
        except Exception as e:
            print(f"读取版本信息失败: {e}")

        return "未知版本"

    def scroll_to_section(self, index):
        """Scroll to the selected section"""
        if index < 0 or index >= len(self.sections):
            return

        section_title = self.categories_widget.item(index).text()
        if section_title in self.sections:
            section = self.sections[section_title]
            self.scroll_area.ensureWidgetVisible(section)

    def toggle_theme(self, index):
        """Toggle between light and dark themes"""
        if index == 0:
            self.theme_manager.apply_theme("light")
            self.current_theme = "light"
        else:
            self.theme_manager.apply_theme("dark")
            self.current_theme = "dark"

    def update_source_changed(self, text):
        """处理更新源变更"""
        if text == "Mirror酱":
            global_config.get_app_config().update_method = "MirrorChyan"
        else:
            global_config.get_app_config().update_method = "github"
        global_config.save_all_configs()