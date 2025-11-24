# --- main.py ---
import asyncio
import os
import sys
import argparse

import qasync
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyleFactory

from app.main_window import MainWindow
from app.models.logging.log_manager import log_manager
from app.utils.notification_manager import notification_manager
from app.utils.until import clean_up_old_pyinstaller_temps, load_light_palette, \
    StartupResourceUpdateChecker, kill_processes

# ... (Windows ctypes 设置保持不变) ...

logger = log_manager.get_app_logger()


def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


async def shutdown_tasks():
    """优雅地取消所有未完成的异步任务"""
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    if not tasks:
        return

    logger.info(f"Cleaning up {len(tasks)} pending tasks...")
    for task in tasks:
        task.cancel()

    # 等待所有任务取消完成，避免报错
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All tasks cancelled.")


def cleanup_and_exit(loop, app):
    """统一的退出清理入口"""
    try:
        # 1. 执行进程清理 (你原本的 kill_processes)
        kill_processes()

        # 2. 安排异步任务清理
        # 我们创建一个新的 task 来运行 shutdown_tasks，然后停止 loop
        async def _do_shutdown():
            await shutdown_tasks()
            loop.stop()

        asyncio.ensure_future(_do_shutdown(), loop=loop)

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
        loop.stop()


def main():
    base_path = get_base_path()
    clean_up_old_pyinstaller_temps()

    os.chdir(base_path)

    parser = argparse.ArgumentParser(description="MFWPH Application")
    parser.add_argument('-auto', action='store_true', help='Automatically start tasks 5 seconds after launch.')
    parser.add_argument('-s', nargs='+', default=['all'], help='Specify device names to auto-start. Default is "all".')
    parser.add_argument('-exit_on_complete', action='store_true', help='Exit after auto-started tasks are complete.')
    args = parser.parse_args()

    # 修复: 设置 setQuitOnLastWindowClosed(False) 
    # 这样我们可以完全控制退出的时机（尤其是有托盘图标时）
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(load_light_palette())

    icon_path = os.path.join(base_path, 'assets', 'icons', 'app', 'logo.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    notification_manager.set_reference_window(window)
    window.show()

    startup_checker = StartupResourceUpdateChecker(window)
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    # ---- 关键修复：将清理逻辑挂载到 aboutToQuit ----
    # 当 app.quit() 被调用时，这个信号触发
    app.aboutToQuit.connect(lambda: cleanup_and_exit(loop, app))

    # ---- 最终运行事件循环 ----
    with loop:
        try:
            loop.run_forever()
        finally:
            # 确保彻底退出，防止 console 窗口残留
            sys.exit(0)


if __name__ == "__main__":
    main()