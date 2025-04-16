from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QComboBox, QFrame
)

from app.models.logging.log_manager import log_manager


class LogDisplay(QFrame):
    """
    Component to display application and device logs with real-time updates
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logDisplay")
        self.setFrameShape(QFrame.StyledPanel)

        # Current display mode: "all" or device name
        self.current_device = "all"

        # Current log level filter: "all" or specific level
        self.current_log_level = "all"

        # Dictionary to map device handles to device names
        self.handle_to_device = {}
        # Dictionary to map device names to handles
        self.device_to_handle = {}

        # Configure colors for different log levels
        self.log_colors = {
            "INFO": QColor("#888888"),  # Gray instead of blue
            "ERROR": QColor("#F44336"),  # Red
            "WARNING": QColor("#FF9800"),  # Orange
            "DEBUG": QColor("#4CAF50")  # Green
        }

        self.init_ui()

        # Connect to log manager signals
        log_manager.app_log_updated.connect(self.on_app_log_updated)
        log_manager.device_log_updated.connect(self.on_device_log_updated)

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Header with title and device selector
        header_layout = QHBoxLayout()

        # Log display title
        title_label = QLabel("设备日志")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        header_layout.addWidget(title_label)

        # Dropdown for device selection
        self.device_selector = QComboBox()
        self.device_selector.addItem("全部日志", "all")
        self.device_selector.currentIndexChanged.connect(self.on_device_changed)
        header_layout.addStretch()

        # Add log level selector
        self.log_level_selector = QComboBox()
        self.log_level_selector.addItem("全部级别", "all")
        self.log_level_selector.addItem("INFO", "INFO")
        self.log_level_selector.addItem("DEBUG", "DEBUG")
        self.log_level_selector.addItem("WARNING", "WARNING")
        self.log_level_selector.addItem("ERROR", "ERROR")
        self.log_level_selector.currentIndexChanged.connect(self.on_log_level_changed)
        header_layout.addWidget(self.log_level_selector)

        # Add some spacing between selectors
        header_layout.addSpacing(10)

        # Device selector label
        device_label = QLabel("设备:")
        header_layout.addWidget(device_label)
        header_layout.addWidget(self.device_selector)

        main_layout.addLayout(header_layout)

        # Log text display area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMinimumHeight(150)
        self.log_text.setPlaceholderText("暂无日志记录")
        # Set line spacing and text formatting
        self.log_text.document().setDocumentMargin(8)
        self.log_text.setObjectName("log_text")

        main_layout.addWidget(self.log_text)

    def update_device_list(self, devices):
        """Update the device dropdown list"""
        # Store current selection
        current_index = self.device_selector.currentIndex()
        current_data = self.device_selector.currentData() if current_index >= 0 else "all"

        # Clear and repopulate
        self.device_selector.clear()
        self.device_selector.addItem("全部日志", "all")

        for device in devices:
            self.device_selector.addItem(device.device_name, device.device_name)

        # Try to restore previous selection
        new_index = self.device_selector.findData(current_data)
        if new_index >= 0:
            self.device_selector.setCurrentIndex(new_index)
        else:
            self.device_selector.setCurrentIndex(0)

        # Refresh logs for current selection
        self.request_logs_update()

    def on_device_changed(self, index):
        """Handle device selection change"""
        if index >= 0:
            self.current_device = self.device_selector.currentData()
            self.request_logs_update()

    def on_log_level_changed(self, index):
        """Handle log level selection change"""
        if index >= 0:
            self.current_log_level = self.log_level_selector.currentData()
            self.request_logs_update()

    def request_logs_update(self):
        """Request a log update for the current device"""
        if self.current_device == "all":
            logs = log_manager.get_all_logs()
        else:
            logs = log_manager.get_device_logs(self.current_device)

        # Apply log level filtering
        if self.current_log_level != "all":
            filtered_logs = []
            for log in logs:
                level_marker = f" - {self.current_log_level} - "
                if level_marker in log:
                    filtered_logs.append(log)
            logs = filtered_logs

        self.display_logs(logs)

    def display_logs(self, logs):
        """Display logs with optimized formatting - only time and message"""
        # Store current scroll position
        scrollbar = self.log_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() == scrollbar.maximum()

        # Clear text
        self.log_text.clear()

        if not logs:
            self.log_text.setPlainText("暂无日志记录")
            return

        # Process and display logs with color coding and simplified format
        for log in logs:
            try:
                # Determine log level for coloring
                if " - INFO - " in log:
                    level = "INFO"
                elif " - ERROR - " in log:
                    level = "ERROR"
                elif " - WARNING - " in log:
                    level = "WARNING"
                elif " - DEBUG - " in log:
                    level = "DEBUG"
                else:
                    level = "INFO"  # Default

                # Extract timestamp and message only
                # Format is typically: "YYYY-MM-DD HH:MM:SS,SSS - LEVEL - Message"
                parts = log.split(' - ', 2)  # Split into timestamp, level, message

                if len(parts) >= 3:
                    # Extract only the time portion (HH:MM:SS) from timestamp
                    timestamp = parts[0].strip()
                    try:
                        # Extract time part (assumes format like "YYYY-MM-DD HH:MM:SS")
                        time_part = timestamp.split(' ')[1].split(',')[0]  # Gets just HH:MM:SS
                    except IndexError:
                        time_part = timestamp  # Fallback if timestamp format is unexpected

                    message = parts[2].strip()
                    # Format log with proper spacing and indentation for wrapped lines
                    simplified_log = f"{time_part} {message}"

                    # Set color based on log level and display simplified log
                    self.log_text.setTextColor(self.log_colors.get(level, QColor("#888888")))

                    # Add the log with extra spacing between entries
                    if self.log_text.document().isEmpty():
                        self.log_text.append(simplified_log)
                    else:
                        # Insert a small height spacer and then the log
                        self.log_text.append("\n" + simplified_log)
                else:
                    # Fallback for unexpected log format
                    self.log_text.setTextColor(QColor("#888888"))
                    self.log_text.append(log.strip())

            except Exception as e:
                # For any parsing error, just show the line in default color
                self.log_text.setTextColor(QColor("#888888"))
                self.log_text.append(log.strip())

        # Restore scroll to bottom if it was at bottom
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def show_device_logs(self, device_name):
        """Show logs for a specific device"""
        # Find and select the device in the dropdown
        index = self.device_selector.findData(device_name)
        if index >= 0:
            self.device_selector.setCurrentIndex(index)
        else:
            # If device not found, add it
            self.device_selector.addItem(device_name, device_name)
            self.device_selector.setCurrentIndex(self.device_selector.count() - 1)

    def on_app_log_updated(self):
        """Handle app log update signal"""
        if self.current_device == "all":
            self.request_logs_update()

    def on_device_log_updated(self, device_name):
        """Handle device log update signal"""
        if self.current_device == device_name or self.current_device == "all":
            self.request_logs_update()

    def set_device_handle(self, device_name, handle):
        """Set a handle for a device name"""
        # Store handle to device mapping
        self.handle_to_device[handle] = device_name
        # Store device to handle mapping
        self.device_to_handle[device_name] = handle

    def add_log_by_handle(self, handle, message, level="INFO"):
        """Add a log entry to a device identified by its handle"""
        if handle in self.handle_to_device:
            device_name = self.handle_to_device[handle]
            # Use log_manager to add the log
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{timestamp} - {level} - {message}"

            # Add log to device logs
            log_manager.add_device_log(device_name, log_entry)
            return True
        else:
            # Handle not found
            return False

    def get_device_by_handle(self, handle):
        """Get device name associated with a handle"""
        return self.handle_to_device.get(handle)

    def get_handle_by_device(self, device_name):
        """Get handle associated with a device name"""
        return self.device_to_handle.get(device_name)