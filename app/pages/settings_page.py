# --- START OF FILE app/widgets/settings_page.py ---

import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QTimer, QCoreApplication, Qt, QUrl
from PySide6.QtGui import QFont, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QCheckBox,
    QLineEdit, QPushButton, QSizePolicy, QStackedLayout, QMessageBox
)

from app.components.no_wheel_ComboBox import NoWheelComboBox
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.utils.theme_manager import theme_manager
from app.utils.notification_manager import notification_manager
from app.widgets.dependency_sources_dialog import DependencySourcesDialog

from app.utils.update.checker import UpdateChecker
from app.utils.update.downloader import UpdateDownloader
from app.utils.update.installer.factory import UpdateInstallerFactory
from app.utils.update.models import UpdateInfo, UpdateSource

logger = log_manager.get_app_logger()


class SettingsPage(QWidget):
    """设置页面 (已按新需求重构)"""

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        self.theme_manager = theme_manager
        self.current_theme = "light"

        self.update_checker_thread = None
        self.download_thread = None
        self.installer_factory = UpdateInstallerFactory()
        self.app_update_info: UpdateInfo | None = None

        self.download_notification_id = "app_update_download"
        self.initUI()

    def initUI(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.categories_widget = QListWidget()
        self.categories_widget.setFixedWidth(200)
        self.categories_widget.setObjectName("settingsCategories")
        self.categories_widget.setFrameShape(QFrame.NoFrame)
        self.categories_widget.currentRowChanged.connect(self.scroll_to_section)
        categories = ["界面设置", "启动设置", "更新设置", "开发者选项", "关于我们"]
        for category in categories: self.categories_widget.addItem(QListWidgetItem(category))
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setObjectName("settingsScrollArea")
        self.content_widget = QWidget()
        self.content_widget.setObjectName("content_widget")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(20)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.page_title = QLabel("设置")
        self.page_title.setObjectName("pageTitle")
        self.content_layout.addWidget(self.page_title)
        self.sections = {}
        self.create_interface_section()
        self.create_startup_section()
        self.create_update_section()
        self.create_developer_section()
        self.create_about_section()
        self.content_layout.addStretch()
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.categories_widget)
        main_layout.addWidget(self.scroll_area)
        self.categories_widget.setCurrentRow(0)

        self.installer_factory.restart_required.connect(self.handle_restart_required)
        self.installer_factory.install_failed.connect(
            lambda name, msg: notification_manager.show_error(f"安装失败: {msg}", name)
        )

    def create_about_section(self):
        """【已修改】创建"关于我们"页面，并在此处添加主程序更新按钮和频道选择"""
        layout = self.create_section("关于我们")

        app_info_row = QHBoxLayout()
        logo_label = QLabel()
        logo_pixmap = QPixmap("assets/icons/app/logo.png")
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_label.setFixedSize(50, 50)
        app_info_row.addWidget(logo_label)
        app_info_layout = QVBoxLayout()
        app_name_main = QLabel("<b>MFWPH</b>")
        app_name_sub = QLabel("MaaFramework Project Helper")
        self.version_label = QLabel(f"版本 {get_version_info()}")
        app_info_layout.addWidget(app_name_main)
        app_info_layout.addWidget(app_name_sub)
        app_info_layout.addWidget(self.version_label)
        app_info_row.addLayout(app_info_layout)
        app_info_row.addStretch()

        update_controls_layout = QVBoxLayout()
        update_controls_layout.setSpacing(8)

        # 按钮行
        update_buttons_layout = QHBoxLayout()
        self.check_button = QPushButton("检查更新")
        self.check_button.setObjectName("primaryButton")
        self.check_button.clicked.connect(self.check_app_update)

        self.update_button = QPushButton("立即更新")
        self.update_button.setObjectName("primaryButton")
        self.update_button.clicked.connect(self.start_update)
        self.update_button.hide()

        update_buttons_layout.addWidget(self.check_button)
        update_buttons_layout.addWidget(self.update_button)

        # 复选框（频道选择）
        self.beta_checkbox = QCheckBox("接收测试版更新")
        try:  # 从配置加载初始状态
            self.beta_checkbox.setChecked(global_config.get_app_config().receive_beta_update)
        except:
            self.beta_checkbox.setChecked(False)
        self.beta_checkbox.stateChanged.connect(self.on_beta_checkbox_changed)

        update_controls_layout.addLayout(update_buttons_layout)
        update_controls_layout.addWidget(self.beta_checkbox, 0, Qt.AlignRight)  # 右对齐
        app_info_row.addLayout(update_controls_layout)
        # --- [结束] 更新控件容器 ---

        layout.addLayout(app_info_row)
        # ... (其他 "关于我们" 的内容保持不变) ...
        layout.addSpacing(10)
        proj_info_label = QLabel("<b>项目信息</b>")
        layout.addWidget(proj_info_label)
        proj_info_desc = QLabel(
            "本项目基于开源的 <a href='https://github.com/MaaAssistantArknights/MaaFramework'>MaaFramework</a> 框架，旨在辅助自动化脚本的开发与管理。")
        proj_info_desc.setOpenExternalLinks(True)
        proj_info_desc.setWordWrap(True)
        layout.addWidget(proj_info_desc)
        layout.addSpacing(15)
        thanks_label = QLabel("<b>开源组件与鸣谢</b>")
        layout.addWidget(thanks_label)
        thanks_text = QLabel(
            "感谢以下开源项目为本项目提供支持：<br>• <a href='https://pypi.org/project/PySide6/'>PySide6</a><br>• <a href='https://opencv.org/'>OpenCV</a>")
        thanks_text.setOpenExternalLinks(True)
        thanks_text.setWordWrap(True)
        layout.addWidget(thanks_text)
        layout.addSpacing(15)
        copyright_label = QLabel(
            "© 2025 MFWPH 团队<br>本软件遵循 <a href='https://opensource.org/licenses/MIT'>MIT 许可证</a> 进行发布。")
        copyright_label.setOpenExternalLinks(True)
        copyright_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright_label)
        return layout

    def on_beta_checkbox_changed(self, state):
        """【新增】处理接收测试版更新的复选框状态变化"""
        is_checked = (state == Qt.CheckState.Checked.value)
        try:
            global_config.get_app_config().receive_beta_update = is_checked
            global_config.save_all_configs()
            if is_checked:
                notification_manager.show_warning("测试版更新已启用，可能包含不稳定功能。", "设置已保存")
            else:
                notification_manager.show_info("测试版更新已关闭，您将只接收稳定版本。", "设置已保存")
        except Exception as e:
            logger.error(f"保存测试版更新设置失败: {e}")
            notification_manager.show_error("保存设置失败", "错误")

    def check_app_update(self):
        """
        【已修改】检查主程序更新。如果当前版本未知，则假定版本为 "0.0.0" 以获取最新版本。
        """
        if self.update_checker_thread and self.update_checker_thread.isRunning(): return
        if self.download_thread and self.download_thread.isRunning(): return

        current_version = get_version_info()
        effective_version = current_version

        if current_version == "未知版本":
            notification_manager.show_warning("无法获取当前应用版本，将尝试获取最新可用版本。", "版本未知")
            effective_version = "0.0.0"

        self.check_button.setEnabled(False)
        self.check_button.setText("检查中...")
        self.update_button.hide()

        channel = 'beta' if self.beta_checkbox.isChecked() else 'stable'
        notification_manager.show_info(f"正在从 GitHub ({channel}频道) 检查最新版本...", "检查更新")

        app_resource_mock = SimpleNamespace(
            resource_name="MFWPH 主程序",
            resource_version=effective_version,
            mirror_update_service_id=None,
            resource_rep_url="https://github.com/TanyaShue/MFWPH"
        )

        # 【已修改】将 source='github' 作为参数传递给检查器，以强制使用 GitHub 源
        self.update_checker_thread = UpdateChecker(
            app_resource_mock,
            single_mode=True,
            channel=channel,
            source='github'
        )
        self.update_checker_thread.update_found.connect(self.handle_update_found)
        self.update_checker_thread.update_not_found.connect(self.handle_update_not_found)
        self.update_checker_thread.check_failed.connect(self.handle_check_failed)
        self.update_checker_thread.start()
    # --- 其他所有方法（create_*, handle_*, 等）保持不变 ---
    def create_section(self, title):
        section = QWidget()
        section.setObjectName(f"section_{title}")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        section_layout.addWidget(title_label)
        content = QWidget()
        content.setObjectName("contentCard")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)
        section_layout.addWidget(content)
        self.content_layout.addWidget(section)
        self.sections[title] = section
        return content_layout

    def create_interface_section(self):
        layout = self.create_section("界面设置")
        theme_row = QHBoxLayout()
        theme_label = QLabel("界面主题")
        theme_combo = NoWheelComboBox()
        theme_combo.addItems(["明亮主题", "深色主题(实验内容,不够完善)"])
        theme_combo.setCurrentIndex(1 if self.current_theme == "dark" else 0)
        theme_combo.currentIndexChanged.connect(self.toggle_theme)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(theme_combo)
        theme_row.addStretch()
        lang_row = QHBoxLayout()
        lang_label = QLabel("界面语言")
        lang_combo = NoWheelComboBox()
        lang_combo.addItem("简体中文")
        lang_row.addWidget(lang_label)
        lang_row.addWidget(lang_combo)
        lang_row.addStretch()
        note = QLabel("注：语言设置更改将在应用重启后生效")
        note.setObjectName("infoText")
        window_settings_row = QHBoxLayout()
        minimize_to_tray_checkbox = QCheckBox("点击关闭按钮时最小化到系统托盘")
        minimize_to_tray_checkbox.setChecked(global_config.get_app_config().minimize_to_tray_on_close)
        minimize_to_tray_checkbox.stateChanged.connect(self.on_minimize_to_tray_changed)
        window_settings_row.addWidget(minimize_to_tray_checkbox)
        window_settings_row.addStretch()
        layout.addLayout(theme_row)
        layout.addLayout(lang_row)
        layout.addLayout(window_settings_row)
        layout.addWidget(note)

    def on_minimize_to_tray_changed(self, state):
        app_config = global_config.get_app_config()
        app_config.minimize_to_tray_on_close = (state == Qt.CheckState.Checked.value)
        global_config.save_all_configs()

    def create_startup_section(self):
        layout = self.create_section("启动设置")
        dep_source_button = QPushButton("依赖源")
        dep_source_button.setObjectName("primaryButton")
        dep_source_button.clicked.connect(self.show_dependency_sources_dialog)
        layout.addWidget(dep_source_button)

    def show_dependency_sources_dialog(self):
        dialog = DependencySourcesDialog(self)
        dialog.exec()

    def create_update_section(self):
        """【已修改】创建更新设置的界面区域，移除了更新源切换功能"""
        layout = self.create_section("更新设置")

        update_row = QHBoxLayout()
        auto_check = QCheckBox("自动检查资源更新")
        update_row.addWidget(auto_check)
        update_row.addStretch()
        layout.addLayout(update_row)

        try:
            auto_check.setChecked(global_config.get_app_config().auto_check_update)
        except:
            auto_check.setChecked(False)

        def on_auto_check_changed(state):
            is_checked = (state == Qt.CheckState.Checked.value)
            global_config.get_app_config().auto_check_update = is_checked
            global_config.save_all_configs()
            msg = "应用将在启动时自动检查资源更新" if is_checked else "您需要手动检查资源更新"
            title = "自动更新已启用" if is_checked else "自动更新已关闭"
            notification_manager.show_info(msg, title)

        auto_check.stateChanged.connect(on_auto_check_changed)

        # GitHub Token 设置
        github_token_row = QHBoxLayout()
        github_token_label = QLabel("GitHub Token:")
        github_token_input = QLineEdit()
        github_token_input.setEchoMode(QLineEdit.Password)
        save_github_token_button = QPushButton("保存密钥")
        save_github_token_button.setObjectName("primaryButton")

        try:
            current_token = global_config.get_app_config().github_token
            if current_token: github_token_input.setText(current_token)
        except:
            pass

        github_token_row.addWidget(github_token_label)
        github_token_row.addWidget(github_token_input, 1)
        github_token_row.addWidget(save_github_token_button)
        layout.addLayout(github_token_row)

        # Mirror酱 CDK 设置
        cdk_row = QHBoxLayout()
        cdk_label = QLabel("mirror酱 CDK:")
        cdk_input = QLineEdit()
        cdk_input.setEchoMode(QLineEdit.Password)
        save_cdk_button = QPushButton("保存密钥")
        save_cdk_button.setObjectName("primaryButton")
        try:
            current_cdk = global_config.get_app_config().CDK
            if current_cdk: cdk_input.setText(current_cdk)
        except:
            pass
        cdk_row.addWidget(cdk_label)
        cdk_row.addWidget(cdk_input, 1)
        cdk_row.addWidget(save_cdk_button)
        layout.addLayout(cdk_row)

        def save_github_token():
            global_config.get_app_config().github_token = github_token_input.text()
            global_config.save_all_configs()
            notification_manager.show_success("GitHub Token 已成功保存", "保存成功")

        save_github_token_button.clicked.connect(save_github_token)

        def save_cdk():
            global_config.get_app_config().CDK = cdk_input.text()
            global_config.save_all_configs()
            notification_manager.show_success("CDK 已成功保存", "保存成功")

        save_cdk_button.clicked.connect(save_cdk)

    def handle_update_found(self, update_info: UpdateInfo):
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")
        self.app_update_info = update_info
        self.update_button.show()
        notification_manager.show_success(
            f"发现新版本 {update_info.new_version}！当前版本：{update_info.current_version}",
            "有可用更新", duration=0
        )

    def handle_update_not_found(self):
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")
        self.update_button.hide()
        current_version = get_version_info()
        notification_manager.show_info(f"您的应用程序已是最新版本（{current_version}）", "无可用更新")

    def handle_check_failed(self, resource_name, error_message):
        self.check_button.setEnabled(True)
        self.check_button.setText("立即检查更新")
        self.update_button.hide()
        notification_manager.show_error(f"无法检查更新：{error_message}", "检查更新失败")

    def start_update(self):
        if not self.app_update_info:
            notification_manager.show_error("没有更新信息，请先检查更新", "操作失败")
            return
        if self.download_thread and self.download_thread.isRunning():
            notification_manager.show_warning("更新正在下载中，请稍候", "下载进行中")
            return

        self.update_button.setEnabled(False)
        self.update_button.setText("下载中...")
        notification_manager.show_progress(
            self.download_notification_id,
            f"正在下载版本 {self.app_update_info.new_version}...", "下载更新", 0.0
        )

        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.download_thread = UpdateDownloader(self.app_update_info, temp_dir)
        self.download_thread.progress_updated.connect(self.update_download_progress)
        self.download_thread.download_completed.connect(self.handle_download_completed)
        self.download_thread.download_failed.connect(self.handle_download_failed)
        self.download_thread.start()

    def update_download_progress(self, resource_name, progress, speed):
        notification_manager.update_progress(
            self.download_notification_id, progress / 100.0,
            f"正在更新 {int(progress)}% ({speed:.2f} MB/s)"
        )

    def handle_download_completed(self, update_info: UpdateInfo, file_path: str):
        notification_manager.close_progress(self.download_notification_id)
        self.update_button.setEnabled(True)
        self.update_button.setText("立即更新")
        notification_manager.show_success("更新文件下载完成", "下载成功")

        reply = QMessageBox.question(
            self, "下载完成",
            "更新已下载完成。\n\n安装更新将需要重启应用程序。\n是否立即安装？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            try:
                self.installer_factory.install_update(update_info, file_path, resource=None)
                notification_manager.show_info("更新程序已启动，应用程序将自动重启以完成更新", "正在更新")
            except Exception as e:
                notification_manager.show_error(f"无法启动更新程序：{str(e)}", "更新失败")
        else:
            notification_manager.show_info("更新已下载但未安装，您可以稍后再次点击“立即更新”进行安装。", "更新已推迟")

    def handle_download_failed(self, resource_name, error):
        notification_manager.close_progress(self.download_notification_id)
        self.update_button.setEnabled(True)
        self.update_button.setText("立即更新")
        notification_manager.show_error(f"更新下载失败：{error}", "下载失败")

    def handle_restart_required(self):
        QTimer.singleShot(1500, QCoreApplication.quit)

    def scroll_to_section(self, index):
        if 0 <= index < len(self.sections):
            section_title = self.categories_widget.item(index).text()
            if section_title in self.sections:
                self.scroll_area.ensureWidgetVisible(self.sections[section_title])

    def toggle_theme(self, index):
        old_theme, self.current_theme = self.current_theme, "light" if index == 0 else "dark"
        self.theme_manager.apply_theme(self.current_theme)
        if old_theme != self.current_theme:
            theme_name = "明亮主题" if self.current_theme == "light" else "深色主题"
            notification_manager.show_success(f"界面已切换到{theme_name}", "主题已更改")
            if self.current_theme == "dark":
                notification_manager.show_warning("深色主题仍在开发中，部分界面可能显示不正常", "实验性功能")

    def create_developer_section(self):
        layout = self.create_section("开发者选项")
        debug_row = QHBoxLayout()
        debug_label = QLabel("调试模式")
        self.debug_checkbox = QCheckBox("启用调试日志")
        try:
            self.debug_checkbox.setChecked(global_config.app_config.debug_model)
        except:
            self.debug_checkbox.setChecked(False)
        self.debug_checkbox.stateChanged.connect(self.on_debug_changed)
        debug_row.addWidget(debug_label)
        debug_row.addWidget(self.debug_checkbox)
        debug_row.addStretch()
        log_btn = QPushButton("打开软件日志文件夹")
        log_btn.setObjectName("primaryButton")
        log_btn.clicked.connect(self.open_log_folder)
        debug_row.addWidget(log_btn)
        debug_btn = QPushButton("打开调试日志文件夹")
        debug_btn.setObjectName("primaryButton")
        debug_btn.clicked.connect(self.open_debug_folder)
        debug_row.addWidget(debug_btn)
        layout.addLayout(debug_row)
        warning = QLabel("⚠️ 注意：启用调试模式可能会影响应用性能并生成大量日志文件")
        warning.setObjectName("warningText")
        layout.addWidget(warning)

    def open_log_folder(self):
        log_path = os.path.abspath("logs")
        if os.path.exists(log_path): QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))

    def open_debug_folder(self):
        debug_path = os.path.abspath("assets/debug")
        if os.path.exists(debug_path): QDesktopServices.openUrl(QUrl.fromLocalFile(debug_path))

    def on_debug_changed(self, state):
        is_enabled = (state == Qt.CheckState.Checked.value)
        try:
            global_config.app_config.debug_model = is_enabled
            global_config.save_all_configs()
            if hasattr(log_manager, 'set_debug_mode'): log_manager.set_debug_mode(is_enabled)
            msg = "调试模式已启用，将生成详细日志" if is_enabled else "调试模式已关闭"
            title = "调试模式已启用" if is_enabled else "调试模式已关闭"
            notification_manager.show_info(msg, title)
        except Exception as e:
            logger.error(f"切换调试模式时出错: {e}")
            self.debug_checkbox.setChecked(not is_enabled)
            notification_manager.show_error("调试模式切换失败", "操作失败")


def get_version_info():
    """从versioninfo.txt文件中获取版本信息"""
    base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.getcwd()
    version_file_path = os.path.join(base_path, 'versioninfo_MFWPH.txt')
    try:
        with open(version_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip().startswith('version='):
                    return line.split('=', 1)[1].strip()
    except Exception as e:
        logger.warning(f"读取版本信息失败: {e}, 使用默认版本v1.0.0")
    return "v1.0.0"