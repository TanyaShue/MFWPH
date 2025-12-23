# --- START OF FILE app/widgets/settings_page.py ---

import os
import platform
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime

from PySide6.QtCore import QTimer, QCoreApplication, Qt, QUrl, QThread, Signal, QMimeData
from PySide6.QtGui import QFont, QPixmap, QDesktopServices, QIntValidator, QClipboard, QGuiApplication
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QCheckBox,
    QLineEdit, QPushButton, QSizePolicy, QStackedLayout, QMessageBox
)

from app.components.no_wheel_ComboBox import NoWheelComboBox
from app.config.config_manager import get_config_directory
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager, app_logger
from app.utils.theme_manager import theme_manager
from app.utils.notification_manager import notification_manager
from app.widgets.dependency_sources_dialog import DependencySourcesDialog

from app.utils.update.checker import UpdateChecker
from app.utils.update.downloader import UpdateDownloader
from app.utils.update.installer.factory import UpdateInstallerFactory
from app.utils.update.models import UpdateInfo, UpdateSource

logger = log_manager.get_app_logger()


class LogExportWorker(QThread):
    """后台日志导出线程：负责压缩日志并清理旧文件"""
    finished = Signal(str)  # 成功信号，传递zip路径
    error = Signal(str)  # 失败信号，传递错误信息
    progress = Signal(float, str)  # 进度信号: (0.0-1.0的小数, 状态文本)

    def __init__(self, base_path, log_dir, debug_dir):
        super().__init__()
        self.base_path = base_path
        self.log_dir = log_dir
        self.debug_dir = debug_dir

    def run(self):
        try:
            # 1. 生成 ZIP 路径
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"logs_export_{timestamp}.zip"
            zip_path = os.path.join(self.base_path, zip_filename)

            # 2. 预先扫描所有需要处理的文件 (用于计算进度)
            files_to_process = []  # 存储元组: (绝对路径, 压缩包内路径)

            # 扫描 logs 目录
            if os.path.exists(self.log_dir):
                for root, dirs, files in os.walk(self.log_dir):
                    for file in files:
                        # 跳过之前的导出文件，防止递归打包
                        if file.startswith("logs_export_") and file.endswith(".zip"):
                            continue
                        abs_path = os.path.join(root, file)
                        arc_name = os.path.join("logs", os.path.relpath(abs_path, self.log_dir))
                        files_to_process.append((abs_path, arc_name))

            # 扫描 debug 目录
            if os.path.exists(self.debug_dir):
                for root, dirs, files in os.walk(self.debug_dir):
                    for file in files:
                        abs_path = os.path.join(root, file)
                        arc_name = os.path.join("assets/debug", os.path.relpath(abs_path, self.debug_dir))
                        files_to_process.append((abs_path, arc_name))

            total_files = len(files_to_process)
            processed_count = 0

            # 3. 创建压缩包并写入文件
            files_to_delete = []  # 记录成功写入后需要删除的源文件路径

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for abs_path, arc_name in files_to_process:
                    # 写入压缩包
                    zipf.write(abs_path, arc_name)
                    files_to_delete.append(abs_path)

                    # 更新进度
                    processed_count += 1
                    if total_files > 0:
                        percent = processed_count / total_files
                        # 保留两位小数的进度，文本显示当前处理数量
                        self.progress.emit(percent, f"正在打包 ({processed_count}/{total_files})...")

            # 4. 删除原文件 (清理阶段)
            self.progress.emit(1.0, "正在清理旧日志文件...")

            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                except OSError:
                    # 跳过被占用的文件
                    pass

            self.finished.emit(zip_path)

        except Exception as e:
            self.error.emit(str(e))


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
        self.last_exported_zip_path = None  # 记录最近导出的压缩包路径

        # 日志导出相关
        self.log_worker = None
        self.export_notification_id = "log_export_process"

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

    # --- 修改开始: 更新主程序检查逻辑 ---
    def check_app_update(self):
        """
        【已修改】检查主程序更新。此方法现在会检测用户平台并查找对应的Release包。
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

        # 1. 检测平台并构建目标资源文件名
        try:
            system = platform.system().lower()
            machine = platform.machine().lower()

            if system == "windows":
                os_name, ext = "windows", "zip"
            elif system == "linux":
                os_name, ext = "linux", "tar.gz"
            elif system == "darwin":
                os_name, ext = "macos", "tar.gz"
            else:
                raise ValueError(f"不支持的操作系统: {platform.system()}")

            if machine in ["amd64", "x86_64"]:
                arch_name = "x64"
            elif machine in ["arm64", "aarch64"]:
                arch_name = "arm64"
            else:
                raise ValueError(f"不支持的CPU架构: {platform.machine()}")

            target_asset_name = f"MFWPH_{os_name}-{arch_name}.{ext}"
            logger.info(f"正在查找主程序更新包, 目标文件: '{target_asset_name}'")

        except ValueError as e:
            self.handle_check_failed("MFWPH 主程序", str(e))
            return

        channel = 'beta' if self.beta_checkbox.isChecked() else 'stable'
        notification_manager.show_info(f"正在从 GitHub ({channel}频道) 检查最新版本...", "检查更新")

        app_resource_mock = SimpleNamespace(
            resource_name="MFWPH 主程序",
            resource_version=effective_version,
            mirror_update_service_id=None,
            resource_rep_url="https://github.com/TanyaShue/MFWPH"
        )

        # 2. 将目标文件名传递给更新检查器
        self.update_checker_thread = UpdateChecker(
            app_resource_mock,
            single_mode=True,
            channel=channel,
            source='github',
            target_asset_name=target_asset_name  # <-- 将目标文件名传递给检查器
        )
        self.update_checker_thread.update_found.connect(self.handle_update_found)
        self.update_checker_thread.update_not_found.connect(self.handle_update_not_found)
        self.update_checker_thread.check_failed.connect(self.handle_check_failed)
        self.update_checker_thread.start()

    # --- 修改结束 ---

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
        """【已修改】创建启动设置的界面区域，并添加等待时间输入框"""
        layout = self.create_section("启动设置")

        # 依赖源按钮
        dep_source_button = QPushButton("依赖源")
        dep_source_button.setObjectName("primaryButton")
        dep_source_button.clicked.connect(self.show_dependency_sources_dialog)
        layout.addWidget(dep_source_button, 0, Qt.AlignLeft)  # 左对齐

        layout.addSpacing(10)

        # 模拟器启动等待时间
        wait_time_row = QHBoxLayout()
        wait_time_label = QLabel("模拟器启动等待时间 (秒) ")
        self.wait_time_input = QLineEdit()
        self.wait_time_input.setValidator(QIntValidator(0, 300, self))  # 限制输入为0-300的整数
        self.wait_time_input.setFixedWidth(100)  # 设置一个合适的宽度

        # 从配置加载初始值
        try:
            current_wait_time = global_config.get_app_config().emulator_start_wait_time
            self.wait_time_input.setText(str(current_wait_time))
        except Exception as e:
            logger.warning(f"无法加载模拟器启动等待时间: {e}, 使用默认值 30")
            self.wait_time_input.setText("30")

        # 当编辑完成时（例如，用户点击别处），触发保存
        self.wait_time_input.editingFinished.connect(self.on_emulator_wait_time_changed)

        wait_time_row.addWidget(wait_time_label)
        wait_time_row.addWidget(self.wait_time_input)
        wait_time_row.addStretch()
        layout.addLayout(wait_time_row)

    def on_emulator_wait_time_changed(self):
        """【新增】当模拟器启动等待时间输入框编辑完成时，保存设置"""
        app_config = global_config.get_app_config()
        try:
            new_value = int(self.wait_time_input.text())
            # 仅在值发生变化时保存并提示
            if app_config.emulator_start_wait_time != new_value:
                app_config.emulator_start_wait_time = new_value
                global_config.save_all_configs()
                notification_manager.show_info(f"模拟器启动等待时间已设置为 {new_value} 秒。", "设置已保存")
        except ValueError:
            # 如果输入为空或无效（例如，用户清空了输入框），则恢复为之前的值
            current_value = app_config.emulator_start_wait_time
            self.wait_time_input.setText(str(current_value))
            notification_manager.show_warning("请输入有效的等待时间（0-300秒）。", "输入无效")
        except Exception as e:
            logger.error(f"保存模拟器启动等待时间失败: {e}")
            notification_manager.show_error("保存设置失败", "错误")

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
        # 关闭下载进度通知
        notification_manager.close_progress(self.download_notification_id)
        self.update_button.setEnabled(True)
        self.update_button.setText("立即更新")

        # 提示下载成功
        notification_manager.show_success("更新文件下载完成，正在准备安装更新……", "下载成功")

        try:
            # 执行安装
            self.installer_factory.install_update(update_info, file_path, resource=None)

            # 通知用户即将重启
            notification_manager.show_info(
                "更新程序已启动，应用程序将在 5 秒后自动重启以完成更新。",
                "正在更新"
            )

            # 5 秒后重启（可选：退出或重新启动）
            def restart_app():
                import sys, os
                python = sys.executable
                os.execl(python, python, *sys.argv)  # 自动重启当前应用

            QTimer.singleShot(5000, restart_app)

        except Exception as e:
            notification_manager.show_error(f"无法启动更新程序：{str(e)}", "更新失败")

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

        # 调试模式行
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
        layout.addLayout(debug_row)

        # 日志文件夹按钮行
        log_folder_row = QHBoxLayout()
        log_btn = QPushButton("打开软件日志文件夹")
        log_btn.setObjectName("primaryButton")
        log_btn.clicked.connect(self.open_log_folder)
        log_folder_row.addWidget(log_btn)
        debug_btn = QPushButton("打开调试日志文件夹")
        debug_btn.setObjectName("primaryButton")
        debug_btn.clicked.connect(self.open_debug_folder)
        log_folder_row.addWidget(debug_btn)
        log_folder_row.addStretch()
        layout.addLayout(log_folder_row)

        # 导出日志按钮行
        export_log_row = QHBoxLayout()
        export_log_btn = QPushButton("导出日志")
        export_log_btn.setObjectName("primaryButton")
        export_log_btn.clicked.connect(self.export_logs)
        export_log_row.addWidget(export_log_btn)
        export_log_row.addStretch()
        layout.addLayout(export_log_row)

        # 配置文件目录按钮行
        config_folder_row = QHBoxLayout()
        config_folder_btn = QPushButton("打开配置文件目录")
        config_folder_btn.setObjectName("primaryButton")
        config_folder_btn.clicked.connect(self.open_config_folder)
        config_folder_row.addWidget(config_folder_btn)
        config_folder_row.addStretch()
        layout.addLayout(config_folder_row)

        warning = QLabel("⚠️ 注意：启用调试模式可能会影响应用性能并生成大量日志文件")
        warning.setObjectName("warningText")
        layout.addWidget(warning)

    def open_log_folder(self):
        log_path = os.path.abspath("logs")
        if os.path.exists(log_path): QDesktopServices.openUrl(QUrl.fromLocalFile(log_path))

    def open_debug_folder(self):
        debug_path = os.path.abspath("assets/debug")
        if os.path.exists(debug_path): QDesktopServices.openUrl(QUrl.fromLocalFile(debug_path))

    def open_config_folder(self):
        config_path = get_config_directory()
        if os.path.exists(config_path): QDesktopServices.openUrl(QUrl.fromLocalFile(config_path))

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

    def export_logs(self):
        """导出日志文件：后台打包并清理旧日志"""

        # 1. 防止重复点击
        if self.log_worker and self.log_worker.isRunning():
            notification_manager.show_warning("正在后台打包日志，请稍候...", "操作进行中")
            return

        # 2. 路径准备
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.getcwd()

        log_dir = os.path.join(base_path, "logs")
        debug_dir = os.path.join(base_path, "assets", "debug")

        # 简单检查是否有文件夹存在
        if not os.path.exists(log_dir) and not os.path.exists(debug_dir):
            notification_manager.show_warning("未找到日志文件夹", "无需导出")
            return

        # 3. 初始化进度通知 (初始进度 0.0)
        notification_manager.show_progress(
            self.export_notification_id,
            "正在扫描日志文件...",
            "准备导出",
            0.0
        )

        # 4. 启动后台线程
        self.log_worker = LogExportWorker(base_path, log_dir, debug_dir)
        self.log_worker.finished.connect(self.on_export_finished)
        self.log_worker.error.connect(self.on_export_error)
        self.log_worker.progress.connect(self.update_export_progress)  # <--- 连接进度信号
        self.log_worker.start()

    def update_export_progress(self, percent, msg):
        """更新导出进度条"""
        # 调用 notification_manager 更新进度
        # 假设 update_progress 接受 (id, float进度0-1, 文本消息)
        notification_manager.update_progress(
            self.export_notification_id,
            percent,
            msg
        )

    def on_export_finished(self, zip_path):
        """日志导出成功的回调"""
        # 关闭进度通知
        notification_manager.close_progress(self.export_notification_id)

        logger.info(f"日志导出成功: {zip_path}")

        # 弹窗询问复制
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("日志导出成功")
        msg_box.setText(f"日志已打包并清理旧文件。\n保存路径：\n{zip_path}\n\n是否要复制这个压缩包到剪贴板？")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.button(QMessageBox.Yes).setText("是，复制")
        msg_box.button(QMessageBox.No).setText("否，关闭")

        result = msg_box.exec()

        if result == QMessageBox.Yes:
            try:
                clipboard = QGuiApplication.clipboard()
                mime_data = QMimeData()
                mime_data.setUrls([QUrl.fromLocalFile(zip_path)])
                clipboard.setMimeData(mime_data)
                notification_manager.show_success("压缩包已复制到剪贴板", "复制成功")
            except Exception as e:
                notification_manager.show_error(f"复制失败: {e}", "错误")

    def on_export_error(self, error_msg):
        """日志导出失败的回调"""
        notification_manager.close_progress(self.export_notification_id)
        logger.error(f"导出日志失败: {error_msg}")
        notification_manager.show_error(f"导出失败: {error_msg}", "错误")


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


app_logger.info(f"欢迎来到MFWPH,当前版本为: {get_version_info()}")