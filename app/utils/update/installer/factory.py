# --- START OF FILE app/utils/update/installer/factory.py ---

from PySide6.QtCore import QObject, Signal, QThread

from app.utils.update.models import UpdateInfo, UpdateSource
from app.utils.update.installer.base import BaseInstaller
from app.utils.update.installer.github import GithubInstaller
from app.utils.update.installer.mirror import MirrorInstaller
from app.models.config.resource_config import ResourceConfig
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class UpdateInstallerFactory(QObject):
    """
    安装器工厂，根据更新源创建、配置并运行合适的安装器。
    这是UI层与安装逻辑交互的唯一入口。
    """
    install_started = Signal(str)
    install_completed = Signal(str, str, list)
    install_failed = Signal(str, str)
    restart_required = Signal()

    def __init__(self):
        super().__init__()
        self.installer: BaseInstaller = None
        self.thread: QThread = None

    def install_update(self, update_info: UpdateInfo, resource: ResourceConfig, file_path: str):
        """
        主安装方法。它会创建一个安装器 "Worker" 和一个 QThread,
        然后将 Worker 移动到线程中异步执行。
        """
        logger.info(f"Installer factory creating installer for source: {update_info.source.name}")

        if self.thread and self.thread.isRunning():
            logger.warning("An installation is already in progress.")
            self.install_failed.emit(update_info.resource_name, "另一个安装正在进行中")
            return

        # 1. 根据更新源创建对应的安装器 "Worker" 实例
        if update_info.source == UpdateSource.GITHUB:
            self.installer = GithubInstaller(resource, update_info, file_path)
        elif update_info.source == UpdateSource.MIRROR:
            self.installer = MirrorInstaller(resource, update_info, file_path)
        else:
            error_msg = f"不支持的更新源: {update_info.source}"
            logger.error(error_msg)
            self.install_failed.emit(update_info.resource_name, error_msg)
            return

        # 2. 创建一个 QThread
        self.thread = QThread()

        # 3. 将 Worker 移动到线程
        self.installer.moveToThread(self.thread)

        # 4. 连接信号和槽
        # 代理信号：将 Worker 的信号连接到工厂自身的信号上
        self.installer.install_started.connect(self.install_started)
        self.installer.install_completed.connect(self.install_completed)
        self.installer.install_failed.connect(self.install_failed)
        self.installer.restart_required.connect(self.restart_required)

        # 线程启动时，执行 Worker 的 install 方法
        self.thread.started.connect(self.installer.install)

        # Worker 完成工作后，安全退出并清理线程
        def on_finished():
            self.thread.quit()
            self.thread.wait()
            self.installer.deleteLater()  # 确保在正确的线程中删除
            self.thread.deleteLater()
            self.installer = None
            self.thread = None

        self.installer.install_completed.connect(on_finished)
        self.installer.install_failed.connect(on_finished)

        # 5. 启动线程
        self.thread.start()

# --- END OF FILE app/utils/update/installer/factory.py ---