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
        # 决定性的第一条日志，确认工作线程已启动
        logger.info(f"在工作线程中开始为 '{self.resource.resource_name}' (Mirror 源) 进行安装。")
        self.install_started.emit(self.resource.resource_name)
        try:
            logger.debug("步骤 1: 正在检查是否需要重启...")
            needs_restart, detected_type = self._check_if_restart_required()
            final_update_type = detected_type or self.update_info.update_type
            logger.info(
                f"重启检查完成。需要重启: {needs_restart}, 更新类型: '{final_update_type}'。")

            if needs_restart:
                logger.info(f"步骤 2: 正在为 '{self.resource.resource_name}' 启动外部更新程序。")
                self.launch_updater(final_update_type)
                self.restart_required.emit()
            else:
                logger.info(
                    f"步骤 2: 正在为 '{self.resource.resource_name}' 直接应用更新 (无需重启)。")
                self._apply_update_directly(final_update_type)
        except Exception as e:
            logger.error(f"'{self.resource.resource_name}' 安装失败: {e}", exc_info=True)
            self.install_failed.emit(self.resource.resource_name, str(e))

    def _check_if_restart_required(self):
        """
        【最终优化版】高效检查是否需要重启，并增加详细日志。
        """
        try:
            logger.debug("正在打开 ZIP 文件以检查内容 (不解压)...")
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                all_files_in_zip = zip_ref.namelist()
                logger.debug(f"ZIP 包包含 {len(all_files_in_zip)} 个条目。")

                if "changes.json" in all_files_in_zip:
                    logger.debug("发现 'changes.json'。正在为增量更新分析重启需求。")
                    with tempfile.TemporaryDirectory() as temp_dir:
                        # 只解压这一个必要的小文件
                        zip_ref.extract("changes.json", temp_dir)
                        changes_file = Path(temp_dir) / "changes.json"
                        with open(changes_file, 'r', encoding='utf-8') as f:
                            changes = json.load(f)

                        files_to_check = changes.get("added", []) + changes.get("modified", [])
                        logger.debug(f"正在检查 {len(files_to_check)} 个新增/修改的文件是否存在锁定。")
                        for file in files_to_check:
                            normalized_file = file.replace('/', os.sep)
                            # 检查是否是主程序
                            if normalized_file == self.app_name:
                                logger.warning(
                                    f"需要重启: 文件 '{normalized_file}' 是主应用程序可执行文件。")
                                return True, "incremental"
                            # 检查文件是否被锁定
                            if update_utils.is_file_locked(Path(normalized_file)):
                                logger.warning(
                                    f"需要重启: 文件 '{normalized_file}' 当前被其他进程锁定。")
                                return True, "incremental"

                        logger.info("检查完成: 增量更新中没有文件需要重启。")
                        return False, "incremental"
                else:
                    logger.info(
                        "未找到 'changes.json'。假定为完整更新，为安全起见，总是需要重启。")
                    return True, "full"
        except Exception as e:
            logger.error(f"重启检查期间发生错误: {e}。默认需要重启。",
                         exc_info=True)
            # 出现任何异常时，安全起见，默认需要重启
            return True, self.update_info.update_type or "full"

    def _apply_update_directly(self, update_type):
        logger.debug(f"开始直接更新流程 (类型: {update_type})。")
        original_resource_dir = Path(self.resource.source_file).parent

        logger.debug(f"正在为 '{self.resource.resource_name}' 创建备份...")
        update_utils.create_backup(self.resource.resource_name, original_resource_dir)
        logger.info(f"已为 '{self.resource.resource_name}' 创建备份。")

        with tempfile.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            logger.debug(f"正在将 '{self.file_path}' 解压到临时目录 '{extract_path}'...")
            with zipfile.ZipFile(self.file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            logger.debug("解压完成。")

            if update_type == "incremental":
                changes_file = extract_path / "changes.json"
                if not changes_file.exists():
                    raise ValueError("增量更新包中缺少 changes.json")
                self._apply_incremental_changes(extract_path, changes_file)
            else:
                self._apply_full_update(extract_path, original_resource_dir)

        logger.debug("正在更新配置文件中的资源版本...")
        self.resource.resource_version = self.new_version
        global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))
        global_config.save_all_configs()
        logger.info(f"'{self.resource.resource_name}' 的直接更新已成功完成。")
        self.install_completed.emit(self.resource.resource_name, self.new_version, [])

    def _apply_incremental_changes(self, extract_dir, changes_file):
        logger.info("正在应用增量变更...")
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
        logger.info("正在应用完整更新...")
        resource_dir_in_source = source_dir
        for root, _, files in os.walk(source_dir):
            if "resource_config.json" in files:
                resource_dir_in_source = Path(root)
                break
        logger.debug(f"源内容目录: '{resource_dir_in_source}', 目标目录: '{target_dir}'")

        if target_dir.exists():
            logger.debug(f"正在移除已存在的目标目录: '{target_dir}'")
            shutil.rmtree(target_dir)

        logger.debug("正在复制新文件...")
        shutil.copytree(resource_dir_in_source, target_dir)
        logger.info("完整更新应用成功。")

    def launch_updater(self, update_type):
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

        if not self.updater_path.exists():
            raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")
        current_pid = os.getpid()
        args = [str(self.updater_path), str(self.file_path), "--type", update_type, "--restart", self.app_name,
                "--wait-pid", str(current_pid)]
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen(args, creationflags=creation_flags)
        logger.info(f"启动独立更新程序: {' '.join(args)}")