# --- START OF FILE app/utils/update/installer/app.py ---

import os
import subprocess
from pathlib import Path

from app.utils.update.installer.base import BaseInstaller
from app.utils import update_utils
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class AppInstaller(BaseInstaller):
    """MFWPH 主程序的安装器"""

    def __init__(self, update_info, file_path: str):
        # 注意：主程序没有 resource 对象，所以我们简化 __init__
        # 我们需要从 BaseInstaller 借用 QObject 的 __init__
        super(BaseInstaller, self).__init__()
        self.update_info = update_info
        self.file_path = Path(file_path)

        # 获取更新器路径和应用名称
        base_path = update_utils.get_base_path()
        self.app_name = update_utils.get_executable_name("MFWPH")
        self.updater_name = update_utils.get_executable_name("updater")
        self.updater_path = base_path / self.updater_name

    def install(self):
        """主程序的安装逻辑非常简单：总是启动外部更新器"""
        self.install_started.emit("MFWPH 主程序")
        try:
            if not self.updater_path.exists():
                raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")

            # 确保文件路径是绝对路径
            absolute_file_path = self.file_path.resolve()

            current_pid = os.getpid()
            args = [str(self.updater_path), str(absolute_file_path), "--type", "full", "--restart", self.app_name,
                    "--wait-pid", str(current_pid)]

            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if update_utils.sys.platform == "win32" else 0
            subprocess.Popen(args, creationflags=creation_flags)

            logger.info(f"已启动独立更新程序: {' '.join(args)}")

            # 发射需要重启的信号，让UI知道可以退出了
            self.restart_required.emit()
            # 这里的 completed 信号可能不会被处理，因为应用即将退出，但为了流程完整性我们仍然发射
            self.install_completed.emit("MFWPH 主程序", self.update_info.new_version, [])

        except Exception as e:
            logger.error(f"启动更新程序失败: {e}", exc_info=True)
            self.install_failed.emit("MFWPH 主程序", str(e))

# --- END OF FILE app/utils/update/installer/app.py ---