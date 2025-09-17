# --- START OF FILE app/utils/update/installer/base.py ---

from PySide6.QtCore import QObject, Signal
from abc import ABC, ABCMeta, abstractmethod
from pathlib import Path

from app.models.config.resource_config import ResourceConfig
from app.utils.update.models import UpdateInfo


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

    def __init__(self, resource: ResourceConfig, update_info: UpdateInfo, file_path: str | None):
        super().__init__()
        self.resource = resource
        self.update_info = update_info

        # 【修正】安全地处理 file_path 可能为 None 的情况
        self.file_path = Path(file_path) if file_path is not None else None

        self.new_version = update_info.new_version

    @abstractmethod
    def install(self):
        """
        执行安装的核心方法。
        """
        raise NotImplementedError

# --- END OF FILE app/utils/update/installer/base.py ---