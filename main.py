# --- main.py ---
import asyncio
import os
import sys
import argparse
import multiprocessing
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtWidgets import QApplication, QStyleFactory
import qasync

from app.main_window import MainWindow
from app.models.logging.log_manager import log_manager
from app.models.config.global_config import global_config
from app.utils.notification_manager import notification_manager
from app.utils.until import (
    clean_up_old_pyinstaller_temps,
    load_light_palette,
    StartupResourceUpdateChecker,
    kill_processes,
)

from core.tasker_manager import task_manager

logger = log_manager.get_app_logger()

_job_handle = None


# -----------------------------------------------------------------------------
# Windows Job Object（保持）
# -----------------------------------------------------------------------------
def setup_windows_job_object():
    if sys.platform != "win32":
        return

    global _job_handle
    try:
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ctypes.windll.kernel32.SetInformationJobObject(
            h_job, 9, ctypes.pointer(info), ctypes.sizeof(info)
        )
        ctypes.windll.kernel32.AssignProcessToJobObject(
            h_job, ctypes.windll.kernel32.GetCurrentProcess()
        )

        _job_handle = h_job
        logger.info("Windows Job Object enabled.")

    except Exception as e:
        logger.error(f"Job Object setup failed: {e}")


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# -----------------------------------------------------------------------------
# ✅ 真正可靠的退出流程（必达）
# -----------------------------------------------------------------------------
async def perform_graceful_shutdown(loop, app, window):
    logger.info("🛑 Graceful shutdown started")

    # 1️⃣ UI 立刻消失
    try:
        window.hide()
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
        app.quit()
    except Exception:
        pass

    os._exit(0)  # 最终兜底，确保不留后台


# -----------------------------------------------------------------------------
# 关闭事件 Patch（修复版）
# -----------------------------------------------------------------------------
def patch_mainwindow_exit_logic(window: MainWindow, loop, app):
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

        # 👉 仅“最小化到托盘”时阻止关闭
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


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
def main():
    multiprocessing.freeze_support()
    setup_windows_job_object()

    base_path = get_base_path()
    clean_up_old_pyinstaller_temps()
    os.chdir(base_path)

    parser = argparse.ArgumentParser()
    parser.add_argument("-auto", action="store_true")
    parser.add_argument("-s", nargs="+", default=["all"])
    parser.add_argument("-exit_on_complete", action="store_true")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # ❗ 关键：允许 Qt 正常在窗口关闭时退出
    app.setQuitOnLastWindowClosed(True)

    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(load_light_palette())

    icon_path = os.path.join(base_path, "assets", "icons", "app", "logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    notification_manager.set_reference_window(window)

    patch_mainwindow_exit_logic(window, loop, app)

    window.show()

    startup_checker = StartupResourceUpdateChecker(window)
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
