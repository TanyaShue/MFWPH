import functools
import logging
import logging.handlers
import os
import zipfile
from datetime import datetime
from typing import Dict, List, Any, Callable

from PySide6.QtCore import QObject, Signal, QTimer


class LogManager(QObject):
    """
    Manages logs for the application, supporting both global and device-specific logs.
    It buffers logs in memory and writes them to disk once per second.
    Emits signals immediately when new logs are generated.
    """
    # Signals for log updates
    app_log_updated = Signal()
    device_log_updated = Signal(str)  # device_name

    def __init__(self, flush_interval_ms: int = 1000):
        super().__init__()
        self.loggers: Dict[str, logging.Logger] = {}
        self.memory_handlers: List[logging.handlers.MemoryHandler] = []
        self.log_dir = "logs"
        self.backup_dir = os.path.join(self.log_dir, "backup")
        self.handle_to_device: Dict[Any, str] = {}
        self.context_to_logger: Dict[Any, logging.Logger] = {}

        self.session_start_time = datetime.now()
        self.session_start_str = self.session_start_time.strftime("%Y-%m-%d %H:%M:%S")

        self._ensure_directories()
        self._check_and_backup_logs()

        self.initialize_logger("app", "app.log")

        app_logger = self.get_app_logger()
        if app_logger:
            app_logger.info(f"=== New session started at {self.session_start_str} ===")

        # Setup a timer to flush logs periodically
        self.flush_timer = QTimer(self)
        self.flush_timer.timeout.connect(self.flush_all_logs)
        self.flush_timer.start(flush_interval_ms)

    def flush_all_logs(self):
        """Flushes all buffered logs to their respective files."""
        for handler in self.memory_handlers:
            handler.flush()

    def _ensure_directories(self):
        """Ensure the log directory and backup directory exist"""
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _check_and_backup_logs(self):
        """Backup logs if size exceeds threshold and create fresh log files"""
        self.flush_all_logs() # Ensure all buffered logs are written before checking
        log_files_to_backup = []
        total_size = 0

        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(self.log_dir, filename)
                log_files_to_backup.append(file_path)
                total_size += os.path.getsize(file_path)

        if total_size > 1 * 1024 * 1024: # If total size > 1MB
            self._backup_logs(log_files_to_backup)
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
        """
        Initialize a logger with a memory buffer that flushes to a file handler.
        """
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        # Clear any existing handlers to avoid duplication
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        sanitized_log_file = self._sanitize_filename(log_file)
        file_path = os.path.join(self.log_dir, sanitized_log_file)

        # Create the target file handler
        file_handler = logging.FileHandler(file_path, encoding='utf-8', mode='a')
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # Create a memory handler with the file handler as its target
        # Capacity is how many records to buffer before forcing a flush.
        # We primarily rely on the timer, so this can be a reasonably large number.
        memory_handler = logging.handlers.MemoryHandler(
            capacity=1024,
            flushLevel=logging.CRITICAL, # Only auto-flush on critical errors
            target=file_handler
        )
        self.memory_handlers.append(memory_handler)
        logger.addHandler(memory_handler)

        # Add signal handlers directly to the logger to ensure they fire immediately
        if name == "app":
            logger.addHandler(AppLogSignalHandler(self))
        elif name.startswith("device_"):
            device_name = name[7:]
            logger.addHandler(DeviceLogSignalHandler(device_name, self))

        ContextLogger.add_context_logging(logger, self)

        self.loggers[name] = logger
        return logger

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename to ensure it's valid for the file system"""
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\r', '\n']
        sanitized = filename
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        return sanitized.strip().strip('.') or "unnamed_device.log"

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
        if context in self.context_to_logger:
            return self.context_to_logger[context]

        try:
            handle = context.tasker._handle
            device_name = self.handle_to_device.get(handle)
            if device_name:
                logger = self.get_device_logger(device_name)
                self.context_to_logger[context] = logger
                return logger
            else:
                app_logger = self.get_app_logger()
                app_logger.warning(f"No device found for handle: {handle}, using app logger")
                self.context_to_logger[context] = app_logger
                return app_logger
        except (AttributeError, Exception) as e:
            app_logger = self.get_app_logger()
            if app_logger:
                app_logger.warning(f"Error getting context logger: {str(e)}")
            self.context_to_logger[context] = app_logger
            return app_logger

    @staticmethod
    def sync_to_app(level: str = 'info') -> Callable:
        """Decorator: syncs a device log to the application log."""
        def decorator(func):
            @functools.wraps(func)
            def wrapper(logger, message, *args, **kwargs):
                result = func(logger, message, *args, **kwargs)
                try:
                    log_manager = logger.log_manager
                    app_logger = log_manager.get_app_logger()
                    if app_logger and app_logger != logger:
                        device_name = "unknown"
                        for name, lg in log_manager.loggers.items():
                            if lg == logger and name.startswith("device_"):
                                device_name = name[7:]
                                break
                        log_method = getattr(app_logger, level)
                        log_method(f"[{device_name}] {message}")
                except Exception:
                    pass
                return result
            return wrapper
        return decorator

    def set_device_handle(self, device_name: str, handle: Any) -> None:
        """Associate a handle with a device name"""
        self.get_device_logger(device_name)
        self.handle_to_device[handle] = device_name
        self.context_to_logger.clear()

    def get_device_logs(self, device_name: str) -> List[str]:
        """Retrieve all logs for a specific device from the current session"""
        self.flush_all_logs() # Ensure buffer is written to file before reading
        log_file = os.path.join(self.log_dir, f"{device_name}.log")
        if not os.path.exists(log_file):
            return []

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        session_lines = []
        for line in all_lines:
            try:
                timestamp_str = line.split(' - ')[0].strip()
                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                if log_time >= self.session_start_time:
                    session_lines.append(line)
            except (ValueError, IndexError):
                session_lines.append(line)
        return session_lines

    def get_all_logs(self) -> List[str]:
        """Retrieve all logs from the main application log from the current session"""
        self.flush_all_logs() # Ensure buffer is written to file before reading
        log_file = os.path.join(self.log_dir, "app.log")
        if not os.path.exists(log_file):
            return []

        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        session_lines = []
        for line in all_lines:
            try:
                timestamp_str = line.split(' - ')[0].strip()
                log_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                if log_time >= self.session_start_time:
                    session_lines.append(line)
            except (ValueError, IndexError):
                session_lines.append(line)
        return session_lines


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


class ContextLogger:
    """Helper class to provide context-based logging capabilities"""
    @staticmethod
    def add_context_logging(logger, log_manager):
        logger.log_manager = log_manager
        def log_with_context(level, context, message):
            log_method = getattr(logger, level)
            log_method(message)
            try:
                app_logger = log_manager.get_app_logger()
                if app_logger and app_logger != logger:
                    device_name = "unknown"
                    for name, lg in log_manager.loggers.items():
                        if lg == logger and name.startswith("device_"):
                            device_name = name[7:]
                            break
                    app_log_method = getattr(app_logger, level)
                    app_log_method(f"[{device_name}] {message}")
            except Exception:
                pass

        logger.debug_context = lambda context, message: log_with_context("debug", context, message)
        logger.info_context = lambda context, message: log_with_context("info", context, message)
        logger.warning_context = lambda context, message: log_with_context("warning", context, message)
        logger.error_context = lambda context, message: log_with_context("error", context, message)
        logger.critical_context = lambda context, message: log_with_context("critical", context, message)
        return logger


# Create a singleton instance
log_manager = LogManager()
app_logger = log_manager.get_app_logger()