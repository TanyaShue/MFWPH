import json
import shutil
import sys
import tempfile
import zipfile
import os
import subprocess
from pathlib import Path

from app.utils.update.installer.base import BaseInstaller
from app.models.config.global_config import global_config
from app.utils import update_utils
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class MirrorInstaller(BaseInstaller):
    """处理来自 Mirror酱 的更新安装"""

    def __init__(self, resource, update_info, file_path: str):
        super().__init__(resource, update_info, file_path)
        base_path = update_utils.get_base_path()
        self.app_name = update_utils.get_executable_name("MFWPH")
        self.updater_name = update_utils.get_executable_name("updater")
        self.updater_path = base_path / self.updater_name

    def install(self):
        logger.info(f"Starting installation for '{self.resource.resource_name}' (Mirror source).")
        self.install_started.emit(self.resource.resource_name)
        try:
            logger.debug("Checking if a restart is required...")
            needs_restart, detected_type = self._check_if_restart_required()
            final_update_type = detected_type or self.update_info.update_type
            logger.debug(f"Restart check result: needs_restart={needs_restart}, update_type='{final_update_type}'.")

            if needs_restart:
                logger.info(f"Restart is required for '{self.resource.resource_name}'. Launching external updater.")
                self.launch_updater(final_update_type)
                self.restart_required.emit()
            else:
                logger.info(f"Applying update directly for '{self.resource.resource_name}' as no restart is needed.")
                self._apply_update_directly(final_update_type)
        except Exception as e:
            logger.error(f"Installation failed for '{self.resource.resource_name}': {e}", exc_info=True)
            self.install_failed.emit(self.resource.resource_name, str(e))

    def _check_if_restart_required(self):
        """
        【已优化】检查是否需要重启，通过读取ZIP文件列表而非完全解压。
        """
        try:
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                all_files_in_zip = zip_ref.namelist()
                logger.debug(f"ZIP package contains {len(all_files_in_zip)} files.")

                if "changes.json" in all_files_in_zip:
                    logger.debug("Found 'changes.json', treating as incremental update for restart check.")
                    with tempfile.TemporaryDirectory() as temp_dir:
                        zip_ref.extract("changes.json", temp_dir)
                        changes_file = Path(temp_dir) / "changes.json"
                        with open(changes_file, 'r', encoding='utf-8') as f:
                            changes = json.load(f)

                        files_to_check = changes.get("added", []) + changes.get("modified", [])
                        logger.debug(f"Checking {len(files_to_check)} added/modified files for locks.")
                        for file in files_to_check:
                            normalized_file = file.replace('/', os.sep)
                            if normalized_file == self.app_name:
                                logger.warning(f"File '{normalized_file}' is the main application, restart required.")
                                return True, "incremental"
                            if update_utils.is_file_locked(Path(normalized_file)):
                                logger.warning(f"File '{normalized_file}' is locked, restart required.")
                                return True, "incremental"

                        logger.info("No locked files found in incremental update. Direct application is possible.")
                        return False, "incremental"
                else:
                    logger.info("No 'changes.json' found. Assuming full update which requires a restart.")
                    return True, "full"
        except Exception as e:
            logger.error(f"Error while checking for restart: {e}. Defaulting to requiring a restart.", exc_info=True)
            return True, self.update_info.update_type or "full"

    def _apply_update_directly(self, update_type):
        logger.debug(f"Starting direct update process (type: {update_type}).")
        original_resource_dir = Path(self.resource.source_file).parent

        logger.debug(f"Creating backup for '{self.resource.resource_name}'...")
        update_utils.create_backup(self.resource.resource_name, original_resource_dir)
        logger.info(f"Backup created for '{self.resource.resource_name}'.")

        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            logger.debug(f"Extracting '{self.file_path}' to temporary directory '{extract_path}'...")
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            logger.debug("Extraction complete.")

            if update_type == "incremental":
                changes_file = extract_path / "changes.json"
                if not changes_file.exists():
                    raise ValueError("增量更新包中缺少 changes.json")
                self._apply_incremental_changes(extract_path, changes_file)
            else:
                self._apply_full_update(extract_path, original_resource_dir)

        logger.debug("Updating resource version in config...")
        self.resource.resource_version = self.new_version
        global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))
        global_config.save_all_configs()
        logger.info(f"Direct update for '{self.resource.resource_name}' completed successfully.")
        self.install_completed.emit(self.resource.resource_name, self.new_version, [])

    def _apply_incremental_changes(self, extract_dir, changes_file):
        logger.info("Applying incremental changes...")
        with open(changes_file, 'r', encoding='utf-8') as f:
            changes = json.load(f)

        added_modified = changes.get("added", []) + changes.get("modified", [])
        logger.debug(f"Files to add/modify: {len(added_modified)}")
        for file_path_str in added_modified:
            source, target = Path(extract_dir) / file_path_str, Path(file_path_str)
            logger.debug(f"Copying '{source}' to '{target}'")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): target.unlink()
            shutil.copy2(source, target)

        deleted_files = changes.get("deleted", [])
        logger.debug(f"Files to delete: {len(deleted_files)}")
        for file_path_str in deleted_files:
            target = Path(file_path_str)
            if target.exists():
                logger.debug(f"Deleting '{target}'")
                target.unlink()
        logger.info("增量更新应用成功。")

    def _apply_full_update(self, source_dir, target_dir):
        logger.info("Applying full update...")
        resource_dir_in_source = source_dir
        for root, _, files in os.walk(source_dir):
            if "resource_config.json" in files:
                resource_dir_in_source = Path(root)
                break
        logger.debug(f"Source content directory: '{resource_dir_in_source}', Target directory: '{target_dir}'")

        if target_dir.exists():
            logger.debug(f"Removing existing target directory: '{target_dir}'")
            shutil.rmtree(target_dir)

        logger.debug("Copying new files...")
        shutil.copytree(resource_dir_in_source, target_dir)
        logger.info("完整更新应用成功。")

    def launch_updater(self, update_type):
        if not self.updater_path.exists():
            raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")

        current_pid = os.getpid()
        args = [
            str(self.updater_path),
            str(self.file_path.resolve()),  # 确保传递绝对路径
            "--type", update_type,
            "--restart", self.app_name,
            "--wait-pid", str(current_pid)
        ]
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen(args, creationflags=creation_flags)
        logger.info(f"启动独立更新程序: {' '.join(args)}")