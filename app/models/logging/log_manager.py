import functools
import logging
import os
import zipfile
from datetime import datetime
from typing import Dict, List, Any, Callable

from PySide6.QtCore import QObject, Signal


class LogManager(QObject):
    """
    Manages logs for the application, supporting both global and device-specific logs.
    Emits signals when new logs are added.
    """
    # Signals for log updates
    app_log_updated = Signal()
    device_log_updated = Signal(str)  # device_name

    def __init__(self):
        super().__init__()
        self.loggers: Dict[str, logging.Logger] = {}
        self.log_dir = "logs"
        self.backup_dir = os.path.join(self.log_dir, "backup")
        self.handle_to_device: Dict[Any, str] = {}
        self.context_to_logger: Dict[Any, logging.Logger] = {}

        # Record session start time for filtering logs
        self.session_start_time = datetime.now()
        self.session_start_str = self.session_start_time.strftime("%Y-%m-%d %H:%M:%S")

        # Setup directories and check log size
        self._ensure_directories()
        self._check_and_backup_logs()

        # Initialize the main application logger
        self.initialize_logger("app", "app.log")

        # Log session start
        app_logger = self.get_app_logger()
        if app_logger:
            app_logger.info(f"=== New session started at {self.session_start_str} ===")

    def _ensure_directories(self):
        """Ensure the log directory and backup directory exist"""
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _check_and_backup_logs(self):
        """Backup logs if size exceeds threshold and create fresh log files"""
        log_files_to_backup = []
        total_size = 0

        # Calculate total size of log files
        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(self.log_dir, filename)
                log_files_to_backup.append(file_path)
                total_size += os.path.getsize(file_path)

        # If total size > 10MB, backup logs and then clear them
        if total_size > 1 * 1024 * 1024:
            self._backup_logs(log_files_to_backup)

            # Clear existing log files for fresh start ONLY after backup
            for file_path in log_files_to_backup:
                open(file_path, 'w', encoding='utf-8').close()

    def _backup_logs(self, log_files):
        """Backup log files to a zip archive"""
        if not log_files:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = os.path.join(self.backup_dir, f"logs_backup_{timestamp}.zip")

        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in log_files:
                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    zipf.write(file_path, os.path.basename(file_path))

    def initialize_logger(self, name: str, log_file: str) -> logging.Logger:
        """Initialize a logger with the given name and file"""
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # Remove any existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Create file handler with sanitized filename
        sanitized_log_file = self._sanitize_filename(log_file)
        file_handler = logging.FileHandler(
            os.path.join(self.log_dir, sanitized_log_file),
            encoding='utf-8',
            mode='a'
        )

        # Set formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Add signal handler
        if name == "app":
            logger.addHandler(AppLogSignalHandler(self))
        elif name.startswith("device_"):
            device_name = name[7:]  # Remove "device_" prefix
            logger.addHandler(DeviceLogSignalHandler(device_name, self))

        # 添加context日志记录能力
        ContextLogger.add_context_logging(logger, self)

        self.loggers[name] = logger
        return logger

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to ensure it's valid for the file system"""
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\r', '\n']
        sanitized = filename

        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')

        sanitized = sanitized.strip().strip('.')

        return sanitized if sanitized else "unnamed_device.log"

    def get_device_logger(self, device_name: str) -> logging.Logger:
        """Get or create a logger for a specific device"""
        logger_name = f"device_{device_name}"
        log_file = f"{device_name}.log"

        return self.loggers.get(logger_name) or self.initialize_logger(logger_name, log_file)

    def get_app_logger(self) -> logging.Logger:
        """Get the main application logger"""
        return self.loggers.get("app")

    def get_context_logger(self, context: Any) -> logging.Logger:
        """Get logger associated with a context object"""
        # 如果已经缓存了此context的logger，直接返回
        if context in self.context_to_logger:
            return self.context_to_logger[context]

        try:
            handle = context.tasker._handle
            device_name = self.handle_to_device.get(handle)

            if device_name:
                # 获取设备logger
                logger = self.get_device_logger(device_name)
                # 缓存起来，提高性能
                self.context_to_logger[context] = logger
                return logger
            else:
                # 如果找不到设备，返回应用logger
                app_logger = self.get_app_logger()
                app_logger.warning(f"No device found for handle: {handle}, using app logger")
                self.context_to_logger[context] = app_logger
                return app_logger
        except (AttributeError, Exception) as e:
            # 发生错误时返回应用logger
            app_logger = self.get_app_logger()
            if app_logger:
                app_logger.warning(f"Error getting context logger: {str(e)}")
            self.context_to_logger[context] = app_logger
            return app_logger

    # 装饰器，用于自动同步日志到app logger
    def sync_to_app(level: str = 'info') -> Callable:
        """装饰器：将日志同步到应用日志"""

        def decorator(func):
            @functools.wraps(func)
            def wrapper(logger, message, *args, **kwargs):
                # 执行原始日志记录
                result = func(logger, message, *args, **kwargs)

                # 同步到应用日志
                try:
                    log_manager = logger.log_manager
                    app_logger = log_manager.get_app_logger()
                    if app_logger and app_logger != logger:
                        # 确定设备名称
                        device_name = "unknown"
                        for name, lg in log_manager.loggers.items():
                            if lg == logger and name.startswith("device_"):
                                device_name = name[7:]  # Remove "device_" prefix
                                break

                        log_method = getattr(app_logger, level)
                        log_method(f"[{device_name}] {message}")
                except Exception:
                    # 同步失败不影响原始日志记录
                    pass

                return result

            return wrapper

        return decorator

    def set_device_handle(self, device_name: str, handle: Any) -> None:
        """Associate a handle with a device name"""
        self.get_device_logger(device_name)  # Ensure logger is initialized
        self.handle_to_device[handle] = device_name

        # 清除可能已缓存的context_to_logger映射
        # 因为handle关联变化可能影响context的logger映射
        self.context_to_logger.clear()

    def get_device_logs(self, device_name: str, max_lines: int = 100) -> List[str]:
        """Retrieve recent logs for a specific device, filtered by current session"""
        log_file = os.path.join(self.log_dir, f"{device_name}.log")
        if not os.path.exists(log_file):
            return []

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Filter lines by session start time
        session_lines = []
        for line in all_lines:
            try:
                # Extract timestamp from log line (assuming format: '2023-01-01 12:34:56 - INFO - message')
                timestamp_str = line.split(' - ')[0].strip()
                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                # Only include logs from current session
                if log_time >= self.session_start_time:
                    session_lines.append(line)
            except (ValueError, IndexError):
                # If we can't parse the timestamp, include the line anyway
                # This ensures we don't lose any logs due to format issues
                session_lines.append(line)

        # Return the last 'max_lines' lines from the current session
        return session_lines[-max_lines:] if len(session_lines) > max_lines else session_lines

    def get_all_logs(self, max_lines: int = 100) -> List[str]:
        """Retrieve recent logs from the main application log, filtered by current session"""
        log_file = os.path.join(self.log_dir, "app.log")
        if not os.path.exists(log_file):
            return []

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Filter lines by session start time
        session_lines = []
        for line in all_lines:
            try:
                # Extract timestamp from log line (assuming format: '2023-01-01 12:34:56 - INFO - message')
                timestamp_str = line.split(' - ')[0].strip()
                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                # Only include logs from current session
                if log_time >= self.session_start_time:
                    session_lines.append(line)
            except (ValueError, IndexError):
                # If we can't parse the timestamp, include the line anyway
                session_lines.append(line)

        # Return the last 'max_lines' lines from the current session
        return session_lines[-max_lines:] if len(session_lines) > max_lines else session_lines


class AppLogSignalHandler(logging.Handler):
    """Custom logging handler that emits a signal when app logs are updated"""

    def __init__(self, log_manager):
        super().__init__()
        self.log_manager = log_manager

    def emit(self, record):
        self.log_manager.app_log_updated.emit()


class DeviceLogSignalHandler(logging.Handler):
    """Custom logging handler that emits a signal when device logs are updated"""

    def __init__(self, device_name, log_manager):
        super().__init__()
        self.device_name = device_name
        self.log_manager = log_manager

    def emit(self, record):
        self.log_manager.device_log_updated.emit(self.device_name)


# 扩展Logger类，添加辅助方法，使其能够直接使用context记录日志
class ContextLogger:
    """Helper class to provide context-based logging capabilities"""

    @staticmethod
    def add_context_logging(logger, log_manager):
        """Add context logging methods to a logger"""
        # 存储对log_manager的引用
        logger.log_manager = log_manager

        # 添加context日志记录方法
        def log_with_context(level, context, message):
            # 记录到当前logger
            log_method = getattr(logger, level)
            log_method(message)

            # 同步到应用logger（如果当前不是应用logger）
            try:
                app_logger = log_manager.get_app_logger()
                if app_logger and app_logger != logger:
                    # 查找设备名称
                    device_name = "unknown"
                    for name, lg in log_manager.loggers.items():
                        if lg == logger and name.startswith("device_"):
                            device_name = name[7:]  # Remove "device_" prefix
                            break

                    app_log_method = getattr(app_logger, level)
                    app_log_method(f"[{device_name}] {message}")
            except Exception:
                pass  # 同步失败不影响原始日志

        # 添加各个日志级别的context方法
        logger.debug_context = lambda context, message: log_with_context("debug", context, message)
        logger.info_context = lambda context, message: log_with_context("info", context, message)
        logger.warning_context = lambda context, message: log_with_context("warning", context, message)
        logger.error_context = lambda context, message: log_with_context("error", context, message)
        logger.critical_context = lambda context, message: log_with_context("critical", context, message)

        return logger


# Create a singleton instance
log_manager = LogManager()