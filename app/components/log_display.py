# -*- coding: UTF-8 -*-
"""
日志显示组件 - 重构版
使用增量追加更新，优化实时性和流畅性
"""

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QFrame
)
from datetime import datetime
from typing import List, Optional

from app.models.logging.log_manager import log_manager, LogRecord
from app.components.no_wheel_ComboBox import NoWheelComboBox


class LogDisplay(QFrame):
    """
    日志显示组件 - 重构版
    - 使用新的LogRecord信号，无需从文件读取
    - 增量追加更新，提高性能
    - 批量处理日志，保持UI流畅
    """
    MAX_DISPLAY_LOGS = 100  # UI中显示的最大日志条数

    def __init__(self, parent=None, enable_log_level_filter=False, show_device_selector=True):
        super().__init__(parent)
        self.setObjectName("logDisplay")
        self.setFrameShape(QFrame.StyledPanel)

        # 会话开始时间
        self.session_start_time = datetime.now()

        # 设备选择器可见性
        self.show_device_selector = show_device_selector

        # 当前显示模式："all" 或设备名
        self.current_device = "all"

        # 日志级别过滤
        self.current_log_level = "INFO"
        self.enable_log_level_filter = enable_log_level_filter

        # 日志级别层级（从低到高）
        self.log_level_hierarchy = ["DEBUG", "INFO", "WARNING", "ERROR"]

        # 设备句柄映射（保持向后兼容）
        self.handle_to_device = {}
        self.device_to_handle = {}

        # 当前会话的日志记录（使用LogRecord对象）
        self.session_logs: List[LogRecord] = []

        # 待处理的新日志（用于批量更新）
        self._pending_logs: List[LogRecord] = []

        # 批量更新定时器
        self._batch_timer: Optional[QTimer] = None

        # 是否需要完全重绘
        self._needs_full_refresh = False

        # 当前显示的日志数量
        self._displayed_log_count = 0

        # 日志颜色配置
        self.log_colors = {
            "INFO": QColor("#888888"),    # 灰色
            "ERROR": QColor("#F44336"),   # 红色
            "WARNING": QColor("#FF9800"), # 橙色
            "DEBUG": QColor("#4CAF50")    # 绿色
        }

        self.init_ui()
        self._setup_batch_timer()
        self._connect_signals()

    def init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)

        # 头部：标题和选择器
        header_layout = QHBoxLayout()

        # 日志标题
        title_label = QLabel("设备日志")
        title_label.setFont(QFont("Arial", 12, QFont.Bold))
        title_label.setObjectName("sectionTitle")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # 日志级别选择器
        self.log_level_selector = NoWheelComboBox()
        self.log_level_selector.addItem("INFO", "INFO")
        self.log_level_selector.addItem("DEBUG", "DEBUG")
        self.log_level_selector.addItem("WARNING", "WARNING")
        self.log_level_selector.addItem("ERROR", "ERROR")
        self.log_level_selector.currentIndexChanged.connect(self.on_log_level_changed)

        if not self.enable_log_level_filter:
            self.log_level_selector.setEnabled(False)

        header_layout.addWidget(self.log_level_selector)

        # 设备选择器
        if self.show_device_selector:
            header_layout.addSpacing(10)
            device_label = QLabel("设备:")
            header_layout.addWidget(device_label)

            self.device_selector = NoWheelComboBox()
            self.device_selector.addItem("全部日志", "all")
            self.device_selector.currentIndexChanged.connect(self.on_device_changed)
            header_layout.addWidget(self.device_selector)
        else:
            self.device_selector = NoWheelComboBox()
            self.device_selector.setVisible(False)

        main_layout.addLayout(header_layout)

        # 日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setMinimumHeight(150)
        self.log_text.setPlaceholderText("暂无日志记录")
        self.log_text.document().setDocumentMargin(8)
        self.log_text.setObjectName("log_text")

        main_layout.addWidget(self.log_text)

    def _setup_batch_timer(self):
        """设置批量更新定时器"""
        self._batch_timer = QTimer()
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._process_pending_logs)

    def _connect_signals(self):
        """连接日志管理器的信号"""
        # 连接新信号（携带LogRecord）
        log_manager.app_log_added.connect(self._on_app_log_added)
        log_manager.device_log_added.connect(self._on_device_log_added)

    def _on_app_log_added(self, record: LogRecord):
        """处理应用日志添加信号"""
        # 添加到会话日志
        self.session_logs.append(record)

        # 裁剪会话日志以防止内存溢出
        if len(self.session_logs) > 2000:
            self.session_logs = self.session_logs[-2000:]
            self._needs_full_refresh = True

        # 检查是否需要显示
        if self._should_display_log(record):
            self._pending_logs.append(record)
            self._schedule_batch_update()

    def _on_device_log_added(self, device_name: str, record: LogRecord):
        """处理设备日志添加信号"""
        # 添加到会话日志
        self.session_logs.append(record)

        # 裁剪会话日志
        if len(self.session_logs) > 2000:
            self.session_logs = self.session_logs[-2000:]
            self._needs_full_refresh = True

        # 检查是否需要显示
        if self._should_display_log(record):
            self._pending_logs.append(record)
            self._schedule_batch_update()

    def _should_display_log(self, record: LogRecord) -> bool:
        """判断日志是否应该显示"""
        # 检查设备过滤
        if self.current_device != "all":
            if record.device_name != self.current_device:
                return False

        # 检查日志级别过滤
        try:
            record_level_index = self.log_level_hierarchy.index(record.level)
        except ValueError:
            record_level_index = 1  # 默认INFO

        if self.enable_log_level_filter:
            selected_level_index = self.log_level_hierarchy.index(self.current_log_level)
            return record_level_index >= selected_level_index
        else:
            # 默认显示INFO及以上级别
            info_level_index = self.log_level_hierarchy.index("INFO")
            return record_level_index >= info_level_index

    def _schedule_batch_update(self):
        """调度批量更新"""
        if not self._batch_timer.isActive():
            self._batch_timer.start(50)  # 50ms延迟，收集更多日志

    def _process_pending_logs(self):
        """处理待显示的日志"""
        if not self._pending_logs and not self._needs_full_refresh:
            return

        # 如果需要完全刷新，则重建整个显示
        if self._needs_full_refresh:
            self._needs_full_refresh = False
            self._pending_logs.clear()
            self.refresh_display()
            return

        # 增量追加模式
        scrollbar = self.log_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        # 检查是否需要裁剪显示
        total_after_append = self._displayed_log_count + len(self._pending_logs)
        if total_after_append > self.MAX_DISPLAY_LOGS:
            # 超过最大显示数量，进行完全刷新
            self._pending_logs.clear()
            self.refresh_display()
            return

        # 追加新日志
        for record in self._pending_logs:
            self._append_log_to_display(record)
            self._displayed_log_count += 1

        self._pending_logs.clear()

        # 如果之前在底部，滚动到底部
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def _append_log_to_display(self, record: LogRecord):
        """追加单条日志到显示区域"""
        # 移动光标到末尾
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_text.setTextCursor(cursor)

        # 设置颜色
        color = self.log_colors.get(record.level, QColor("#888888"))
        self.log_text.setTextColor(color)

        # 格式化并追加
        display_text = record.to_display_string()
        if not self.log_text.document().isEmpty():
            # 添加更大的间隔：两行空行
            self.log_text.append("")
            self.log_text.append("")
        self.log_text.insertPlainText(display_text)

    def refresh_display(self):
        """完全刷新日志显示"""
        # 过滤日志
        filtered_logs = [
            record for record in self.session_logs
            if self._should_display_log(record)
        ]

        # 存储滚动位置
        scrollbar = self.log_text.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        # 清空显示
        self.log_text.clear()
        self._displayed_log_count = 0

        # 限制显示数量
        displayable_logs = filtered_logs[-self.MAX_DISPLAY_LOGS:]

        if not displayable_logs:
            self.log_text.setPlainText("暂无日志记录")
            return

        # 如果日志被截断，显示提示
        if len(filtered_logs) > self.MAX_DISPLAY_LOGS:
            self.log_text.setTextColor(QColor("#888888"))
            self.log_text.append(f"--- 日志过多，仅显示最新的 {self.MAX_DISPLAY_LOGS} 条 ---")
            self.log_text.append("")

        # 显示日志
        for record in displayable_logs:
            self._append_log_to_display(record)
            self._displayed_log_count += 1

        # 恢复滚动位置
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def on_device_changed(self, index):
        """设备选择变更处理"""
        if index >= 0:
            self.current_device = self.device_selector.currentData()
            self._needs_full_refresh = True
            self._schedule_batch_update()

    def on_log_level_changed(self, index):
        """日志级别选择变更处理"""
        if index >= 0:
            self.current_log_level = self.log_level_selector.currentData()
            self._needs_full_refresh = True
            self._schedule_batch_update()

    def update_device_list(self, devices):
        """更新设备下拉列表"""
        if not self.show_device_selector:
            return

        current_index = self.device_selector.currentIndex()
        current_data = self.device_selector.currentData() if current_index >= 0 else "all"

        self.device_selector.clear()
        self.device_selector.addItem("全部日志", "all")

        for device in devices:
            self.device_selector.addItem(device.device_name, device.device_name)

        new_index = self.device_selector.findData(current_data)
        if new_index >= 0:
            self.device_selector.setCurrentIndex(new_index)
        else:
            self.device_selector.setCurrentIndex(0)

    def show_device_logs(self, device_name):
        """显示特定设备的日志"""
        if not self.show_device_selector:
            self.current_device = device_name
            self._needs_full_refresh = True
            self._schedule_batch_update()
            return

        index = self.device_selector.findData(device_name)
        if index >= 0:
            self.device_selector.setCurrentIndex(index)
        else:
            self.device_selector.addItem(device_name, device_name)
            self.device_selector.setCurrentIndex(self.device_selector.count() - 1)

    # ========== 向后兼容的方法 ==========

    def set_device_handle(self, device_name, handle):
        """设置设备句柄（向后兼容）"""
        self.handle_to_device[handle] = device_name
        self.device_to_handle[device_name] = handle

    def add_log_by_handle(self, handle, message, level="INFO"):
        """通过句柄添加日志（向后兼容）"""
        if handle in self.handle_to_device:
            device_name = self.handle_to_device[handle]
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"{timestamp} - {level} - {message}"
            log_manager.add_device_log(device_name, log_entry)
            return True
        return False

    def get_device_by_handle(self, handle):
        """获取句柄对应的设备名（向后兼容）"""
        return self.handle_to_device.get(handle)

    def get_handle_by_device(self, device_name):
        """获取设备名对应的句柄（向后兼容）"""
        return self.device_to_handle.get(device_name)

    # ========== 废弃的方法（保留以兼容，但不再使用）==========

    def add_session_log(self, log_entry, device_name=None):
        """添加会话日志（向后兼容，不再推荐使用）"""
        # 解析日志条目并创建LogRecord
        try:
            parts = log_entry.split(' - ', 2)
            if len(parts) >= 3:
                timestamp_str = parts[0].strip()
                level = parts[1].strip()
                message = parts[2].strip()
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            else:
                timestamp = datetime.now()
                level = "INFO"
                message = log_entry
        except Exception:
            timestamp = datetime.now()
            level = "INFO"
            message = log_entry

        record = LogRecord(
            timestamp=timestamp,
            level=level,
            message=message,
            device_name=device_name
        )
        self.session_logs.append(record)

        if self._should_display_log(record):
            self._pending_logs.append(record)
            self._schedule_batch_update()

    def parse_log_timestamp(self, log_line):
        """解析日志时间戳（向后兼容）"""
        try:
            timestamp_str = log_line.split(' - ')[0].strip()
            if ',' in timestamp_str:
                timestamp_str = timestamp_str.split(',')[0]
            return datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except:
            return None

    def is_log_from_current_session(self, log_line):
        """检查日志是否属于当前会话（向后兼容）"""
        timestamp = self.parse_log_timestamp(log_line)
        if timestamp:
            return timestamp >= self.session_start_time
        return False

    def on_app_log_updated(self):
        """旧信号处理器（向后兼容，不再使用）"""
        pass

    def on_device_log_updated(self, device_name):
        """旧信号处理器（向后兼容，不再使用）"""
        pass

    def display_logs(self, logs):
        """显示日志列表（向后兼容）"""
        self.refresh_display()
