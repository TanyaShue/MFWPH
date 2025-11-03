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

    # 设置系统状态，防止进入休眠
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_AWAYMODE_REQUIRED = 0x00000040  # Windows Vista+ 支持 Away Mode

    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
    )
    ctypes.windll.kernel32.SetErrorMode(0x8003)

# 获取应用程序日志记录器
logger = log_manager.get_app_logger()

def get_base_path():
    """
    获取资源文件的绝对基础路径。
    这对于在开发环境和打包后的应用中都能正确定位资源文件至关重要。
    """
    if getattr(sys, 'frozen', False):
        # 如果应用被 PyInstaller 打包（无论是单文件还是单目录）
        # `sys.executable` 指向的是可执行文件（例如 MFWPH）的路径
        return os.path.dirname(sys.executable)
    else:
        # 如果是在正常的开发环境中运行 .py 脚本
        # `__file__` 指向当前脚本的路径
        return os.path.dirname(os.path.abspath(__file__))

def main():
    """
    主函数
    """
    # 1. 获取可靠的程序根目录
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

    # --- 添加系统托盘图标 ---
    icon_path = os.path.join(base_path, 'assets', 'icons', 'app', 'logo.png')

    if os.path.exists(icon_path):
        # 创建 QIcon 对象
        app_icon = QIcon(icon_path)

        # 设置应用程序的窗口图标（对所有窗口生效）
        app.setWindowIcon(app_icon)

    # 设置异步事件循环
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 创建并显示主窗口
    window = MainWindow()
    notification_manager.set_reference_window(window)
    window.show()

    # 创建启动资源更新检查器
    startup_checker = StartupResourceUpdateChecker(window)

    # 延迟1秒后检查更新，确保主窗口完全加载
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    # 设置退出时的清理
    app.aboutToQuit.connect(kill_processes)

    # 运行事件循环
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()