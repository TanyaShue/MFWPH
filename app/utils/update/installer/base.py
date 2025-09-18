from PySide6.QtCore import QObject, Signal
from abc import ABC, ABCMeta, abstractmethod
from pathlib import Path

from app.models.config.resource_config import ResourceConfig
from app.utils.update.models import UpdateInfo
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class InstallerMeta(type(QObject), ABCMeta):
    pass


class BaseInstaller(QObject, ABC, metaclass=InstallerMeta):
    """
    安装器抽象基类。
    """
    install_started = Signal(str)
    install_completed = Signal(str, str, list)
    install_failed = Signal(str, str)
    restart_required = Signal()

    def __init__(self, resource: ResourceConfig | None, update_info: UpdateInfo, file_path: str | None):
        super().__init__()
        self.resource = resource
        self.update_info = update_info
        self.file_path = Path(file_path) if file_path is not None else None
        self.new_version = update_info.new_version

        # 增加初始化日志
        resource_name = resource.resource_name if resource else update_info.resource_name
        logger.debug(
            f"{self.__class__.__name__} initialized for '{resource_name}'. "
            f"New version: '{self.new_version}', File path: '{self.file_path}'"
        )

    @abstractmethod
    def install(self):
        """
        执行安装的核心方法。
        """
        raise NotImplementedError