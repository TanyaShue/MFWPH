from PySide6.QtCore import QObject, Signal, QThread

from app.utils.update.models import UpdateInfo, UpdateSource
from app.utils.update.installer.base import BaseInstaller
from app.utils.update.installer.github import GithubInstaller
from app.utils.update.installer.mirror import MirrorInstaller
from app.utils.update.installer.app import AppInstaller
from app.models.config.resource_config import ResourceConfig
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class UpdateInstallerFactory(QObject):
    """
    安装器工厂，根据更新源创建、配置并运行合适的安装器。
    """
    install_started = Signal(str)
    install_completed = Signal(str, str, list)
    install_failed = Signal(str, str)
    restart_required = Signal()

    def __init__(self):
        super().__init__()
        self.installer: BaseInstaller = None
        self.thread: QThread = None

    def install_update(self, update_info: UpdateInfo, file_path: str, resource: ResourceConfig | None = None):
        """
        【已修改】主安装方法。resource 参数现在是可选的。
        """

        effective_source = update_info.source
        if update_info.resource_name == "MFWPH 主程序":
            logger.debug(f"检测到主程序更新。将更新源从 {update_info.source.name} 强制更正为 APP。")
            effective_source = UpdateSource.APP

        logger.info(f"安装器工厂正在为更新源 {effective_source.name} 创建安装器")

        if self.thread and self.thread.isRunning():
            logger.warning("一个安装任务已在进行中。")
            self.install_failed.emit(update_info.resource_name, "另一个安装正在进行中")
            return

        installer_class = None
        if effective_source == UpdateSource.GITHUB:
            if not resource:
                # 理论上修复后不会进入此分支，但保留作为安全校验
                self.install_failed.emit(update_info.resource_name, "GitHub 资源更新需要 resource 对象")
                return
            self.installer = GithubInstaller(resource, update_info, file_path)
            installer_class = "GithubInstaller"
        elif effective_source == UpdateSource.MIRROR:
            if not resource:
                self.install_failed.emit(update_info.resource_name, "Mirror酱资源更新需要 resource 对象")
                return
            self.installer = MirrorInstaller(resource, update_info, file_path)
            installer_class = "MirrorInstaller"
        elif effective_source == UpdateSource.APP:
            self.installer = AppInstaller(update_info, file_path)
            installer_class = "AppInstaller"
        else:
            error_msg = f"不支持的更新源: {update_info.source}"
            logger.error(error_msg)
            self.install_failed.emit(update_info.resource_name, error_msg)
            return

        logger.debug(f"已成功创建 '{installer_class}' 实例。")

        self.thread = QThread()
        self.installer.moveToThread(self.thread)
        logger.debug(f"'{installer_class}' 已移动到新的 QThread。")

        # 连接信号
        self.installer.install_started.connect(self.install_started)
        self.installer.install_completed.connect(self.install_completed)
        self.installer.install_failed.connect(self.install_failed)
        self.installer.restart_required.connect(self.restart_required)
        self.thread.started.connect(self.installer.install)
        logger.debug("所有信号已连接。")

        def on_finished():
            logger.debug(f"'{installer_class}' 的 QThread 已结束。开始清理。")
            self.thread.quit()
            self.thread.wait()
            self.installer.deleteLater()
            self.thread.deleteLater()
            self.installer = None
            self.thread = None
            logger.debug("安装器和 QThread 已被清理。")

        self.installer.install_completed.connect(on_finished)
        self.installer.install_failed.connect(on_finished)
        self.installer.restart_required.connect(on_finished)

        logger.info("正在启动安装器线程...")
        self.thread.start()