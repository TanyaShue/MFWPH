import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.utils.update_check import install_update, schedule_pending_update


class ResourceDownloader:
    """Resource downloader class with batch operations capability"""

    @staticmethod
    def get_pending_operations():
        """Get all pending operations that need to be applied after restart"""
        operations_file = Path("assets/pending_updates/operations.json")
        if not operations_file.exists():
            return []

        try:
            with open(operations_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.error(f"Failed to load pending operations: {str(e)}")
            return []

    @staticmethod
    def apply_pending_operations():
        """Apply all pending operations on application startup"""
        operations = ResourceDownloader.get_pending_operations()
        if not operations:
            return

        # Get app root directory
        app_root_dir = Path.cwd()
        pending_dir = Path("assets/pending_updates/files")

        # Create a list to store operations that failed
        failed_operations = []

        # Sort operations by type to ensure proper order (executable last)
        operations.sort(key=lambda op: 0 if op["type"] != "executable" else 1)

        # Process each operation
        for operation in operations:
            op_type = operation.get("type")
            file_path = operation.get("path")

            if not op_type or not file_path:
                continue

            try:
                if op_type == "copy":
                    # Copy file from pending to target
                    source = pending_dir / file_path
                    target = app_root_dir / file_path

                    # Ensure target directory exists
                    target.parent.mkdir(parents=True, exist_ok=True)

                    # Copy the file
                    if source.exists():
                        shutil.copy2(source, target)

                elif op_type == "delete":
                    # Delete the file
                    target = app_root_dir / file_path
                    if target.exists():
                        target.unlink()

                elif op_type == "executable":
                    # Special handling for executable
                    source = pending_dir / file_path
                    target = app_root_dir / file_path

                    # For now, just try to copy it directly
                    # In a real application, this might require a more complex approach
                    if source.exists():
                        # Try to rename the original executable first
                        if target.exists():
                            backup = app_root_dir / f"{file_path}.bak"
                            if backup.exists():
                                backup.unlink()
                            target.rename(backup)

                        # Copy the new executable
                        shutil.copy2(source, target)
            except Exception as e:
                # Log the error and add to failed operations
                logger = log_manager.get_app_logger()
                logger.error(f"Failed to apply operation {op_type} for {file_path}: {str(e)}")
                failed_operations.append(operation)

        # If there were failures, write them back to the file
        if failed_operations:
            with open(operations_file, 'w', encoding='utf-8') as f:
                json.dump(failed_operations, f, ensure_ascii=False, indent=4)
        else:
            # Clear the operations file and clean up
            operations_file = Path("assets/pending_updates/operations.json")
            if operations_file.exists():
                operations_file.unlink()

            # Clean up the pending directory
            if pending_dir.exists():
                try:
                    shutil.rmtree(pending_dir)
                except:
                    pass

    @staticmethod
    def check_and_apply_updates_for_all_resources():
        """Check for updates for all resources and apply them if available"""
        resources = global_config.get_all_resource_configs()
        resources_with_update = [r for r in resources if r.resource_update_service_id]

        if not resources_with_update:
            return "没有找到配置了更新源的资源"

        # Create temp directory
        temp_dir = Path("assets/temp")
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Track update stats
        updates_found = 0
        updates_applied = 0
        update_errors = []

        # Check each resource
        for resource in resources_with_update:
            try:
                # Check for update (simplified version)
                update_found, latest_version, download_url, update_type = ResourceDownloader.check_for_update(resource)

                if update_found:
                    updates_found += 1
                    # Download and apply update
                    success = ResourceDownloader.download_and_apply_update(
                        resource, download_url, latest_version, update_type, temp_dir
                    )
                    if success:
                        updates_applied += 1
                    else:
                        update_errors.append(f"资源 {resource.resource_name} 更新失败")
            except Exception as e:
                update_errors.append(f"资源 {resource.resource_name} 检查或更新时出错: {str(e)}")

        # Build result message
        if updates_found == 0:
            return "所有资源均为最新版本"
        else:
            message = f"找到 {updates_found} 个更新，成功应用 {updates_applied} 个"
            if update_errors:
                message += f"\n错误:\n" + "\n".join(update_errors)
            return message

    @staticmethod
    def check_for_update(resource):
        """Check if an update is available for a resource"""
        # Determine update method
        update_method = global_config.get_app_config().update_method

        # Default return values
        update_found = False
        latest_version = ""
        download_url = ""
        update_type = "full"

        try:
            if update_method == "MirrorChyan":
                # Get resource update service ID
                rid = resource.resource_update_service_id
                if not rid:
                    return update_found, latest_version, download_url, update_type

                # Get CDK from global config
                cdk = global_config.get_app_config().CDK if hasattr(global_config.get_app_config(), 'CDK') else ""

                # Determine update channel
                channel = "beta" if global_config.get_app_config().receive_beta_update else "stable"

                # Construct API URL and parameters
                api_url = f"https://mirrorchyan.com/api/resources/{rid}/latest"
                params = {
                    "current_version": resource.resource_version,
                    "cdk": cdk,
                    "user_agent": "ResourceDownloader",
                    "channel": channel
                }

                # Make API request
                response = requests.get(api_url, params=params)
                response.raise_for_status()

                # Parse response
                result = response.json()

                # Check error code
                error_code = result.get("code")
                if error_code is not None and error_code != 0:
                    return update_found, latest_version, download_url, update_type

                # Extract data
                data = result.get("data", {})
                latest_version = data.get("version_name", "")
                download_url = data.get("url", "")
                update_type = data.get("update_type", "full")

                # Determine if update is available
                if latest_version and latest_version != resource.resource_version:
                    update_found = True
            else:
                # GitHub update check
                repo_url = resource.resource_rep_url
                if not repo_url or "github.com" not in repo_url:
                    return update_found, latest_version, download_url, update_type

                # Parse GitHub repository URL
                repo_parts = repo_url.rstrip("/").split("github.com/")
                if len(repo_parts) != 2:
                    return update_found, latest_version, download_url, update_type

                owner_repo = repo_parts[1]

                # Get latest release info
                api_url = f"https://api.github.com/repos/{owner_repo}/releases/latest"
                headers = {"Accept": "application/vnd.github.v3+json"}

                response = requests.get(api_url, headers=headers)

                if response.status_code == 404:
                    # Try tags instead
                    api_url = f"https://api.github.com/repos/{owner_repo}/tags"
                    response = requests.get(api_url, headers=headers)

                response.raise_for_status()
                result = response.json()

                # Parse result
                if "/releases/latest" in api_url:
                    # Handle releases
                    latest_version = result.get("tag_name", "")
                    download_assets = result.get("assets", [])
                    if download_assets:
                        download_url = download_assets[0].get("browser_download_url", "")
                    else:
                        download_url = result.get("zipball_url", "")
                else:
                    # Handle tags
                    if result and isinstance(result, list) and len(result) > 0:
                        latest_tag = result[0]
                        latest_version = latest_tag.get("name", "").lstrip("v")
                        download_url = f"https://github.com/{owner_repo}/archive/refs/tags/{latest_tag.get('name', '')}.zip"

                # Determine if update is available
                if latest_version and latest_version != resource.resource_version:
                    update_found = True
        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.error(f"Error checking for update: {str(e)}")

        return update_found, latest_version, download_url, update_type

    @staticmethod
    def download_and_apply_update(resource, download_url, version, update_type, temp_dir):
        """Download and apply an update for a resource"""
        try:
            # Set temporary attributes
            resource.temp_version = version
            resource.temp_update_type = update_type

            # Create output filename
            filename = f"{resource.resource_name}_{version}.zip"
            output_path = temp_dir / filename

            # Download file
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Apply update
            locked_files = install_update(resource, str(output_path))

            # Log information about locked files
            if locked_files and len(locked_files) > 0:
                logger = log_manager.get_app_logger()
                logger.info(
                    f"Resource {resource.resource_name} has {len(locked_files)} locked files that will be updated on restart")

            return True
        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.error(f"Error downloading or applying update: {str(e)}")
            return False


class ResourceVersionManager:
    """Manages resource versions, history and rollbacks"""

    @staticmethod
    def get_resource_history(resource_name):
        """Get backup history for a specific resource"""
        history_dir = Path("assets/history")
        if not history_dir.exists():
            return []

        # Find all backups for this resource
        history_files = []
        for file in history_dir.glob(f"{resource_name}_*.zip"):
            try:
                # Parse filename to extract version and timestamp
                # Format: resource_name_version_timestamp.zip
                parts = file.stem.split('_')
                if len(parts) >= 3:
                    # Extract version (could be multiple parts if version has underscores)
                    timestamp_part = parts[-1]
                    version_parts = parts[1:-1]
                    version = '_'.join(version_parts)

                    # Parse timestamp
                    timestamp = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")

                    history_files.append({
                        "file_path": str(file),
                        "version": version,
                        "timestamp": timestamp,
                        "formatted_date": timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    })
            except Exception:
                # Skip files that don't match the expected format
                continue

        # Sort by timestamp (newest first)
        history_files.sort(key=lambda x: x["timestamp"], reverse=True)
        return history_files

    @staticmethod
    def rollback_to_version(resource_name, backup_file_path):
        """Roll back a resource to a previous version from backup"""
        try:
            # Get the resource configuration
            resource = None
            for r in global_config.get_all_resource_configs():
                if r.resource_name == resource_name:
                    resource = r
                    break

            if not resource:
                raise ValueError(f"找不到资源 {resource_name}")

            # Get the resource directory
            resource_dir = Path(resource.source_file).parent

            # Create temp directory for extraction
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Extract backup
                with zipfile.ZipFile(backup_file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)

                # Backup current version before rollback
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                rollback_backup_filename = f"{resource_name}_{resource.resource_version}_{timestamp}_pre_rollback.zip"
                rollback_backup_path = Path("assets/history") / rollback_backup_filename

                # Ensure history directory exists
                Path("assets/history").mkdir(parents=True, exist_ok=True)

                # Create backup of current version
                with zipfile.ZipFile(rollback_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(resource_dir):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = f"{resource_name}/{os.path.relpath(file_path, resource_dir)}"
                            zipf.write(file_path, arcname)

                # Find the root directory in the extracted backup
                # This might be just temp_path or a subdirectory like temp_path/resource_name
                root_dir = temp_path
                for item in os.listdir(temp_path):
                    item_path = temp_path / item
                    if item_path.is_dir() and (item_path / "resource_config.json").exists():
                        root_dir = item_path
                        break
                    elif item == resource_name and item_path.is_dir():
                        root_dir = item_path
                        break

                # Keep track of locked files
                locked_files = []

                # Selectively update files
                for root, dirs, files in os.walk(root_dir):
                    # Get relative path
                    if root_dir == temp_path:
                        relative_path = os.path.relpath(root, root_dir)
                    else:
                        # Handle case where files are in a subdirectory named after the resource
                        if root_dir.name == resource_name:
                            relative_path = os.path.relpath(root, root_dir)
                        else:
                            # Handle other cases
                            relative_path = os.path.relpath(root, root_dir)

                    # Create directories in target
                    for dir_name in dirs:
                        dir_path = resource_dir / relative_path / dir_name
                        dir_path.mkdir(parents=True, exist_ok=True)

                    # Copy/replace files
                    for file_name in files:
                        source_file = Path(root) / file_name
                        target_file = resource_dir / relative_path / file_name

                        try:
                            # Delete existing file if it exists
                            if target_file.exists():
                                target_file.unlink()

                            # Create parent directory if it doesn't exist
                            target_file.parent.mkdir(parents=True, exist_ok=True)

                            # Copy the file
                            shutil.copy2(source_file, target_file)
                        except PermissionError:
                            # File is locked, schedule for update after restart
                            locked_files.append(str(target_file))
                            schedule_pending_update(source_file, relative_path / file_name)

                # Extract version from the backup filename
                backup_filename = Path(backup_file_path).name
                version_parts = backup_filename.split('_')
                if len(version_parts) >= 2:
                    version = version_parts[1]

                    # Update resource version in global_config
                    resource.resource_version = version
                    global_config.save_all_configs()

                # Return result with locked files information
                return {
                    "success": True,
                    "locked_files": locked_files,
                    "message": f"资源已回滚到版本 {version}"
                }

        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.error(f"Rollback failed: {str(e)}")
            return {
                "success": False,
                "message": f"回滚失败: {str(e)}"
            }

    @staticmethod
    def clean_history(resource_name=None, keep_count=5):
        """Clean up old history files, keeping only the most recent ones"""
        history_dir = Path("assets/history")
        if not history_dir.exists():
            return

        try:
            if resource_name:
                # Get history for specific resource
                history_files = ResourceVersionManager.get_resource_history(resource_name)

                # Keep only the specified number of most recent backups
                files_to_delete = history_files[keep_count:]

                # Delete older files
                for file_info in files_to_delete:
                    file_path = Path(file_info["file_path"])
                    if file_path.exists():
                        file_path.unlink()
            else:
                # Group all history files by resource
                all_resources = {}

                for file in history_dir.glob("*.zip"):
                    # Extract resource name from filename
                    parts = file.stem.split('_')
                    if len(parts) >= 3:
                        res_name = parts[0]
                        if res_name not in all_resources:
                            all_resources[res_name] = []

                        # Parse timestamp
                        try:
                            timestamp_part = parts[-1]
                            timestamp = datetime.strptime(timestamp_part, "%Y%m%d_%H%M%S")

                            all_resources[res_name].append({
                                "file_path": file,
                                "timestamp": timestamp
                            })
                        except:
                            # Skip files with invalid timestamp format
                            continue

                # For each resource, keep only the most recent files
                for res_name, files in all_resources.items():
                    # Sort by timestamp (newest first)
                    files.sort(key=lambda x: x["timestamp"], reverse=True)

                    # Delete older files
                    for file_info in files[keep_count:]:
                        file_path = file_info["file_path"]
                        if file_path.exists():
                            file_path.unlink()

            return True
        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.error(f"Error cleaning history: {str(e)}")
            return False


class BatchOperationManager:
    """Manages batch operations for resources"""

    @staticmethod
    def apply_batch_operation(operation_type, resources=None):
        """Apply a batch operation to multiple resources"""
        if resources is None:
            # Get all resources if none specified
            resources = global_config.get_all_resource_configs()

        results = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": []
        }

        for resource in resources:
            try:
                if operation_type == "check_update":
                    # Check for updates
                    update_found, latest_version, download_url, update_type = ResourceDownloader.check_for_update(
                        resource)

                    if update_found:
                        # Record update info for later use
                        resource.temp_version = latest_version
                        resource.temp_download_url = download_url
                        resource.temp_update_type = update_type
                        results["success"] += 1
                    else:
                        results["skipped"] += 1

                elif operation_type == "update_all":
                    # Update all resources that have pending updates
                    if hasattr(resource, 'temp_download_url') and resource.temp_download_url:
                        # Create temp directory
                        temp_dir = Path("assets/temp")
                        temp_dir.mkdir(parents=True, exist_ok=True)

                        # Download and apply update
                        success = ResourceDownloader.download_and_apply_update(
                            resource,
                            resource.temp_download_url,
                            resource.temp_version,
                            resource.temp_update_type,
                            temp_dir
                        )

                        if success:
                            results["success"] += 1
                        else:
                            results["failed"] += 1
                            results["errors"].append(f"资源 {resource.resource_name} 更新失败")
                    else:
                        results["skipped"] += 1

                elif operation_type == "cleanup_history":
                    # Clean up history files
                    success = ResourceVersionManager.clean_history(resource.resource_name)
                    if success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"资源 {resource.resource_name} 操作失败: {str(e)}")

        return results


# Initialize on module import
def initialize_update_system():
    """Initialize the update system on application startup"""
    try:
        # Create necessary directories
        Path("assets/temp").mkdir(parents=True, exist_ok=True)
        Path("assets/history").mkdir(parents=True, exist_ok=True)
        Path("assets/pending_updates").mkdir(parents=True, exist_ok=True)

        # Apply any pending operations from previous session
        ResourceDownloader.apply_pending_operations()

        # Clean up temp directory
        try:
            temp_dir = Path("assets/temp")
            if temp_dir.exists():
                for item in temp_dir.iterdir():
                    if item.is_file():
                        item.unlink()
        except Exception as e:
            logger = log_manager.get_app_logger()
            logger.warning(f"Failed to clean temp directory: {str(e)}")

        return True
    except Exception as e:
        logger = log_manager.get_app_logger()
        logger.error(f"Failed to initialize update system: {str(e)}")
        return False


# Call initialize function when module is imported
initialize_update_system()