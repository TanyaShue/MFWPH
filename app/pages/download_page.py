"""
资源下载页面，提供资源下载和更新检查功能。
支持独立更新程序的重启机制。
"""
from pathlib import Path

import requests
from PySide6.QtCore import QTimer, QCoreApplication
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QHBoxLayout,
                               QProgressBar, QMessageBox, QSizePolicy, QDialog)

from app.models.config.global_config import global_config
from app.utils.update_check import UpdateChecker, UpdateDownloader
from app.utils.update_install import UpdateInstaller
from app.widgets.add_resource_dialog import AddResourceDialog


class DownloadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadPage")
        self.threads = []  # 存储线程引用
        self.pending_updates = []  # 存储待处理的更新

        # 创建更新安装器
        self.installer = UpdateInstaller()

        self._init_ui()
        self.load_resources()

    def _init_ui(self):
        """初始化UI元素"""
        layout = QVBoxLayout(self)

        # 页面标题
        title_label = QLabel("资源下载")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # 主框架
        main_frame = QFrame()
        main_frame.setObjectName("mainFrame")
        main_frame.setFrameShape(QFrame.StyledPanel)
        main_layout = QVBoxLayout(main_frame)

        # 顶部按钮行
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.setObjectName("topButtonsLayout")

        # 添加资源按钮
        self.add_resource_button = QPushButton("添加新资源")
        self.add_resource_button.setObjectName("primaryButton")
        self.add_resource_button.setIcon(QIcon("assets/icons/add.png"))
        self.add_resource_button.clicked.connect(self.show_add_resource_dialog)
        top_buttons_layout.addWidget(self.add_resource_button)

        top_buttons_layout.addStretch()

        # 更新所有按钮
        self.update_all_button = QPushButton("一键检查所有更新")
        self.update_all_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.update_all_button.setObjectName("secondaryButton")
        self.update_all_button.clicked.connect(self.check_all_updates)
        top_buttons_layout.addWidget(self.update_all_button)

        main_layout.addLayout(top_buttons_layout)

        # 资源表格
        main_layout.addWidget(self._create_section_label("可用资源"))
        self.resources_table = self._create_table(["资源名称", "版本", "作者", "描述", "操作"])
        self.resources_table.setObjectName("resourcesTable")
        main_layout.addWidget(self.resources_table)

        # 下载队列表格
        main_layout.addWidget(self._create_section_label("下载队列"))
        self.queue_table = self._create_table(["资源名称", "进度", "速度", "操作"])
        self.queue_table.setObjectName("queueTable")
        main_layout.addWidget(self.queue_table)

        layout.addWidget(main_frame)

        # 连接安装器信号
        self.installer.install_completed.connect(self._handle_install_completed)
        self.installer.install_failed.connect(self._handle_install_failed)
        self.installer.restart_required.connect(self._handle_restart_required)

    def _create_section_label(self, text):
        """创建具有一致样式的章节标签"""
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _create_table(self, headers):
        """创建具有一致样式的表格"""
        table = QTableWidget(0, len(headers))
        table.setObjectName("baseTable")
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        # 使表格只读
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        return table

    def show_add_resource_dialog(self):
        """显示添加新资源的对话框"""
        dialog = AddResourceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.add_new_resource(dialog.get_data())

    def add_new_resource(self, data):
        """添加新资源"""
        # 显示处理状态
        self.add_resource_button.setEnabled(False)
        self.add_resource_button.setText("添加中...")

        # 创建临时目录
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 处理 URL
        url = data["url"]
        if "github.com" in url and not url.endswith(".zip"):
            # 处理 GitHub 仓库 URL 以获取下载链接
            self._process_github_repo(url, data)
        else:
            self._download_resource(url, data)

    def _process_github_repo(self, repo_url, data):
        """处理 GitHub 仓库 URL 以获取下载链接"""
        try:
            # 解析 GitHub URL
            parts = repo_url.split('github.com/')[1].split('/')
            if len(parts) < 2:
                self._show_add_error("GitHub地址格式不正确")
                return

            owner, repo = parts[0], parts[1]
            if repo.endswith('.git'):
                repo = repo[:-4]

            # 获取最新发布信息
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            response = requests.get(api_url)

            if response.status_code != 200:
                self._show_add_error(f"API返回错误 ({response.status_code})")
                return

            release_info = response.json()
            latest_version = release_info.get('tag_name', '').lstrip('v')

            # 如果未提供名称，则使用仓库名称
            if not data["name"]:
                data["name"] = repo

            # 查找 ZIP 资源
            download_url = None
            for asset in release_info.get('assets', []):
                if asset.get('name', '').endswith('.zip'):
                    download_url = asset.get('browser_download_url')
                    break

            if not download_url:
                self._show_add_error("找不到可下载的资源包")
                return

            # 下载 ZIP
            self._download_resource(download_url, data, latest_version)

        except Exception as e:
            self._show_add_error(str(e))

    def _download_resource(self, url, data, version=None):
        """添加资源到下载队列并启动下载线程"""
        # 准备资源名称
        resource_name = data["name"] if data["name"] else "新资源"

        # 添加到下载队列
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(resource_name))
        self.queue_table.setRowHeight(row, 45)

        # 添加进度条
        progress_bar = QProgressBar()
        progress_bar.setObjectName("downloadProgressBar")
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        self.queue_table.setCellWidget(row, 1, progress_bar)

        # 添加速度标签
        speed_label = QLabel("等待中...")
        speed_label.setObjectName("speedLabel")
        self.queue_table.setCellWidget(row, 2, speed_label)

        # 添加取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setFixedHeight(30)
        self.queue_table.setCellWidget(row, 3, cancel_btn)

        # 创建下载线程
        temp_dir = Path("assets/temp")
        thread = UpdateDownloader(resource_name, url, temp_dir, data=data, version=version)

        # 连接信号
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_resource_download_completed)
        thread.download_failed.connect(self._handle_resource_download_failed)

        # 连接取消按钮
        cancel_btn.clicked.connect(thread.cancel)

        # 启动线程
        self.threads.append(thread)
        thread.start()

    def _update_download_progress(self, resource_name, progress, speed):
        """更新队列表格中的下载进度"""
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if item and item.text() == resource_name:
                progress_bar = self.queue_table.cellWidget(row, 1)
                if progress_bar:
                    progress_bar.setValue(int(progress))
                    progress_bar.setFormat(f"{int(progress)}%")

                speed_label = self.queue_table.cellWidget(row, 2)
                if speed_label:
                    speed_label.setText(f"{speed:.2f} MB/s")
                break

    def _handle_resource_download_completed(self, resource_name, file_path, data):
        """处理资源下载完成"""
        # 从队列中移除
        self._remove_from_queue(resource_name)

        try:
            # 根据数据类型确定是新资源还是更新
            if isinstance(data, dict):
                # 新资源
                self.installer.install_new_resource(resource_name, file_path, data)
            else:
                # 资源更新
                self.installer.install_update(data, file_path)

        except Exception as e:
            self._show_error(resource_name, str(e))

    def _handle_install_completed(self, resource_name, version, locked_files):
        """处理安装完成信号"""
        # 重新加载资源并恢复按钮
        self.load_resources()
        self._restore_add_button()

        # 显示成功消息
        QMessageBox.information(self, "操作完成", f"资源 {resource_name} 已成功添加/更新到版本 {version}")

    def _handle_install_failed(self, resource_name, error_message):
        """处理安装失败信号"""
        self._restore_add_button()
        self._show_error(resource_name, error_message)

    def _handle_restart_required(self):
        """处理需要重启的情况"""
        # 显示确认对话框
        reply = QMessageBox.question(
            self,
            "需要重启应用",
            "此更新需要重启应用程序才能完成。\n\n应用程序将自动重启，您的更新将在重启后应用。\n\n是否立即重启？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # 退出应用程序（独立更新程序会自动重启）
            QTimer.singleShot(100, QCoreApplication.quit)
        else:
            QMessageBox.information(
                self,
                "更新延迟",
                "更新已下载但尚未应用。请手动重启应用程序以完成更新。"
            )

    def _handle_resource_download_failed(self, resource_name, error):
        """处理资源下载失败"""
        self._remove_from_queue(resource_name)
        self._restore_add_button()
        QMessageBox.warning(self, "下载失败", f"资源 {resource_name} 下载失败:\n{error}")

    def _remove_from_queue(self, resource_name):
        """从下载队列中移除资源"""
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if item and item.text() == resource_name:
                self.queue_table.removeRow(row)
                break

    def _restore_add_button(self):
        """恢复添加资源按钮状态"""
        self.add_resource_button.setEnabled(True)
        self.add_resource_button.setText("添加新资源")

    def _show_add_error(self, error):
        """显示添加资源时的错误"""
        self._restore_add_button()
        QMessageBox.warning(self, "添加失败", f"添加资源失败:\n{error}")

    def _show_error(self, resource_name, error):
        """显示通用错误消息"""
        QMessageBox.warning(self, "操作失败", f"资源 {resource_name} 操作失败: {error}")

    def load_resources(self):
        """从全局配置加载资源到表格"""
        resources = global_config.get_all_resource_configs()

        # 清空表格
        self.resources_table.setRowCount(0)

        # 添加资源到表格
        for i, resource in enumerate(resources):
            self.resources_table.insertRow(i)
            self.resources_table.setItem(i, 0, QTableWidgetItem(resource.resource_name))
            self.resources_table.setItem(i, 1, QTableWidgetItem(resource.resource_version))
            self.resources_table.setItem(i, 2, QTableWidgetItem(resource.resource_author))
            self.resources_table.setItem(i, 3, QTableWidgetItem(resource.resource_description))

            # 添加检查更新按钮
            check_btn = QPushButton("检查更新")
            check_btn.setObjectName("check_btn")
            check_btn.clicked.connect(lambda checked, r=resource: self.check_resource_update(r))
            self.resources_table.setCellWidget(i, 4, check_btn)

            # 设置行高
            self.resources_table.setRowHeight(i, 45)

    def check_resource_update(self, resource):
        """检查单个资源的更新"""
        # 查找此资源的按钮
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource.resource_name:
                check_btn = self.resources_table.cellWidget(row, 4)

                # 处理没有更新源的资源
                if not resource.resource_rep_url and not resource.resource_update_service_id:
                    no_update_source_btn = QPushButton("无更新源")
                    no_update_source_btn.setObjectName("no_update_source_btn")
                    no_update_source_btn.setEnabled(False)
                    self.resources_table.setCellWidget(row, 4, no_update_source_btn)
                    # 延迟后恢复按钮
                    QTimer.singleShot(3000, lambda: self._restore_check_button(resource.resource_name))
                    return

                # 更新正常检查的按钮状态
                check_btn.setText("检查中...")
                check_btn.setEnabled(False)
                check_btn.setObjectName("downloading_btn")
                self.resources_table.setCellWidget(row, 4, check_btn)
                break

        # 创建检查线程
        thread = UpdateChecker(resource, single_mode=True)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)

        # 启动线程
        self.threads.append(thread)
        thread.start()

    def _handle_update_found(self, resource_name, latest_version, current_version, download_url, update_type):
        """处理发现资源更新"""
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource_name:
                # 更新版本显示
                self.resources_table.item(row, 1).setText(f"{current_version} → {latest_version}")

                # 替换为更新按钮
                resource = next((r for r in global_config.get_all_resource_configs()
                                 if r.resource_name == resource_name), None)

                if resource:
                    # 在按钮中添加更新类型指示器
                    update_type_display = "增量" if update_type == "incremental" else "完整"
                    update_btn = QPushButton(f"{update_type_display}更新")
                    update_btn.setObjectName("update_btn")
                    update_btn.setFixedHeight(30)
                    update_btn.clicked.connect(
                        lambda checked, r=resource, url=download_url, v=latest_version, up=update_type:
                        self.start_update(r, url, v, up)
                    )
                    self.resources_table.setCellWidget(row, 4, update_btn)
                break

    def _handle_update_not_found(self, resource_name):
        """处理未发现资源更新"""
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource_name:
                # 显示已是最新版本
                latest_version_btn = QPushButton("已是最新版本")
                latest_version_btn.setObjectName("latest_version_btn")
                latest_version_btn.setFixedHeight(30)
                latest_version_btn.setEnabled(False)
                self.resources_table.setCellWidget(row, 4, latest_version_btn)

                # 延迟后恢复按钮
                QTimer.singleShot(3000, lambda: self._restore_check_button(resource_name))
                break

    def _handle_check_failed(self, resource_name, error_message):
        """处理更新检查失败"""
        self._restore_check_button(resource_name)
        QMessageBox.warning(self, "检查更新失败", f"{resource_name}: {error_message}")

    def _restore_check_button(self, resource_name):
        """在临时状态显示后恢复检查按钮"""
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource_name:
                resource = next((r for r in global_config.get_all_resource_configs()
                                 if r.resource_name == resource_name), None)

                if resource:
                    check_btn = QPushButton("检查更新")
                    check_btn.setObjectName("check_btn")
                    check_btn.setFixedHeight(30)
                    check_btn.clicked.connect(lambda checked, r=resource: self.check_resource_update(r))
                    self.resources_table.setCellWidget(row, 4, check_btn)
                break

    def start_update(self, resource, url, version, update_type):
        """开始下载更新"""
        # 存储临时属性以便稍后在更新过程中使用
        resource.temp_version = version
        resource.temp_update_type = update_type

        # 创建临时目录
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 添加到下载队列
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(resource.resource_name))
        self.queue_table.setRowHeight(row, 45)

        # 添加进度条
        progress_bar = QProgressBar()
        progress_bar.setObjectName("downloadProgressBar")
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        self.queue_table.setCellWidget(row, 1, progress_bar)

        # 添加速度标签
        speed_label = QLabel("等待中...")
        speed_label.setObjectName("speedLabel")
        self.queue_table.setCellWidget(row, 2, speed_label)

        # 添加取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setFixedHeight(30)
        self.queue_table.setCellWidget(row, 3, cancel_btn)

        # 更新资源表格按钮
        for i in range(self.resources_table.rowCount()):
            item = self.resources_table.item(i, 0)
            if item and item.text() == resource.resource_name:
                # 在按钮文本中显示更新类型
                update_type_display = "增量" if update_type == "incremental" else "完整"
                downloading_btn = QPushButton(f"下载{update_type_display}更新...")
                downloading_btn.setObjectName("downloading_btn")
                downloading_btn.setFixedHeight(30)
                downloading_btn.setEnabled(False)
                self.resources_table.setCellWidget(i, 4, downloading_btn)
                break

        # 创建下载线程
        thread = UpdateDownloader(resource.resource_name, url, temp_dir, resource=resource, version=version)

        # 连接信号
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_resource_download_completed)
        thread.download_failed.connect(self._handle_resource_download_failed)

        # 连接取消按钮
        cancel_btn.clicked.connect(thread.cancel)

        # 启动线程
        self.threads.append(thread)
        thread.start()

    def check_all_updates(self):
        """检查所有资源的更新"""
        self.update_all_button.setText("正在检查更新...")
        self.update_all_button.setEnabled(False)
        self.update_all_button.setObjectName("downloading_btn")

        # 获取所有资源
        resources = global_config.get_all_resource_configs()

        # 过滤具有更新源的资源
        resources_with_update = [r for r in resources if r.resource_update_service_id or r.resource_rep_url]

        if not resources_with_update:
            self.update_all_button.setText("一键检查所有更新")
            self.update_all_button.setObjectName("update_all_button")
            self.update_all_button.setEnabled(True)

            # 显示没有具有更新源的资源的消息框
            QMessageBox.information(self, "检查更新", "没有找到配置了更新源的资源")
            return

        # 创建检查线程
        thread = UpdateChecker(resources_with_update)
        thread.update_found.connect(self._handle_update_found)
        thread.check_completed.connect(self._handle_batch_check_completed)

        # 启动线程
        self.threads.append(thread)
        thread.start()

    def _handle_batch_check_completed(self, total_checked, updates_found):
        """处理批量更新检查完成"""
        self.update_all_button.setEnabled(True)

        if updates_found == 0:
            # 未找到更新
            self.update_all_button.setText("一键检查所有更新")
            self.update_all_button.setObjectName("update_all_button")
            QMessageBox.information(self, "检查更新", f"已检查 {total_checked} 个资源，所有资源均为最新版本。")
        else:
            # 找到更新，更改按钮为更新所有
            self.update_all_button.setText(f"一键更新 ({updates_found})")
            self.update_all_button.setObjectName("update_all_btn_updates_available")
            self.update_all_button.clicked.disconnect()
            self.update_all_button.clicked.connect(self._update_all_resources)

    def _update_all_resources(self):
        """更新所有具有可用更新的资源"""
        # 收集所有需要更新的资源
        self.pending_updates = []

        for row in range(self.resources_table.rowCount()):
            update_btn = self.resources_table.cellWidget(row, 4)
            if update_btn and isinstance(update_btn, QPushButton) and "更新" in update_btn.text():
                self.pending_updates.append(update_btn)

        # 依次触发更新
        if self.pending_updates:
            self.pending_updates[0].click()

    def _check_and_update_next(self):
        """检查并更新下一个待处理的资源"""
        if self.pending_updates and len(self.pending_updates) > 1:
            self.pending_updates.pop(0)
            self.pending_updates[0].click()