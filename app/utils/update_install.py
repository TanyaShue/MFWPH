import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

# 新增导入
import git
from git.exc import InvalidGitRepositoryError

from PySide6.QtCore import QObject, Signal

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


def get_executable_name(base_name):
    """根据当前平台获取可执行文件名"""
    if sys.platform == "win32":
        return f"{base_name}.exe"
    return base_name


def get_base_path():
    """获取应用程序的根目录"""
    base_path = Path.cwd() if not getattr(sys, 'frozen', False) else Path(sys.executable).parent
    logger.debug(f"Application base path determined: {base_path}")
    return base_path


class UpdateInstaller(QObject):
    """更新安装器"""
    install_started = Signal(str)
    install_completed = Signal(str, str, list)
    install_failed = Signal(str, str)
    restart_required = Signal()

    def __init__(self):
        super().__init__()
        base_path = get_base_path()
        self.app_name = get_executable_name("MFWPH")
        self.updater_name = get_executable_name("updater")
        self.updater_path = base_path / self.updater_name
        logger.debug(f"UpdateInstaller initialized. App: '{self.app_name}', Updater: '{self.updater_path}'")

    def install_update(self, resource, file_path):
        """
        安装资源更新。
        【已修改】为 GitHub 源增加了特殊处理逻辑。
        """
        self.install_started.emit(resource.resource_name)
        new_version = getattr(resource, 'temp_version', "unknown")
        logger.debug(
            f"Starting install_update for resource '{resource.resource_name}' with file '{file_path}' to version '{new_version}'.")

        try:
            # **新增逻辑分支：检查是否为 GitHub 源**
            if resource.resource_rep_url and "github.com" in resource.resource_rep_url:
                logger.debug(f"'{resource.resource_name}' is a GitHub resource. Using GitHub install logic.")
                self._install_from_github(resource, new_version, file_path)
            # **Mirror酱或其它源的逻辑保持不变**
            else:
                logger.debug(f"'{resource.resource_name}' is a standard resource. Using standard install logic.")
                fallback_update_type = getattr(resource, 'temp_update_type', "full")
                needs_restart, detected_type = self._check_if_restart_required(file_path)
                final_update_type = detected_type or fallback_update_type
                logger.debug(
                    f"Restart required: {needs_restart}. Detected update type: '{detected_type}'. Final update type: '{final_update_type}'.")

                if needs_restart:
                    logger.info(f"Restart is required for '{resource.resource_name}'. Launching external updater.")
                    self.launch_updater(file_path, final_update_type)
                    self.restart_required.emit()
                else:
                    logger.info(f"Applying update directly for '{resource.resource_name}' as no restart is needed.")
                    self._apply_update_directly(resource, file_path, new_version, final_update_type)

        except Exception as e:
            logger.error(f"安装资源 {resource.resource_name} 更新失败: {str(e)}")
            self.install_failed.emit(resource.resource_name, str(e))

    def _install_from_github(self, resource, new_version, downloaded_zip_path):
        """
        【新增】处理来自 GitHub 的更新安装。
        自动检测资源目录是 Git 仓库还是普通文件夹，并选择合适的更新方式。
        """
        resource_path = Path(resource.source_file).parent
        logger.info(f"开始为 GitHub 资源 '{resource.resource_name}' 安装更新至版本 '{new_version}'")
        logger.debug(f"Resource path for '{resource.resource_name}' is '{resource_path}'.")

        try:
            # 尝试将目录作为 Git 仓库打开
            repo = git.Repo(resource_path)
            logger.info(f"检测到 '{resource.resource_name}' 是一个 Git 仓库，将使用 Git 更新。")
            self._update_via_git(repo, new_version, resource)
        except InvalidGitRepositoryError:
            # 如果不是 Git 仓库，则使用下载的 ZIP 包进行覆盖安装
            logger.info(f"'{resource.resource_name}' 不是 Git 仓库，将使用 ZIP 包覆盖更新。")
            logger.debug(f"Downloaded ZIP path for override: '{downloaded_zip_path}'.")
            # 完整更新总是需要备份
            self._create_backup(resource.resource_name, resource_path)
            self._apply_full_update(downloaded_zip_path, resource_path, is_zip=True)

            # 更新配置并发出成功信号
            logger.debug("Updating resource version in config and saving.")
            resource.resource_version = new_version
            global_config.load_resource_config(str(resource_path / "resource_config.json"))
            global_config.save_all_configs()
            self.install_completed.emit(resource.resource_name, new_version, [])
        except Exception as e:
            logger.error(f"通过 Git 更新资源 {resource.resource_name} 失败: {e}")
            self.install_failed.emit(resource.resource_name, str(e))

    def _update_via_git(self, repo: git.Repo, new_version: str, resource):
        """
        【新增】使用 Git 命令来更新资源。
        """
        logger.info("正在拉取最新的标签...")
        # 拉取所有最新的标签信息
        logger.debug("Executing: git fetch --tags --force")
        repo.git.fetch('--tags', '--force')

        # 构造 tag 名称，兼容带'v'和不带'v'的前缀
        tag_name = f"v{new_version}" if not new_version.startswith('v') else new_version

        logger.info(f"正在检出标签: {tag_name}")
        logger.debug(f"Executing: git checkout tags/{tag_name}")
        # 检出到指定的标签
        repo.git.checkout(f'tags/{tag_name}')

        logger.info(f"Git 更新成功。正在更新配置文件版本号...")
        # 更新配置文件中的版本号
        resource.resource_version = new_version
        global_config.save_all_configs()  # 保存所有配置的更改

        self.install_completed.emit(resource.resource_name, new_version, [])

    def launch_updater(self, file_path, update_type):
        """启动独立更新程序"""
        if not self.updater_path.exists():
            error_msg = f"独立更新程序不存在，请检查路径: {self.updater_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        self._update_updater_if_needed(file_path)
        current_pid = os.getpid()
        args = [
            str(self.updater_path), str(file_path),
            "--type", update_type, "--restart", self.app_name,
            "--wait-pid", str(current_pid)
        ]
        logger.info(f"启动独立更新程序: {' '.join(args)}")
        logger.debug(f"Updater arguments: {args}")
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        subprocess.Popen(args, creationflags=creation_flags)

    def _check_if_restart_required(self, file_path):
        """检查是否需要重启来应用更新"""
        logger.debug(f"Checking if restart is required for update file: {file_path}")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            logger.debug(f"Extracting update file to temporary directory: {temp_path}")
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            changes_file = temp_path / "changes.json"
            if changes_file.exists():
                logger.debug(f"Found changes.json at {changes_file}. Processing as incremental update.")
                with open(changes_file, 'r', encoding='utf-8') as f:
                    changes = json.load(f)
                logger.debug(f"Changes content: {changes}")

                all_files = changes.get("added", []) + changes.get("modified", [])
                for file in all_files:
                    if file == self.app_name or self._is_file_locked(Path(file)):
                        logger.warning(f"File '{file}' requires restart (is app executable or locked).")
                        return True, "incremental"
                logger.debug("No files in incremental update require a restart.")
                return False, "incremental"
            else:
                logger.debug("No changes.json found. Assuming full update which requires restart.")
                return True, "full"

    def _is_file_locked(self, file_path):
        """检查文件是否被锁定"""
        if not file_path.exists():
            return False
        logger.debug(f"Checking if file is locked: {file_path}")
        try:
            with open(file_path, 'a'):
                pass
            logger.debug(f"File '{file_path}' is not locked.")
            return False
        except (IOError, OSError):
            logger.warning(f"File '{file_path}' is locked.")
            return True

    def install_new_resource(self, resource_name, file_path, data):
        """安装新资源"""
        self.install_started.emit(resource_name)
        logger.debug(f"Starting to install new resource '{resource_name}' from '{file_path}'.")
        try:
            with tempfile.TemporaryDirectory() as extract_dir:
                logger.debug(f"Extracting new resource to temp directory '{extract_dir}'.")
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                resource_dir, _ = self._find_or_create_config(extract_dir, data, resource_name)
                logger.debug(f"Determined resource content directory: '{resource_dir}'.")
                target_dir = Path(f"assets/resource/{resource_name.lower().replace(' ', '_')}")
                logger.debug(f"Target directory for new resource: '{target_dir}'.")
                if target_dir.exists():
                    logger.warning(f"Target directory '{target_dir}' already exists. Creating backup and removing it.")
                    self._create_backup(resource_name, target_dir)
                    shutil.rmtree(target_dir)
                shutil.copytree(resource_dir, target_dir)
                logger.info(f"Successfully copied new resource to '{target_dir}'.")
                global_config.load_resource_config(str(target_dir / "resource_config.json"))
                self.install_completed.emit(resource_name, data.get("version", "1.0.0"), [])
        except Exception as e:
            logger.error(f"安装新资源 {resource_name} 失败: {str(e)}")
            self.install_failed.emit(resource_name, str(e))

    def _update_updater_if_needed(self, file_path):
        """检查并更新updater（如果更新包中包含的话）"""
        logger.debug(f"Checking for updater executable '{self.updater_name}' in package '{file_path}'.")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)

                updater_in_package = None
                root_updater = temp_path / self.updater_name
                if root_updater.exists():
                    logger.debug(f"Updater found at root of the package: {root_updater}")
                    updater_in_package = root_updater
                else:
                    logger.debug("Updater not in root, searching subdirectories.")
                    for root, _, files in os.walk(temp_path):
                        if self.updater_name in files:
                            updater_in_package = Path(root) / self.updater_name
                            logger.debug(f"Updater found in subdirectory: {updater_in_package}")
                            break

                if updater_in_package and updater_in_package.exists():
                    logger.info(f"发现新的 {self.updater_name}，准备覆盖现有版本")
                    backup_path = self.updater_path.with_suffix(self.updater_path.suffix + '.backup')
                    if self.updater_path.exists():
                        logger.debug(f"Backing up current updater to {backup_path}")
                        shutil.copy2(self.updater_path, backup_path)
                    try:
                        if self.updater_path.exists():
                            self.updater_path.unlink()
                        shutil.copy2(updater_in_package, self.updater_path)
                        logger.info(f"已更新 {self.updater_name}")
                        if backup_path.exists():
                            logger.debug(f"Removing backup updater file: {backup_path}")
                            backup_path.unlink()
                    except Exception as e:
                        logger.error(f"更新 {self.updater_name} 失败: {str(e)}")
                        if backup_path.exists() and not self.updater_path.exists():
                            logger.warning(f"Restoring updater from backup: {backup_path}")
                            shutil.copy2(backup_path, self.updater_path)
                        raise
                else:
                    logger.debug(f"更新包中未发现 {self.updater_name}，跳过更新")
        except Exception as e:
            logger.warning(f"检查/更新 {self.updater_name} 时出错: {str(e)}")

    def _apply_update_directly(self, resource, file_path, new_version, update_type):
        """直接应用更新（不需要重启的情况）"""
        logger.debug(f"Applying update directly for '{resource.resource_name}'. Type: {update_type}.")
        with tempfile.TemporaryDirectory() as extract_dir:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            original_resource_dir = Path(resource.source_file).parent
            logger.debug(f"Original resource directory: {original_resource_dir}")
            self._create_backup(resource.resource_name, original_resource_dir)
            if update_type == "incremental":
                changes_file = Path(extract_dir) / "changes.json"
                if changes_file.exists():
                    logger.debug("Applying incremental changes.")
                    self._apply_incremental_changes(extract_dir, changes_file)
                else:
                    raise ValueError("增量更新包中缺少 changes.json")
            else:  # full
                logger.debug("Applying full update.")
                self._apply_full_update(extract_dir, original_resource_dir)
            if new_version:
                logger.debug(f"Setting new version to '{new_version}'.")
                resource.resource_version = new_version
            global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))
            global_config.save_all_configs()
            self.install_completed.emit(resource.resource_name, new_version, [])

    def _apply_incremental_changes(self, extract_dir, changes_file):
        """应用增量更新变更"""
        with open(changes_file, 'r', encoding='utf-8') as f:
            changes = json.load(f)
        extract_path = Path(extract_dir)
        logger.debug(f"Applying incremental changes from {changes_file}: {changes}")
        for file_path in changes.get("added", []):
            source, target = extract_path / file_path, Path(file_path)
            logger.debug(f"[ADD] Source: '{source}', Target: '{target}'")
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        for file_path in changes.get("modified", []):
            source, target = extract_path / file_path, Path(file_path)
            logger.debug(f"[MODIFY] Source: '{source}', Target: '{target}'")
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists(): target.unlink()
                shutil.copy2(source, target)
        for file_path in changes.get("deleted", []):
            target = Path(file_path)
            logger.debug(f"[DELETE] Target: '{target}'")
            if target.exists(): target.unlink()

    def _apply_full_update(self, source_path, target_dir, is_zip=False):
        """
        应用完整更新。
        【已修改】增加 is_zip 参数以处理来自文件或目录的源。
        """
        logger.debug(f"Applying full update from '{source_path}' to '{target_dir}'. Is source a zip: {is_zip}.")
        extract_dir = tempfile.TemporaryDirectory()
        extract_path = Path(extract_dir.name)
        try:
            if is_zip:
                with zipfile.ZipFile(source_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                logger.debug(f"ZIP extracted to '{extract_path}'.")
                # GitHub的zip包解压后有一层额外目录，需要处理
                unzipped_folder = next(extract_path.iterdir(), None)
                if unzipped_folder and unzipped_folder.is_dir():
                    logger.debug(f"Found single root folder in ZIP: '{unzipped_folder}'. Using it as source.")
                    source_dir = unzipped_folder
                else:
                    logger.debug("No single root folder in ZIP. Using extraction path as source.")
                    source_dir = extract_path
            else:
                source_dir = Path(source_path)

            resource_dir_in_source = None
            logger.debug(f"Searching for 'resource_config.json' in '{source_dir}' to identify content root.")
            for root, _, files in os.walk(source_dir):
                if "resource_config.json" in files:
                    resource_dir_in_source = root
                    logger.debug(f"Found 'resource_config.json' in '{resource_dir_in_source}'.")
                    break

            if not resource_dir_in_source:
                # 如果没有配置文件，就默认使用源目录
                logger.debug("No 'resource_config.json' found. Using source directory as content root.")
                resource_dir_in_source = source_dir

            if target_dir.exists():
                logger.debug(f"Removing existing target directory: '{target_dir}'.")
                shutil.rmtree(target_dir)
            logger.debug(f"Copying from '{resource_dir_in_source}' to '{target_dir}'.")
            shutil.copytree(resource_dir_in_source, target_dir)
        finally:
            extract_dir.cleanup()

    def _find_or_create_config(self, extract_dir, data, resource_name):
        """查找现有配置或创建新配置"""
        logger.debug(f"Searching for 'resource_config.json' in '{extract_dir}'.")
        for root, _, files in os.walk(extract_dir):
            if "resource_config.json" in files:
                logger.debug(f"Found existing config at '{root}'.")
                return root, os.path.join(root, "resource_config.json")

        logger.debug("No existing config found. Creating a new one.")
        main_dir = extract_dir
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                main_dir = item_path
                logger.debug(f"Identified main content directory as '{main_dir}'.")
                break
        resource_config = {
            "resource_name": data["name"] or resource_name,
            "resource_version": data.get("version", "1.0.0"),
            "resource_author": data.get("author", "未知"),
            "resource_description": data["description"] or "从外部源添加的资源",
            "resource_rep_url": data["url"] if "github.com" in data["url"] else "",
            "mirror_update_service_id": "" if "github.com" in data["url"] else data.get("service_id", "")
        }
        logger.debug(f"New resource config data: {resource_config}")
        resource_config_path = os.path.join(main_dir, "resource_config.json")
        with open(resource_config_path, 'w', encoding='utf-8') as f:
            json.dump(resource_config, f, ensure_ascii=False, indent=4)
        logger.info(f"Created new resource_config.json at '{resource_config_path}'.")
        return main_dir, resource_config_path

    def _create_backup(self, resource_name, resource_dir):
        """创建资源备份"""
        history_dir = Path("assets/history")
        history_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_version = "unknown"
        config_file = resource_dir / "resource_config.json"
        logger.debug(f"Creating backup for '{resource_name}' from '{resource_dir}'.")
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    current_version = json.load(f).get("resource_version", "unknown")
            except Exception as e:
                logger.warning(f"Could not read version from '{config_file}': {e}")
        backup_path = history_dir / f"{resource_name}_{current_version}_{timestamp}.zip"
        logger.debug(f"Backup destination: '{backup_path}'.")
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(resource_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = f"{resource_name}/{os.path.relpath(file_path, resource_dir)}"
                    zipf.write(file_path, arcname)
        logger.info(f"创建备份: {backup_path}")
        return str(backup_path)


def initialize_update_system():
    """在应用程序启动时初始化更新系统"""
    logger.debug("Initializing update system.")
    try:
        temp_dir_path = Path("assets/temp")
        history_dir_path = Path("assets/history")
        logger.debug(f"Ensuring directory exists: {temp_dir_path}")
        temp_dir_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensuring directory exists: {history_dir_path}")
        history_dir_path.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Cleaning temporary directory: {temp_dir_path}")
        if temp_dir_path.exists():
            for item in temp_dir_path.iterdir():
                if item.is_file():
                    logger.debug(f"Removing temp file: {item}")
                    item.unlink()
        updater_path = get_base_path() / get_executable_name("updater")
        if not updater_path.exists():
            logger.warning("独立更新程序不存在，某些更新功能可能无法使用")
        logger.debug("Update system initialization successful.")
        return True
    except Exception as e:
        logger.error(f"初始化更新系统失败: {str(e)}")
        return False