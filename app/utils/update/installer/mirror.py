# --- START OF FILE app/utils/update/installer/mirror.py ---

import json
import shutil
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
        self.install_started.emit(self.resource.resource_name)
        try:
            needs_restart, detected_type = self._check_if_restart_required()
            final_update_type = detected_type or self.update_info.update_type

            if needs_restart:
                logger.info(f"Restart is required for '{self.resource.resource_name}'. Launching external updater.")
                self.launch_updater(final_update_type)
                self.restart_required.emit()
            else:
                logger.info(f"Applying update directly for '{self.resource.resource_name}' as no restart is needed.")
                self._apply_update_directly(final_update_type)
        except Exception as e:
            self.install_failed.emit(self.resource.resource_name, str(e))

    def _check_if_restart_required(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            changes_file = temp_path / "changes.json"
            if changes_file.exists():
                with open(changes_file, 'r', encoding='utf-8') as f:
                    changes = json.load(f)

                all_files = changes.get("added", []) + changes.get("modified", [])
                for file in all_files:
                    if file == self.app_name or update_utils.is_file_locked(Path(file)):
                        logger.warning(f"File '{file}' requires restart (is app executable or locked).")
                        return True, "incremental"
                return False, "incremental"
            else:
                return True, "full"

    def _apply_update_directly(self, update_type):
        original_resource_dir = Path(self.resource.source_file).parent
        update_utils.create_backup(self.resource.resource_name, original_resource_dir)

        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)

            if update_type == "incremental":
                changes_file = extract_path / "changes.json"
                if not changes_file.exists(): raise ValueError("增量更新包中缺少 changes.json")
                self._apply_incremental_changes(extract_path, changes_file)
            else:
                self._apply_full_update(extract_path, original_resource_dir)

        self.resource.resource_version = self.new_version
        global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))
        global_config.save_all_configs()
        self.install_completed.emit(self.resource.resource_name, self.new_version, [])

    def _apply_incremental_changes(self, extract_dir, changes_file):
        with open(changes_file, 'r', encoding='utf-8') as f:
            changes = json.load(f)
        for file_path_str in changes.get("added", []) + changes.get("modified", []):
            source, target = Path(extract_dir) / file_path_str, Path(file_path_str)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): target.unlink()
            shutil.copy2(source, target)
        for file_path_str in changes.get("deleted", []):
            target = Path(file_path_str)
            if target.exists(): target.unlink()
        logger.info("增量更新应用成功。")

    def _apply_full_update(self, source_dir, target_dir):
        resource_dir_in_source = source_dir
        for root, _, files in os.walk(source_dir):
            if "resource_config.json" in files:
                resource_dir_in_source = Path(root)
                break

        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(resource_dir_in_source, target_dir)
        logger.info("完整更新应用成功。")

    def launch_updater(self, update_type):
        if not self.updater_path.exists():
            raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")

        current_pid = os.getpid()
        args = [str(self.updater_path), str(self.file_path), "--type", update_type, "--restart", self.app_name,
                "--wait-pid", str(current_pid)]
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen(args, creationflags=creation_flags)
        logger.info(f"启动独立更新程序: {' '.join(args)}")

# --- END OF FILE app/utils/update/installer/mirror.py ---