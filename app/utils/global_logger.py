# -*- coding: UTF-8 -*-
"""
全局日志管理器
提供统一的logger访问接口，避免每个模块重复实现logger设置

使用方式:
    from app.utils.global_logger import get_logger, get_device_logger
    
    # 获取应用日志器
    logger = get_logger()
    logger.info("应用日志")
    
    # 获取设备日志器
    device_logger = get_device_logger("设备名")
    device_logger.info("设备日志")
"""

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.logging.log_manager import LogManager

# 全局日志管理器实例
_log_manager: Optional["LogManager"] = None
_app_logger: Optional[logging.Logger] = None


def set_global_logger(logger: logging.Logger) -> None:
    """设置全局应用logger（向后兼容）"""
    global _app_logger
    _app_logger = logger


def set_log_manager(log_manager_instance: "LogManager") -> None:
    """设置全局日志管理器实例"""
    global _log_manager, _app_logger
    _log_manager = log_manager_instance
    _app_logger = log_manager_instance.get_app_logger()


def get_log_manager() -> Optional["LogManager"]:
    """获取全局日志管理器实例"""
    return _log_manager


def get_logger() -> logging.Logger:
    """
    获取全局应用logger
    
    这是获取应用日志器的推荐方式。
    
    Returns:
        logging.Logger: 应用程序日志器
    """
    if _app_logger is not None:
        return _app_logger
    
    # 如果logger未设置，尝试从日志管理器获取
    if _log_manager is not None:
        return _log_manager.get_app_logger()
    
    # 返回临时控制台logger
    temp_logger = logging.getLogger("temp_mfwph")
    if not temp_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        temp_logger.addHandler(handler)
        temp_logger.setLevel(logging.INFO)
    return temp_logger


def get_device_logger(device_name: str) -> logging.Logger:
    """
    获取设备专属日志器
    
    每个设备有独立的日志器，日志会写入设备专属的日志文件。
    
    Args:
        device_name: 设备名称
        
    Returns:
        logging.Logger: 设备日志器
    """
    if _log_manager is not None:
        return _log_manager.get_device_logger(device_name)
    
    # 如果日志管理器未初始化，返回临时logger
    temp_logger = logging.getLogger(f"temp_device_{device_name}")
    if not temp_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        temp_logger.addHandler(handler)
        temp_logger.setLevel(logging.INFO)
    return temp_logger


def initialize_global_logger(log_manager_instance: "LogManager") -> None:
    """
    初始化全局日志器
    
    应在应用启动时调用此函数。
    
    Args:
        log_manager_instance: LogManager实例
    """
    set_log_manager(log_manager_instance)


# 便捷的日志函数（可选使用）
def debug(message: str) -> None:
    """记录DEBUG级别日志"""
    get_logger().debug(message)


def info(message: str) -> None:
    """记录INFO级别日志"""
    get_logger().info(message)


def warning(message: str) -> None:
    """记录WARNING级别日志"""
    get_logger().warning(message)


def error(message: str) -> None:
    """记录ERROR级别日志"""
    get_logger().error(message)


def critical(message: str) -> None:
    """记录CRITICAL级别日志"""
    get_logger().critical(message)
