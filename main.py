import asyncio
import os
import sys

import psutil
from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QPalette, QColor
from qasync import QEventLoop

from app.models.logging.log_manager import log_manager
from app.main_window import MainWindow
from app.utils.notification_manager import notification_manager
from app.models.config.global_config import global_config
from app.pages.settings_page import AppUpdateChecker

# 获取应用程序日志记录器
logger = log_manager.get_app_logger()


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


class StartupUpdateChecker:
    """启动时的更新检查器"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.update_checker_thread = None

    def check_for_updates(self):
        """检查是否需要自动检查更新"""
        try:
            # 获取自动检查更新配置
            auto_check = global_config.get_app_config().auto_check_update
            if not isinstance(auto_check, bool):
                auto_check = False

            if auto_check:
                logger.info("自动检查更新已启用，开始检查...")
                # 显示正在检查更新的通知
                notification_manager.show_info(
                    "正在后台检查应用更新...",
                    "自动更新检查"
                )

                # 创建并启动更新检查线程
                self.update_checker_thread = AppUpdateChecker()
                self.update_checker_thread.update_found.connect(self._handle_update_found)
                self.update_checker_thread.update_not_found.connect(self._handle_update_not_found)
                self.update_checker_thread.check_failed.connect(self._handle_check_failed)
                self.update_checker_thread.start()
            else:
                logger.info("自动检查更新未启用")

        except Exception as e:
            logger.error(f"启动时检查更新配置失败: {e}")

    def _handle_update_found(self, latest_version, current_version, download_url):
        """处理发现更新的情况"""
        logger.info(f"发现新版本: {latest_version} (当前版本: {current_version})")

        # 使用通知管理器显示更新可用的通知
        notification_manager.show_warning(
            f"发现新版本 {latest_version} 可用！\n当前版本：{current_version}\n请前往设置页面更新。",
            "有可用更新",
            duration=10000  # 显示10秒
        )

        # 可选：存储更新信息供后续使用
        if hasattr(self.main_window, 'set_update_available'):
            self.main_window.set_update_available(True, latest_version)

    def _handle_update_not_found(self):
        """处理未发现更新的情况"""
        logger.info("当前已是最新版本")
        # 启动时如果没有更新，不显示通知，避免打扰用户

    def _handle_check_failed(self, error_message):
        """处理检查失败的情况"""
        logger.error(f"自动检查更新失败: {error_message}")
        # 只在日志中记录，不显示通知，避免启动时的错误提示打扰用户


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
    notification_manager.set_reference_window(window)
    window.show()

    # 显示启动成功通知
    QTimer.singleShot(500, lambda: notification_manager.show_success("MFWPH 启动成功!", "欢迎来到MFWPH"))

    # 创建启动更新检查器
    startup_checker = StartupUpdateChecker(window)

    # 延迟1秒后检查更新，确保主窗口完全加载
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    sys.exit(app.exec())