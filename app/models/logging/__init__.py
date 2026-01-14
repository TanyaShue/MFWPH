# -*- coding: UTF-8 -*-
"""
日志模块

提供统一的日志管理接口:
- LogManager: 日志管理器单例
- LogRecord: 日志记录数据类
- LogBuffer: 内存日志缓冲区
- log_manager: 全局日志管理器实例
- app_logger: 应用程序日志器
"""

from app.models.logging.log_manager import (
    LogManager,
    LogRecord,
    LogBuffer,
    log_manager,
    app_logger,
)

__all__ = [
    "LogManager",
    "LogRecord",
    "LogBuffer",
    "log_manager",
    "app_logger",
]
