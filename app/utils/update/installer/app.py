import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject

from app.utils.update.installer.base import BaseInstaller
from app.utils import update_utils
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class AppInstaller(BaseInstaller):
    """MFWPH 主程序的安装器"""

    def __init__(self, update_info, file_path: str):
        # BaseInstaller.__init__ 需要 resource，但主程序没有，所以我们绕过它
        # 但我们仍然需要调用 QObject 的 init
        QObject.__init__(self)
        self.update_info = update_info
        self.file_path = Path(file_path)
        self.new_version = update_info.new_version
        logger.debug(
            f"AppInstaller initialized for 'MFWPH 主程序'. New version: '{self.new_version}', File: '{self.file_path}'")

        base_path = update_utils.get_base_path()
        self.app_name = update_utils.get_executable_name("MFWPH")
        self.updater_name = update_utils.get_executable_name("updater")
        self.updater_path = base_path / self.updater_name

    def install(self):
        """主程序的安装逻辑非常简单：总是启动外部更新器"""
        logger.info("Starting installation for 'MFWPH 主程序'.")
        self.install_started.emit("MFWPH 主程序")
        try:
            if not self.updater_path.exists():
                raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")
            logger.debug(f"Updater found at: {self.updater_path}")

            absolute_file_path = self.file_path.resolve()
            current_pid = os.getpid()
            args = [
                str(self.updater_path), str(absolute_file_path), "--type", "full",
                "--restart", self.app_name, "--wait-pid", str(current_pid)
            ]

            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if update_utils.sys.platform == "win32" else 0
            subprocess.Popen(args, creationflags=creation_flags)
            logger.info(f"已启动独立更新程序: {' '.join(args)}")

            logger.info("Restart required signal emitted. The application should now exit.")
            self.restart_required.emit()

            # 这个信号可能在应用退出前不会被主线程处理，但我们仍然发送它
            self.install_completed.emit("MFWPH 主程序", self.new_version, [])

        except Exception as e:
            logger.error(f"启动更新程序失败: {e}", exc_info=True)
            self.install_failed.emit("MFWPH 主程序", str(e))