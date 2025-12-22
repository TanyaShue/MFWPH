# --- app/exit_handler.py ---
"""
退出处理模块
负责应用的优雅退出和清理
"""

import asyncio
import os

from core.tasker_manager import task_manager
from app.utils.until import kill_processes
from app.utils.global_logger import get_logger


logger = get_logger()


async def force_exit_cleanup():
    """强制退出清理函数"""
    logger.info("开始强制退出清理...")

    try:
        # 快速停止所有任务（最多等待2秒）
        logger.info("停止所有任务...")
        await asyncio.wait_for(task_manager.stop_all(), timeout=2.0)
        logger.info("任务管理器已停止")
    except asyncio.TimeoutError:
        logger.warning("任务停止超时，继续退出")
    except Exception as e:
        logger.error(f"停止任务时出错: {e}")

    try:
        # 快速清理子进程
        kill_processes()
        logger.info("子进程已清理")
    except Exception as e:
        logger.error(f"清理子进程时出错: {e}")

    logger.info("强制退出进程...")
    os._exit(1)


async def perform_graceful_shutdown(loop, app, window):
    logger.info("🛑 Graceful shutdown started")

    # 1️⃣ UI 立刻消失（如果有窗口的话）
    try:
        if window:
            window.hide()
        if app:
            app.processEvents()
    except Exception:
        pass

    # 2️⃣ 尝试优雅关闭后台任务（最多 3 秒）
    try:
        logger.info("Stopping task manager (timeout=3s)...")
        await asyncio.wait_for(task_manager.stop_all(), timeout=3)
        logger.info("Task manager stopped cleanly.")
    except asyncio.TimeoutError:
        logger.warning("Task manager shutdown timed out.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    # 3️⃣ 清理子进程兜底
    try:
        kill_processes()
    except Exception:
        pass

    # 4️⃣ 停止事件循环
    try:
        loop.stop()
    except Exception:
        pass

    # 5️⃣ Qt quit + OS 级强退（双保险）
    logger.info("💀 Forcing process exit.")
    try:
        if app:
            app.quit()
    except Exception:
        pass

    os._exit(0)  # 最终兜底，确保不留后台
