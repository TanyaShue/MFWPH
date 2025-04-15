from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox


class AddResourceDialog(QDialog):
    """Dialog for adding new resources"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("addResourceDialog")
        self.setWindowTitle("添加新资源")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Resource URL field
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("urlEdit")
        self.url_edit.setPlaceholderText("GitHub仓库链接或ZIP文件URL")
        form_layout.addRow("资源链接:", self.url_edit)

        # Resource name field
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("nameEdit")
        self.name_edit.setPlaceholderText("自动提取 (可选)")
        form_layout.addRow("资源名称:", self.name_edit)

        # Description field
        self.desc_edit = QTextEdit()
        self.desc_edit.setObjectName("descEdit")
        self.desc_edit.setPlaceholderText("资源描述 (可选)")
        self.desc_edit.setMaximumHeight(100)
        form_layout.addRow("描述:", self.desc_edit)

        layout.addLayout(form_layout)

        # Add buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.setObjectName("buttonBox")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        # Connect validation
        self.url_edit.textChanged.connect(self.validate_input)

        layout.addWidget(self.button_box)

    def validate_input(self):
        """Enable OK button only if URL is valid"""
        url = self.url_edit.text().strip()
        valid = url.startswith(("http://", "https://")) and (
                "github.com" in url or url.endswith(".zip")
        )
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def get_data(self):
        """Return the dialog data"""
        return {
            "url": self.url_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip()
        }

