# --- app/utils/global_logger.py ---
"""
全局日志管理器
提供统一的logger访问接口，避免每个模块重复实现logger设置
"""

import logging
from typing import Optional


# 全局logger实例
_app_logger: Optional[logging.Logger] = None


def set_global_logger(logger: logging.Logger) -> None:
    """设置全局应用logger"""
    global _app_logger
    _app_logger = logger


def get_logger() -> logging.Logger:
    """获取全局应用logger"""
    if _app_logger is None:
        # 如果logger未设置，返回一个临时的控制台logger
        temp_logger = logging.getLogger("temp_mfwph")
        if not temp_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            temp_logger.addHandler(handler)
            temp_logger.setLevel(logging.INFO)
        return temp_logger

    return _app_logger


def initialize_global_logger(log_manager_instance) -> None:
    """初始化全局logger（兼容旧接口）"""
    logger = log_manager_instance.get_app_logger()
    set_global_logger(logger)
