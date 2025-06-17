import asyncio
import os
import sys

import psutil
from PySide6.QtCore import QTimer, QThread, Signal
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QPalette, QColor
from qasync import QEventLoop

from app.models.config.app_config import Resource
from app.models.logging.log_manager import log_manager
from app.main_window import MainWindow
from app.utils.notification_manager import notification_manager
from app.models.config.global_config import global_config
from app.pages.settings_page import AppUpdateChecker
from app.utils.update_check import UpdateChecker

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

class StartupResourceUpdateChecker:
    """启动时的资源更新检查器"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.update_checker_thread = None
        self.resources_with_updates = []

    def check_for_updates(self):
        """检查是否需要自动检查资源更新"""
        try:
            # 获取自动检查更新配置
            auto_check = global_config.get_app_config().auto_check_update
            if not isinstance(auto_check, bool):
                auto_check = False

            if auto_check:
                logger.info("自动检查资源更新已启用，开始检查...")

                # 获取所有已安装的资源
                resources = self._get_installed_resources()

                if not resources:
                    logger.info("没有已安装的资源需要检查更新")
                    return

                # 显示正在检查更新的通知
                notification_manager.show_info(
                    f"正在后台检查 {len(resources)} 个资源的更新...",
                    "自动更新检查"
                )

                # 创建并启动资源更新检查线程
                self.update_checker_thread = UpdateChecker(resources, single_mode=False)
                self.update_checker_thread.update_found.connect(self._handle_resource_update_found)
                self.update_checker_thread.update_not_found.connect(self._handle_resource_update_not_found)
                self.update_checker_thread.check_failed.connect(self._handle_resource_check_failed)
                self.update_checker_thread.check_completed.connect(self._handle_check_completed)
                self.update_checker_thread.start()
            else:
                logger.info("自动检查更新未启用")

        except Exception as e:
            logger.error(f"启动时检查更新配置失败: {e}")

    def _get_installed_resources(self):
        """获取所有已安装的资源"""
        try:
            resources=global_config.resource_configs.values()
            return resources

        except Exception as e:
            logger.error(f"获取已安装资源列表失败: {e}")
            return []

    def _handle_resource_update_found(self, resource_name, latest_version, current_version, download_url, update_type):
        """处理发现资源更新的情况"""
        logger.info(f"资源 {resource_name} 发现新版本: {latest_version} (当前版本: {current_version})")

        # 收集有更新的资源
        self.resources_with_updates.append({
            'name': resource_name,
            'latest_version': latest_version,
            'current_version': current_version,
            'download_url': download_url,
            'update_type': update_type
        })

    def _handle_resource_update_not_found(self, resource_name):
        """处理资源未发现更新的情况"""
        logger.info(f"资源 {resource_name} 已是最新版本")

    def _handle_resource_check_failed(self, resource_name, error_message):
        """处理资源检查失败的情况"""
        logger.error(f"资源 {resource_name} 检查更新失败: {error_message}")

    def _handle_check_completed(self, total_checked, updates_found):
        """处理所有资源检查完成"""
        logger.info(f"资源更新检查完成: 共检查 {total_checked} 个资源，发现 {updates_found} 个更新")

        if updates_found > 0:
            # 构建更新通知消息
            update_list = []
            for update in self.resources_with_updates[:3]:  # 最多显示3个
                update_list.append(f"• {update['name']} → {update['latest_version']}")

            if updates_found > 3:
                update_list.append(f"• ... 以及其他 {updates_found - 3} 个资源")

            message = f"发现 {updates_found} 个资源有可用更新：\n" + "\n".join(update_list)

            # 显示更新通知
            notification_manager.show_warning(
                message + "\n\n请前往资源管理页面查看详情",
                "资源更新可用",
                duration=10000  # 显示10秒
            )

            # 可选：通知主窗口有资源更新
            if hasattr(self.main_window, 'set_resource_updates_available'):
                self.main_window.set_resource_updates_available(True, self.resources_with_updates)
        else:
            # 所有资源都是最新的，不显示通知（避免打扰用户）
            logger.info("所有资源均为最新版本")


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

    # 创建启动资源更新检查器（修改：使用资源更新检查器而不是应用更新检查器）
    startup_checker = StartupResourceUpdateChecker(window)

    # 延迟1秒后检查更新，确保主窗口完全加载
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    sys.exit(app.exec())