# --- app/task/task_manager.py ---
"""
任务管理模块
负责任务的启动、调度和管理
"""

import asyncio
import os
from PySide6.QtWidgets import QApplication

from app.models.config.global_config import global_config
from app.utils.global_logger import get_logger
from core.tasker_manager import task_manager


logger = get_logger()


def get_devices_to_start(args):
    """根据启动参数确定要启动的设备列表"""
    devices_to_start = args.device

    # 处理"all"参数
    if "all" in devices_to_start:
        app_config = global_config.get_app_config()
        devices_to_start = [device.device_name for device in app_config.devices]
        logger.info(f"启动所有设备: {devices_to_start}")
    else:
        logger.info(f"启动指定设备: {devices_to_start}")

    return devices_to_start


async def start_device_tasks(device_name, config_name=None):
    """启动单个设备的所有任务"""
    device_config = global_config.get_device_config(device_name)
    if not device_config:
        logger.error(f"找不到设备配置: {device_name}")
        return False

    logger.info(f"启动设备 {device_name} 的所有任务")

    # 如果指定了配置方案，先切换配置
    if config_name:
        logger.info(f"为设备 {device_name} 使用配置方案: {config_name}")
        # 这里可以添加配置切换逻辑，如果需要的话

    # 启动设备的所有任务
    success = await task_manager.run_device_all_resource_task(device_config)
    if success:
        logger.info(f"设备 {device_name} 任务启动成功")
    else:
        logger.warning(f"设备 {device_name} 任务启动失败")

    return success


def create_device_completion_handler(device_names, completed_devices):
    """创建设备完成处理函数"""
    def on_device_completed(device_name):
        if device_name in device_names:
            logger.info(f"设备 {device_name} 所有任务已完成")
            completed_devices.add(device_name)

            # 检查是否所有设备都已完成
            if completed_devices >= set(device_names):
                logger.info("所有设备任务都已完成，准备退出程序")
                # 获取当前的app和loop
                try:
                    app = QApplication.instance()
                    loop = asyncio.get_event_loop()
                    window = None
                    if hasattr(app, '_main_window'):
                        window = app._main_window
                    from app.exit_handler import perform_graceful_shutdown
                    asyncio.create_task(perform_graceful_shutdown(loop, app, window))
                except Exception as e:
                    logger.error(f"获取应用实例失败，直接退出: {e}")
                    os._exit(0)
    return on_device_completed


async def check_timeout_and_active_tasks(device_names, completed_devices, start_time, timeout_seconds):
    """检查超时和活跃任务状态"""
    # 检查超时
    current_time = asyncio.get_event_loop().time()
    if current_time - start_time > timeout_seconds:
        logger.warning(f"等待任务完成超时 ({timeout_seconds}秒)，强制退出")
        os._exit(1)

    # 检查是否还有活跃的任务处理器
    active_devices = [name for name in device_names if task_manager.is_device_active(name)]
    if not active_devices and completed_devices < set(device_names):
        logger.warning("没有活跃的任务处理器但任务未完成，可能出现异常")
        # 等待一段时间再检查
        await asyncio.sleep(10)


async def wait_for_all_tasks_complete(device_names, timeout_seconds=3600):
    """
    等待指定设备的所有任务完成

    Args:
        device_names: 要等待的设备名称列表
        timeout_seconds: 超时时间（秒），0表示无限制
    """
    try:
        completed_devices = set()
        start_time = asyncio.get_event_loop().time()

        # 连接任务完成信号
        on_device_completed = create_device_completion_handler(device_names, completed_devices)
        task_manager.all_tasks_completed.connect(on_device_completed)

        if timeout_seconds > 0:
            logger.info(f"等待任务完成，超时时间: {timeout_seconds}秒")
        else:
            logger.info("等待任务完成，无超时限制")

        # 等待任务完成或超时
        while completed_devices < set(device_names):
            await asyncio.sleep(5)

            # 只有在设置了超时时间时才检查超时
            if timeout_seconds > 0:
                await check_timeout_and_active_tasks(device_names, completed_devices, start_time, timeout_seconds)

        logger.info("任务完成等待结束")

    except Exception as e:
        logger.error(f"等待任务完成时发生错误: {e}")
        os._exit(1)


async def start_tasks_on_startup(args):
    """
    根据启动参数自动启动任务
    """
    try:
        logger.info(f"启动参数: device={args.device}, config={args.config}, exit_on_complete={args.exit_on_complete}, timeout={getattr(args, 'timeout', 3600)}")

        # 等待配置加载完成
        await asyncio.sleep(1)

        devices_to_start = get_devices_to_start(args)

        # 为每个设备启动任务
        for device_name in devices_to_start:
            await start_device_tasks(device_name, args.config)

        # 如果设置了退出参数，监听任务完成
        if args.exit_on_complete:
            timeout_seconds = getattr(args, 'timeout', 3600)
            logger.info("等待所有任务完成...")
            await wait_for_all_tasks_complete(devices_to_start, timeout_seconds)

    except Exception as e:
        logger.error(f"启动任务时发生错误: {e}")
        if args.exit_on_complete:
            os._exit(1)  # 出错时直接退出
