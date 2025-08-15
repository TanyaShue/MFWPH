"""
重构后的更新安装模块
与独立更新程序配合工作，支持增量和完整更新
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


def get_executable_name(base_name):
    """根据当前平台获取可执行文件名"""
    if sys.platform == "win32":
        return f"{base_name}.exe"
    return base_name


class UpdateInstaller(QObject):
    """更新安装器"""
    # 信号定义
    install_started = Signal(str)  # resource_name
    install_completed = Signal(str, str, list)  # resource_name, version, locked_files
    install_failed = Signal(str, str)  # resource_name, error_message
    restart_required = Signal()  # 需要重启应用程序

    def __init__(self):
        """初始化安装器"""
        super().__init__()
        # 根据平台动态确定可执行文件名
        self.app_name = get_executable_name("MFWPH")
        self.updater_name = get_executable_name("updater")
        self.updater_path = Path(self.updater_name)  # 独立更新程序路径

    def _check_if_restart_required(self, file_path):
        """检查是否需要重启来应用更新"""
        # 如果更新包中包含主程序或正在使用的文件，则需要重启
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 解压更新包
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_path)

            # 检查增量更新
            changes_file = temp_path / "changes.json"
            if changes_file.exists():
                with open(changes_file, 'r', encoding='utf-8') as f:
                    changes = json.load(f)

                # 检查是否包含主程序
                all_files = []
                all_files.extend(changes.get("added", []))
                all_files.extend(changes.get("modified", []))

                for file in all_files:
                    # 使用动态获取的应用名称
                    if file == self.app_name or self._is_file_locked(Path(file)):
                        return True, "incremental"

            # 检查完整更新（总是需要重启）
            else:
                return True, "full"

        return False, None

    def _is_file_locked(self, file_path):
        """检查文件是否被锁定"""
        if not file_path.exists():
            return False
        try:
            # 尝试以写模式打开文件
            with open(file_path, 'a'):
                pass
            return False
        except (IOError, OSError):
            return True

    def install_new_resource(self, resource_name, file_path, data):
        """
        安装新资源

        Args:
            resource_name: 资源名称
            file_path: 下载的文件路径
            data: 资源数据
        """
        self.install_started.emit(resource_name)

        try:
            # 对于新资源，通常不需要重启
            with tempfile.TemporaryDirectory() as extract_dir:
                # 解压 ZIP
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # 查找或创建资源配置
                resource_dir, resource_config_path = self._find_or_create_config(
                    extract_dir, data, resource_name
                )

                # 创建目标目录
                target_dir = Path(f"assets/resource/{resource_name.lower().replace(' ', '_')}")
                if target_dir.exists():
                    # 备份现有资源
                    self._create_backup(resource_name, target_dir)
                    shutil.rmtree(target_dir)

                # 复制文件到目标目录
                shutil.copytree(resource_dir, target_dir)

                # 加载新资源配置
                global_config.load_resource_config(str(target_dir / "resource_config.json"))

                # 完成安装
                self.install_completed.emit(resource_name, data.get("version", "1.0.0"), [])

        except Exception as e:
            logger.error(f"安装新资源 {resource_name} 失败: {str(e)}")
            self.install_failed.emit(resource_name, str(e))

    def install_update(self, resource, file_path):
        """
        安装资源更新

        Args:
            resource: 资源对象
            file_path: 下载的文件路径
        """
        self.install_started.emit(resource.resource_name)

        try:
            # 获取新版本号和更新类型
            new_version = getattr(resource, 'temp_version', None)
            update_type = getattr(resource, 'temp_update_type', "full")

            # 检查是否需要重启
            needs_restart, detected_type = self._check_if_restart_required(file_path)

            if needs_restart:
                # 使用独立更新程序
                self._launch_updater(file_path, detected_type or update_type)
                # 发送重启信号
                self.restart_required.emit()
            else:
                # 直接应用更新（仅适用于不涉及主程序的增量更新）
                self._apply_update_directly(resource, file_path, new_version, update_type)

        except Exception as e:
            logger.error(f"安装资源 {resource.resource_name} 更新失败: {str(e)}")
            self.install_failed.emit(resource.resource_name, str(e))

    def _launch_updater(self, file_path, update_type):
        """启动独立更新程序"""
        if not self.updater_path.exists():
            raise FileNotFoundError(f"独立更新程序不存在: {self.updater_path}")

        # 检查更新包中是否包含新的updater并进行覆盖
        self._update_updater_if_needed(file_path)

        # 获取当前进程PID
        current_pid = os.getpid()

        # 构建命令行参数，使用动态获取的应用名称
        args = [
            str(self.updater_path),
            str(file_path),
            "--type", update_type,
            "--restart", self.app_name,
            "--wait-pid", str(current_pid)
        ]

        logger.info(f"启动独立更新程序: {' '.join(args)}")

        # 启动独立更新程序
        if sys.platform == "win32":
            # Windows下使用CREATE_NEW_PROCESS_GROUP确保独立运行
            subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            subprocess.Popen(args)

    def _update_updater_if_needed(self, file_path):
        """检查并更新updater（如果更新包中包含的话）"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # 解压更新包
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)

                # 查找updater
                updater_in_package = None

                # 在根目录查找
                root_updater = temp_path / self.updater_name
                if root_updater.exists():
                    updater_in_package = root_updater
                else:
                    # 递归查找updater
                    for root, dirs, files in os.walk(temp_path):
                        if self.updater_name in files:
                            updater_in_package = Path(root) / self.updater_name
                            break

                # 如果找到updater，则进行覆盖
                if updater_in_package and updater_in_package.exists():
                    logger.info(f"发现新的 {self.updater_name}，准备覆盖现有版本")

                    # 创建当前updater的备份
                    backup_path = self.updater_path.with_suffix(self.updater_path.suffix + '.backup')
                    if self.updater_path.exists():
                        shutil.copy2(self.updater_path, backup_path)
                        logger.info(f"已备份当前 {self.updater_name} 到: {backup_path}")

                    try:
                        # 覆盖updater
                        if self.updater_path.exists():
                            # 在Windows上可能需要先删除再复制
                            self.updater_path.unlink()

                        shutil.copy2(updater_in_package, self.updater_path)
                        logger.info(f"已更新 {self.updater_name}")

                        # 删除备份文件（如果更新成功）
                        if backup_path.exists():
                            backup_path.unlink()

                    except Exception as e:
                        logger.error(f"更新 {self.updater_name} 失败: {str(e)}")
                        # 如果更新失败，尝试恢复备份
                        if backup_path.exists() and not self.updater_path.exists():
                            try:
                                shutil.copy2(backup_path, self.updater_path)
                                logger.info(f"已从备份恢复 {self.updater_name}")
                            except Exception as restore_error:
                                logger.error(f"恢复 {self.updater_name} 备份失败: {str(restore_error)}")
                        raise
                else:
                    logger.debug(f"更新包中未发现 {self.updater_name}，跳过更新")

        except Exception as e:
            logger.warning(f"检查/更新 {self.updater_name} 时出错: {str(e)}")
            # 这里不抛出异常，因为updater更新失败不应该阻止主要的更新流程
            # 除非是严重错误，可以继续使用现有的updater

    def _apply_update_directly(self, resource, file_path, new_version, update_type):
        """直接应用更新（不需要重启的情况）"""
        with tempfile.TemporaryDirectory() as extract_dir:
            # 解压 ZIP
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # 获取原始资源目录
            original_resource_dir = Path(resource.source_file).parent

            # 创建备份
            self._create_backup(resource.resource_name, original_resource_dir)

            if update_type == "incremental":
                # 应用增量更新
                changes_file = Path(extract_dir) / "changes.json"
                if changes_file.exists():
                    self._apply_incremental_changes(extract_dir, changes_file)
                else:
                    raise ValueError("增量更新包中缺少 changes.json")
            else:
                # 应用完整更新
                self._apply_full_update(extract_dir, original_resource_dir)

            # 更新版本信息
            if new_version:
                resource.resource_version = new_version

            # 重新加载资源配置
            global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))

            # 保存配置
            global_config.save_all_configs()

            # 完成安装
            self.install_completed.emit(resource.resource_name, new_version, [])

    def _apply_incremental_changes(self, extract_dir, changes_file):
        """应用增量更新变更"""
        with open(changes_file, 'r', encoding='utf-8') as f:
            changes = json.load(f)

        extract_path = Path(extract_dir)

        # 处理添加的文件
        for file_path in changes.get("added", []):
            source = extract_path / file_path
            target = Path(file_path)

            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                logger.info(f"添加文件: {file_path}")

        # 处理修改的文件
        for file_path in changes.get("modified", []):
            source = extract_path / file_path
            target = Path(file_path)

            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target.unlink()
                shutil.copy2(source, target)
                logger.info(f"更新文件: {file_path}")

        # 处理删除的文件
        for file_path in changes.get("deleted", []):
            target = Path(file_path)
            if target.exists():
                target.unlink()
                logger.info(f"删除文件: {file_path}")

    def _apply_full_update(self, extract_dir, target_dir):
        """应用完整更新"""
        # 查找资源目录
        resource_dir = None
        for root, dirs, files in os.walk(extract_dir):
            if "resource_config.json" in files:
                resource_dir = root
                break

        if not resource_dir:
            raise ValueError("更新包中未找到 resource_config.json")

        # 清空目标目录并复制新文件
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(resource_dir, target_dir)

    def _find_or_create_config(self, extract_dir, data, resource_name):
        """查找现有配置或创建新配置"""
        # 尝试查找现有配置
        for root, dirs, files in os.walk(extract_dir):
            if "resource_config.json" in files:
                return root, os.path.join(root, "resource_config.json")

        # 创建新配置
        main_dir = extract_dir
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                main_dir = item_path
                break

        # 创建资源配置
        resource_config = {
            "resource_name": data["name"] or resource_name,
            "resource_version": data.get("version", "1.0.0"),
            "resource_author": data.get("author", "未知"),
            "resource_description": data["description"] or "从外部源添加的资源",
            "resource_rep_url": data["url"] if "github.com" in data["url"] else "",
            "resource_update_service_id": "" if "github.com" in data["url"] else data.get("service_id", "")
        }

        # 写入配置文件
        resource_config_path = os.path.join(main_dir, "resource_config.json")
        with open(resource_config_path, 'w', encoding='utf-8') as f:
            json.dump(resource_config, f, ensure_ascii=False, indent=4)

        return main_dir, resource_config_path

    def _create_backup(self, resource_name, resource_dir):
        """创建资源备份"""
        # 创建历史目录
        history_dir = Path("assets/history")
        history_dir.mkdir(parents=True, exist_ok=True)

        # 创建时间戳备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 获取当前版本
        current_version = "unknown"
        config_file = resource_dir / "resource_config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    current_version = config.get("resource_version", "unknown")
            except:
                pass

        backup_filename = f"{resource_name}_{current_version}_{timestamp}.zip"
        backup_path = history_dir / backup_filename

        # 创建备份
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(resource_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = f"{resource_name}/{os.path.relpath(file_path, resource_dir)}"
                    zipf.write(file_path, arcname)

        logger.info(f"创建备份: {backup_path}")
        return str(backup_path)


# 初始化函数
def initialize_update_system():
    """在应用程序启动时初始化更新系统"""
    try:
        # 创建必要的目录
        Path("assets/temp").mkdir(parents=True, exist_ok=True)
        Path("assets/history").mkdir(parents=True, exist_ok=True)

        # 清理临时目录
        try:
            temp_dir = Path("assets/temp")
            if temp_dir.exists():
                for item in temp_dir.iterdir():
                    if item.is_file():
                        item.unlink()
        except Exception as e:
            logger.warning(f"清理临时目录失败: {str(e)}")

        # 检查独立更新程序是否存在
        updater_path = Path(get_executable_name("updater"))
        if not updater_path.exists():
            logger.warning("独立更新程序不存在，某些更新功能可能无法使用")

        return True
    except Exception as e:
        logger.error(f"初始化更新系统失败: {str(e)}")
        return False