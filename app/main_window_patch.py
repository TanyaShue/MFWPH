# --- app/main_window_patch.py ---
"""
主窗口补丁模块
负责主窗口的退出逻辑补丁
"""

import asyncio
import os

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from app.models.config.global_config import global_config
from app.utils.global_logger import get_logger
from app.exit_handler import perform_graceful_shutdown


logger = get_logger()


def patch_mainwindow_exit_logic(window, loop, app):
    """为主窗口应用退出逻辑补丁"""
    def save_window_config():
        try:
            size = window.size()
            pos = window.pos()
            app_config = global_config.get_app_config()
            app_config.window_size = f"{size.width()}x{size.height()}"
            app_config.window_position = f"{pos.x()},{pos.y()}"
            global_config.save_all_configs()
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def patched_close_event(event: QCloseEvent):
        app_config = global_config.get_app_config()

        # 👉 仅"最小化到托盘"时阻止关闭
        if app_config.minimize_to_tray_on_close:
            event.ignore()
            window.hide()
            return

        # 👉 真正退出
        logger.info("User requested exit (window close).")
        save_window_config()

        event.accept()  # 允许 Qt 关闭窗口
        asyncio.create_task(
            perform_graceful_shutdown(loop, app, window)
        )

    def patched_force_quit():
        logger.info("User requested exit (tray).")
        save_window_config()
        asyncio.create_task(
            perform_graceful_shutdown(loop, app, window)
        )

    window.closeEvent = patched_close_event
    window.force_quit = patched_force_quit

    logger.info("MainWindow exit logic patched (safe-exit mode).")
