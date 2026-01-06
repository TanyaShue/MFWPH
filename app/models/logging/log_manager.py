import functools
import logging
import logging.handlers
import os
import sys
import zipfile
import atexit
from datetime import datetime
from typing import Dict, List, Any, Callable, Optional
from queue import Queue

# 尝试导入Qt，如果失败则使用纯Python实现
try:
    from PySide6.QtCore import QObject, Signal
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    # 如果Qt不可用，创建一个简单的基类
    class QObject:
        def __init__(self):
            pass
    
    class Signal:
        def __init__(self, *args):
            self._callbacks = []
        
        def connect(self, callback):
            self._callbacks.append(callback)
        
        def disconnect(self, callback):
            if callback in self._callbacks:
                self._callbacks.remove(callback)
        
        def emit(self, *args, **kwargs):
            for callback in self._callbacks:
                try:
                    callback(*args, **kwargs)
                except Exception:
                    pass


class LogManager(QObject):
    """
    管理应用程序日志，支持全局日志和设备特定日志
    使用QueueHandler + QueueListener实现异步日志写入，确保日志不丢失
    """
    # 日志更新信号
    app_log_updated = Signal()
    device_log_updated = Signal(str)  # device_name

    def __init__(self):
        super().__init__()
        self.loggers: Dict[str, logging.Logger] = {}
        self.log_dir = "logs"
        self.backup_dir = os.path.join(self.log_dir, "backup")
        self.handle_to_device: Dict[Any, str] = {}
        self.context_to_logger: Dict[Any, logging.Logger] = {}
        
        # 使用队列处理器实现异步日志 - 使用有界队列避免内存溢出
        self.log_queue = Queue(maxsize=1000)  # 最大1000条日志队列
        self.queue_listener: Optional[logging.handlers.QueueListener] = None
        self.file_handlers: Dict[str, logging.FileHandler] = {}

        self.session_start_time = datetime.now()
        self.session_start_str = self.session_start_time.strftime("%Y-%m-%d %H:%M:%S")

        self._ensure_directories()
        self._check_and_backup_logs()

        # 启动队列监听器
        self._start_queue_listener()

        # 初始化应用日志
        self.initialize_logger("app", "app.log")

        app_logger = self.get_app_logger()
        if app_logger:
            app_logger.info(f"=== 新会话开始于 {self.session_start_str} ===")

        # 注册退出时的清理函数
        atexit.register(self.shutdown)

    def _start_queue_listener(self):
        """启动队列监听器，负责从队列中取出日志并写入"""
        # QueueListener会在后台线程中处理所有的handler
        # 我们暂时创建一个空的listener，稍后添加handlers
        self.queue_listener = logging.handlers.QueueListener(
            self.log_queue,
            respect_handler_level=True
        )
        self.queue_listener.start()

    def shutdown(self):
        """关闭日志系统，确保所有日志都被写入"""
        if self.queue_listener:
            try:
                self.queue_listener.stop()
            except Exception:
                pass
            self.queue_listener = None
        
        # 关闭所有文件处理器
        for handler in self.file_handlers.values():
            try:
                handler.flush()
                handler.close()
            except Exception:
                pass

    def _ensure_directories(self):
        """确保日志目录和备份目录存在"""
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _check_and_backup_logs(self):
        """检查日志文件大小，超过阈值则备份"""
        log_files_to_backup = []
        total_size = 0

        for filename in os.listdir(self.log_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(self.log_dir, filename)
                log_files_to_backup.append(file_path)
                total_size += os.path.getsize(file_path)

        if total_size > 1 * 1024 * 1024:  # 如果总大小 > 1MB
            self._backup_logs(log_files_to_backup)
            for file_path in log_files_to_backup:
                open(file_path, 'w', encoding='utf-8').close()

    def _backup_logs(self, log_files):
        """将日志文件备份到zip压缩包"""
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
        初始化一个logger，使用QueueHandler实现异步日志
        """
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # 不传播到父logger

        # 清除任何现有的处理器以避免重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        sanitized_log_file = self._sanitize_filename(log_file)
        file_path = os.path.join(self.log_dir, sanitized_log_file)

        # 创建文件处理器（直接写入文件，不缓冲）
        file_handler = logging.FileHandler(file_path, encoding='utf-8', mode='a')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.file_handlers[name] = file_handler

        # 创建控制台处理器（直接输出到控制台）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)

        # 将handlers添加到队列监听器
        # 停止现有的listener，添加新的handler，然后重启
        if self.queue_listener:
            self.queue_listener.stop()
        
        # 收集所有现有的handlers
        all_handlers = list(self.file_handlers.values())
        
        # 重新创建listener包含所有handlers
        self.queue_listener = logging.handlers.QueueListener(
            self.log_queue,
            *all_handlers,
            console_handler,
            respect_handler_level=True
        )
        self.queue_listener.start()

        # 为logger添加队列处理器
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        logger.addHandler(queue_handler)

        # 添加信号处理器（直接添加到logger，不通过队列）
        if name == "app":
            signal_handler = AppLogSignalHandler(self)
            signal_handler.setLevel(logging.DEBUG)
            logger.addHandler(signal_handler)
        elif name.startswith("device_"):
            device_name = name[7:]
            signal_handler = DeviceLogSignalHandler(device_name, self)
            signal_handler.setLevel(logging.DEBUG)
            logger.addHandler(signal_handler)

        # 添加上下文日志功能
        ContextLogger.add_context_logging(logger, self)

        self.loggers[name] = logger
        return logger

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名，确保其对文件系统有效"""
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\r', '\n']
        sanitized = filename
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '_')
        return sanitized.strip().strip('.') or "unnamed_device.log"

    def get_device_logger(self, device_name: str) -> logging.Logger:
        """获取或创建特定设备的logger"""
        logger_name = f"device_{device_name}"
        log_file = f"{device_name}.log"
        return self.loggers.get(logger_name) or self.initialize_logger(logger_name, log_file)

    def get_app_logger(self) -> logging.Logger:
        """获取主应用程序logger"""
        return self.loggers.get("app")

    def get_context_logger(self, context: Any) -> logging.Logger:
        """获取与上下文对象关联的logger"""
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
                app_logger.warning(f"未找到句柄对应的设备: {handle}，使用应用日志")
                self.context_to_logger[context] = app_logger
                return app_logger
        except (AttributeError, Exception) as e:
            app_logger = self.get_app_logger()
            if app_logger:
                app_logger.warning(f"获取上下文logger时出错: {str(e)}")
            self.context_to_logger[context] = app_logger
            return app_logger

    @staticmethod
    def sync_to_app(level: str = 'info') -> Callable:
        """装饰器：将设备日志同步到应用程序日志"""
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
        """关联句柄与设备名称"""
        self.get_device_logger(device_name)
        self.handle_to_device[handle] = device_name
        self.context_to_logger.clear()

    def get_device_logs(self, device_name: str) -> List[str]:
        """从当前会话检索特定设备的所有日志"""
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
        """从当前会话检索主应用程序日志的所有日志"""
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
    """自定义日志处理器，在应用日志更新时发出信号"""
    def __init__(self, log_manager):
        super().__init__()
        self.log_manager = log_manager
        self._last_emit_time = 0
        self._emit_interval = 0.1  # 最小发射间隔100ms

    def emit(self, record):
        import time
        current_time = time.time()
        # 限制信号发射频率，避免过于频繁的UI更新
        if current_time - self._last_emit_time >= self._emit_interval:
            self.log_manager.app_log_updated.emit()
            self._last_emit_time = current_time


class DeviceLogSignalHandler(logging.Handler):
    """自定义日志处理器，在设备日志更新时发出信号"""
    def __init__(self, device_name, log_manager):
        super().__init__()
        self.device_name = device_name
        self.log_manager = log_manager
        self._last_emit_time = 0
        self._emit_interval = 0.1  # 最小发射间隔100ms

    def emit(self, record):
        import time
        current_time = time.time()
        # 限制信号发射频率，避免过于频繁的UI更新
        if current_time - self._last_emit_time >= self._emit_interval:
            self.log_manager.device_log_updated.emit(self.device_name)
            self._last_emit_time = current_time


class ContextLogger:
    """辅助类，提供基于上下文的日志功能"""
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


# 创建单例实例
log_manager = LogManager()
app_logger = log_manager.get_app_logger()
