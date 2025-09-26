import asyncio
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                               QDialogButtonBox, QComboBox, QWidget, QPushButton,
                               QHBoxLayout, QLabel, QApplication, QStyle, QListView)
from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, Qt

from app.models.config.global_config import global_config
from app.utils.resource_manager import get_github_repo_refs

class AddResourceDialog(QDialog):
    """
    一个现代、固定大小的对话框，用于通过GitHub URL添加新资源。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.repo_url = ""
        self.is_url_valid = False
        self._load_status_icons()

        self.setup_ui()
        self.setup_connections()
        self.apply_stylesheet()
        self.on_mode_changed()

    def _load_status_icons(self):
        """加载Qt内置的样式图标，避免依赖外部文件"""
        style = self.style()
        icon_size = QSize(18, 18)
        self.icon_success = style.standardIcon(QStyle.SP_DialogApplyButton).pixmap(icon_size)
        self.icon_failure = style.standardIcon(QStyle.SP_DialogCancelButton).pixmap(icon_size)
        self.icon_info = style.standardIcon(QStyle.SP_MessageBoxInformation).pixmap(icon_size)

    def setup_ui(self):
        """初始化和布局UI组件"""
        self.setObjectName("addResourceDialog")
        self.setWindowTitle("从 GitHub 添加资源")
        self.setFont(QFont("Segoe UI", 10))
        self.resize(550, 350)
        self.setMinimumSize(550, 350)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        mode_layout = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("从 GitHub URL 导入", "url")
        mode_layout.addRow("导入方式:", self.mode_combo)
        main_layout.addLayout(mode_layout)

        url_page = QWidget()
        form_layout = QFormLayout(url_page)
        form_layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form_layout.setVerticalSpacing(12)

        url_input_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://github.com/owner/repo")
        self.check_url_button = QPushButton("检查")
        self.check_url_button.setObjectName("checkUrlButton")
        self.check_url_button.setFixedWidth(80)
        url_input_layout.addWidget(self.url_edit)
        url_input_layout.addWidget(self.check_url_button)
        form_layout.addRow("GitHub 仓库链接:", url_input_layout)

        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 5, 0, 5)
        self.status_icon_label = QLabel()
        self.status_icon_label.setPixmap(self.icon_info)
        self.status_text_label = QLabel("请输入一个有效的 GitHub 仓库链接。")
        self.status_text_label.setObjectName("statusTextLabel")
        status_layout.addWidget(self.status_icon_label)
        status_layout.addWidget(self.status_text_label)
        status_layout.addStretch()
        form_layout.addRow(status_layout)

        self.ref_label = QLabel("选择分支或标签:")
        self.ref_combo = QComboBox()
        form_layout.addRow(self.ref_label, self.ref_combo)
        self.ref_label.hide()
        self.ref_combo.hide()

        main_layout.addWidget(url_page)
        main_layout.addStretch(1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("添加")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
        main_layout.addWidget(self.button_box)

    def setup_connections(self):
        """连接信号和槽"""
        self.url_edit.textChanged.connect(self.on_url_text_changed)
        self.check_url_button.clicked.connect(
            lambda: asyncio.create_task(self.on_check_url_clicked())
        )
        self.ref_combo.currentIndexChanged.connect(self.validate_input)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def on_mode_changed(self):
        self.validate_input()

    def on_url_text_changed(self):
        """当URL输入框文本改变时，重置状态"""
        self.is_url_valid = False
        self.ref_label.hide()
        self.ref_combo.hide()
        self.ref_combo.clear()
        self.status_icon_label.setPixmap(self.icon_info)
        self.status_text_label.setText("URL已更改，请重新检查。")
        self.status_text_label.setProperty("status", "default")
        self.check_url_button.setText("检查")
        self.check_url_button.setEnabled(bool(self.url_edit.text().strip()))
        self.refresh_style(self.status_text_label)
        self.validate_input()

    async def on_check_url_clicked(self):
        """（异步）处理“检查”按钮点击"""
        url_to_check = self.url_edit.text().strip()
        if not url_to_check:
            return

        # 更新UI，准备开始检查
        self.check_url_button.setEnabled(False)
        self.check_url_button.setText("检查中...")
        self.status_text_label.setText("正在检查仓库...")
        self.status_text_label.setProperty("status", "checking")
        self.refresh_style(self.status_text_label)

        try:
            is_valid, branches, tags = await asyncio.to_thread(
                get_github_repo_refs, url_to_check,global_config.get_app_config().github_token
            )

        except Exception as e:
            # 处理网络请求或函数本身可能抛出的异常
            print(f"执行 get_github_repo_refs 时发生异常: {e}")
            is_valid, branches, tags = False, [], []

        # 5. 回到主线程，根据后台任务的结果更新UI
        self.is_url_valid = is_valid
        if is_valid:
            self.repo_url = url_to_check
            self.status_icon_label.setPixmap(self.icon_success)
            self.status_text_label.setText("验证成功！请选择一个分支或标签。")
            self.status_text_label.setProperty("status", "success")
            self._populate_ref_combo(branches, tags)
            self.ref_label.show()
            self.ref_combo.show()
        else:
            self.repo_url = ""
            self.status_icon_label.setPixmap(self.icon_failure)
            self.status_text_label.setText("链接无效或仓库不存在，请重试。")
            self.status_text_label.setProperty("status", "failure")
            self.ref_label.hide()
            self.ref_combo.hide()

        self.check_url_button.setEnabled(True)
        self.check_url_button.setText("检查")
        self.refresh_style(self.status_text_label)
        self.validate_input()

    def _populate_ref_combo(self, branches, tags):
        """填充分支和标签到下拉框，并设置默认项"""
        self.ref_combo.clear()

        if tags:
            # 添加一个不可选的分隔符/标题
            self.ref_combo.addItem("--- 标签 (Tags) ---")
            self.ref_combo.model().item(self.ref_combo.count() - 1).setEnabled(False)
            for tag in tags:
                self.ref_combo.addItem(f"tag: {tag}", userData=tag)

        if branches and tags:
            self.ref_combo.insertSeparator(self.ref_combo.count())

        if branches:
            self.ref_combo.addItem("--- 分支 (Branches) ---")
            self.ref_combo.model().item(self.ref_combo.count() - 1).setEnabled(False)
            for branch in branches:
                self.ref_combo.addItem(f"branch: {branch}", userData=branch)

        # 默认选择
        if tags:
            self.ref_combo.setCurrentIndex(1)
        elif branches:
            branch_start_index = self.ref_combo.count() - len(branches)
            self.ref_combo.setCurrentIndex(branch_start_index)

        self.refresh_style(self.ref_combo)

    def validate_input(self):
        """验证输入以启用“添加”按钮"""
        is_ok_enabled = (self.is_url_valid and
                         self.ref_combo.currentIndex() > -1 and
                         self.ref_combo.currentData() is not None)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(is_ok_enabled)

    def get_data(self):
        """返回对话框数据"""
        if self.is_url_valid and self.ref_combo.currentData():
            return {"mode": "url", "url": self.repo_url, "ref": self.ref_combo.currentData()}
        return None

    def refresh_style(self, widget):
        """刷新控件样式以应用属性选择器"""
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def apply_stylesheet(self):
        """应用QSS样式"""
        qss = """
            #addResourceDialog { background-color: #F8F9FA; }
            QLabel, QRadioButton { color: #333; }
            QLineEdit, QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CED4DA;
                padding: 6px 8px;
                border-radius: 4px;
                color: #212529;
            }
            QLineEdit:focus, QComboBox:focus { border-color: #007BFF; }
            QComboBox::drop-down { border: none; }

            QPushButton {
                border: none; padding: 8px 16px;
                border-radius: 4px; font-weight: bold; color: white;
            }
            #checkUrlButton { background-color: #007BFF; }
            #checkUrlButton:hover { background-color: #0069D9; }
            #checkUrlButton:disabled { background-color: #6C757D; }

            QDialogButtonBox QPushButton { background-color: #6C757D; }
            QDialogButtonBox QPushButton:hover { background-color: #5A6268; }
            QDialogButtonBox QPushButton:default { background-color: #007BFF; }
            QDialogButtonBox QPushButton:default:hover { background-color: #0069D9; }

            #statusTextLabel[status="default"] { color: #6C757D; }
            #statusTextLabel[status="checking"] { color: #007BFF; }
            #statusTextLabel[status="success"] { color: #28A745; font-weight: bold; }
            #statusTextLabel[status="failure"] { color: #DC3545; font-weight: bold; }
        """
        self.setStyleSheet(qss)
