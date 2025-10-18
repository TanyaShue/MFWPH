import os
import shutil
import tempfile
from pathlib import Path

# import git
import requests
from PySide6.QtCore import (QTimer, QCoreApplication, Qt, Signal, Property, QPropertyAnimation, QEasingCurve, QThread)
from PySide6.QtGui import QIcon, QPainter, QColor, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QPushButton,
                               QHBoxLayout, QMessageBox, QSizePolicy,
                               QDialog, QStackedWidget,
                               QScrollArea, QComboBox, QProgressBar, QTextBrowser)  # <-- 修改: 导入 QTextBrowser
# from git import InvalidGitRepositoryError

from app.models.config.app_config import ResourceUpdateConfig
from app.models.config.global_config import global_config
from app.models.logging.log_manager import app_logger
from app.utils.notification_manager import notification_manager
from app.utils.update.checker import UpdateChecker
from app.utils.update.downloader import UpdateDownloader
from app.utils.update.installer.factory import UpdateInstallerFactory
from app.utils.update.models import UpdateInfo, UpdateSource  # 导入 UpdateSource
from app.widgets.download.add_resource_dialog import AddResourceDialog

# 用于更新频道的显示文本和内部值的映射
CHANNEL_MAP = {
    "稳定版": "stable",
    "测试版": "beta",
    "开发版": "alpha"
}
REVERSE_CHANNEL_MAP = {v: k for k, v in CHANNEL_MAP.items()}


class AnimatedIndicator(QWidget):
    """一个简单的动画指示器，用于显示更新状态"""

    def __init__(self, color="#10b981"):
        super().__init__()
        self._opacity = 0.0
        self.setFixedSize(8, 8)
        self._color = QColor(color)
        self._animation = QPropertyAnimation(self, b"opacity", self)
        self._animation.setDuration(1000)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

    @Property(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        color = self._color
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.drawEllipse(self.rect())

    def start(self):
        self._animation.start()

    def stop(self):
        self._animation.stop()
        self.hide()


class ResourceListItem(QFrame):
    """自定义的资源列表项"""
    clicked = Signal(object)

    def __init__(self, resource):
        super().__init__()
        self.resource = resource
        self.is_selected = False
        self.has_update = False
        self._init_ui()

    def _init_ui(self):
        self.setObjectName("resourceItem")
        self.setFixedHeight(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("resourceItemIcon")
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setScaledContents(True)
        self._set_icon(f"assets/resource/{self.resource.resource_id}/{self.resource.resource_icon}")
        layout.addWidget(self.icon_label)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)
        self.name_label = QLabel(self.resource.resource_name)
        self.name_label.setObjectName("resourceItemName")
        self.version_label = QLabel(f"版本 {self.resource.resource_version}")
        self.version_label.setObjectName("resourceItemVersion")
        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.version_label)
        layout.addWidget(info_container, 1)

        self.update_indicator = AnimatedIndicator("#10b981")
        self.update_indicator.hide()
        layout.addWidget(self.update_indicator)

    def _set_icon(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            pixmap = QPixmap(44, 44)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#cbd5e1"), 1.5))
            painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 8, 8)
            painter.end()
        self.icon_label.setPixmap(pixmap)

    def set_selected(self, selected):
        self.is_selected = selected
        self.setProperty("selected", selected)
        self.style().polish(self)

    def set_update_status(self, has_update):
        self.has_update = has_update
        if has_update:
            self.update_indicator.start()
            self.update_indicator.show()
        else:
            self.update_indicator.stop()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.resource)
        super().mousePressEvent(event)


class ResourceDetailView(QWidget):
    """资源详情视图（集成操作按钮）"""
    check_update_clicked = Signal(object)
    start_update_clicked = Signal(object)  # 只发送 resource
    cancel_download_clicked = Signal(object)
    source_changed_recheck = Signal(object)

    def __init__(self):
        super().__init__()
        self.current_resource = None
        self._init_ui()
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("detailScrollArea")
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        header = self._create_header()
        layout.addWidget(header)
        self.action_bar = self._create_action_bar()
        layout.addWidget(self.action_bar)

        self.changelog_card = self._create_changelog_card()
        layout.addWidget(self.changelog_card)
        self.changelog_card.hide()

        desc_card = self._create_description_card()
        layout.addWidget(desc_card)
        layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _create_header(self):
        header_widget = QWidget()
        layout = QHBoxLayout(header_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        self.large_icon = QLabel()
        self.large_icon.setFixedSize(80, 80)
        self.large_icon.setObjectName("detailIcon")
        self.large_icon.setScaledContents(True)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self.title_label = QLabel("请选择一个资源")
        self.title_label.setObjectName("detailTitle")
        self.author_label = QLabel("作者")
        self.author_label.setObjectName("detailAuthor")
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.author_label)

        source_layout = QVBoxLayout()
        source_layout.setSpacing(4)
        source_label = QLabel("更新源")
        source_label.setObjectName("sourceLabel")
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("sourceCombo")
        self.source_combo.addItems(["GitHub", "Mirror酱"])
        self.source_combo.setCursor(Qt.PointingHandCursor)
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_combo)

        channel_layout = QVBoxLayout()
        channel_layout.setSpacing(4)
        channel_label = QLabel("更新频道")
        channel_label.setObjectName("sourceLabel")
        self.channel_combo = QComboBox()
        self.channel_combo.setObjectName("sourceCombo")
        self.channel_combo.addItems(CHANNEL_MAP.keys())
        self.channel_combo.setCursor(Qt.PointingHandCursor)
        channel_layout.addWidget(channel_label)
        channel_layout.addWidget(self.channel_combo)

        layout.addWidget(self.large_icon)
        layout.addLayout(info_layout, 1)
        layout.addStretch()
        layout.addLayout(source_layout)
        layout.addLayout(channel_layout)
        return header_widget

    def _create_action_bar(self):
        bar = QFrame()
        bar.setObjectName("detailActionBar")
        bar.setFixedHeight(80)
        self.action_layout = QHBoxLayout(bar)
        self.action_layout.setContentsMargins(24, 0, 24, 0)
        self.action_stack = QStackedWidget()
        self.action_layout.addWidget(self.action_stack, 1)

        # 状态 0: 检查更新按钮
        self.check_button = QPushButton("检查更新")
        self.check_button.setObjectName("checkButton")
        self.check_button.setFixedHeight(40)
        self.check_button.clicked.connect(self._on_check_clicked)
        self.action_stack.addWidget(self.check_button)

        # 状态 1: 可用更新
        update_widget = QWidget()
        update_layout = QHBoxLayout(update_widget)
        self.update_version_label = QLabel()
        self.update_version_label.setObjectName("updateVersionInfo")
        self.update_version_label.setWordWrap(True)  # <-- 修复: 允许版本信息换行
        self.update_button = QPushButton("立即更新")
        self.update_button.setObjectName("updateButton")
        self.update_button.setFixedHeight(40)
        self.update_button.clicked.connect(self._on_update_clicked)
        update_layout.addWidget(self.update_version_label, 1)
        update_layout.addWidget(self.update_button)
        self.action_stack.addWidget(update_widget)

        # 状态 2: 下载中
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        progress_layout.setSpacing(12)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setObjectName("downloadProgressBar")
        self.speed_label = QLabel("0 MB/s")
        self.speed_label.setObjectName("downloadSpeed")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.setFixedHeight(32)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.speed_label)
        progress_layout.addWidget(self.cancel_button)
        self.action_stack.addWidget(progress_widget)

        # 状态 3: 最新版本 (成功状态)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.action_stack.addWidget(self.status_label)

        # --- 修改开始: 新增状态 4, 用于显示错误信息和重试按钮 ---
        error_widget = QWidget()
        error_layout = QHBoxLayout(error_widget)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.setSpacing(12)
        self.error_label = QLabel()
        self.error_label.setObjectName("statusLabel")
        self.error_label.setWordWrap(True)  # <-- 修复: 允许错误信息换行, 避免撑大窗口
        self.error_label.setAlignment(Qt.AlignCenter)
        self.retry_button = QPushButton("重试")
        self.retry_button.setObjectName("cancelButton")  # 复用一个比较中性的样式
        self.retry_button.setFixedHeight(32)
        self.retry_button.clicked.connect(self._on_check_clicked)  # 点击重试就重新检查
        error_layout.addWidget(self.error_label, 1)
        error_layout.addWidget(self.retry_button)
        self.action_stack.addWidget(error_widget)
        # --- 修改结束 ---

        return bar

    def _create_changelog_card(self):
        card = QFrame()
        card.setObjectName("detailCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("更新日志")
        title.setObjectName("cardTitle")

        self.changelog_browser = QTextBrowser()
        self.changelog_browser.setObjectName("changelogContent")
        self.changelog_browser.setReadOnly(True)
        self.changelog_browser.setOpenExternalLinks(True)  # 自动打开链接
        self.changelog_browser.setFrameShape(QFrame.NoFrame)
        self.changelog_browser.setMinimumHeight(150)  # 设置一个最小高度

        layout.addWidget(title)
        layout.addWidget(self.changelog_browser)
        return card

    def _create_description_card(self):
        card = QFrame()
        card.setObjectName("detailCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("描述")
        title.setObjectName("cardTitle")
        self.desc_label = QLabel("暂无描述。")
        self.desc_label.setObjectName("cardContent")
        self.desc_label.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.desc_label)
        return card

    def set_resource(self, resource, cached_status=None):
        self.current_resource = resource
        self.title_label.setText(resource.resource_name)
        self.author_label.setText(f"作者: {resource.resource_author or '未知'}")
        pixmap = QPixmap(f"assets/resource/{resource.resource_id}/{resource.resource_icon}")
        if pixmap.isNull():
            pixmap = QPixmap(80, 80)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#cbd5e1"), 2))
            painter.drawRoundedRect(pixmap.rect().adjusted(2, 2, -2, -2), 12, 12)
            painter.end()
        self.large_icon.setPixmap(pixmap)
        self.desc_label.setText(resource.resource_description or "该资源暂无描述。")
        self.source_combo.blockSignals(True)
        self.channel_combo.blockSignals(True)
        update_method = global_config.app_config.get_resource_update_method(resource.resource_name).lower()
        update_channel = global_config.app_config.get_resource_update_channel(resource.resource_name)
        self.source_combo.setCurrentText("Mirror酱" if 'mirrorchyan' in update_method else "GitHub")
        self.channel_combo.setCurrentText(REVERSE_CHANNEL_MAP.get(update_channel, "稳定版"))
        self.source_combo.blockSignals(False)
        self.channel_combo.blockSignals(False)

        self.changelog_card.hide()
        if cached_status:
            status = cached_status.get('status')
            details = cached_status.get('details', {})
            if status == 'available':
                self.set_update_available(details.get('version'), details.get('release_note'))
            elif status == 'latest':
                self.set_latest_version()
            elif status == 'error':
                self.set_error(details.get('message', '未知错误'))
            elif status == 'checking':
                self.set_checking()
            else:
                self.reset_action_bar()
        else:
            self.reset_action_bar()

    def _on_source_changed(self, text):
        if not self.current_resource: return
        resource_name = self.current_resource.resource_name
        new_method = 'MirrorChyan' if text == "Mirror酱" else 'github'

        config = global_config.app_config.resource_update_methods.get(resource_name)

        if config is None or config.method != new_method:
            if config is None:
                current_channel = CHANNEL_MAP.get(self.channel_combo.currentText(), 'stable')
                config = ResourceUpdateConfig(method=new_method, channel=current_channel)
                global_config.app_config.resource_update_methods[resource_name] = config
            else:
                config.method = new_method

            global_config.save_all_configs()
            notification_manager.show_info(
                f"'{resource_name}' 的更新源已设为 {text}。正在重新检查更新...", "设置已保存")
            self.set_checking()
            self.source_changed_recheck.emit(self.current_resource)

    def _on_channel_changed(self, text):
        if not self.current_resource: return
        resource_name = self.current_resource.resource_name
        new_channel = CHANNEL_MAP.get(text, 'stable')

        config = global_config.app_config.resource_update_methods.get(resource_name)

        if config is None or config.channel != new_channel:
            if config is None:
                current_method = self._get_current_method_from_ui()
                config = ResourceUpdateConfig(method=current_method, channel=new_channel)
                global_config.app_config.resource_update_methods[resource_name] = config
            else:
                config.channel = new_channel

            global_config.save_all_configs()
            notification_manager.show_info(
                f"'{resource_name}' 的更新频道已设为 {text}。正在重新检查更新...", "设置已保存")
            self.set_checking()
            self.source_changed_recheck.emit(self.current_resource)

    def _get_current_method_from_ui(self):
        return 'MirrorChyan' if self.source_combo.currentText() == "Mirror酱" else 'github'

    def _on_check_clicked(self):
        if self.current_resource:
            self.set_checking()
            self.check_update_clicked.emit(self.current_resource)

    def _on_update_clicked(self):
        if self.current_resource:
            self.start_update_clicked.emit(self.current_resource)

    def _on_cancel_clicked(self):
        if self.current_resource:
            self.cancel_download_clicked.emit(self.current_resource)

    def set_checking(self):
        self.changelog_card.hide()
        self.check_button.setText("正在检查...")
        self.check_button.setEnabled(False)
        self.action_stack.setCurrentIndex(0)

    def set_update_available(self, new_version, release_note):
        self.update_version_label.setText(f"发现新版本: <b>{new_version}</b>")
        self.update_button.setText("立即更新")
        self.changelog_browser.setMarkdown(release_note or "此版本没有提供更新日志。")
        self.changelog_card.show()
        self.action_stack.setCurrentIndex(1)

    def set_downloading(self, progress, speed):
        self.action_stack.setCurrentIndex(2)
        self.progress_bar.setValue(int(progress))
        self.speed_label.setText(f"{speed:.1f} MB/s")

    def set_latest_version(self):
        self.changelog_card.hide()
        self.status_label.setText("您当前已是最新版本。")
        self.status_label.setProperty("status", "success")
        self.status_label.style().polish(self.status_label)
        self.action_stack.setCurrentIndex(3)

    def set_error(self, error_msg):
        self.changelog_card.hide()
        self.error_label.setText(f"错误: {error_msg}")
        self.error_label.setProperty("status", "error")
        self.error_label.style().polish(self.error_label)
        self.action_stack.setCurrentIndex(4)  # 切换到包含重试按钮的错误界面

    def reset_action_bar(self):
        self.changelog_card.hide()
        self.check_button.setText("检查更新")
        self.check_button.setEnabled(True)
        self.action_stack.setCurrentIndex(0)


class GitInstallerThread(QThread):
    progress_updated = Signal(str)
    install_succeeded = Signal(str)
    install_failed = Signal(str)

    def __init__(self, repo_url, ref, parent=None):
        super().__init__(parent)
        self.repo_url = repo_url
        self.ref = ref
        self.repo_name = repo_url.split('/')[-1].replace('.git', '')

    def run(self):
        try:
            temp_dir = Path("assets/temp")
            resource_dir = Path("assets/resource")
            temp_dir.mkdir(parents=True, exist_ok=True)
            resource_dir.mkdir(parents=True, exist_ok=True)
            final_path = resource_dir / self.repo_name
            if final_path.exists():
                raise FileExistsError(f"目标目录 'assets/resource/{self.repo_name}' 已存在。")

            if shutil.which('git') is not None:
                self.progress_updated.emit("Git 克隆中...")
                import git
                git.Repo.clone_from(self.repo_url, final_path, branch=self.ref, depth=1)
            else:
                notification_manager.show_info("未检测到 Git 环境，将使用 API 下载。")
                self.progress_updated.emit("API 下载中...")
                self._download_zip_from_github(final_path)

            self.install_succeeded.emit(self.repo_name)

        except Exception as e:
            self.install_failed.emit(str(e))

    def _download_zip_from_github(self, final_path):
        parts = self.repo_url.split('github.com/')[1].split('/')
        owner, repo = parts[0], parts[1].replace('.git', '')
        zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{self.ref}"

        headers = {}
        github_token = global_config.app_config.github_token
        if github_token: headers["Authorization"] = f"token {github_token}"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = Path(temp_dir) / "repo.zip"
            with requests.get(zip_url, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()
                with open(temp_zip_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192): f.write(chunk)

            extract_path = Path(temp_dir) / "extracted"
            shutil.unpack_archive(temp_zip_path, extract_path)
            unzipped_folder = next(extract_path.iterdir(), None)
            if not unzipped_folder: raise FileNotFoundError("解压失败")

            shutil.move(str(unzipped_folder), str(final_path))


class DownloadPage(QWidget):
    """下载页面主类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadPage")
        self.active_checkers = {}
        self.active_downloaders = {}
        self.resource_items = {}
        self.selected_resource = None
        self.update_status_cache = {}
        self.current_update_info = {}

        self.installer = UpdateInstallerFactory()
        self.git_installer_thread = None

        self._init_ui()
        self._connect_signals()
        self.load_resources()
        self._apply_stylesheet()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel)
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, 1)

    def _create_left_panel(self):
        panel = QWidget()
        panel.setObjectName("leftPanel")
        panel.setFixedWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = self._create_left_header()
        layout.addWidget(header)
        scroll_area = QScrollArea()
        scroll_area.setObjectName("resourceListScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        self.resources_container = QWidget()
        self.resources_layout = QVBoxLayout(self.resources_container)
        self.resources_layout.setContentsMargins(12, 8, 12, 8)
        self.resources_layout.setSpacing(8)
        scroll_area.setWidget(self.resources_container)
        layout.addWidget(scroll_area)
        bottom_bar = self._create_bottom_bar()
        layout.addWidget(bottom_bar)
        return panel

    def _create_left_header(self):
        header = QFrame()
        header.setObjectName("leftPanelHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel("资源管理")
        title.setObjectName("leftPanelTitle")
        layout.addWidget(title)
        layout.addStretch()
        return header

    def _create_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("leftPanelBottomBar")
        bar.setFixedHeight(70)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)
        self.add_btn = QPushButton(" 添加资源")
        self.add_btn.setObjectName("bottomBarButton")
        self.add_btn.setIcon(QIcon("assets/icons/add.png"))
        self.add_btn.setFixedHeight(40)
        self.add_btn.clicked.connect(self.show_add_resource_dialog)
        self.check_all_btn = QPushButton(" 全部检查")
        self.check_all_btn.setObjectName("bottomBarButton")
        self.check_all_btn.setIcon(QIcon("assets/icons/refresh.png"))
        self.check_all_btn.setFixedHeight(40)
        self.check_all_btn.clicked.connect(self.check_all_updates)
        layout.addWidget(self.add_btn)
        layout.addWidget(self.check_all_btn)
        return bar

    def _create_right_panel(self):
        panel = QWidget()
        panel.setObjectName("rightPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.content_stack = QStackedWidget()
        self.empty_widget = self._create_empty_state()
        self.detail_view = ResourceDetailView()
        self.content_stack.addWidget(self.empty_widget)
        self.content_stack.addWidget(self.detail_view)
        layout.addWidget(self.content_stack)
        return panel

    def _create_empty_state(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        icon_label = QLabel()
        pixmap = QPixmap("assets/icons/empty.png").scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        text_label = QLabel("从左侧选择一个资源以查看详情")
        text_label.setObjectName("emptyStateText")
        hint_label = QLabel("您可以使用“添加资源”按钮来添加新资源。")
        hint_label.setObjectName("emptyStateHint")
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addWidget(hint_label)
        return widget

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            #downloadPage { background-color: #f8fafc; }
            #leftPanel { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
            #leftPanelHeader { border-bottom: 1px solid #e2e8f0; }
            #leftPanelTitle { font-size: 18px; font-weight: 600; color: #1e293b; }
            #resourceListScroll { border: none; }
            #resourceItem { border-radius: 8px; border: 1px solid transparent; }
            #resourceItem:hover { background-color: #f1f5f9; }
            #resourceItem[selected="true"] { background-color: #e0f2fe; border-color: #38bdf8; }
            #resourceItemName { font-size: 14px; font-weight: 600; color: #334155; }
            #resourceItemVersion { font-size: 12px; color: #64748b; }
            #leftPanelBottomBar { border-top: 1px solid #e2e8f0; }
            #bottomBarButton { background-color: #f1f5f9; color: #475569; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; }
            #bottomBarButton:hover { background-color: #e2e8f0; }
            #rightPanel { background-color: #f8fafc; }
            #detailScrollArea { border: none; }
            #emptyStateText { font-size: 16px; color: #475569; font-weight: 500; }
            #emptyStateHint { font-size: 13px; color: #94a3b8; }
            #detailIcon { border-radius: 12px; }
            #detailTitle { font-size: 24px; font-weight: 700; color: #1e293b; }
            #detailAuthor { font-size: 14px; color: #64748b; }
            #sourceLabel { font-size: 12px; color: #64748b; font-weight: 500; margin-left: 2px; }
            #sourceCombo { border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px; background-color: white; }
            #sourceCombo::drop-down { border: none; }
            #detailActionBar { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
            #checkButton, #updateButton { border: none; border-radius: 8px; font-weight: 600; padding: 0 16px; }
            #checkButton { background-color: #3b82f6; color: white; }
            #checkButton:hover { background-color: #2563eb; }
            #updateButton { background-color: #10b981; color: white; }
            #updateButton:hover { background-color: #059669; }
            #updateVersionInfo { font-size: 14px; color: #334155; }
            #downloadSpeed { font-size: 13px; color: #475569; }
            #statusLabel[status="success"] { color: #16a34a; font-weight: 600; }
            #statusLabel[status="error"] { color: #dc2626; font-weight: 600; }
            #detailCard { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
            #cardTitle { font-size: 16px; font-weight: 600; color: #334155; }
            #cardContent { font-size: 14px; color: #475569; line-height: 1.5; }
            #changelogContent { background-color: transparent; border: none; font-size: 14px; color: #475569; }
            #downloadProgressBar { border: none; background-color: #e2e8f0; border-radius: 6px; }
            #downloadProgressBar::chunk { background-color: #3b82f6; border-radius: 6px; }
            #cancelButton { background-color: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px; font-weight: 500; padding: 0 12px; }
            #cancelButton:hover { background-color: #e2e8f0; border-color: #d1d5db; }
        """)

    def load_resources(self):
        for item in self.resource_items.values(): item.deleteLater()
        self.resource_items.clear()
        while self.resources_layout.count():
            item = self.resources_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        resources = global_config.get_all_resource_configs()
        for resource in resources:
            item = ResourceListItem(resource)
            item.clicked.connect(self._on_resource_selected)
            self.resources_layout.addWidget(item)
            self.resource_items[resource.resource_name] = item
        self.resources_layout.addStretch()

        if not self.selected_resource and resources:
            self._on_resource_selected(resources[0])
        elif not resources:
            self.content_stack.setCurrentIndex(0)
            self.selected_resource = None

    def _on_resource_selected(self, resource):
        if self.selected_resource == resource: return
        self.selected_resource = resource
        for name, item in self.resource_items.items():
            item.set_selected(name == resource.resource_name)
        cached_status = self.update_status_cache.get(resource.resource_name)
        self.detail_view.set_resource(resource, cached_status)
        self.content_stack.setCurrentIndex(1)

    def _connect_signals(self):
        self.installer.install_completed.connect(self._handle_install_completed)
        self.installer.install_failed.connect(self._handle_install_failed)
        self.installer.restart_required.connect(self._handle_restart_required)

        self.detail_view.check_update_clicked.connect(self._check_resource_update)
        self.detail_view.start_update_clicked.connect(self._start_update)
        self.detail_view.cancel_download_clicked.connect(self._cancel_download)
        self.detail_view.source_changed_recheck.connect(self._check_resource_update)

    def _check_resource_update(self, resource):
        if resource.resource_name in self.active_checkers: return

        self.update_status_cache[resource.resource_name] = {'status': 'checking'}
        thread = UpdateChecker(resource, single_mode=True)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)
        thread.finished.connect(lambda: self.active_checkers.pop(resource.resource_name, None))
        self.active_checkers[resource.resource_name] = thread
        thread.start()

    def _start_update(self, resource):
        update_info = self.current_update_info.get(resource.resource_name)
        if not update_info:
            notification_manager.show_error("没有找到更新信息，请先检查更新。", resource.resource_name)
            return

        is_git_repo = False
        if update_info.source == UpdateSource.GITHUB:
            resource_path = Path(resource.source_file).parent

            if shutil.which('git') is not None:
                try:
                    import git
                    git.Repo(resource_path)
                    is_git_repo = True
                except Exception as e:
                    app_logger.error(e)
                    is_git_repo = False
            else:
                is_git_repo = False

        if is_git_repo:
            notification_manager.show_info("检测到Git仓库，将直接通过Git更新...", resource.resource_name)
            self.detail_view.status_label.setText("正在通过Git更新...")
            self.detail_view.status_label.setProperty("status", "")
            self.detail_view.action_stack.setCurrentIndex(3)
            self.installer.install_update(update_info, file_path=None, resource=resource)

        else:
            if resource.resource_name in self.active_downloaders: return
            notification_manager.show_info("正在准备下载...", resource.resource_name)
            self.detail_view.set_downloading(0, 0)
            temp_dir = Path("assets/temp")

            thread = UpdateDownloader(update_info, temp_dir)
            thread.progress_updated.connect(self._update_download_progress)
            thread.download_completed.connect(self._handle_download_completed)
            thread.download_failed.connect(self._handle_download_failed)
            thread.finished.connect(lambda: self.active_downloaders.pop(resource.resource_name, None))
            self.active_downloaders[resource.resource_name] = thread
            thread.start()

    def _handle_download_completed(self, update_info: UpdateInfo, file_path: str):
        resource = next(
            (r for r in global_config.get_all_resource_configs() if r.resource_name == update_info.resource_name), None)
        if resource:
            self.installer.install_update(update_info, file_path, resource)
        else:
            if update_info.resource_name == "MFWPH 主程序":
                self.installer.install_update(update_info, file_path, None)
            else:
                self._handle_install_failed(update_info.resource_name, "找不到本地资源配置")

    def _cancel_download(self, resource):
        thread = self.active_downloaders.get(resource.resource_name)
        if thread:
            thread.cancel()
            cached_status = self.update_status_cache.get(resource.resource_name)
            if cached_status and cached_status['status'] == 'available':
                details = cached_status.get('details', {})
                self.detail_view.set_update_available(details.get('version'), details.get('release_note'))
            else:
                self.detail_view.reset_action_bar()
            notification_manager.show_info(f"'{resource.resource_name}' 的下载已取消。", "操作已取消")

    def _handle_update_found(self, update_info: UpdateInfo):
        self.current_update_info[update_info.resource_name] = update_info
        self.update_status_cache[update_info.resource_name] = {
            'status': 'available',
            'details': {'version': update_info.new_version, 'release_note': update_info.release_note}
        }
        if item := self.resource_items.get(update_info.resource_name):
            item.set_update_status(True)
        if self.selected_resource and self.selected_resource.resource_name == update_info.resource_name:
            self.detail_view.set_update_available(update_info.new_version, update_info.release_note)

    def _handle_update_not_found(self, resource_name):
        self.update_status_cache[resource_name] = {'status': 'latest'}
        if item := self.resource_items.get(resource_name): item.set_update_status(False)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_latest_version()

    def _handle_check_failed(self, resource_name, error_message):
        self.update_status_cache[resource_name] = {'status': 'error', 'details': {'message': error_message}}
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error(error_message)
        notification_manager.show_error(f"更新检查失败: {error_message}", resource_name)

    def _update_download_progress(self, resource_name, progress, speed):
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_downloading(progress, speed)

    def _handle_download_failed(self, resource_name, error):
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error(f"下载失败: {error}")
        notification_manager.show_error(f"下载失败: {error}", resource_name)

    def check_all_updates(self):
        self.check_all_btn.setText("检查中...")
        self.check_all_btn.setEnabled(False)
        resources_with_update = [r for r in global_config.get_all_resource_configs() if
                                 r.mirror_update_service_id or r.resource_rep_url]
        if not resources_with_update:
            self.check_all_btn.setText("全部检查")
            self.check_all_btn.setEnabled(True)
            notification_manager.show_info("没有找到可检查更新的资源。", "更新检查")
            return
        for r in resources_with_update: self.update_status_cache[r.resource_name] = {'status': 'checking'}

        batch_checker = UpdateChecker(resources_with_update)
        batch_checker.update_found.connect(self._handle_update_found)
        batch_checker.update_not_found.connect(self._handle_update_not_found)
        batch_checker.check_failed.connect(self._handle_check_failed)
        batch_checker.check_completed.connect(self._handle_batch_check_completed)
        self.batch_checker_thread = batch_checker
        batch_checker.start()

    def _handle_batch_check_completed(self, total_checked, updates_found):
        self.check_all_btn.setEnabled(True)
        self.check_all_btn.setText("全部检查")
        if updates_found > 0:
            notification_manager.show_success(f"检查完成，发现 {updates_found} 个可用更新。", "检查完成")
        else:
            notification_manager.show_success(f"所有 {total_checked} 个资源都已是最新版本。", "检查完成")

    def show_add_resource_dialog(self):
        dialog = AddResourceDialog(self)
        if dialog.exec() == QDialog.Accepted: self.add_new_resource(dialog.get_data())

    def add_new_resource(self, data):
        url, ref = data.get('url'), data.get('ref')
        if not url or not ref or "github.com" not in url:
            notification_manager.show_error("请输入有效的GitHub仓库地址和分支/标签。", "输入无效")
            return
        if self.git_installer_thread and self.git_installer_thread.isRunning():
            notification_manager.show_warning("请等待当前添加操作完成。")
            return
        self.add_btn.setEnabled(False)
        self.add_btn.setText("添加中...")
        self.git_installer_thread = GitInstallerThread(url, ref, self)
        self.git_installer_thread.install_succeeded.connect(self._handle_add_succeeded)
        self.git_installer_thread.install_failed.connect(self._handle_add_failed)
        self.git_installer_thread.start()

    def _handle_add_succeeded(self, resource_name):
        self._restore_add_button()
        notification_manager.show_success(f"资源 '{resource_name}' 添加成功！", "成功")
        resource_dir = "assets/resource/"
        if not os.path.exists(resource_dir):
            os.makedirs(resource_dir)
        global_config.load_all_resources_from_directory(resource_dir)
        self.load_resources()

    def _handle_add_failed(self, error_message):
        self._restore_add_button()
        notification_manager.show_error(f"添加资源失败: {error_message}", "错误")

    def _restore_add_button(self):
        self.add_btn.setEnabled(True)
        self.add_btn.setText(" 添加资源")

    def _handle_install_completed(self, resource_name, version, locked_files):
        notification_manager.show_success(f"资源 {resource_name} 已更新至版本 {version}", "更新成功")
        self.update_status_cache.pop(resource_name, None)
        self.current_update_info.pop(resource_name, None)
        self.load_resources()
        for res in global_config.get_all_resource_configs():
            if res.resource_name == resource_name:
                self._on_resource_selected(res)
                self.detail_view.set_latest_version()
                break

    def _handle_install_failed(self, resource_name, error_message):
        notification_manager.show_error(f"安装失败: {error_message}", resource_name)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error(f"安装失败: {error_message}")

    # --- 修改开始: 优化重启流程 ---
    def _handle_restart_required(self):
        # 直接显示通知, 不再弹窗让用户确认
        notification_manager.show_info(
            "本次更新需要重启应用程序才能生效，程序将在 5 秒后自动重启。",
            "即将重启"
        )
        QTimer.singleShot(5000, QCoreApplication.quit)
