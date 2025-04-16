import json
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class DownloadThread(QThread):
    """Unified thread for downloading resources and updates"""
    progress_updated = Signal(str, float, float)  # resource_name, progress, speed
    download_completed = Signal(str, str, object)  # resource_name, file_path, data/resource
    download_failed = Signal(str, str)  # resource_name, error

    def __init__(self, resource_name, url, output_dir, data=None, resource=None, version=None):
        super().__init__()
        self.resource_name = resource_name
        self.url = url
        self.output_dir = output_dir
        self.data = data
        self.resource = resource
        self.version = version or "1.0.0"
        self.is_cancelled = False

    def run(self):
        try:
            if self.url is None or self.url == "":
                raise RuntimeError("can't download resource,cdk为空或cdk不存在")
            # Create output filename
            filename = f"{self.resource_name}_{self.version}.zip"
            output_path = self.output_dir / filename
            # Download file with progress
            response = requests.get(self.url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0)) or 1024 * 1024  # Default 1MB
            chunk_size = max(4096, total_size // 100)

            with open(output_path, 'wb') as f:
                downloaded = 0
                last_update_time = time.time()

                for chunk in response.iter_content(chunk_size=chunk_size):
                    if self.is_cancelled:
                        f.close()
                        if output_path.exists():
                            output_path.unlink()
                        return

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Calculate progress and speed
                        progress = (downloaded / total_size) * 100
                        current_time = time.time()
                        elapsed = current_time - last_update_time

                        if elapsed >= 0.5:
                            speed = (chunk_size / 1024 / 1024) / elapsed  # MB/s
                            self.progress_updated.emit(self.resource_name, progress, speed)
                            last_update_time = current_time

            # Send completion signal
            result_data = self.resource if self.resource else self.data
            self.download_completed.emit(self.resource_name, str(output_path), result_data)
        except Exception as e:
            self.download_failed.emit(self.resource_name, str(e))

    def cancel(self):
        """Cancel download"""
        self.is_cancelled = True


class UpdateCheckThread(QThread):
    """Thread for checking updates using API or GitHub"""
    update_found = Signal(str, str, str, str,
                          str)  # resource_name, latest_version, current_version, download_url, update_type
    update_not_found = Signal(str)  # resource_name (single mode only)
    check_failed = Signal(str, str)  # resource_name, error_message (single mode only)
    check_completed = Signal(int, int)  # total_checked, updates_found (batch mode only)

    def __init__(self, resources, single_mode=False):
        super().__init__()
        self.resources = [resources] if single_mode else resources
        self.single_mode = single_mode
        self.update_method = global_config.get_app_config().update_method
        # 根据更新方法设置基础URL
        self.mirror_base_url = "https://mirrorchyan.com/api"
        self.github_api_url = "https://api.github.com"
        self.logger = log_manager.get_app_logger()

    def run(self):
        updates_found = 0

        for resource in self.resources:
            if self.update_method == "MirrorChyan":
                # 使用Mirror酱API更新检查
                updates_found += self._check_update_mirror(resource)
            else:
                # 使用GitHub更新检查
                updates_found += self._check_update_github(resource)

        # Signal completion in batch mode
        if not self.single_mode:
            self.check_completed.emit(len(self.resources), updates_found)

    def _check_update_mirror(self, resource):
        """使用Mirror酱API检查更新"""
        # 获取资源更新服务ID
        rid = resource.resource_update_service_id
        if not rid:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "没有配置更新源")
            return 0

        try:
            # 从全局配置中获取 CDK（如果有配置）
            cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

            # 根据测试版设置选择更新通道
            channel = "beta" if global_config.get_app_config().receive_beta_update else "stable"

            # 构造 API URL 与参数
            api_url = f"{self.mirror_base_url}/resources/{rid}/latest"
            params = {
                "current_version": resource.resource_version,
                "cdk": cdk,
                "user_agent": "ResourceDownloader",
                "channel": channel  # 根据配置动态选择通道
            }

            # 打印日志时移除或隐藏 cdk
            log_params = params.copy()
            log_params["cdk"] = "***"  # 或者使用 log_params.pop("cdk") 来完全移除

            self.logger.debug(
                f"检查资源:{resource.resource_name}更新,api_url:{api_url},params:{log_params}"
            )

            response = requests.get(api_url, params=params)

            self.logger.debug(f"资源检查响应:{response}")
            # 定义业务逻辑错误码与说明的对应关系
            error_map = {
                1001: "INVALID_PARAMS: 参数不正确，请参考集成文档",
                7001: "KEY_EXPIRED: CDK 已过期",
                7002: "KEY_INVALID: CDK 错误",
                7003: "RESOURCE_QUOTA_EXHAUSTED: CDK 今日下载次数已达上限",
                7004: "KEY_MISMATCHED: CDK 类型和待下载的资源不匹配",
                8001: "RESOURCE_NOT_FOUND: 对应架构和系统下的资源不存在",
                8002: "INVALID_OS: 错误的系统参数",
                8003: "INVALID_ARCH: 错误的架构参数",
                8004: "INVALID_CHANNEL: 错误的更新通道参数",
                1: "UNDIVIDED: 未区分的业务错误，以响应体 JSON 的 msg 为准",
            }

            # 处理非200状态码
            if response.status_code != 200:
                error_message = f"API返回错误 ({response.status_code})"

                # 尝试解析错误响应中的JSON数据
                try:
                    error_data = response.json()
                    error_code = error_data.get("code")
                    error_msg = error_data.get("msg", "")

                    if error_code is not None:
                        # 查找对应的错误描述
                        error_detail = error_map.get(error_code, error_msg or "未知业务错误")
                        error_message = f"业务错误 ({error_code}): {error_detail}"
                except:
                    # 如果无法解析JSON，仅使用HTTP状态码作为错误信息
                    pass

                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, error_message)
                return 0

            # 解析返回的 JSON 数据
            result = response.json()

            # 错误码处理
            error_code = result.get("code")
            # 确保error_code不是None并且不等于0
            if error_code is not None and error_code != 0:
                if error_code > 0:
                    # 业务逻辑错误，根据返回码寻找对应的错误说明
                    detail = error_map.get(error_code, result.get("msg", "未知业务错误，请联系 Mirror 酱技术支持"))
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, f"业务错误 ({error_code}): {detail}")
                else:  # 处理error_code < 0的情况
                    # 意料之外的严重错误
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name,
                                               "意料之外的严重错误，请及时联系 Mirror 酱的技术支持处理")
                return 0

            # 若接口返回成功（code == 0），则从数据中提取版本与下载链接
            data = result.get("data", {})
            latest_version = data.get("version_name", "")
            download_url = data.get("url", "")
            update_type = data.get("update_type", "full")

            if latest_version and latest_version != resource.resource_version:
                # 检测到新版本，发出更新通知
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url,
                    update_type
                )
                return 1
            elif self.single_mode:
                # 未检测到新版本，发出没有更新的信号
                self.update_not_found.emit(resource.resource_name)
                return 0

        except Exception as e:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, f"检查更新异常: {str(e)}")
            return 0

        return 0

    def _check_update_github(self, resource):
        """使用GitHub检查更新"""
        repo_url = resource.resource_rep_url

        if not repo_url or "github.com" not in repo_url:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, "未配置有效的GitHub仓库URL")
            return 0

        try:
            # 解析GitHub仓库URL
            repo_parts = repo_url.rstrip("/").split("github.com/")
            if len(repo_parts) != 2:
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, "GitHub仓库URL格式无效")
                return 0

            owner_repo = repo_parts[1]

            # 获取GitHub仓库最新的发布版本
            api_url = f"{self.github_api_url}/repos/{owner_repo}/releases/latest"

            # 设置请求头
            headers = {
                "Accept": "application/vnd.github.v3+json"
            }

            # 发送请求
            response = requests.get(api_url, headers=headers)

            if response.status_code == 404:
                # 尝试获取tags
                api_url = f"{self.github_api_url}/repos/{owner_repo}/tags"
                response = requests.get(api_url, headers=headers)
            # Handle HTTP errors
            if response.status_code == 403:
                error_message = "请求被拒绝 (403)：可能是超出了 API 请求速率限制或缺少认证信息。"
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, error_message)
                return 0

            if response.status_code != 200:
                if self.single_mode:
                    self.check_failed.emit(resource.resource_name, f"GitHub API返回错误 ({response.status_code})")
                return 0

            result = response.json()

            # 解析返回结果
            if "/releases/latest" in api_url:
                # 处理releases数据
                latest_version = result.get("tag_name", "")
                download_assets = result.get("assets", [])
                if download_assets:
                    # 获取第一个资源的下载URL
                    download_url = download_assets[0].get("browser_download_url", "")
                else:
                    # 如果没有资源，使用zip下载URL
                    download_url = result.get("zipball_url", "")
            else:
                # 处理tags数据
                if not result or not isinstance(result, list):
                    if self.single_mode:
                        self.check_failed.emit(resource.resource_name, "无法找到任何版本标签")
                    return 0

                # 获取最新的tag
                latest_tag = result[0]
                latest_version = latest_tag.get("name", "").lstrip("v")

                # 构建下载URL
                download_url = f"https://github.com/{owner_repo}/archive/refs/tags/{latest_tag.get('name', '')}.zip"

            # 比较版本
            if latest_version and latest_version != resource.resource_version:
                self.update_found.emit(
                    resource.resource_name,
                    latest_version,
                    resource.resource_version,
                    download_url,
                    "full"  # GitHub默认为完整更新
                )
                return 1
            elif self.single_mode:
                self.update_not_found.emit(resource.resource_name)
                return 0

        except Exception as e:
            if self.single_mode:
                self.check_failed.emit(resource.resource_name, f"检查GitHub更新时出错: {str(e)}")
            return 0

        return 0


def process_github_repo(repo_url, data, download_callback, error_callback):
    """Process GitHub repository URL to get download URL"""
    try:
        # Parse GitHub URL
        parts = repo_url.split('github.com/')[1].split('/')
        if len(parts) < 2:
            error_callback("GitHub地址格式不正确")
            return

        owner, repo = parts[0], parts[1]
        if repo.endswith('.git'):
            repo = repo[:-4]

        # Get latest release info
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        response = requests.get(api_url)

        if response.status_code != 200:
            error_callback(f"API返回错误 ({response.status_code})")
            return

        release_info = response.json()
        latest_version = release_info.get('tag_name', '').lstrip('v')

        # Use repo name if name not provided
        if not data["name"]:
            data["name"] = repo

        # Find ZIP asset
        download_url = None
        for asset in release_info.get('assets', []):
            if asset.get('name', '').endswith('.zip'):
                download_url = asset.get('browser_download_url')
                break

        if not download_url:
            error_callback("找不到可下载的资源包")
            return

        # Download ZIP
        download_callback(download_url, data, latest_version)

    except Exception as e:
        error_callback(str(e))


def install_new_resource(resource_name, file_path, data):
    """Install a newly downloaded resource"""
    with tempfile.TemporaryDirectory() as extract_dir:
        # Extract ZIP
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Find or create resource config
        resource_dir, resource_config_path = find_or_create_config(extract_dir, data, resource_name)

        # Create target directory
        target_dir = Path(f"assets/resource/{resource_name.lower().replace(' ', '_')}")
        if target_dir.exists():
            shutil.rmtree(target_dir)

        # Copy files to target directory
        shutil.copytree(resource_dir, target_dir)

        # Load new resource config
        global_config.load_resource_config(str(target_dir / "resource_config.json"))


def find_or_create_config(extract_dir, data, resource_name):
    """Find existing config or create a new one"""
    # Try to find existing config
    for root, dirs, files in os.walk(extract_dir):
        if "resource_config.json" in files:
            return root, os.path.join(root, "resource_config.json")

    # Create new config
    main_dir = extract_dir
    for item in os.listdir(extract_dir):
        item_path = os.path.join(extract_dir, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            main_dir = item_path
            break

    # Create resource config
    resource_config = {
        "resource_name": data["name"] or resource_name,
        "resource_version": data.get("version", "1.0.0"),
        "resource_author": data.get("author", "未知"),
        "resource_description": data["description"] or "从外部源添加的资源",
        "resource_update_service_id": data["url"] if "github.com" in data["url"] else ""
    }

    # Write config file
    resource_config_path = os.path.join(main_dir, "resource_config.json")
    with open(resource_config_path, 'w', encoding='utf-8') as f:
        json.dump(resource_config, f, ensure_ascii=False, indent=4)

    return main_dir, resource_config_path


def install_update(resource, file_path):
    """Install an update for an existing resource"""
    # 获取传入的新版本号（从start_update方法传递过来的version参数）
    new_version = resource.temp_version if hasattr(resource, 'temp_version') else None
    # 获取更新类型（从start_update方法传递过来的update_type参数）
    update_type = resource.temp_update_type if hasattr(resource, 'temp_update_type') else "full"

    with tempfile.TemporaryDirectory() as extract_dir:
        # Extract ZIP
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # Get original resource directory
        original_resource_dir = Path(resource.source_file).parent

        # Handle incremental update
        locked_files = []
        if update_type == "incremental":
            changes_path = os.path.join(extract_dir, "changes.json")

            if os.path.exists(changes_path):
                locked_files = apply_incremental_update(resource, extract_dir, original_resource_dir, changes_path)
            else:
                # Fall back to full update if changes.json is missing
                locked_files = apply_full_update(resource, extract_dir, original_resource_dir)
        else:
            # Handle full update
            locked_files = apply_full_update(resource, extract_dir, original_resource_dir)

        # Reload resource config
        global_config.load_resource_config(str(original_resource_dir / "resource_config.json"))

        # Make sure the version is updated in global_config
        for r in global_config.get_all_resource_configs():
            if r.resource_name == resource.resource_name and new_version:
                r.resource_version = new_version
                break

        # Save all configs
        global_config.save_all_configs()

        return locked_files


def apply_full_update(resource, extract_dir, original_resource_dir):
    """Apply a full update by replacing all files with file lock handling"""
    # Find resource directory
    resource_dir = None
    resource_config_path = None

    for root, dirs, files in os.walk(extract_dir):
        if "resource_config.json" in files:
            resource_config_path = os.path.join(root, "resource_config.json")
            resource_dir = root
            break

    if not resource_config_path:
        raise ValueError("更新包中未找到resource_config.json文件")

    # Create backup of files that will be updated
    create_selective_backup(resource, resource_dir, original_resource_dir)

    # List to track files that couldn't be updated due to locks
    locked_files = []

    # Apply update with file lock handling
    app_root_dir = Path.cwd()
    for root, dirs, files in os.walk(resource_dir):
        # Get relative path from source directory
        relative_path = os.path.relpath(root, resource_dir)

        # Create directories in target if they don't exist
        for dir_name in dirs:
            dir_path = original_resource_dir / relative_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

        # Copy/replace files
        for file_name in files:
            source_file = Path(root) / file_name
            target_file = original_resource_dir / relative_path / file_name
            relative_target = os.path.relpath(target_file, app_root_dir)

            # Try to update the file
            try:
                # Delete existing file if it exists
                if target_file.exists():
                    target_file.unlink()

                # Create parent directory if it doesn't exist
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(source_file, target_file)
            except PermissionError:
                # File is locked, add to pending updates
                locked_files.append(relative_target)
                schedule_pending_update(source_file, relative_target)

    # Return list of locked files to be shown in UI
    return locked_files


def apply_incremental_update(resource, extract_dir, original_resource_dir, changes_path):
    """Apply an incremental update based on changes.json"""
    try:
        # Load changes.json
        with open(changes_path, 'r', encoding='utf-8') as f:
            changes = json.load(f)

        # Get application root directory (where the application is running from)
        app_root_dir = Path.cwd()

        # Create directories to store pending operations
        pending_dir = Path("assets/pending_updates")
        pending_dir.mkdir(parents=True, exist_ok=True)

        # List to track files that couldn't be updated due to locks
        locked_files = []

        # Create backup for modified files
        create_incremental_backup(resource, changes, app_root_dir)

        # Handle modified files
        if "modified" in changes:
            for file_path in changes["modified"]:
                # Special handling for main executable
                if file_path == "MFWPH.exe":
                    # Handle MFWPH.exe with post-restart update mechanism
                    schedule_post_restart_update(extract_dir, file_path)
                    continue

                # Get source and target paths
                source_file = Path(extract_dir) / file_path
                target_file = app_root_dir / file_path

                # Ensure source file exists
                if source_file.exists():
                    # Ensure target directory exists
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # Try to replace file
                    try:
                        if target_file.exists():
                            target_file.unlink()
                        shutil.copy2(source_file, target_file)
                    except PermissionError:
                        # File is locked, add to pending updates
                        locked_files.append(file_path)
                        schedule_pending_update(source_file, file_path)

        # Handle added files
        if "added" in changes:
            for file_path in changes["added"]:
                # Special handling for main executable
                if file_path == "MFWPH.exe":
                    # Handle MFWPH.exe with post-restart update mechanism
                    schedule_post_restart_update(extract_dir, file_path)
                    continue

                # Get source and target paths
                source_file = Path(extract_dir) / file_path
                target_file = app_root_dir / file_path

                # Ensure source file exists
                if source_file.exists():
                    # Ensure target directory exists
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # Try to add new file
                    try:
                        shutil.copy2(source_file, target_file)
                    except PermissionError:
                        # File is locked, add to pending updates
                        locked_files.append(file_path)
                        schedule_pending_update(source_file, file_path)

        # Handle deleted files
        if "deleted" in changes:
            for file_path in changes["deleted"]:
                # Special handling for main executable
                if file_path == "MFWPH.exe":
                    continue

                # Get target path
                target_file = app_root_dir / file_path

                # Try to delete file if it exists
                if target_file.exists():
                    try:
                        target_file.unlink()
                    except PermissionError:
                        # File is locked, schedule for deletion after restart
                        locked_files.append(file_path)
                        schedule_file_deletion(file_path)

        # Return list of locked files
        return locked_files

    except Exception as e:
        # If anything goes wrong, fall back to full update
        logger = log_manager.get_app_logger()
        logger.error(f"应用增量更新时出错: {str(e)}, 回退到完整更新")
        return apply_full_update(resource, extract_dir, original_resource_dir)


def schedule_pending_update(source_file, file_path):
    """Schedule a file to be updated after application restart"""
    # Create pending updates directory if it doesn't exist
    pending_dir = Path("assets/pending_updates/files")
    pending_dir.mkdir(parents=True, exist_ok=True)

    # Create target directory for the source file
    target_dir = pending_dir / Path(file_path).parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy the source file to the pending directory
    pending_file = pending_dir / file_path
    shutil.copy2(source_file, pending_file)

    # Add to the pending operations file
    add_pending_operation("copy", file_path)


def schedule_file_deletion(file_path):
    """Schedule a file to be deleted after application restart"""
    # Add to the pending operations file
    add_pending_operation("delete", file_path)


def schedule_post_restart_update(extract_dir, file_path):
    """Special handling for updating the main executable"""
    # Create pending updates directory if it doesn't exist
    pending_dir = Path("assets/pending_updates/files")
    pending_dir.mkdir(parents=True, exist_ok=True)

    # Copy the executable to the pending directory
    source_file = Path(extract_dir) / file_path
    pending_file = pending_dir / file_path

    if source_file.exists():
        # Ensure parent directory exists
        pending_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, pending_file)

        # Add to the pending operations file with special executable flag
        add_pending_operation("executable", file_path)


def add_pending_operation(operation_type, file_path):
    """Add an operation to the pending operations file"""
    # Create operations file
    operations_file = Path("assets/pending_updates/operations.json")

    # Read existing operations if file exists
    operations = []
    if operations_file.exists():
        try:
            with open(operations_file, 'r', encoding='utf-8') as f:
                operations = json.load(f)
        except:
            operations = []

    # Add new operation
    operations.append({
        "type": operation_type,
        "path": file_path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # Write back to file
    with open(operations_file, 'w', encoding='utf-8') as f:
        json.dump(operations, f, ensure_ascii=False, indent=4)


def show_locked_files_message(resource_name, locked_files, parent=None):
    """Show a message to the user about locked files"""
    if not locked_files or len(locked_files) == 0:
        return ""

    # Create a message with the list of locked files
    message = f"资源 {resource_name} 的以下文件因被占用无法立即更新，将在应用重启后完成更新：\n\n"

    # Limit the number of files shown to avoid excessively long messages
    max_files_to_show = 10
    files_to_show = locked_files[:max_files_to_show]

    for file in files_to_show:
        message += f"• {file}\n"

    if len(locked_files) > max_files_to_show:
        message += f"\n...以及其他 {len(locked_files) - max_files_to_show} 个文件"

    message += "\n\n这些文件将在应用下次启动时自动更新。"

    # Show message box if parent is provided
    if parent:
        QMessageBox.information(parent, "文件更新待处理", message)

    return message


def create_incremental_backup(resource, changes, app_root_dir):
    """Create a backup of only the modified and deleted files in an incremental update"""
    # Create history directory
    history_dir = Path("assets/history")
    history_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{resource.resource_name}_{resource.resource_version}_{timestamp}.zip"
    backup_path = history_dir / backup_filename

    # Only backup files that will be modified or deleted
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Backup modified files
        if "modified" in changes:
            for file_path in changes["modified"]:
                # Get the original file path
                original_file_path = app_root_dir / file_path
                if original_file_path.exists():
                    # Add to backup with proper relative path
                    arcname = file_path
                    zipf.write(original_file_path, arcname)

        # Backup deleted files
        if "deleted" in changes:
            for file_path in changes["deleted"]:
                # Get the original file path
                original_file_path = app_root_dir / file_path
                if original_file_path.exists():
                    # Add to backup with proper relative path
                    arcname = file_path
                    zipf.write(original_file_path, arcname)


def create_selective_backup(resource, update_dir, original_dir):
    """Create a backup of only the files that will be updated"""
    # Create history directory
    history_dir = Path("assets/history")
    history_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{resource.resource_name}_{resource.resource_version}_{timestamp}.zip"
    backup_path = history_dir / backup_filename

    # Only backup files that exist in the update package
    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(update_dir):
            for file in files:
                # Get relative path from update directory
                relative_path = os.path.relpath(os.path.join(root, file), update_dir)

                # Check if this file exists in original directory
                original_file_path = original_dir / relative_path
                if original_file_path.exists():
                    # Add to backup with proper relative path
                    arcname = f"{resource.resource_name}/{relative_path}"
                    zipf.write(original_file_path, arcname)


def selective_update(source_dir, target_dir):
    """Selectively update files instead of replacing entire directory"""
    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        # Get relative path from source directory
        relative_path = os.path.relpath(root, source_dir)

        # Create directories in target if they don't exist
        for dir_name in dirs:
            dir_path = target_dir / relative_path / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)

        # Copy/replace files
        for file_name in files:
            source_file = Path(root) / file_name
            target_file = target_dir / relative_path / file_name

            # Delete existing file if it exists
            if target_file.exists():
                target_file.unlink()

            # Create parent directory if it doesn't exist
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy the file
            shutil.copy2(source_file, target_file)


