# -*- coding: UTF-8 -*-
"""
日志管理器 - 重构版
使用内存缓冲区替代文件读取，优化UI显示性能
"""

import functools
import logging
import logging.handlers
import os
import sys
import zipfile
import atexit
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Callable, Optional, Deque

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


@dataclass
class LogRecord:
    """日志记录数据类，用于内存缓冲和UI显示"""
    timestamp: datetime
    level: str
    message: str
    device_name: Optional[str] = None  # None表示app日志
    
    def to_formatted_string(self) -> str:
        """转换为格式化的日志字符串"""
        time_str = self.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        return f"{time_str} - {self.level} - {self.message}"
    
    def to_display_string(self) -> str:
        """转换为用于UI显示的简化字符串（仅时间和消息）"""
        time_str = self.timestamp.strftime('%H:%M:%S')
        return f"{time_str} {self.message}"


class LogBuffer:
    """
    内存日志缓冲区
    维护当前会话的日志记录，供UI快速读取
    """
    def __init__(self, max_size: int = 2000):
        self.max_size = max_size
        self.app_logs: Deque[LogRecord] = deque(maxlen=max_size)
        self.device_logs: Dict[str, Deque[LogRecord]] = defaultdict(
            lambda: deque(maxlen=max_size)
        )
        self._lock = None  # 可以添加线程锁如果需要
    
    def add_app_log(self, record: LogRecord) -> None:
        """添加应用程序日志"""
        self.app_logs.append(record)
    
    def add_device_log(self, device_name: str, record: LogRecord) -> None:
        """添加设备日志"""
        record.device_name = device_name
        self.device_logs[device_name].append(record)
    
    def get_app_logs(self) -> List[LogRecord]:
        """获取所有应用程序日志"""
        return list(self.app_logs)
    
    def get_device_logs(self, device_name: str) -> List[LogRecord]:
        """获取指定设备的所有日志"""
        return list(self.device_logs.get(device_name, []))
    
    def get_all_logs(self) -> List[LogRecord]:
        """获取所有日志（app + 所有设备），按时间排序"""
        all_records = list(self.app_logs)
        for device_logs in self.device_logs.values():
            all_records.extend(device_logs)
        return sorted(all_records, key=lambda r: r.timestamp)
    
    def clear(self) -> None:
        """清空所有日志"""
        self.app_logs.clear()
        self.device_logs.clear()
    
    def clear_device(self, device_name: str) -> None:
        """清空指定设备的日志"""
        if device_name in self.device_logs:
            self.device_logs[device_name].clear()


class LogManager(QObject):
    """
    日志管理器 - 重构版
    - 使用内存缓冲区存储当前会话日志
    - 信号携带LogRecord对象，无节流
    - 保持文件异步写入
    """
    # 新信号：携带日志记录对象
    app_log_added = Signal(object)          # LogRecord
    device_log_added = Signal(str, object)  # device_name, LogRecord
    
    # 保留旧信号以保持兼容性（但不再推荐使用）
    app_log_updated = Signal()
    device_log_updated = Signal(str)

    def __init__(self):
        super().__init__()
        self.loggers: Dict[str, logging.Logger] = {}
        self.log_dir = "logs"
        self.backup_dir = os.path.join(self.log_dir, "backup")
        self.handle_to_device: Dict[Any, str] = {}
        self.context_to_logger: Dict[Any, logging.Logger] = {}
        
        # 内存日志缓冲区
        self.log_buffer = LogBuffer(max_size=2000)
        
        # 使用队列处理器实现异步日志写入
        self.log_queue = Queue(maxsize=1000)
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
        """启动队列监听器，负责从队列中取出日志并写入文件"""
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
        logger.propagate = False

        # 清除任何现有的处理器以避免重复
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        sanitized_log_file = self._sanitize_filename(log_file)
        file_path = os.path.join(self.log_dir, sanitized_log_file)

        # 创建文件处理器
        file_handler = logging.FileHandler(file_path, encoding='utf-8', mode='a')
        file_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.file_handlers[name] = file_handler

        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)

        # 更新队列监听器
        if self.queue_listener:
            self.queue_listener.stop()
        
        all_handlers = list(self.file_handlers.values())
        self.queue_listener = logging.handlers.QueueListener(
            self.log_queue,
            *all_handlers,
            console_handler,
            respect_handler_level=True
        )
        self.queue_listener.start()

        # 为logger添加队列处理器（用于异步文件写入）
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        logger.addHandler(queue_handler)

        # 添加信号处理器（用于UI更新和内存缓冲）
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

    # ========== 新API：从内存缓冲区获取日志 ==========
    
    def get_app_log_records(self) -> List[LogRecord]:
        """获取应用程序日志记录列表"""
        return self.log_buffer.get_app_logs()
    
    def get_device_log_records(self, device_name: str) -> List[LogRecord]:
        """获取设备日志记录列表"""
        return self.log_buffer.get_device_logs(device_name)
    
    def get_all_log_records(self) -> List[LogRecord]:
        """获取所有日志记录，按时间排序"""
        return self.log_buffer.get_all_logs()

    # ========== 兼容旧API：返回格式化字符串 ==========
    
    def get_device_logs(self, device_name: str) -> List[str]:
        """从内存缓冲区获取设备日志（兼容旧API）"""
        records = self.log_buffer.get_device_logs(device_name)
        return [record.to_formatted_string() for record in records]

    def get_all_logs(self) -> List[str]:
        """从内存缓冲区获取应用日志（兼容旧API）"""
        records = self.log_buffer.get_app_logs()
        return [record.to_formatted_string() for record in records]
    
    def add_device_log(self, device_name: str, log_entry: str) -> None:
        """手动添加设备日志条目（兼容旧API）"""
        # 解析日志条目
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
        self.log_buffer.add_device_log(device_name, record)
        self.device_log_added.emit(device_name, record)
        self.device_log_updated.emit(device_name)


class AppLogSignalHandler(logging.Handler):
    """
    应用日志信号处理器
    - 将日志记录添加到内存缓冲区
    - 发出携带LogRecord的信号
    - 无节流限制，保证实时性
    """
    def __init__(self, log_manager: LogManager):
        super().__init__()
        self.log_manager = log_manager

    def emit(self, record: logging.LogRecord):
        try:
            # 创建LogRecord对象
            log_record = LogRecord(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                message=self.format_message(record),
                device_name=None
            )
            
            # 添加到内存缓冲区
            self.log_manager.log_buffer.add_app_log(log_record)
            
            # 发出新信号（携带日志记录）
            self.log_manager.app_log_added.emit(log_record)
            
            # 发出旧信号（兼容性）
            self.log_manager.app_log_updated.emit()
            
        except Exception:
            # 日志处理器不应抛出异常
            pass
    
    def format_message(self, record: logging.LogRecord) -> str:
        """格式化日志消息"""
        return record.getMessage()


class DeviceLogSignalHandler(logging.Handler):
    """
    设备日志信号处理器
    - 将日志记录添加到设备专属的内存缓冲区
    - 发出携带LogRecord的信号
    - 无节流限制，保证实时性
    """
    def __init__(self, device_name: str, log_manager: LogManager):
        super().__init__()
        self.device_name = device_name
        self.log_manager = log_manager

    def emit(self, record: logging.LogRecord):
        try:
            # 创建LogRecord对象
            log_record = LogRecord(
                timestamp=datetime.fromtimestamp(record.created),
                level=record.levelname,
                message=self.format_message(record),
                device_name=self.device_name
            )
            
            # 添加到设备日志缓冲区
            self.log_manager.log_buffer.add_device_log(self.device_name, log_record)
            
            # 发出新信号（携带设备名和日志记录）
            self.log_manager.device_log_added.emit(self.device_name, log_record)
            
            # 发出旧信号（兼容性）
            self.log_manager.device_log_updated.emit(self.device_name)
            
        except Exception:
            # 日志处理器不应抛出异常
            pass
    
    def format_message(self, record: logging.LogRecord) -> str:
        """格式化日志消息"""
        return record.getMessage()


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
