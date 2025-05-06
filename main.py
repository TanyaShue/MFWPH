import asyncio
import os
import sys

import psutil
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QPalette, QColor
from qasync import QEventLoop

from app.models.logging.log_manager import log_manager
from app.main_window import MainWindow


def load_light_palette() -> QPalette:
    """构造并返回一个浅色调 QPalette"""
    palette = QPalette()
    # 窗口和背景
    palette.setColor(QPalette.Window, QColor("#FFFFFF"))
    palette.setColor(QPalette.Base, QColor("#F0F0F0"))
    palette.setColor(QPalette.AlternateBase, QColor("#E0E0E0"))
    # 文本
    palette.setColor(QPalette.WindowText, QColor("#000000"))
    palette.setColor(QPalette.Text, QColor("#000000"))
    # 按钮
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#000000"))
    # 选中高亮
    palette.setColor(QPalette.Highlight, QColor("#0078D7"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    # ToolTip
    palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#000000"))
    return palette


def kill_processes():
    app_logger = log_manager.get_app_logger()

    # 获取当前进程
    current_process = psutil.Process(os.getpid())
    current_process_name = current_process.name()

    # 查找并终止所有 ADB 进程
    for proc in psutil.process_iter(['name', 'pid']):
        if proc.info.get('name', '').lower() == "adb.exe":
            try:
                proc.kill()
                app_logger.info(f"Killed adb.exe process with pid {proc.pid}")
            except Exception as e:
                app_logger.error(f"Failed to kill adb.exe process with pid {proc.pid}: {e}")

    # 查找并终止与当前程序同名的其他进程及其子进程（不包括当前进程）
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.info['name'] == current_process_name and proc.pid != current_process.pid:
                for child in proc.children(recursive=True):
                    try:
                        child.kill()
                        app_logger.info(f"Killed child process {child.name()} with pid {child.pid}")
                    except Exception as e:
                        app_logger.error(f"Failed to kill child process with pid {child.pid}: {e}")
                proc.kill()
                app_logger.info(f"Killed process {current_process_name} with pid {proc.pid}")
        except Exception as e:
            app_logger.error(f"Error handling process: {e}")

    app_logger.info("Process cleanup completed")


if __name__ == "__main__":
    # ---------- 强制浅色主题设置开始 ----------
    app = QApplication(sys.argv)

    # 1. 强制使用 Fusion 样式（不跟随系统主题）
    app.setStyle(QStyleFactory.create("Fusion"))

    # 2. 应用自定义浅色调 Palette
    app.setPalette(load_light_palette())

    # 设置异步事件循环
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.aboutToQuit.connect(kill_processes)

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())
