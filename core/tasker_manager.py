# -*- coding: UTF-8 -*-
"""
任务管理器 (重构版)
- 集中管理所有设备的任务队列。
- 按需创建和销毁任务执行器 (TaskExecutor)。
- 每个设备同时只运行一个任务处理器。
"""

from typing import Dict, Optional, List, Union, DefaultDict
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QMutex, QMutexLocker
from qasync import asyncSlot

from app.models.config.app_config import DeviceConfig, Resource
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from core.task_executor import TaskExecutor  # 导入重构后的执行器
from core.device_state_machine import DeviceState
from core.device_status_manager import device_status_manager


class TaskerManager(QObject):
    """
    集中管理所有设备任务的管理器（重构版）。
    使用设备任务队列和按需生成的执行器。
    """
    # ... [信号定义与原版一致] ...
    device_added = Signal(str)
    device_removed = Signal(str)
    device_state_changed = Signal(str, DeviceState)
    task_submitted = Signal(str, str)
    all_tasks_completed = Signal(str)
    error_occurred = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._device_queues: DefaultDict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._device_processors: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()  # 用于保护 _device_processors 字典
        self.logger = log_manager.get_app_logger()

        self._total_tasks_submitted = 0
        self._total_tasks_completed = 0

        self._connect_status_manager_signals()
        self.logger.info("TaskerManager (重构版) 初始化完成")

    def _connect_status_manager_signals(self):
        """连接状态管理器的信号"""
        device_status_manager.state_changed.connect(self._on_device_state_changed)

    @Slot(str, object, object, dict)
    def _on_device_state_changed(self, name: str, old_state: DeviceState, new_state: DeviceState, context: dict):
        """设备状态变化回调"""
        self.device_state_changed.emit(name, new_state)
        if new_state == DeviceState.ERROR:
            error_msg = context.get('error_message', '未知错误')
            self.logger.error(f"设备 {name} 进入错误状态: {error_msg}")
            self.error_occurred.emit(name, error_msg)

    async def _process_device_queue(self, device_name: str, device_config: DeviceConfig):
        """
        【核心循环】为单个设备处理其任务队列。
        该协程在有任务时运行，任务完成后自动退出。
        """
        self.logger.info(f"设备 {device_name} 的任务处理器已启动。")
        self.device_added.emit(device_name)

        try:
            queue = self._device_queues[device_name]
            while not queue.empty():
                try:
                    task_data = await queue.get()
                    self.logger.info(f"设备 {device_name} 从队列中获取新任务，准备执行...")

                    # 每次都创建一个新的执行器实例
                    executor = TaskExecutor(device_config, parent=self)

                    # 连接信号，处理任务状态变化
                    executor.task_state_changed.connect(self._on_task_state_changed)

                    # 执行完整的任务生命周期
                    await executor.run_task_lifecycle(task_data)

                    queue.task_done()
                    self.logger.info(f"设备 {device_name} 的一批任务已处理完毕。")

                except asyncio.CancelledError:
                    self.logger.warning(f"设备 {device_name} 的任务处理器被取消。")
                    # 将未处理的任务放回队列，以便恢复后继续
                    # if 'task_data' in locals():
                    #     await queue.put(task_data)
                    break  # 退出循环
                except Exception as e:
                    self.logger.error(f"处理设备 {device_name} 队列时发生错误: {e}", exc_info=True)
                    self.error_occurred.emit(device_name, f"任务处理循环错误: {e}")
                    # 等待一会再继续，防止快速失败循环
                    await asyncio.sleep(5)

            if queue.empty():
                self.logger.info(f"设备 {device_name} 的任务队列已空。")
                self.all_tasks_completed.emit(device_name)

        finally:
            self.logger.info(f"设备 {device_name} 的任务处理器已停止。")
            async with self._lock:
                if device_name in self._device_processors:
                    del self._device_processors[device_name]
                # 如果队列为空，也删除队列对象以释放资源
                if self._device_queues[device_name].empty():
                    del self._device_queues[device_name]
            self.device_removed.emit(device_name)

    @Slot(str, str, object, dict)
    def _on_task_state_changed(self, task_id: str, state: DeviceState, context: dict):
        """任务状态变化回调"""
        # 从状态管理器获取任务的详细信息
        task_manager = device_status_manager.get_task_manager(task_id)
        if not task_manager:
            self.logger.warning(f"任务状态变化时未找到ID为 {task_id} 的管理器，可能已被清理。")
            return

        # 【错误修正】
        # 错误的代码: device_name = task_manager.device_name
        # 正确的代码: 从 context 字典中获取 device_name
        task_context = task_manager.get_context()
        device_name = task_context.get('device_name')

        if not device_name:
            self.logger.error(f"无法从任务 {task_id} 的状态管理器中获取设备名称！")
            return

        self.logger.debug(f"任务 {task_id} (设备: {device_name}) 状态变为: {state.value}")

        if state == DeviceState.COMPLETED:
            self._total_tasks_completed += 1
        elif state == DeviceState.FAILED:
            # 使用信号传递过来的 context，因为它包含了最新的错误信息
            error_msg = context.get('error_message', '未知错误')
            self.logger.error(f"设备 {device_name} 的任务 {task_id} 失败: {error_msg}")
            self.error_occurred.emit(device_name, f"任务 {task_id} 失败: {error_msg}")

    @asyncSlot(str, object)
    async def submit_task(self, device_name: str, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]):
        """
        异步向特定设备的队列提交任务。如果设备空闲，则启动任务处理器。
        """
        device_config = global_config.get_device_config(device_name)
        if not device_config:
            error_msg = f"提交任务失败: 找不到设备配置 {device_name}"
            self.logger.error(error_msg)
            self.error_occurred.emit(device_name, error_msg)
            return

        task_count = len(task_data) if isinstance(task_data, list) else 1
        self.logger.info(f"向设备 {device_name} 提交 {task_count} 个任务到队列")

        queue = self._device_queues[device_name]
        await queue.put(task_data)

        self._total_tasks_submitted += task_count
        # 注意: task_submitted 信号现在无法立即发出，因为 task_id 在执行器内部才生成。
        # 可以在TaskExecutor.run_task_lifecycle开始时发出信号。

        # 检查是否需要启动该设备的处理循环
        async with self._lock:
            if device_name not in self._device_processors:
                self.logger.info(f"设备 {device_name} 当前无任务处理器，正在创建一个新的。")
                processor_task = asyncio.create_task(
                    self._process_device_queue(device_name, device_config)
                )
                self._device_processors[device_name] = processor_task
            else:
                self.logger.debug(f"设备 {device_name} 已有任务处理器在运行，任务已入队。")

    @asyncSlot(str)
    async def stop_device_processing(self, device_name: str) -> bool:
        """
        停止特定设备的任务处理并清空其任务队列。
        这将取消当前正在执行的任务并销毁其执行器。
        """
        self.logger.info(f"请求停止设备 {device_name} 的所有任务处理...")
        async with self._lock:
            if device_name in self._device_processors:
                processor = self._device_processors[device_name]
                processor.cancel()
                # 等待处理器任务完成其清理工作
                await asyncio.sleep(0.1)
                del self._device_processors[device_name]
                self.logger.info(f"设备 {device_name} 的任务处理器已被取消。")

            # 清空队列
            if device_name in self._device_queues:
                queue = self._device_queues[device_name]
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                del self._device_queues[device_name]
                self.logger.info(f"设备 {device_name} 的任务队列已清空。")
                return True
        return False

    @asyncSlot()
    async def stop_all(self) -> None:
        """异步停止所有设备的任务处理器"""
        self.logger.info("正在停止所有任务处理器...")
        async with self._lock:
            device_names = list(self._device_processors.keys())

        if not device_names:
            self.logger.info("没有活跃的任务处理器需要停止。")
            return

        tasks = [self.stop_device_processing(name) for name in device_names]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("所有任务处理器已停止。")

    @asyncSlot(str)
    async def pause_device(self, device_name: str) -> bool:
        """
        暂停设备的任务执行。
        这将取消当前任务并销毁执行器，但保留队列中未执行的任务。
        """
        async with self._lock:
            if device_name in self._device_processors:
                self.logger.info(f"正在暂停设备 {device_name}...")
                processor = self._device_processors.pop(device_name)
                processor.cancel()
                device_status_manager.get_device_manager(device_name).set_state(DeviceState.PAUSED)
                self.logger.info(f"设备 {device_name} 已暂停。当前任务已中断。")
                return True
        self.logger.warning(f"无法暂停设备 {device_name}，因为它当前不活跃。")
        return False

    @asyncSlot(str)
    async def resume_device(self, device_name: str) -> bool:
        """
        恢复设备的任务执行。
        如果设备队列中有任务，将启动一个新的任务处理器。
        """
        async with self._lock:
            if device_name in self._device_processors:
                self.logger.info(f"设备 {device_name} 已经在运行，无需恢复。")
                return True

            if device_name in self._device_queues and not self._device_queues[device_name].empty():
                self.logger.info(f"正在恢复设备 {device_name}...")
                device_config = global_config.get_device_config(device_name)
                if not device_config:
                    self.logger.error(f"无法恢复：找不到设备 {device_name} 的配置。")
                    return False

                processor_task = asyncio.create_task(
                    self._process_device_queue(device_name, device_config)
                )
                self._device_processors[device_name] = processor_task
                device_status_manager.get_device_manager(device_name).set_state(DeviceState.IDLE)  # 或其他合适的状态
                return True

        self.logger.warning(f"无法恢复设备 {device_name}，任务队列为空。")
        return False

    # ... [其他辅助方法，如 get_statistics, is_device_active, run_device_all_resource_task 等需要相应调整] ...

    def is_device_active(self, device_name: str) -> bool:
        """检查设备处理器是否处于活跃状态"""
        return device_name in self._device_processors

    def get_device_queue_info(self) -> Dict[str, int]:
        """获取所有设备的队列长度信息"""
        return {name: queue.qsize() for name, queue in self._device_queues.items()}

    def get_device_state(self, device_name: str) -> Optional[DeviceState]:
        """获取设备状态"""
        device_manager = device_status_manager.get_device_manager(device_name)
        return device_manager.get_state() if device_manager else None

    @asyncSlot(DeviceConfig)
    async def run_device_all_resource_task(self, device_config: DeviceConfig) -> bool:
        """异步一键启动：提交所有已启用资源的任务"""
        self.logger.info(f"为设备 {device_config.device_name} 一键启动所有已启用资源任务")
        enabled_resources = [r for r in device_config.resources if r.enable]

        def get_all_runtime_configs():
            return [
                config for r in enabled_resources
                if
                (config := global_config.get_runtime_configs_for_resource(r.resource_name, device_config.device_name))
            ]

        runtime_configs = await asyncio.to_thread(get_all_runtime_configs)
        if not runtime_configs:
            self.logger.warning(f"设备 {device_config.device_name} 没有找到可用的运行时配置")
            return False

        await self.submit_task(device_config.device_name, runtime_configs)
        return True

    @asyncSlot(str, str)
    async def run_resource_task(self, device_config_name: str, resource_name: str) -> None:
        """提交指定资源的任务"""
        self.logger.info(f"为设备 {device_config_name} 提交资源 {resource_name} 的任务")
        runtime_config = global_config.get_runtime_configs_for_resource(resource_name, device_config_name)
        if not runtime_config:
            error_msg = f"找不到设备 {device_config_name} 资源 {resource_name} 的运行时配置"
            self.logger.error(error_msg)
            self.error_occurred.emit(device_config_name, error_msg)
            return

        await self.submit_task(device_config_name, runtime_config)


# 单例模式
task_manager = TaskerManager()