import os
import shutil
import json
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit,
                               QDialogButtonBox, QComboBox, QStackedWidget,
                               QWidget, QPushButton, QHBoxLayout, QFileDialog,
                               QMessageBox)


class AddResourceDialog(QDialog):
    """Dialog for adding new resources"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("addResourceDialog")
        self.setWindowTitle("添加新资源")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Add mode selection dropdown
        mode_layout = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("modeCombo")
        self.mode_combo.addItem("通过URL导入", "url")
        self.mode_combo.addItem("手动添加", "manual")
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        mode_layout.addRow("导入方式:", self.mode_combo)
        layout.addLayout(mode_layout)

        # Create stacked widget for different input modes
        self.stacked_widget = QStackedWidget()

        # URL import page
        self.url_page = self.create_url_page()
        self.stacked_widget.addWidget(self.url_page)

        # Manual import page
        self.manual_page = self.create_manual_page()
        self.stacked_widget.addWidget(self.manual_page)

        layout.addWidget(self.stacked_widget)

        # Add buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.setObjectName("buttonBox")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        layout.addWidget(self.button_box)

        # Set default mode and validation
        self.on_mode_changed(0)  # Default to URL import

    def create_url_page(self):
        """Create URL import page"""
        page = QWidget()
        layout = QFormLayout(page)

        # Resource URL field
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("urlEdit")
        self.url_edit.setPlaceholderText("GitHub仓库链接或ZIP文件URL")
        self.url_edit.textChanged.connect(self.validate_url_input)
        layout.addRow("资源链接:", self.url_edit)

        return page

    def create_manual_page(self):
        """Create manual import page"""
        page = QWidget()
        layout = QFormLayout(page)

        # Resource path field
        resource_layout = QHBoxLayout()
        self.resource_path_edit = QLineEdit()
        self.resource_path_edit.setObjectName("resourcePathEdit")
        self.resource_path_edit.setPlaceholderText("选择包含model、image、pipeline的文件夹")
        self.resource_path_edit.textChanged.connect(self.validate_manual_input)
        resource_browse_btn = QPushButton("浏览...")
        resource_browse_btn.clicked.connect(self.browse_resource_path)
        resource_layout.addWidget(self.resource_path_edit)
        resource_layout.addWidget(resource_browse_btn)
        layout.addRow("资源路径:", resource_layout)

        # Agent path field
        agent_layout = QHBoxLayout()
        self.agent_path_edit = QLineEdit()
        self.agent_path_edit.setObjectName("agentPathEdit")
        self.agent_path_edit.setPlaceholderText("选择包含.py文件的agent文件夹")
        self.agent_path_edit.textChanged.connect(self.validate_manual_input)
        agent_browse_btn = QPushButton("浏览...")
        agent_browse_btn.clicked.connect(self.browse_agent_path)
        agent_layout.addWidget(self.agent_path_edit)
        agent_layout.addWidget(agent_browse_btn)
        layout.addRow("Agent路径:", agent_layout)

        # Config file field (optional)
        config_layout = QHBoxLayout()
        self.config_path_edit = QLineEdit()
        self.config_path_edit.setObjectName("configPathEdit")
        self.config_path_edit.setPlaceholderText("选择resource_config.json文件 (可选)")
        config_browse_btn = QPushButton("浏览...")
        config_browse_btn.clicked.connect(self.browse_config_path)
        config_layout.addWidget(self.config_path_edit)
        config_layout.addWidget(config_browse_btn)
        layout.addRow("配置文件:", config_layout)

        return page

    def on_mode_changed(self, index):
        """Handle mode change"""
        self.stacked_widget.setCurrentIndex(index)
        if index == 0:  # URL mode
            self.validate_url_input()
        else:  # Manual mode
            self.validate_manual_input()

    def browse_resource_path(self):
        """Browse for resource directory"""
        path = QFileDialog.getExistingDirectory(
            self, "选择资源文件夹", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if path:
            self.resource_path_edit.setText(path)

    def browse_agent_path(self):
        """Browse for agent directory"""
        path = QFileDialog.getExistingDirectory(
            self, "选择Agent文件夹", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        if path:
            self.agent_path_edit.setText(path)

    def browse_config_path(self):
        """Browse for config file"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择配置文件", "",
            "JSON文件 (*.json);;所有文件 (*)"
        )
        if path:
            self.config_path_edit.setText(path)

    def validate_url_input(self):
        """Validate URL input"""
        url = self.url_edit.text().strip()
        valid = url.startswith(("http://", "https://")) and (
                "github.com" in url or url.endswith(".zip")
        )
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def validate_manual_input(self):
        """Validate manual input"""
        resource_path = self.resource_path_edit.text().strip()
        agent_path = self.agent_path_edit.text().strip()

        valid = (os.path.isdir(resource_path) and
                 os.path.isdir(agent_path) and
                 self.check_agent_folder(agent_path))

        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def check_agent_folder(self, path):
        """Check if agent folder contains .py files"""
        if not os.path.isdir(path):
            return False

        for file in os.listdir(path):
            if file.endswith('.py'):
                return True
        return False

    def get_resource_name_from_config(self, config_path):
        """Get resource name from config file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('name', '')
        except:
            return ''

    def generate_unique_resource_name(self, base_name="新建资源"):
        """Generate unique resource name"""
        assets_dir = Path("assets/resource")
        assets_dir.mkdir(parents=True, exist_ok=True)

        counter = 1
        while True:
            name = f"{base_name}_{counter}"
            if not (assets_dir / name).exists():
                return name
            counter += 1

    def copy_resources(self, resource_path, agent_path, config_path, target_dir):
        """Copy resources to target directory"""
        try:
            target_path = Path(target_dir)
            target_path.mkdir(parents=True, exist_ok=True)

            # Copy resource directory contents
            resource_src = Path(resource_path)
            for item in resource_src.iterdir():
                if item.is_dir():
                    shutil.copytree(item, target_path / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target_path)

            # Copy agent directory
            agent_src = Path(agent_path)
            agent_target = target_path / "agent"
            if agent_target.exists():
                shutil.rmtree(agent_target)
            shutil.copytree(agent_src, agent_target)

            # Copy config file if provided
            if config_path and os.path.isfile(config_path):
                shutil.copy2(config_path, target_path / "resource_config.json")

            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制文件时发生错误: {str(e)}")
            return False

    def get_data(self):
        """Return the dialog data"""
        mode = self.mode_combo.currentData()

        if mode == "url":
            return {
                "mode": "url",
                "url": self.url_edit.text().strip()
            }
        else:  # manual mode
            resource_path = self.resource_path_edit.text().strip()
            agent_path = self.agent_path_edit.text().strip()
            config_path = self.config_path_edit.text().strip()

            # Determine resource name
            resource_name = ""
            if config_path and os.path.isfile(config_path):
                resource_name = self.get_resource_name_from_config(config_path)

            if not resource_name:
                resource_name = self.generate_unique_resource_name()

            # Create target directory path
            target_dir = f"assets/resource/{resource_name}"

            # Copy resources
            if self.copy_resources(resource_path, agent_path, config_path, target_dir):
                return {
                    "mode": "manual",
                    "resource_path": resource_path,
                    "agent_path": agent_path,
                    "config_path": config_path,
                    "resource_name": resource_name,
                    "target_dir": target_dir
                }
            else:
                return None