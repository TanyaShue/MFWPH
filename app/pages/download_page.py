import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QTableWidget,
                               QTableWidgetItem, QPushButton, QHeaderView, QHBoxLayout,
                               QProgressBar, QMessageBox, QSizePolicy, QDialog, QFormLayout,
                               QLineEdit, QTextEdit, QDialogButtonBox, QComboBox)

from app.models.config.global_config import global_config
from app.utils.update import UpdateCheckThread, DownloadThread
from app.widgets.add_resource_dialog import AddResourceDialog


class DownloadPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadPage")
        self.threads = []  # Store thread references
        self._init_ui()
        self.load_resources()

    def _init_ui(self):
        """Initialize UI elements"""
        layout = QVBoxLayout(self)

        # Page title
        title_label = QLabel("资源下载")
        title_label.setObjectName("pageTitle")
        layout.addWidget(title_label)

        # Main frame
        main_frame = QFrame()
        main_frame.setObjectName("mainFrame")
        main_frame.setFrameShape(QFrame.StyledPanel)
        main_layout = QVBoxLayout(main_frame)

        # Top buttons row
        top_buttons_layout = QHBoxLayout()
        top_buttons_layout.setObjectName("topButtonsLayout")

        # Add resource button
        self.add_resource_button = QPushButton("添加新资源")
        self.add_resource_button.setObjectName("add_resource_button")
        self.add_resource_button.setIcon(QIcon("assets/icons/add.png"))
        self.add_resource_button.clicked.connect(self.show_add_resource_dialog)
        top_buttons_layout.addWidget(self.add_resource_button)

        top_buttons_layout.addStretch()

        # Update all button
        self.update_all_button = QPushButton("一键检查所有更新")
        self.update_all_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.update_all_button.setObjectName("update_all_button")
        self.update_all_button.clicked.connect(self.check_all_updates)
        top_buttons_layout.addWidget(self.update_all_button)

        main_layout.addLayout(top_buttons_layout)

        # Resources table
        main_layout.addWidget(self._create_section_label("可用资源"))
        self.resources_table = self._create_table(["资源名称", "版本", "作者", "描述", "操作"])
        self.resources_table.setObjectName("resourcesTable")
        main_layout.addWidget(self.resources_table)

        # Download queue table
        main_layout.addWidget(self._create_section_label("下载队列"))
        self.queue_table = self._create_table(["资源名称", "进度", "速度", "操作"])
        self.queue_table.setObjectName("queueTable")
        main_layout.addWidget(self.queue_table)

        layout.addWidget(main_frame)

    def _create_section_label(self, text):
        """Create a section label with consistent styling"""
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _create_table(self, headers):
        """Create a table with consistent styling"""
        table = QTableWidget(0, len(headers))
        table.setObjectName("baseTable")
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        # Make table read-only
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        return table

    def show_add_resource_dialog(self):
        """Show dialog to add a new resource"""
        dialog = AddResourceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.add_new_resource(dialog.get_data())

    def add_new_resource(self, data):
        """Add a new resource"""
        # Show processing state
        self.add_resource_button.setEnabled(False)
        self.add_resource_button.setText("添加中...")

        # Create temp directory
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Process URL
        url = data["url"]
        if "github.com" in url and not url.endswith(".zip"):
            self._process_github_repo(url, data)
        else:
            self._download_resource(url, data)

    def _process_github_repo(self, repo_url, data):
        """Process GitHub repository URL"""
        try:
            # Parse GitHub URL
            parts = repo_url.split('github.com/')[1].split('/')
            if len(parts) < 2:
                self._show_add_error("GitHub地址格式不正确")
                return

            owner, repo = parts[0], parts[1]
            if repo.endswith('.git'):
                repo = repo[:-4]

            # Get latest release info
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            response = requests.get(api_url)

            if response.status_code != 200:
                self._show_add_error(f"API返回错误 ({response.status_code})")
                return

            release_info = response.json()
            latest_version = release_info.get('tag_name', '').lstrip('v')

            # Use repo name if name not provided
            if not data["name"]:
                data["name"] = repo

            # Find ZIP asset
            download_url = None
            for asset in release_info.get('assets', []):
                if asset.get('name', '').endswith('.zip'):
                    download_url = asset.get('browser_download_url')
                    break

            if not download_url:
                self._show_add_error("找不到可下载的资源包")
                return

            # Download ZIP
            self._download_resource(download_url, data, latest_version)

        except Exception as e:
            self._show_add_error(str(e))

    def _download_resource(self, url, data, version=None):
        """Download a resource file and add to queue"""
        # Prepare resource name
        resource_name = data["name"] if data["name"] else "新资源"

        # Add to download queue
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(resource_name))
        self.queue_table.setRowHeight(row, 45)

        # Add progress bar
        progress_bar = QProgressBar()
        progress_bar.setObjectName("downloadProgressBar")
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        self.queue_table.setCellWidget(row, 1, progress_bar)

        # Add speed label
        speed_label = QLabel("等待中...")
        speed_label.setObjectName("speedLabel")
        self.queue_table.setCellWidget(row, 2, speed_label)

        # Add cancel button
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setFixedHeight(30)
        self.queue_table.setCellWidget(row, 3, cancel_btn)

        # Create download thread
        temp_dir = Path("assets/temp")
        thread = DownloadThread(resource_name, url, temp_dir, data, version=version)

        # Connect signals
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_resource_download_completed)
        thread.download_failed.connect(self._handle_resource_download_failed)

        # Connect cancel button
        cancel_btn.clicked.connect(thread.cancel)

        # Start thread
        self.threads.append(thread)
        thread.start()

    def _update_download_progress(self, resource_name, progress, speed):
        """Update download progress in queue table"""
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
        """Handle completed resource download"""
        # Remove from queue
        self._remove_from_queue(resource_name)

        try:
            # Install the resource
            if isinstance(data, dict):
                # New resource
                self._install_new_resource(resource_name, file_path, data)
            else:
                # Resource update
                self._install_update(data, file_path)

            # Reload resources and restore button
            self.load_resources()
            self._restore_add_button()

            # Show success message
            QMessageBox.information(self, "下载完成", f"资源 {resource_name} 已成功添加/更新")

        except Exception as e:
            self._show_error(resource_name, str(e))

    def _handle_resource_download_failed(self, resource_name, error):
        """Handle failed resource download"""
        self._remove_from_queue(resource_name)
        self._restore_add_button()
        QMessageBox.warning(self, "下载失败", f"资源 {resource_name} 下载失败:\n{error}")

    def _remove_from_queue(self, resource_name):
        """Remove a resource from the download queue"""
        for row in range(self.queue_table.rowCount()):
            item = self.queue_table.item(row, 0)
            if item and item.text() == resource_name:
                self.queue_table.removeRow(row)
                break

    def _restore_add_button(self):
        """Restore the add resource button state"""
        self.add_resource_button.setEnabled(True)
        self.add_resource_button.setText("添加新资源")

    def _show_add_error(self, error):
        """Display error when adding resource"""
        self._restore_add_button()
        QMessageBox.warning(self, "添加失败", f"添加资源失败:\n{error}")

    def _show_error(self, resource_name, error):
        """Display generic error message"""
        QMessageBox.warning(self, "操作失败", f"资源 {resource_name} 操作失败: {error}")

    def _install_new_resource(self, resource_name, file_path, data):
        """Install a newly downloaded resource"""
        with tempfile.TemporaryDirectory() as extract_dir:
            # Extract ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find or create resource config
            resource_dir, resource_config_path = self._find_or_create_config(extract_dir, data, resource_name)

            # Create target directory
            target_dir = Path(f"assets/resource/{resource_name.lower().replace(' ', '_')}")
            if target_dir.exists():
                shutil.rmtree(target_dir)

            # Copy files to target directory
            shutil.copytree(resource_dir, target_dir)

            # Load new resource config
            global_config.load_resource_config(str(target_dir / "resource_config.json"))

    def _find_or_create_config(self, extract_dir, data, resource_name):
        """Find existing config or create a new one"""
        # Try to find existing config
        for root, dirs, files in os.walk(extract_dir):
            if "resource_config.json" in files:
                return root, os.path.join(root, "resource_config.json")

        # Create new config
        main_dir = extract_dir
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                main_dir = item_path
                break

        # Create resource config
        resource_config = {
            "resource_name": data["name"] or resource_name,
            "resource_version": data.get("version", "1.0.0"),
            "resource_author": data.get("author", "未知"),
            "resource_description": data["description"] or "从外部源添加的资源",
            "resource_update_service_id": data["url"] if "github.com" in data["url"] else ""
        }

        # Write config file
        resource_config_path = os.path.join(main_dir, "resource_config.json")
        with open(resource_config_path, 'w', encoding='utf-8') as f:
            json.dump(resource_config, f, ensure_ascii=False, indent=4)

        return main_dir, resource_config_path

    def _install_update(self, resource, file_path):
        """Install an update for an existing resource"""
        # 获取传入的新版本号（从start_update方法传递过来的version参数）
        new_version = resource.temp_version if hasattr(resource, 'temp_version') else None

        with tempfile.TemporaryDirectory() as extract_dir:
            # Extract ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find resource directory
            resource_dir = None
            resource_config_path = None

            for root, dirs, files in os.walk(extract_dir):
                if "resource_config.json" in files:
                    resource_config_path = os.path.join(root, "resource_config.json")
                    resource_dir = root
                    break

            if not resource_config_path:
                raise ValueError("更新包中未找到resource_config.json文件")

            # Get original resource directory
            original_resource_dir = Path(resource.source_file).parent

            # Create selective backup of files that will be updated
            self._create_selective_backup(resource, resource_dir, original_resource_dir)

            # Selectively update files instead of replacing entire directory
            self._selective_update(resource_dir, original_resource_dir)

            # Reload resource config
            global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))

            # Make sure the version is updated in global_config
            for r in global_config.get_all_resource_configs():
                if r.resource_name == resource.resource_name and new_version:
                    r.resource_version = new_version
                    break

            # Save all configs
            global_config.save_all_configs()

    def _create_selective_backup(self, resource, update_dir, original_dir):
        """Create a backup of only the files that will be updated"""
        # Create history directory
        history_dir = Path("assets/history")
        history_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamped backup filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{resource.resource_name}_{resource.resource_version}_{timestamp}.zip"
        backup_path = history_dir / backup_filename

        # Only backup files that exist in the update package
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(update_dir):
                for file in files:
                    # Get relative path from update directory
                    relative_path = os.path.relpath(os.path.join(root, file), update_dir)

                    # Check if this file exists in original directory
                    original_file_path = original_dir / relative_path
                    if original_file_path.exists():
                        # Add to backup with proper relative path
                        arcname = f"{resource.resource_name}/{relative_path}"
                        zipf.write(original_file_path, arcname)

    def _selective_update(self, source_dir, target_dir):
        """Selectively update files instead of replacing entire directory"""
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        for root, dirs, files in os.walk(source_dir):
            # Get relative path from source directory
            relative_path = os.path.relpath(root, source_dir)

            # Create directories in target if they don't exist
            for dir_name in dirs:
                dir_path = target_dir / relative_path / dir_name
                dir_path.mkdir(parents=True, exist_ok=True)

            # Copy/replace files
            for file_name in files:
                source_file = Path(root) / file_name
                target_file = target_dir / relative_path / file_name

                # Delete existing file if it exists
                if target_file.exists():
                    target_file.unlink()

                # Create parent directory if it doesn't exist
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(source_file, target_file)

    def load_resources(self):
        """Load resources from global config into the table"""
        resources = global_config.get_all_resource_configs()

        # Clear table
        self.resources_table.setRowCount(0)

        # Add resources to table
        for i, resource in enumerate(resources):
            self.resources_table.insertRow(i)
            self.resources_table.setItem(i, 0, QTableWidgetItem(resource.resource_name))
            self.resources_table.setItem(i, 1, QTableWidgetItem(resource.resource_version))
            self.resources_table.setItem(i, 2, QTableWidgetItem(resource.resource_author))
            self.resources_table.setItem(i, 3, QTableWidgetItem(resource.resource_description))

            # Add check update button
            check_btn = QPushButton("检查更新")
            check_btn.setObjectName("check_btn")
            check_btn.clicked.connect(lambda checked, r=resource: self.check_resource_update(r))
            self.resources_table.setCellWidget(i, 4, check_btn)

            # Set row height
            self.resources_table.setRowHeight(i, 45)

    def check_resource_update(self, resource):
        """Check for updates for a single resource"""
        # Find button for this resource
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource.resource_name:
                check_btn = self.resources_table.cellWidget(row, 4)

                # Handle resource without update source
                if not resource.resource_rep_url and not resource.resource_update_service_id:
                    no_update_source_btn = QPushButton("无更新源")
                    no_update_source_btn.setObjectName("no_update_source_btn")
                    no_update_source_btn.setEnabled(False)
                    self.resources_table.setCellWidget(row, 4, no_update_source_btn)
                    # Restore button after delay
                    QTimer.singleShot(3000, lambda: self._restore_check_button(resource.resource_name))
                    return

                # Update button state for normal check
                check_btn.setText("检查中...")
                check_btn.setEnabled(False)
                check_btn.setObjectName("downloading_btn")
                self.resources_table.setCellWidget(row, 4, check_btn)
                break

        # Create check thread
        thread = UpdateCheckThread(resource, single_mode=True)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)

        # Start thread
        self.threads.append(thread)
        thread.start()

    def _handle_update_found(self, resource_name, latest_version, current_version, download_url):
        """Handle update found for a resource"""
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource_name:
                # Update version display
                self.resources_table.item(row, 1).setText(f"{current_version} → {latest_version}")

                # Replace button with update button
                resource = next((r for r in global_config.get_all_resource_configs()
                                 if r.resource_name == resource_name), None)

                if resource:
                    update_btn = QPushButton("更新")
                    update_btn.setObjectName("update_btn")
                    update_btn.setFixedHeight(30)
                    update_btn.clicked.connect(
                        lambda checked, r=resource, url=download_url, v=latest_version:
                        self.start_update(r, url, v)
                    )
                    self.resources_table.setCellWidget(row, 4, update_btn)
                break

    def _handle_update_not_found(self, resource_name):
        """Handle no update found for a resource"""
        for row in range(self.resources_table.rowCount()):
            item = self.resources_table.item(row, 0)
            if item and item.text() == resource_name:
                # Show already latest version
                latest_version_btn = QPushButton("已是最新版本")
                latest_version_btn.setObjectName("latest_version_btn")
                latest_version_btn.setFixedHeight(30)
                latest_version_btn.setEnabled(False)
                self.resources_table.setCellWidget(row, 4, latest_version_btn)

                # Restore button after delay
                QTimer.singleShot(3000, lambda: self._restore_check_button(resource_name))
                break

    def _handle_check_failed(self, resource_name, error_message):
        """Handle update check failure"""
        self._restore_check_button(resource_name)
        QMessageBox.warning(self, "检查更新失败", f"{resource_name}: {error_message}")

    def _restore_check_button(self, resource_name):
        """Restore check button after temporary status display"""
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

    def start_update(self, resource, url, version):
        """Start downloading an update"""
        # Create temp directory
        resource.temp_version = version
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Add to download queue
        row = self.queue_table.rowCount()
        self.queue_table.insertRow(row)
        self.queue_table.setItem(row, 0, QTableWidgetItem(resource.resource_name))
        self.queue_table.setRowHeight(row, 45)

        # Add progress bar
        progress_bar = QProgressBar()
        progress_bar.setObjectName("downloadProgressBar")
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        self.queue_table.setCellWidget(row, 1, progress_bar)

        # Add speed label
        speed_label = QLabel("等待中...")
        speed_label.setObjectName("speedLabel")
        self.queue_table.setCellWidget(row, 2, speed_label)

        # Add cancel button
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.setFixedHeight(30)
        self.queue_table.setCellWidget(row, 3, cancel_btn)

        # Update resource table button
        for i in range(self.resources_table.rowCount()):
            item = self.resources_table.item(i, 0)
            if item and item.text() == resource.resource_name:
                downloading_btn = QPushButton("下载中...")
                downloading_btn.setObjectName("downloading_btn")
                downloading_btn.setFixedHeight(30)
                downloading_btn.setEnabled(False)
                self.resources_table.setCellWidget(i, 4, downloading_btn)
                break

        # Create download thread
        thread = DownloadThread(resource.resource_name, url, temp_dir, resource=resource, version=version)

        # Connect signals
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_resource_download_completed)
        thread.download_failed.connect(self._handle_resource_download_failed)

        # Connect cancel button
        cancel_btn.clicked.connect(thread.cancel)

        # Start thread
        self.threads.append(thread)
        thread.start()

    def check_all_updates(self):
        """Check updates for all resources"""
        self.update_all_button.setText("正在检查更新...")
        self.update_all_button.setEnabled(False)
        self.update_all_button.setObjectName("downloading_btn")

        # Get all resources
        resources = global_config.get_all_resource_configs()

        # Filter resources with update sources
        resources_with_update = [r for r in resources if r.resource_update_service_id]

        if not resources_with_update:
            self.update_all_button.setText("一键检查所有更新")
            self.update_all_button.setObjectName("update_all_button")
            self.update_all_button.setEnabled(True)

            # Show message box for no resources with update sources
            QMessageBox.information(self, "检查更新", "没有找到配置了更新源的资源")
            return

        # Create check thread
        thread = UpdateCheckThread(resources_with_update)
        thread.update_found.connect(self._handle_update_found)
        thread.check_completed.connect(self._handle_batch_check_completed)

        # Start thread
        self.threads.append(thread)
        thread.start()

    def _handle_batch_check_completed(self, total_checked, updates_found):
        """Handle completion of batch update check"""
        self.update_all_button.setEnabled(True)

        if updates_found == 0:
            # No updates found
            self.update_all_button.setText("一键检查所有更新")
            self.update_all_button.setObjectName("update_all_button")
            QMessageBox.information(self, "检查更新", f"已检查 {total_checked} 个资源，所有资源均为最新版本。")
        else:
            # Updates found, change button to update all
            self.update_all_button.setText(f"一键更新 ({updates_found})")
            self.update_all_button.setObjectName("update_all_btn_updates_available")
            self.update_all_button.clicked.disconnect()
            self.update_all_button.clicked.connect(self._update_all_resources)

    def _update_all_resources(self):
        """Update all resources with available updates"""
        for row in range(self.resources_table.rowCount()):
            update_btn = self.resources_table.cellWidget(row, 4)
            if update_btn and isinstance(update_btn, QPushButton) and update_btn.text() == "更新":
                update_btn.click()