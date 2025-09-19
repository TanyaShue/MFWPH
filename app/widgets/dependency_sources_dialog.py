
import json
import requests
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QScrollArea, QWidget, QFrame, QGridLayout, QPushButton, QHBoxLayout,
    QTabWidget, QDialogButtonBox, QMessageBox, QInputDialog, QAbstractItemView,
    QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon

from app.utils.notification_manager import notification_manager


class ConnectionTestWorker(QThread):
    """后台线程，用于测试URL连通性，避免UI冻结"""
    result_ready = Signal(QWidget, bool, str)

    def __init__(self, item_widget, url, parent=None):
        super().__init__(parent)
        self.item_widget = item_widget
        self.url = url

    def run(self):
        try:
            response = requests.head(self.url, timeout=5, allow_redirects=True)
            if 200 <= response.status_code < 300:
                self.result_ready.emit(self.item_widget, True, f"连接成功 (状态码: {response.status_code})")
            else:
                self.result_ready.emit(self.item_widget, False, f"连接失败 (状态码: {response.status_code})")
        except requests.exceptions.RequestException as e:
            self.result_ready.emit(self.item_widget, False, f"连接异常: {e.__class__.__name__}")


class StatusListItemWidget(QWidget):
    """自定义列表项Widget，支持在右侧显示状态"""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.text_label = QLabel(text)
        self.status_label = QLabel("")
        self.status_label.setFixedWidth(80) # 给状态标签一个固定宽度
        self.status_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.text_label)
        layout.addStretch()
        layout.addWidget(self.status_label)

    def set_status(self, status_type, tooltip=""):
        status_map = {
            "testing": ("测试中...", "#FFA500"),
            "success": ("✅ 连接成功", "#2ECC71"),
            "failure": ("❌ 连接失败", "#E74C3C"),
            "clear": ("", "")
        }
        text, color = status_map.get(status_type, ("", ""))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")
        self.setToolTip(tooltip)


class DependencySourcesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("依赖源设置")
        self.setMinimumSize(800, 700)
        self.setObjectName("dependencyDialog")

        self.json_path = Path("assets/config/python_runtime_config.json")
        self.data = self._load_data()
        self.test_threads = []

        main_layout = QVBoxLayout(self)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setSpacing(20)

        self._create_ui()

        button_box = QDialogButtonBox()
        self.save_button = button_box.addButton("保存", QDialogButtonBox.AcceptRole)
        self.cancel_button = button_box.addButton("取消", QDialogButtonBox.RejectRole)
        self.save_button.setObjectName("primaryButton")
        self.cancel_button.setObjectName("secondaryButton")
        button_box.accepted.connect(self.save_changes)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)

    def _load_data(self):
        if not self.json_path.exists():
            notification_manager.show_error("未找到依赖源配置文件", str(self.json_path))
            return {}
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f: return json.load(f)
        except Exception as e:
            notification_manager.show_error("解析依赖源文件失败", str(e)); return {}

    def _create_ui(self):
        if not self.data: self.content_layout.addWidget(QLabel("无法加载依赖源数据。")); return
        self.fallback_versions_edits = self._create_kv_section("Fallback Versions", self.data.get("fallback_versions", {}))
        self.python_sources_tabs = self._create_nested_list_section("Python Download Sources", self.data.get("python_download_sources", {}))
        self.pip_sources_list = self._create_list_section("Pip Sources", self.data.get("pip_sources", []), True)
        self.get_pip_sources_list = self._create_list_section("Get-Pip Sources", self.data.get("get_pip_sources", []), True)

    def _create_section_frame(self, title):
        frame = QFrame(); frame.setObjectName("sectionFrame"); layout = QVBoxLayout(frame)
        title_label = QLabel(title); title_label.setObjectName("sectionTitle"); layout.addWidget(title_label)
        return frame, layout

    def _create_kv_section(self, title, data):
        frame, layout = self._create_section_frame(title)
        form_layout = QGridLayout(); layout.addLayout(form_layout); edits = {}
        for i, (key, value) in enumerate(data.items()):
            form_layout.addWidget(QLabel(key), i, 0); line_edit = QLineEdit(str(value));
            form_layout.addWidget(line_edit, i, 1); edits[key] = line_edit
        self.content_layout.addWidget(frame); return edits

    def _add_status_item(self, list_widget, text):
        item = QListWidgetItem(list_widget)
        widget = StatusListItemWidget(text)
        item.setSizeHint(widget.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, widget)

    def _create_list_section(self, title, data, is_testable=False):
        frame, layout = self._create_section_frame(title)
        list_widget = QListWidget(); list_widget.setMinimumHeight(150)
        list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        for text in data: self._add_status_item(list_widget, text)
        list_widget.itemDoubleClicked.connect(self.edit_list_item)
        layout.addWidget(list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加"); add_btn.setObjectName("secondaryButton")
        remove_btn = QPushButton("删除"); remove_btn.setObjectName("secondaryButton")
        btn_layout.addWidget(add_btn); btn_layout.addWidget(remove_btn); btn_layout.addStretch()

        if is_testable:
            test_btn = QPushButton("测试选中"); test_btn.setObjectName("secondaryButton"); test_btn.setEnabled(False)
            test_all_btn = QPushButton("一键测试"); test_all_btn.setObjectName("primaryButton")
            btn_layout.addWidget(test_btn); btn_layout.addWidget(test_all_btn)
            list_widget.itemSelectionChanged.connect(lambda: test_btn.setEnabled(True))
            test_btn.clicked.connect(lambda: self.run_connection_test(list_widget, False, False))
            test_all_btn.clicked.connect(lambda: self.run_connection_test(list_widget, False, True))

        layout.addLayout(btn_layout)
        add_btn.clicked.connect(lambda: self.add_list_item(list_widget))
        remove_btn.clicked.connect(lambda: self.remove_list_item(list_widget))
        self.content_layout.addWidget(frame); return list_widget

    def _create_nested_list_section(self, title, data):
        frame, layout = self._create_section_frame(title); tab_widget = QTabWidget(); layout.addWidget(tab_widget)
        for os_key, urls in data.items():
            tab_content = QWidget(); tab_layout = QVBoxLayout(tab_content); list_widget = QListWidget()
            list_widget.setMinimumHeight(200); list_widget.setDragDropMode(QAbstractItemView.InternalMove)
            for url in urls: self._add_status_item(list_widget, url)
            list_widget.itemDoubleClicked.connect(self.edit_list_item); tab_layout.addWidget(list_widget)

            btn_layout = QHBoxLayout()
            add_btn = QPushButton("添加"); add_btn.setObjectName("secondaryButton")
            remove_btn = QPushButton("删除"); remove_btn.setObjectName("secondaryButton")
            test_btn = QPushButton("测试选中"); test_btn.setObjectName("secondaryButton"); test_btn.setEnabled(False)
            test_all_btn = QPushButton("一键测试"); test_all_btn.setObjectName("primaryButton")
            btn_layout.addWidget(add_btn); btn_layout.addWidget(remove_btn); btn_layout.addStretch()
            btn_layout.addWidget(test_btn); btn_layout.addWidget(test_all_btn); tab_layout.addLayout(btn_layout)

            # Corrected lambda to capture the button instance
            list_widget.itemSelectionChanged.connect(lambda btn=test_btn: btn.setEnabled(True))
            add_btn.clicked.connect(lambda checked, lw=list_widget: self.add_list_item(lw))
            remove_btn.clicked.connect(lambda checked, lw=list_widget: self.remove_list_item(lw))
            test_btn.clicked.connect(lambda checked, lw=list_widget: self.run_connection_test(lw, True, False))
            test_all_btn.clicked.connect(lambda checked, lw=list_widget: self.run_connection_test(lw, True, True))
            tab_widget.addTab(tab_content, os_key)
        self.content_layout.addWidget(frame); return tab_widget

    def run_connection_test(self, list_widget, is_python_source, test_all):
        items_to_test = []
        if test_all:
            for i in range(list_widget.count()): items_to_test.append(list_widget.item(i))
        elif list_widget.currentItem():
            items_to_test.append(list_widget.currentItem())

        if not items_to_test: return

        py_version = ""
        if is_python_source:
            py_version = (self.fallback_versions_edits.get("3.11").text() or self.fallback_versions_edits.get("3.12").text())
            if not py_version: notification_manager.show_warning("测试失败", "无法找到可用Python版本号"); return

        for item in items_to_test:
            widget = list_widget.itemWidget(item)
            if not widget: continue
            url = widget.text
            if is_python_source: url = url.replace("{version}", py_version)
            widget.set_status("testing")
            thread = ConnectionTestWorker(widget, url, self)
            thread.result_ready.connect(self.on_test_result)
            self.test_threads.append(thread); thread.start()

    def on_test_result(self, widget, success, message):
        widget.set_status("success" if success else "failure", message)

    def edit_list_item(self, item):
        widget = self.sender().itemWidget(item)
        new_text, ok = QInputDialog.getText(self, "编辑条目", "修改依赖源:", QLineEdit.Normal, widget.text)
        if ok and new_text: widget.text_label.setText(new_text); widget.text = new_text; widget.set_status("clear")

    def add_list_item(self, list_widget):
        new_text, ok = QInputDialog.getText(self, "添加条目", "输入新的依赖源:")
        if ok and new_text: self._add_status_item(list_widget, new_text)

    def remove_list_item(self, list_widget):
        item = list_widget.currentItem()
        if not item: return
        widget = list_widget.itemWidget(item)
        reply = QMessageBox.question(self, "确认删除", f"确定要删除 '{widget.text}' 吗?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes: list_widget.takeItem(list_widget.row(item))

    def save_changes(self):
        try:
            new_data = {}
            new_data["fallback_versions"] = {key: edit.text() for key, edit in self.fallback_versions_edits.items()}
            py_sources = {}
            for i in range(self.python_sources_tabs.count()):
                tab_name = self.python_sources_tabs.tabText(i)
                list_widget = self.python_sources_tabs.widget(i).findChild(QListWidget)
                urls = [list_widget.itemWidget(list_widget.item(j)).text for j in range(list_widget.count())]
                py_sources[tab_name] = urls
            new_data["python_download_sources"] = py_sources
            new_data["pip_sources"] = [self.pip_sources_list.itemWidget(self.pip_sources_list.item(i)).text for i in range(self.pip_sources_list.count())]
            new_data["get_pip_sources"] = [self.get_pip_sources_list.itemWidget(self.get_pip_sources_list.item(i)).text for i in range(self.get_pip_sources_list.count())]

            with open(self.json_path, 'w', encoding='utf-8') as f: json.dump(new_data, f, indent=4, ensure_ascii=False)
            notification_manager.show_success("保存成功", "依赖源配置已更新。"); self.accept()
        except Exception as e: notification_manager.show_error("保存失败", str(e))

    def closeEvent(self, event):
        for thread in self.test_threads: thread.quit(); thread.wait()
        super().closeEvent(event)
