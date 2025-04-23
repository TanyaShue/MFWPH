import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager

logger = log_manager.get_app_logger()


class UpdateInstaller(QObject):
    """更新安装器"""
    # 信号定义
    install_started = Signal(str)  # resource_name
    install_completed = Signal(str, str, list)  # resource_name, version, locked_files
    install_failed = Signal(str, str)  # resource_name, error_message

    def __init__(self):
        """初始化安装器"""
        super().__init__()

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
            with tempfile.TemporaryDirectory() as extract_dir:
                # 解压 ZIP
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # 查找或创建资源配置
                resource_dir, resource_config_path = self._find_or_create_config(extract_dir, data, resource_name)

                # 创建目标目录
                target_dir = Path(f"assets/resource/{resource_name.lower().replace(' ', '_')}")
                if target_dir.exists():
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

            with tempfile.TemporaryDirectory() as extract_dir:
                # 解压 ZIP
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # 获取原始资源目录
                original_resource_dir = Path(resource.source_file).parent

                # 创建备份
                self._create_backup(resource, original_resource_dir)

                # 处理更新
                locked_files = []
                if update_type == "incremental":
                    changes_path = os.path.join(extract_dir, "changes.json")

                    if os.path.exists(changes_path):
                        locked_files = self._apply_incremental_update(resource, extract_dir, original_resource_dir,
                                                                      changes_path)
                    else:
                        # 如果没有 changes.json，回退到完整更新
                        locked_files = self._apply_full_update(resource, extract_dir, original_resource_dir)
                else:
                    # 完整更新
                    locked_files = self._apply_full_update(resource, extract_dir, original_resource_dir)

                # 重新加载资源配置
                global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))

                # 更新全局配置中的版本
                for r in global_config.get_all_resource_configs():
                    if r.resource_name == resource.resource_name and new_version:
                        r.resource_version = new_version
                        break

                # 保存所有配置
                global_config.save_all_configs()

                # 完成安装
                self.install_completed.emit(resource.resource_name, new_version, locked_files)

        except Exception as e:
            logger.error(f"安装资源 {resource.resource_name} 更新失败: {str(e)}")
            self.install_failed.emit(resource.resource_name, str(e))

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
            "resource_update_service_id": data["url"] if "github.com" in data["url"] else ""
        }

        # 写入配置文件
        resource_config_path = os.path.join(main_dir, "resource_config.json")
        with open(resource_config_path, 'w', encoding='utf-8') as f:
            json.dump(resource_config, f, ensure_ascii=False, indent=4)

        return main_dir, resource_config_path

    def _create_backup(self, resource, resource_dir):
        """创建资源备份"""
        # 创建历史目录
        history_dir = Path("assets/history")
        history_dir.mkdir(parents=True, exist_ok=True)

        # 创建时间戳备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{resource.resource_name}_{resource.resource_version}_{timestamp}.zip"
        backup_path = history_dir / backup_filename

        # 创建备份
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(resource_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = f"{resource.resource_name}/{os.path.relpath(file_path, resource_dir)}"
                    zipf.write(file_path, arcname)

        return str(backup_path)

    def _apply_full_update(self, resource, extract_dir, original_resource_dir):
        """应用完整更新"""
        # 查找资源目录
        resource_dir = None
        resource_config_path = None

        for root, dirs, files in os.walk(extract_dir):
            if "resource_config.json" in files:
                resource_config_path = os.path.join(root, "resource_config.json")
                resource_dir = root
                break

        if not resource_config_path:
            raise ValueError("更新包中未找到resource_config.json文件")

        # 跟踪无法更新的文件
        locked_files = []

        # 应用更新并处理文件锁
        app_root_dir = Path.cwd()
        for root, dirs, files in os.walk(resource_dir):
            # 获取相对路径
            relative_path = os.path.relpath(root, resource_dir)

            # 创建目标目录
            for dir_name in dirs:
                dir_path = original_resource_dir / relative_path / dir_name
                dir_path.mkdir(parents=True, exist_ok=True)

            # 复制/替换文件
            for file_name in files:
                source_file = Path(root) / file_name
                target_file = original_resource_dir / relative_path / file_name
                relative_target = os.path.relpath(target_file, app_root_dir)

                # 尝试更新文件
                try:
                    # 删除现有文件（如果存在）
                    if target_file.exists():
                        target_file.unlink()

                    # 创建父目录（如果不存在）
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # 复制文件
                    shutil.copy2(source_file, target_file)
                except PermissionError:
                    # 文件被锁定，添加到待处理更新
                    locked_files.append(relative_target)
                    self._schedule_pending_update(source_file, relative_target)

        return locked_files

    def _apply_incremental_update(self, resource, extract_dir, original_resource_dir, changes_path):
        """应用增量更新"""
        try:
            # 加载 changes.json
            with open(changes_path, 'r', encoding='utf-8') as f:
                changes = json.load(f)

            # 获取应用程序根目录
            app_root_dir = Path.cwd()

            # 跟踪无法更新的文件
            locked_files = []

            # 处理修改的文件
            if "modified" in changes:
                for file_path in changes["modified"]:
                    # 特殊处理主可执行文件
                    if file_path == "MFWPH.exe":
                        self._schedule_post_restart_update(extract_dir, file_path)
                        continue

                    # 获取源和目标路径
                    source_file = Path(extract_dir) / file_path
                    target_file = app_root_dir / file_path

                    # 确保源文件存在
                    if source_file.exists():
                        # 确保目标目录存在
                        target_file.parent.mkdir(parents=True, exist_ok=True)

                        # 尝试替换文件
                        try:
                            if target_file.exists():
                                target_file.unlink()
                            shutil.copy2(source_file, target_file)
                        except PermissionError:
                            # 文件被锁定，添加到待处理更新
                            locked_files.append(file_path)
                            self._schedule_pending_update(source_file, file_path)

            # 处理添加的文件
            if "added" in changes:
                for file_path in changes["added"]:
                    # 特殊处理主可执行文件
                    if file_path == "MFWPH.exe":
                        self._schedule_post_restart_update(extract_dir, file_path)
                        continue

                    # 获取源和目标路径
                    source_file = Path(extract_dir) / file_path
                    target_file = app_root_dir / file_path

                    # 确保源文件存在
                    if source_file.exists():
                        # 确保目标目录存在
                        target_file.parent.mkdir(parents=True, exist_ok=True)

                        # 尝试添加新文件
                        try:
                            shutil.copy2(source_file, target_file)
                        except PermissionError:
                            # 文件被锁定，添加到待处理更新
                            locked_files.append(file_path)
                            self._schedule_pending_update(source_file, file_path)

            # 处理删除的文件
            if "deleted" in changes:
                for file_path in changes["deleted"]:
                    # 特殊处理主可执行文件
                    if file_path == "MFWPH.exe":
                        continue

                    # 获取目标路径
                    target_file = app_root_dir / file_path

                    # 尝试删除文件（如果存在）
                    if target_file.exists():
                        try:
                            target_file.unlink()
                        except PermissionError:
                            # 文件被锁定，计划在重启后删除
                            locked_files.append(file_path)
                            self._schedule_file_deletion(file_path)

            return locked_files

        except Exception as e:
            # 如果出错，回退到完整更新
            logger.error(f"应用增量更新时出错: {str(e)}, 回退到完整更新")
            return self._apply_full_update(resource, extract_dir, original_resource_dir)

    def _schedule_pending_update(self, source_file, file_path):
        """计划在应用程序重启后更新文件"""
        # 创建待处理更新目录
        pending_dir = Path("assets/pending_updates/files")
        pending_dir.mkdir(parents=True, exist_ok=True)

        # 为源文件创建目标目录
        target_dir = pending_dir / Path(file_path).parent
        target_dir.mkdir(parents=True, exist_ok=True)

        # 将源文件复制到待处理目录
        pending_file = pending_dir / file_path
        shutil.copy2(source_file, pending_file)

        # 添加到待处理操作文件
        self._add_pending_operation("copy", file_path)

    def _schedule_file_deletion(self, file_path):
        """计划在应用程序重启后删除文件"""
        # 添加到待处理操作文件
        self._add_pending_operation("delete", file_path)

    def _schedule_post_restart_update(self, extract_dir, file_path):
        """特殊处理主可执行文件更新"""
        # 创建待处理更新目录
        pending_dir = Path("assets/pending_updates/files")
        pending_dir.mkdir(parents=True, exist_ok=True)

        # 将可执行文件复制到待处理目录
        source_file = Path(extract_dir) / file_path
        pending_file = pending_dir / file_path

        if source_file.exists():
            # 确保父目录存在
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, pending_file)

            # 添加到待处理操作文件，带有特殊可执行标志
            self._add_pending_operation("executable", file_path)

    def _add_pending_operation(self, operation_type, file_path):
        """添加操作到待处理操作文件"""
        # 创建操作文件
        operations_file = Path("assets/pending_updates/operations.json")

        # 读取现有操作（如果文件存在）
        operations = []
        if operations_file.exists():
            try:
                with open(operations_file, 'r', encoding='utf-8') as f:
                    operations = json.load(f)
            except:
                operations = []

        # 添加新操作
        operations.append({
            "type": operation_type,
            "path": file_path,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # 写回文件
        with open(operations_file, 'w', encoding='utf-8') as f:
            json.dump(operations, f, ensure_ascii=False, indent=4)


class ResourceVersionManager(QObject):
    """资源版本管理器"""
    # 信号定义
    rollback_started = Signal(str)  # resource_name
    rollback_completed = Signal(str, str, list)  # resource_name, version, locked_files
    rollback_failed = Signal(str, str)  # resource_name, error_message

    def __init__(self):
        """初始化版本管理器"""
        super().__init__()

    def get_resource_history(self, resource_name):
        """获取资源的备份历史"""
        history_dir = Path("assets/history")
        if not history_dir.exists():
            return []

        # 查找此资源的所有备份
        history_files = []
        for file in history_dir.glob(f"{resource_name}_*.zip"):
            try:
                # 解析文件名以提取版本和时间戳
                # 格式：resource_name_version_timestamp.zip
                parts = file.stem.split('_')
                if len(parts) >= 3:
                    # 提取版本（如果版本包含下划线）
                    timestamp_part = parts[-1]
                    version_parts = parts[1:-1]
                    version = '_'.join(version_parts)

                    # 解析时间戳
                    timestamp = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")

                    history_files.append({
                        "file_path": str(file),
                        "version": version,
                        "timestamp": timestamp,
                        "formatted_date": timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception:
                # 跳过不匹配预期格式的文件
                continue

        # 按时间戳排序（最新优先）
        history_files.sort(key=lambda x: x["timestamp"], reverse=True)
        return history_files

    def rollback_to_version(self, resource_name, backup_file_path):
        """回滚资源到之前的版本"""
        self.rollback_started.emit(resource_name)

        try:
            # 获取资源配置
            resource = None
            for r in global_config.get_all_resource_configs():
                if r.resource_name == resource_name:
                    resource = r
                    break

            if not resource:
                raise ValueError(f"找不到资源 {resource_name}")

            # 获取资源目录
            resource_dir = Path(resource.source_file).parent

            # 创建临时目录进行提取
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # 提取备份
                with zipfile.ZipFile(backup_file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)

                # 在回滚前备份当前版本
                installer = UpdateInstaller()
                installer._create_backup(resource, resource_dir)

                # 查找提取的备份中的根目录
                root_dir = temp_path
                for item in os.listdir(temp_path):
                    item_path = temp_path / item
                    if item_path.is_dir() and (item_path / "resource_config.json").exists():
                        root_dir = item_path
                        break
                    elif item == resource_name and item_path.is_dir():
                        root_dir = item_path
                        break

                # 跟踪锁定的文件
                locked_files = []

                # 选择性更新文件
                for root, dirs, files in os.walk(root_dir):
                    # 获取相对路径
                    if root_dir == temp_path:
                        relative_path = os.path.relpath(root, root_dir)
                    else:
                        # 处理文件在以资源命名的子目录中的情况
                        if root_dir.name == resource_name:
                            relative_path = os.path.relpath(root, root_dir)
                        else:
                            relative_path = os.path.relpath(root, root_dir)

                    # 在目标中创建目录
                    for dir_name in dirs:
                        dir_path = resource_dir / relative_path / dir_name
                        dir_path.mkdir(parents=True, exist_ok=True)

                    # 复制/替换文件
                    for file_name in files:
                        source_file = Path(root) / file_name
                        target_file = resource_dir / relative_path / file_name

                        try:
                            # 删除现有文件（如果存在）
                            if target_file.exists():
                                target_file.unlink()

                            # 创建父目录（如果不存在）
                            target_file.parent.mkdir(parents=True, exist_ok=True)

                            # 复制文件
                            shutil.copy2(source_file, target_file)
                        except PermissionError:
                            # 文件被锁定，计划在重启后更新
                            locked_files.append(str(target_file))
                            installer._schedule_pending_update(source_file, relative_path / file_name)

                # 从备份文件名中提取版本
                backup_filename = Path(backup_file_path).name
                version_parts = backup_filename.split('_')
                version = "unknown"
                if len(version_parts) >= 2:
                    version = version_parts[1]

                # 更新全局配置中的资源版本
                resource.resource_version = version
                global_config.save_all_configs()

                # 完成回滚
                self.rollback_completed.emit(resource_name, version, locked_files)
                return version

        except Exception as e:
            logger.error(f"回滚失败: {str(e)}")
            self.rollback_failed.emit(resource_name, str(e))
            return None

    def clean_history(self, resource_name=None, keep_count=5):
        """清理旧历史文件，只保留最近的几个"""
        history_dir = Path("assets/history")
        if not history_dir.exists():
            return

        try:
            if resource_name:
                # 获取特定资源的历史
                history_files = self.get_resource_history(resource_name)

                # 只保留指定数量的最新备份
                files_to_delete = history_files[keep_count:]

                # 删除较旧的文件
                for file_info in files_to_delete:
                    file_path = Path(file_info["file_path"])
                    if file_path.exists():
                        file_path.unlink()
            else:
                # 按资源分组所有历史文件
                all_resources = {}

                for file in history_dir.glob("*.zip"):
                    # 从文件名中提取资源名称
                    parts = file.stem.split('_')
                    if len(parts) >= 3:
                        res_name = parts[0]
                        if res_name not in all_resources:
                            all_resources[res_name] = []

                        # 解析时间戳
                        try:
                            timestamp_part = parts[-1]
                            timestamp = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")

                            all_resources[res_name].append({
                                "file_path": file,
                                "timestamp": timestamp
                            })
                        except:
                            # 跳过时间戳格式无效的文件
                            continue

                # 对于每个资源，只保留最新的文件
                for res_name, files in all_resources.items():
                    # 按时间戳排序（最新优先）
                    files.sort(key=lambda x: x["timestamp"], reverse=True)

                    # 删除较旧的文件
                    for file_info in files[keep_count:]:
                        file_path = file_info["file_path"]
                        if file_path.exists():
                            file_path.unlink()

            return True
        except Exception as e:
            logger.error(f"清理历史时出错: {str(e)}")
            return False


class PendingUpdateManager(QObject):
    """待处理更新管理器"""
    # 信号定义
    pending_updates_applied = Signal(int, int)  # total_operations, failed_operations

    def __init__(self):
        """初始化待处理更新管理器"""
        super().__init__()

    def get_pending_operations(self):
        """获取所有需要在重启后应用的待处理操作"""
        operations_file = Path("assets/pending_updates/operations.json")
        if not operations_file.exists():
            return []

        try:
            with open(operations_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载待处理操作失败: {str(e)}")
            return []

    def apply_pending_operations(self):
        """在应用程序启动时应用所有待处理操作"""
        operations = self.get_pending_operations()
        if not operations:
            return

        # 获取应用程序根目录
        app_root_dir = Path.cwd()
        pending_dir = Path("assets/pending_updates/files")

        # 创建一个列表来存储失败的操作
        failed_operations = []

        # 按类型排序操作以确保正确的顺序（可执行文件最后）
        operations.sort(key=lambda op: 0 if op["type"] != "executable" else 1)

        # 处理每个操作
        for operation in operations:
            op_type = operation.get("type")
            file_path = operation.get("path")

            if not op_type or not file_path:
                continue

            try:
                if op_type == "copy":
                    # 从待处理目录复制文件到目标位置
                    source = pending_dir / file_path
                    target = app_root_dir / file_path

                    # 确保目标目录存在
                    target.parent.mkdir(parents=True, exist_ok=True)

                    # 复制文件
                    if source.exists():
                        shutil.copy2(source, target)

                elif op_type == "delete":
                    # 删除文件
                    target = app_root_dir / file_path
                    if target.exists():
                        target.unlink()

                elif op_type == "executable":
                    # 特殊处理可执行文件
                    source = pending_dir / file_path
                    target = app_root_dir / file_path

                    # 现在只是尝试直接复制它
                    # 在实际应用中，这可能需要更复杂的方法
                    if source.exists():
                        # 首先尝试重命名原始可执行文件
                        if target.exists():
                            backup = app_root_dir / f"{file_path}.bak"
                            if backup.exists():
                                backup.unlink()
                            target.rename(backup)

                        # 复制新的可执行文件
                        shutil.copy2(source, target)
            except Exception as e:
                # 记录错误并添加到失败的操作
                logger.error(f"应用操作 {op_type} 到 {file_path} 失败: {str(e)}")
                failed_operations.append(operation)

        # 如果有失败，将它们写回文件
        if failed_operations:
            operations_file = Path("assets/pending_updates/operations.json")
            with open(operations_file, 'w', encoding='utf-8') as f:
                json.dump(failed_operations, f, ensure_ascii=False, indent=4)

            self.pending_updates_applied.emit(len(operations), len(failed_operations))
        else:
            # 清除操作文件并清理
            operations_file = Path("assets/pending_updates/operations.json")
            if operations_file.exists():
                operations_file.unlink()

            # 清理待处理目录
            if pending_dir.exists():
                try:
                    shutil.rmtree(pending_dir)
                except:
                    pass

            self.pending_updates_applied.emit(len(operations), 0)


# 初始化函数
def initialize_update_system():
    """在应用程序启动时初始化更新系统"""
    try:
        # 创建必要的目录
        Path("assets/temp").mkdir(parents=True, exist_ok=True)
        Path("assets/history").mkdir(parents=True, exist_ok=True)
        Path("assets/pending_updates").mkdir(parents=True, exist_ok=True)

        # 应用前一个会话中的任何待处理操作
        pending_manager = PendingUpdateManager()
        pending_manager.apply_pending_operations()

        # 清理临时目录
        try:
            temp_dir = Path("assets/temp")
            if temp_dir.exists():
                for item in temp_dir.iterdir():
                    if item.is_file():
                        item.unlink()
        except Exception as e:
            logger.warning(f"清理临时目录失败: {str(e)}")

        return True
    except Exception as e:
        logger.error(f"初始化更新系统失败: {str(e)}")
        return False


# 当模块被导入时调用初始化函数
initialize_update_system()