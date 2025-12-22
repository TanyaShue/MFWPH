# --- app/config/config_manager.py ---
"""
配置管理模块
负责应用配置的加载、迁移和管理
"""

import json
import os
import sys
import shutil

from app.models.config.global_config import global_config
from app.utils.global_logger import get_logger


logger = get_logger()


def load_resources_directory():
    """加载资源目录（支持PyInstaller打包环境）"""
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller打包环境：exe文件所在目录
            base_path = os.path.dirname(sys.executable)
            logger.info(f"PyInstaller环境，exe目录: {base_path}")
        else:
            # 开发环境：main.py文件所在目录
            # 通过__file__向上查找main.py的位置
            current_dir = os.path.dirname(os.path.abspath(__file__))  # app/config/
            parent_dir = os.path.dirname(current_dir)  # app/
            project_root = os.path.dirname(parent_dir)  # 项目根目录
            base_path = project_root
            logger.info(f"开发环境，项目根目录: {base_path}")

        resource_dir = os.path.join(base_path, "assets", "resource")
        logger.info(f"尝试加载资源目录: {resource_dir}")

        if not os.path.exists(resource_dir):
            os.makedirs(resource_dir)
            logger.info(f"创建资源目录: {resource_dir}")

        global_config.load_all_resources_from_directory(resource_dir)
        logger.info(f"资源目录加载完成: {resource_dir}")
    except OSError as e:
        logger.error(f"创建或访问资源目录时发生操作系统错误: {e}")
    except Exception as e:
        logger.error(f"从资源目录加载时发生未知错误: {e}")
        import traceback
        logger.error(f"详细错误信息: {traceback.format_exc()}")


def get_config_directory():
    """获取配置目录 - 使用统一的平台特定路径"""
    # 直接使用平台特定的标准路径，避免QStandardPaths在conda环境中的不稳定行为
    if os.name == 'nt':  # Windows
        appdata_path = os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == 'darwin':  # macOS
        appdata_path = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:  # Linux and others
        appdata_path = os.path.join(os.path.expanduser("~"), ".config")

    config_base_dir = os.path.join(appdata_path, "MFWPH")

    # 确保配置目录存在
    if not os.path.exists(config_base_dir):
        os.makedirs(config_base_dir)
        logger.info(f"创建配置目录: {config_base_dir}")

    return config_base_dir


def migrate_config_file(config_file_path):
    """迁移配置文件到新位置"""
    try:
        # 检查新位置是否有配置文件
        if os.path.exists(config_file_path):
            logger.info("在新位置找到配置文件，直接加载")
            global_config.load_app_config(config_file_path)
        else:
            logger.info("新位置没有配置文件，尝试迁移")

            # 检查旧位置的配置文件
            old_config_path = "assets/config/app_config.json"
            old_config_dir = os.path.dirname(old_config_path)

            if os.path.exists(old_config_path):
                logger.info(f"从旧位置迁移配置文件: {old_config_path} -> {config_file_path}")
                # 复制配置文件到新位置
                shutil.copy2(old_config_path, config_file_path)
                global_config.load_app_config(config_file_path)
                logger.info("配置文件迁移完成")
            else:
                logger.info("旧位置也没有配置文件，创建默认配置")
                # 创建默认配置文件
                if not os.path.exists(old_config_dir):
                    os.makedirs(old_config_dir)

                # 创建空的配置文件
                with open(config_file_path, "w", encoding="utf-8") as f:
                    f.write("{}")

                global_config.load_app_config(config_file_path)
                logger.info("创建并加载默认配置文件")

        # 设置配置文件的新路径
        global_config.get_app_config().source_file = config_file_path

    except (OSError, IOError) as e:
        logger.error(f"处理应用配置文件时发生IO错误: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"解析应用配置文件失败: {e}")
    except Exception as e:
        logger.error(f"加载应用配置时发生未知错误: {e}")


def setup_default_config():
    """设置默认配置"""
    try:
        # 设置默认窗口大小
        app_config = global_config.get_app_config()
        if not hasattr(app_config, 'window_size') or not app_config.window_size:
            app_config.window_size = "800x600"
            logger.info("设置默认窗口大小: 800x600")
    except Exception as e:
        logger.error(f"获取或处理应用配置时出错: {e}")


def load_and_migrate_config():
    """
    加载并迁移配置文件
    使用 QStandardPaths 获取配置路径，实现配置文件的统一管理
    """
    load_resources_directory()

    config_base_dir = get_config_directory()
    config_file_path = os.path.join(config_base_dir, "app_config.json")
    logger.info(f"使用配置文件路径: {config_file_path}")

    migrate_config_file(config_file_path)
    setup_default_config()
