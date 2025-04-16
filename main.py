import asyncio
import os
import sys

import psutil
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from app.models.logging.log_manager import log_manager


def kill_processes():
    app_logger = log_manager.get_app_logger()

    # 获取当前进程
    current_process = psutil.Process(os.getpid())
    current_process_name = current_process.name()

    # 查找并终止所有ADB进程
    for proc in psutil.process_iter(['name', 'pid']):
        proc_name = proc.info.get('name', '')
        if proc_name.lower() == "adb.exe":
            try:
                proc.kill()
                app_logger.info(f"Killed adb.exe process with pid {proc.pid}")
            except Exception as e:
                app_logger.error(f"Failed to kill adb.exe process with pid {proc.pid}: {e}")

    # 查找并终止与当前程序同名的其他进程及其子进程（不包括当前进程）
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            proc_name = proc.info.get('name', '')
            proc_pid = proc.info.get('pid')

            # 如果进程与当前进程同名但不是当前进程
            if proc_name == current_process_name and proc_pid != current_process.pid:
                # 首先终止所有子进程
                children = proc.children(recursive=True)
                for child in children:
                    try:
                        child.kill()
                        app_logger.info(f"Killed child process {child.name()} with pid {child.pid}")
                    except Exception as e:
                        app_logger.error(f"Failed to kill child process with pid {child.pid}: {e}")

                # 然后终止主进程
                proc.kill()
                app_logger.info(f"Killed process {proc_name} with pid {proc_pid}")
        except Exception as e:
            app_logger.error(f"Error handling process: {e}")

    # 记录完成信息
    app_logger.info("Process cleanup completed")


from app.main_window import MainWindow

if __name__ == "__main__":
    # setup_sys_redirection()
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.aboutToQuit.connect(kill_processes)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
