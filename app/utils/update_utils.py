# --- START OF FILE app/utils/update_utils.py ---

import os
import sys
import json
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
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
    return base_path


def create_backup(resource_name, resource_dir):
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


def is_file_locked(file_path):
    """检查文件是否被锁定"""
    if not file_path.exists():
        return False
    logger.debug(f"Checking if file is locked: {file_path}")
    try:
        # 尝试以附加模式打开文件，这是一种非破坏性的检查方式
        with open(file_path, 'a'):
            pass
        logger.debug(f"File '{file_path}' is not locked.")
        return False
    except (IOError, OSError):
        logger.warning(f"File '{file_path}' is locked.")
        return True

# --- END OF FILE app/utils/update_utils.py ---