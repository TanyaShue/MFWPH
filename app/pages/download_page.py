# download_page.py

from pathlib import Path

from PySide6.QtCore import (QTimer, QCoreApplication, Qt, Signal, Property, QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import QIcon, QPainter, QColor, QPen, QPixmap, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QFrame, QPushButton,
                               QHBoxLayout, QMessageBox, QSizePolicy,
                               QDialog, QStackedWidget,
                               QScrollArea, QGraphicsDropShadowEffect,
                               QStyleOption, QStyle, QComboBox)  # Import QComboBox

from app.components.circular_progress_bar import CircularProgressBar
from app.models.config.global_config import global_config
from app.utils.notification_manager import notification_manager
from app.utils.update_check import UpdateChecker, UpdateDownloader, GitInstallerThread
from app.utils.update_install import UpdateInstaller
from app.widgets.add_resource_dialog import AddResourceDialog


class AnimatedIndicator(QWidget):
    """一个简单的动画指示器，用于显示更新状态"""

    def __init__(self, color="#10b981"):
        super().__init__()
        self.setFixedSize(8, 8)
        self._color = QColor(color)
        self._animation = QPropertyAnimation(self, b"opacity", self)
        self._animation.setDuration(1000)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        # BUG FIX: Initialize the _opacity attribute here.
        self._opacity = 0.0

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
    """自定义资源列表项（简化版）"""
    clicked = Signal(object)  # 发送resource对象

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

        # Left Icon
        self.icon_label = QLabel()
        self.icon_label.setObjectName("resourceItemIcon")
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setScaledContents(True)
        self._set_icon(f"assets/resource/{self.resource.resource_id}/{self.resource.resource_icon}")
        layout.addWidget(self.icon_label)

        # Middle Info
        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(4)

        self.name_label = QLabel(self.resource.resource_name)
        self.name_label.setObjectName("resourceItemName")
        self.version_label = QLabel(f"Version {self.resource.resource_version}")
        self.version_label.setObjectName("resourceItemVersion")

        info_layout.addWidget(self.name_label)
        info_layout.addWidget(self.version_label)
        layout.addWidget(info_container, 1)

        # Update Indicator
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
    """资源详情视图（集成操作）"""
    check_update_clicked = Signal(object)
    start_update_clicked = Signal(object, object)  # resource, item

    def __init__(self):
        super().__init__()
        self.current_resource = None
        self.update_info = None
        self._init_ui()
        # NEW: Connect the combobox signal
        self.source_combo.currentTextChanged.connect(self._on_source_changed)

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

        # Header
        header = self._create_header()
        layout.addWidget(header)

        # Action Bar
        self.action_bar = self._create_action_bar()
        layout.addWidget(self.action_bar)

        # Description
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
        self.title_label = QLabel("Select a Resource")
        self.title_label.setObjectName("detailTitle")
        self.author_label = QLabel("By Author")
        self.author_label.setObjectName("detailAuthor")
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.author_label)

        # NEW: Create update source dropdown
        source_layout = QVBoxLayout()
        source_layout.setSpacing(4)
        source_label = QLabel("Update Source")
        source_label.setObjectName("sourceLabel")
        self.source_combo = QComboBox()
        self.source_combo.setObjectName("sourceCombo")
        self.source_combo.addItems(["GitHub", "MirrorChyan"])
        self.source_combo.setCursor(Qt.PointingHandCursor)
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_combo)

        layout.addWidget(self.large_icon)
        layout.addLayout(info_layout, 1)
        layout.addStretch()
        layout.addLayout(source_layout)
        return header_widget

    def _create_action_bar(self):
        bar = QFrame()
        bar.setObjectName("detailActionBar")
        bar.setFixedHeight(80)

        self.action_layout = QHBoxLayout(bar)
        self.action_layout.setContentsMargins(24, 0, 24, 0)

        # Action Stack
        self.action_stack = QStackedWidget()
        self.action_layout.addWidget(self.action_stack, 1)

        # Page 0: Check for updates
        self.check_button = QPushButton("Check for Updates")
        self.check_button.setObjectName("checkButton")
        self.check_button.setFixedHeight(40)
        self.check_button.setCursor(Qt.PointingHandCursor)
        self.check_button.clicked.connect(self._on_check_clicked)
        self.action_stack.addWidget(self.check_button)

        # Page 1: Update available
        update_widget = QWidget()
        update_layout = QHBoxLayout(update_widget)
        self.update_version_label = QLabel()
        self.update_version_label.setObjectName("updateVersionInfo")
        self.update_button = QPushButton("Update Now")
        self.update_button.setObjectName("updateButton")
        self.update_button.setFixedHeight(40)
        self.update_button.setCursor(Qt.PointingHandCursor)
        self.update_button.clicked.connect(self._on_update_clicked)
        update_layout.addWidget(self.update_version_label, 1)
        update_layout.addWidget(self.update_button)
        self.action_stack.addWidget(update_widget)

        # Page 2: Downloading
        progress_widget = QWidget()
        progress_layout = QHBoxLayout(progress_widget)
        self.progress_bar = CircularProgressBar()
        self.progress_bar.setFixedSize(32, 32)
        self.speed_label = QLabel("0 MB/s")
        self.speed_label.setObjectName("downloadSpeed")
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.speed_label, 1)
        self.action_stack.addWidget(progress_widget)

        # Page 3: Status (Latest / Error)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.action_stack.addWidget(self.status_label)

        return bar

    def _create_description_card(self):
        card = QFrame()
        card.setObjectName("detailCard")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Description")
        title.setObjectName("cardTitle")

        self.desc_label = QLabel("No description available.")
        self.desc_label.setObjectName("cardContent")
        self.desc_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.desc_label)
        return card

    def set_resource(self, resource):
        self.current_resource = resource
        self.update_info = None
        self.title_label.setText(resource.resource_name)
        self.author_label.setText(f"By {resource.resource_author or 'Unknown'}")

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

        self.desc_label.setText(resource.resource_description or "No description available for this resource.")

        # NEW: Set the value for the update source dropdown
        self.source_combo.blockSignals(True)  # Prevent signal emission while setting
        # Use getattr to safely get the attribute with a default value
        update_method = getattr(self.current_resource, 'resource_update_method', 'github').lower()
        if 'mirror' in update_method:
            self.source_combo.setCurrentText("MirrorChyan")
        else:
            self.source_combo.setCurrentText("GitHub")
        self.source_combo.blockSignals(False)

        self.reset_action_bar()

    # NEW: Handler for when the user changes the update source
    def _on_source_changed(self, text):
        if not self.current_resource:
            return

        new_method = 'mirrorchyan' if text == "MirrorChyan" else 'github'

        # Only save if the value actually changed
        current_method = getattr(self.current_resource, 'resource_update_method', 'github')
        if new_method != current_method:
            self.current_resource.resource_update_method = new_method
            global_config.save_all_configs()
            notification_manager.show_info(f"Update source for {self.current_resource.resource_name} set to {text}.")

    def _on_check_clicked(self):
        if self.current_resource:
            self.check_button.setText("Checking...")
            self.check_button.setEnabled(False)
            self.check_update_clicked.emit(self.current_resource)

    def _on_update_clicked(self):
        if self.current_resource and self.update_info:
            self.start_update_clicked.emit(self.current_resource, self)

    def set_update_available(self, new_version, update_type, download_url):
        self.update_info = {
            'version': new_version, 'type': update_type, 'url': download_url
        }
        self.update_version_label.setText(
            f"New version available: <b>{new_version}</b>"
        )
        update_text = "Incremental Update" if update_type == "incremental" else "Full Update"
        self.update_button.setText(update_text)
        self.action_stack.setCurrentIndex(1)

    def set_downloading(self, progress, speed):
        self.action_stack.setCurrentIndex(2)
        self.progress_bar.setValue(int(progress))
        self.speed_label.setText(f"Downloading... ({speed:.1f} MB/s)")

    def set_latest_version(self):
        self.status_label.setText("You have the latest version.")
        self.status_label.setProperty("status", "success")
        self.status_label.style().polish(self.status_label)
        self.action_stack.setCurrentIndex(3)
        QTimer.singleShot(3000, self.reset_action_bar)

    def set_error(self, error_msg):
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setProperty("status", "error")
        self.status_label.style().polish(self.status_label)
        self.action_stack.setCurrentIndex(3)
        QTimer.singleShot(4000, self.reset_action_bar)

    def reset_action_bar(self):
        self.check_button.setText("Check for Updates")
        self.check_button.setEnabled(True)
        self.action_stack.setCurrentIndex(0)


class DownloadPage(QWidget):
    """下载页面主类（重构版）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadPage")
        self.threads = []
        self.resource_items = {}
        self.selected_resource = None
        self.installer = UpdateInstaller()
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
        title = QLabel("Resources")
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

        self.add_btn = QPushButton(" Add Resource")
        self.add_btn.setObjectName("bottomBarButton")
        self.add_btn.setIcon(QIcon("assets/icons/add.png"))
        self.add_btn.setFixedHeight(40)
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.show_add_resource_dialog)

        self.check_all_btn = QPushButton(" Check All")
        self.check_all_btn.setObjectName("bottomBarButton")
        self.check_all_btn.setIcon(QIcon("assets/icons/refresh.png"))
        self.check_all_btn.setFixedHeight(40)
        self.check_all_btn.setCursor(Qt.PointingHandCursor)
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
        text_label = QLabel("Select a resource from the left to see details")
        text_label.setObjectName("emptyStateText")
        hint_label = QLabel("You can add new resources using the 'Add Resource' button.")
        hint_label.setObjectName("emptyStateHint")
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        layout.addWidget(hint_label)
        return widget

    def _connect_signals(self):
        self.installer.install_completed.connect(self._handle_install_completed)
        self.installer.install_failed.connect(self._handle_install_failed)
        self.installer.restart_required.connect(self._handle_restart_required)
        self.detail_view.check_update_clicked.connect(self._check_resource_update)
        self.detail_view.start_update_clicked.connect(self._start_update)

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            /* Main Page */
            #downloadPage { background-color: #f8fafc; }

            /* Left Panel */
            #leftPanel { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
            #leftPanelHeader { border-bottom: 1px solid #e2e8f0; }
            #leftPanelTitle { font-size: 18px; font-weight: 600; color: #1e293b; }
            #resourceListScroll { border: none; }

            /* Resource List Item */
            #resourceItem { border-radius: 8px; border: 1px solid transparent; }
            #resourceItem:hover { background-color: #f1f5f9; }
            #resourceItem[selected="true"] { background-color: #e0f2fe; border-color: #38bdf8; }
            #resourceItemName { font-size: 14px; font-weight: 600; color: #334155; }
            #resourceItemVersion { font-size: 12px; color: #64748b; }

            /* Bottom Bar */
            #leftPanelBottomBar { border-top: 1px solid #e2e8f0; }
            #bottomBarButton {
                background-color: #f1f5f9; color: #475569; border: none;
                border-radius: 8px; font-size: 13px; font-weight: 500;
            }
            #bottomBarButton:hover { background-color: #e2e8f0; }

            /* Right Panel */
            #rightPanel { background-color: #f8fafc; }
            #detailScrollArea { border: none; }

            /* Empty State */
            #emptyStateText { font-size: 16px; color: #475569; font-weight: 500; }
            #emptyStateHint { font-size: 13px; color: #94a3b8; }

            /* Detail View */
            #detailIcon { border-radius: 12px; }
            #detailTitle { font-size: 24px; font-weight: 700; color: #1e293b; }
            #detailAuthor { font-size: 14px; color: #64748b; }

            /* NEW Styles for Source Dropdown */
            #sourceLabel { font-size: 12px; color: #64748b; font-weight: 500; }
            #sourceCombo {
                border: 1px solid #e2e8f0; border-radius: 6px; 
                padding: 6px; background-color: white;
            }
            #sourceCombo::drop-down { border: none; }

            #detailActionBar { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
            #checkButton, #updateButton {
                border: none; border-radius: 8px; font-weight: 600;
                padding: 0 16px;
            }
            #checkButton { background-color: #3b82f6; color: white; }
            #checkButton:hover { background-color: #2563eb; }
            #updateButton { background-color: #10b981; color: white; }
            #updateButton:hover { background-color: #059669; }
            #updateVersionInfo { font-size: 14px; color: #334155; }
            #downloadSpeed { font-size: 14px; color: #475569; margin-left: 12px; }
            #statusLabel[status="success"] { color: #16a34a; font-weight: 600; }
            #statusLabel[status="error"] { color: #dc2626; font-weight: 600; }

            #detailCard { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
            #cardTitle { font-size: 16px; font-weight: 600; color: #334155; }
            #cardContent { font-size: 14px; color: #475569; line-height: 1.5; }
        """)

    # --- The rest of the DownloadPage class is unchanged ---

    def load_resources(self):
        # ... (no changes)
        for item in self.resource_items.values():
            item.deleteLater()
        self.resource_items.clear()
        while self.resources_layout.count():
            item = self.resources_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

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
        # ... (no changes)
        if self.selected_resource == resource:
            return

        self.selected_resource = resource
        for name, item in self.resource_items.items():
            item.set_selected(name == resource.resource_name)

        self.detail_view.set_resource(resource)
        self.content_stack.setCurrentIndex(1)
        self.detail_view.reset_action_bar()

    def _check_resource_update(self, resource):
        # ... (no changes)
        if not resource.resource_rep_url and not resource.resource_update_service_id:
            self.detail_view.set_error("No update source configured")
            return

        thread = UpdateChecker(resource, single_mode=True)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)
        self.threads.append(thread)
        thread.start()

    def _start_update(self, resource, detail_view_item):
        # ... (no changes)
        if not detail_view_item.update_info:
            return

        detail_view_item.set_downloading(0, 0)
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        thread = UpdateDownloader(
            resource.resource_name,
            detail_view_item.update_info['url'],
            temp_dir,
            resource=resource,
            version=detail_view_item.update_info['version']
        )
        thread.progress_updated.connect(self._update_download_progress)
        thread.download_completed.connect(self._handle_download_completed)
        thread.download_failed.connect(self._handle_download_failed)
        self.threads.append(thread)
        thread.start()

    def _handle_update_found(self, resource_name, latest_version, current_version, download_url, update_type):
        # ... (no changes)
        item = self.resource_items.get(resource_name)
        if item:
            item.set_update_status(True)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_update_available(latest_version, update_type, download_url)

    def _handle_update_not_found(self, resource_name):
        # ... (no changes)
        item = self.resource_items.get(resource_name)
        if item:
            item.set_update_status(False)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_latest_version()

    def _handle_check_failed(self, resource_name, error_message):
        # ... (no changes)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error(error_message)
        notification_manager.show_error(f"Update check failed: {error_message}", resource_name)

    def _update_download_progress(self, resource_name, progress, speed):
        # ... (no changes)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_downloading(progress, speed)

    def _handle_download_completed(self, resource_name, file_path, data):
        # ... (no changes)
        try:
            if isinstance(data, dict):
                self.installer.install_new_resource(resource_name, file_path, data)
            else:
                self.installer.install_update(data, file_path)
        except Exception as e:
            if self.selected_resource and self.selected_resource.resource_name == resource_name:
                self.detail_view.set_error("Installation failed")
            notification_manager.show_error(f"Installation failed: {str(e)}", resource_name)

    def _handle_download_failed(self, resource_name, error):
        # ... (no changes)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error("Download failed")
        notification_manager.show_error(f"Download failed: {error}", resource_name)

    def check_all_updates(self):
        # ... (no changes)
        self.check_all_btn.setText("Checking...")
        self.check_all_btn.setEnabled(False)

        resources_with_update = [r for r in global_config.get_all_resource_configs() if
                                 r.mirror_update_service_id or r.resource_rep_url]
        if not resources_with_update:
            self.check_all_btn.setText("Check All")
            self.check_all_btn.setEnabled(True)
            notification_manager.show_info("No resources with an update source found.", "Update Check")
            return

        thread = UpdateChecker(resources_with_update)
        thread.update_found.connect(self._handle_update_found)
        thread.update_not_found.connect(self._handle_update_not_found)
        thread.check_failed.connect(self._handle_check_failed)
        thread.check_completed.connect(self._handle_batch_check_completed)
        self.threads.append(thread)
        thread.start()

    def _handle_batch_check_completed(self, total_checked, updates_found):
        # ... (no changes)
        self.check_all_btn.setEnabled(True)
        self.check_all_btn.setText("Check All")
        if updates_found > 0:
            notification_manager.show_success(f"Found {updates_found} available updates.", "Check Complete")
        else:
            notification_manager.show_success(f"All {total_checked} resources are up to date.", "Check Complete")

    def show_add_resource_dialog(self):
        # ... (no changes)
        dialog = AddResourceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.add_new_resource(dialog.get_data())

    def add_new_resource(self, data):
        # ... (no changes)
        url, ref = data.get('url'), data.get('ref')
        if not url or not ref or "github.com" not in url:
            notification_manager.show_error("Please provide a valid GitHub repository URL and branch/tag.",
                                            "Invalid Input")
            return

        if self.git_installer_thread and self.git_installer_thread.isRunning():
            notification_manager.show_warning("Please wait for the current add operation to complete.")
            return

        self.add_btn.setEnabled(False)
        self.add_btn.setText("Adding...")
        self.git_installer_thread = GitInstallerThread(url, ref, self)
        self.git_installer_thread.install_succeeded.connect(self._handle_add_succeeded)
        self.git_installer_thread.install_failed.connect(self._handle_add_failed)
        self.git_installer_thread.start()

    def _handle_add_succeeded(self, resource_name):
        # ... (no changes)
        self._restore_add_button()
        notification_manager.show_success(f"Resource '{resource_name}' was added successfully!", "Success")
        self.load_resources()

    def _handle_add_failed(self, error_message):
        # ... (no changes)
        self._restore_add_button()
        notification_manager.show_error(f"Failed to add resource: {error_message}", "Error")

    def _restore_add_button(self):
        """恢复添加按钮的初始状态"""
        self.add_btn.setEnabled(True)
        self.add_btn.setText(" Add Resource")

    def _handle_install_completed(self, resource_name, version, locked_files):
        notification_manager.show_success(f"Resource {resource_name} updated to version {version}", "Update Successful")
        self.load_resources()
        for res in global_config.get_all_resource_configs():
            if res.resource_name == resource_name:
                self._on_resource_selected(res)
                break

    def _handle_install_failed(self, resource_name, error_message):
        # ... (no changes)
        notification_manager.show_error(f"Installation failed: {error_message}", resource_name)
        if self.selected_resource and self.selected_resource.resource_name == resource_name:
            self.detail_view.set_error("Installation failed")

    def _handle_restart_required(self):
        # ... (no changes)
        reply = QMessageBox.question(
            self, "Restart Required",
            "This update requires the application to be restarted to take effect.\n\nRestart now?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            QTimer.singleShot(100, QCoreApplication.quit)
        else:
            notification_manager.show_info(
                "The update has been downloaded but not applied. Please restart the application manually.",
                "Restart Pending")