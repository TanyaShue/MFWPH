# --- START OF FILE github.py ---

import shutil
import tempfile
import zipfile
from pathlib import Path

from app.utils.update.installer.base import BaseInstaller
from app.models.config.global_config import global_config
from app.utils import update_utils
from app.models.logging.log_manager import log_manager
from app.utils.update.installer.app import AppInstaller


logger = log_manager.get_app_logger()


class GithubInstaller(BaseInstaller):
    """处理来自 GitHub 的更新安装"""

    def install(self):
        """
        安装器的主入口。
        首先检查更新类型，如果是 'full'，则委托给 AppInstaller。
        否则，执行常规的资源更新逻辑。
        """
        self.install_started.emit(self.resource.resource_name)

        # --- 修改开始: 核心逻辑判断与委托 ---
        # 如果更新类型是 'full'，意味着这是一个完整的主程序包
        if self.update_info.update_type == 'full':
            logger.info(f"更新 '{self.resource.resource_name}' 是一个完整包 (update_type='full')。将委托给 AppInstaller 处理。")
            try:
                # 创建 AppInstaller 实例，并把 resource 传给它，以便它知道要清理哪个目录
                app_installer = AppInstaller(self.update_info, self.file_path, self.resource)

                # 关键：将我们的信号连接到 app_installer 的信号，这样UI才能收到正确的状态更新
                app_installer.install_completed.connect(self.install_completed)
                app_installer.install_failed.connect(self.install_failed)
                app_installer.restart_required.connect(self.restart_required)

                # 启动 AppInstaller 的安装流程
                app_installer.install()
                return  # 委托后，当前安装器的任务结束
            except Exception as e:
                logger.error(f"委托给 AppInstaller 失败: {e}", exc_info=True)
                self.install_failed.emit(self.resource.resource_name, f"委托给主程序安装器失败: {str(e)}")
                return
        # --- 修改结束 ---

        # --- 以下是原有的资源更新逻辑，仅在非 'full' 更新时执行 ---
        resource_path = Path(self.resource.source_file).parent
        try:
            should_try_git = self.file_path is None
            git_is_available = shutil.which('git') is not None

            if should_try_git and git_is_available:
                logger.info(f"开始为 Git 仓库 '{self.resource.resource_name}' 执行 Git 更新...")
                import git
                repo = git.Repo(resource_path)
                self._update_via_git(repo)
            else:
                if should_try_git and not git_is_available:
                    logger.warning(f"'{self.resource.resource_name}' 是一个Git仓库，但未检测到Git环境，将尝试ZIP包更新。")
                    if not self.file_path:
                        raise FileNotFoundError("需要Git更新但环境不存在，且没有提供备用的ZIP文件路径。")
                else:
                    logger.info(f"'{self.resource.resource_name}' 不是 Git 仓库或UI决策下载，将使用 ZIP 包覆盖更新。")

                self._update_via_zip(resource_path)

        except Exception as e:
            logger.error(f"安装 GitHub 资源 {self.resource.resource_name} 失败: {e}", exc_info=True)
            self.install_failed.emit(self.resource.resource_name, str(e))

    def _update_via_git(self, repo):
        try:
            import git
            if repo.is_dirty(untracked_files=True):
                logger.warning("检测到本地有未提交的修改，将使用 git stash 暂存。")
                repo.git.stash('save', 'MaaYYsGUI-Auto-Update-Stash')

            logger.info("正在拉取最新的标签...")
            repo.git.fetch('--tags', '--force')

            tag_name = f"v{self.new_version}" if not self.new_version.startswith('v') else self.new_version
            logger.info(f"正在检出标签: {tag_name}")
            repo.git.checkout(f'tags/{tag_name}')

            if 'MaaYYsGUI-Auto-Update-Stash' in repo.git.stash('list'):
                logger.info("正在尝试恢复之前暂存的本地修改...")
                try:
                    repo.git.stash('pop')
                except git.exc.GitCommandError as e:
                    logger.warning(f"自动恢复暂存失败: {e}。用户的修改仍保留在暂存区中。")

            self.resource.resource_version = self.new_version
            global_config.save_all_configs()
            self.install_completed.emit(self.resource.resource_name, self.new_version, [])
        except Exception as e:
            logger.error(f"Git 更新失败: {str(e)}", exc_info=True)
            self.install_failed.emit(self.resource.resource_name, f"Git 更新失败: {str(e)}")

    def _update_via_zip(self, resource_path: Path):
        try:
            if not self.file_path or not self.file_path.exists():
                raise FileNotFoundError("更新所需的 ZIP 文件不存在。")

            update_utils.create_backup(self.resource.resource_name, resource_path)
            self._apply_full_update_from_zip(self.file_path, resource_path)

            self.resource.resource_version = self.new_version
            global_config.load_resource_config(str(resource_path / "resource_config.json"))
            global_config.save_all_configs()
            self.install_completed.emit(self.resource.resource_name, self.new_version, [])
        except Exception as e:
            logger.error(f"ZIP 更新失败: {str(e)}", exc_info=True)
            self.install_failed.emit(self.resource.resource_name, f"ZIP 更新失败: {str(e)}")

    def _apply_full_update_from_zip(self, source_zip_path, target_dir):
        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with zipfile.ZipFile(source_zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            unzipped_folder = next(extract_path.iterdir(), None)
            source_content_dir = unzipped_folder if unzipped_folder and unzipped_folder.is_dir() else extract_path

            logger.info(f"正在清理目标目录 '{target_dir}' (保留 .git)...")
            if target_dir.exists():
                for item in target_dir.iterdir():
                    if item.name == '.git':
                        continue
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            shutil.copytree(source_content_dir, target_dir, dirs_exist_ok=True)
            logger.info(f"已从 '{source_zip_path}' 完整更新到 '{target_dir}'")