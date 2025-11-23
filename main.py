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

if sys.platform == "win32":
    import ctypes
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_AWAYMODE_REQUIRED = 0x00000040

    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    )
    ctypes.windll.kernel32.SetErrorMode(0x8003)

logger = log_manager.get_app_logger()


def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))


def stop_event_loop():
    """确保在退出应用时完全停止 asyncio 事件循环"""
    loop = asyncio.get_event_loop()
    if loop.is_running():
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

    app = QApplication(sys.argv)
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

    # ---- 修复关键点：Qt退出时同时停止 asyncio ----
    app.aboutToQuit.connect(kill_processes)
    app.aboutToQuit.connect(stop_event_loop)

    # ---- 最终运行事件循环 ----
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
