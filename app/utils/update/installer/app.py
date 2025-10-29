import os
import subprocess
from pathlib import Path
import zipfile
import tempfile
import shutil

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
            f"AppInstaller 已为 'MFWPH 主程序' 初始化。新版本: '{self.new_version}', 文件: '{self.file_path}'")

        base_path = update_utils.get_base_path()
        self.app_name = update_utils.get_executable_name("MFWPH")
        self.updater_name = update_utils.get_executable_name("updater")
        self.updater_path = base_path / self.updater_name

    def install(self):
        """主程序的安装逻辑非常简单：总是启动外部更新器"""
        logger.info("开始为 'MFWPH 主程序' 进行安装。")
        self.install_started.emit("MFWPH 主程序")
        try:
            # --- 修改开始 ---
            try:
                logger.debug(f"检查安装包 '{self.file_path}' 中是否存在更新版的更新器...")
                with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                    if self.updater_name in zip_ref.namelist():
                        logger.info("安装包中发现新版更新器，将先更新更新器本身。")
                        with tempfile.TemporaryDirectory() as temp_dir:
                            zip_ref.extract(self.updater_name, temp_dir)
                            new_updater_path = Path(temp_dir) / self.updater_name
                            shutil.move(str(new_updater_path), str(self.updater_path))
                            logger.info(f"更新器已成功更新到路径: {self.updater_path}")
            except Exception as e:
                logger.warning(f"更新更新器时发生错误: {e}。将尝试使用现有更新器。", exc_info=True)
            # --- 修改结束 ---

            if not self.updater_path.exists():
                raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")
            logger.debug(f"在以下位置找到更新程序: {self.updater_path}")

            absolute_file_path = self.file_path.resolve()
            current_pid = os.getpid()
            args = [
                str(self.updater_path), str(absolute_file_path), "--type", "full",
                "--restart", self.app_name, "--wait-pid", str(current_pid)
            ]

            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if update_utils.sys.platform == "win32" else 0
            subprocess.Popen(args, creationflags=creation_flags)
            logger.info(f"已启动独立更新程序: {' '.join(args)}")

            logger.info("已发出需要重启信号。应用程序现在应当退出。")
            self.restart_required.emit()

            # 这个信号可能在应用退出前不会被主线程处理，但我们仍然发送它
            self.install_completed.emit("MFWPH 主程序", self.new_version, [])

        except Exception as e:
            logger.error(f"启动更新程序失败: {e}", exc_info=True)
            self.install_failed.emit("MFWPH 主程序", str(e))