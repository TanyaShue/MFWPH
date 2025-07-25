# -*- coding: UTF-8 -*-
from typing import Dict, Optional, List, Union
import asyncio
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QMutex, QMutexLocker
from qasync import asyncSlot

from app.models.config.app_config import DeviceConfig, Resource
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from core.task_executor import TaskExecutor, TaskStatus
from core.device_status_manager import device_status_manager, DeviceStatus


@dataclass
class DeviceTaskInfo:
    """设备任务信息"""
    device_name: str
    executor: TaskExecutor
    created_at: datetime
    task_count: int = 0
    last_task_time: Optional[datetime] = None


class TaskerManager(QObject):
    """
    集中管理所有设备任务执行器的管理器，使用单例模式确保整个应用中只有一个实例。
    完全异步化的实现，集成了状态管理器。
    """
    # 设备相关信号
    device_added = Signal(str)  # 设备添加信号
    device_removed = Signal(str)  # 设备移除信号
    device_status_changed = Signal(str, str)  # 设备状态变化信号 (device_name, status)

    # 任务相关信号
    task_submitted = Signal(str, str)  # 任务提交信号 (device_name, task_id)
    all_tasks_completed = Signal(str)  # 设备所有任务完成信号 (device_name)

    # 错误信号
    error_occurred = Signal(str, str)  # 错误发生信号 (device_name, error_message)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._executors: Dict[str, DeviceTaskInfo] = {}
        self._mutex = QMutex()
        self._lock = asyncio.Lock()
        self.logger = log_manager.get_app_logger()

        # 任务统计
        self._total_tasks_submitted = 0
        self._total_tasks_completed = 0

        self.logger.info("TaskerManager 初始化完成")

    @asyncSlot(DeviceConfig)
    async def create_executor(self, device_config: DeviceConfig) -> bool:
        """
        异步创建并启动设备的任务执行器。如果执行器已存在则直接返回 True。
        """
        async with self._lock:
            if device_config.device_name in self._executors:
                self.logger.debug(f"设备 {device_config.device_name} 的任务执行器已存在")
                return True

        try:
            self.logger.info(f"正在为设备 {device_config.device_name} 创建任务执行器")

            # 更新状态为连接中
            device_status_manager.update_device_status(
                device_config.device_name,
                DeviceStatus.CONNECTING
            )

            # 创建执行器
            executor = TaskExecutor(device_config, parent=self)

            # 连接信号
            self._connect_executor_signals(executor, device_config.device_name)

            # 启动执行器 - 直接调用异步方法
            success = await executor.start()

            if success:
                # 设置日志句柄
                if hasattr(executor, '_tasker') and executor._tasker:
                    log_manager.set_device_handle(
                        device_config.device_name,
                        executor._tasker._handle
                    )
                    self.logger.debug(
                        f"已为设备 {device_config.device_name} "
                        f"设置handle: {executor._tasker._handle}"
                    )

                # 保存执行器信息
                async with self._lock:
                    self._executors[device_config.device_name] = DeviceTaskInfo(
                        device_name=device_config.device_name,
                        executor=executor,
                        created_at=datetime.now()
                    )

                # 更新状态为空闲
                device_status_manager.update_device_status(
                    device_config.device_name,
                    DeviceStatus.IDLE
                )

                self.device_added.emit(device_config.device_name)
                self.device_status_changed.emit(device_config.device_name, "active")
                self.logger.info(
                    f"设备 {device_config.device_name} 的任务执行器创建并启动成功"
                )
                return True
            else:
                # 更新状态为错误
                device_status_manager.update_device_status(
                    device_config.device_name,
                    DeviceStatus.ERROR,
                    "任务执行器启动失败"
                )
                self.logger.error(
                    f"设备 {device_config.device_name} 的任务执行器启动失败"
                )
                return False

        except Exception as e:
            error_msg = f"为设备 {device_config.device_name} 创建任务执行器失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 更新状态为错误
            device_status_manager.update_device_status(
                device_config.device_name,
                DeviceStatus.ERROR,
                str(e)
            )

            self.error_occurred.emit(device_config.device_name, str(e))
            return False

    def _connect_executor_signals(self, executor: TaskExecutor, device_name: str):
        """连接执行器信号"""
        # 任务开始时更新状态为运行中
        executor.task_started.connect(
            lambda task_id: self._on_task_started(device_name, task_id)
        )

        # 任务完成时更新统计
        executor.task_completed.connect(
            lambda task_id, result: self._on_task_completed(device_name, task_id)
        )

        # 任务失败时记录
        executor.task_failed.connect(
            lambda task_id, error: self._on_task_failed(device_name, task_id, error)
        )

        # 任务排队时更新队列信息
        executor.task_queued.connect(
            lambda task_id: self._update_queue_status(device_name)
        )

        # 任务取消时更新状态
        executor.task_canceled.connect(
            lambda task_id: self._on_task_canceled(device_name, task_id)
        )

        # 进度更新
        executor.progress_updated.connect(
            lambda task_id, progress: device_status_manager.update_progress(device_name, progress)
        )

    @Slot(str, str)
    def _on_task_started(self, device_name: str, task_id: str):
        """任务开始回调"""
        self.logger.debug(f"设备 {device_name} 的任务 {task_id} 已开始")
        # 更新设备状态为运行中
        device_status_manager.update_device_status(
            device_name,
            DeviceStatus.RUNNING
        )
        # 更新当前任务ID
        device_status_manager.update_status(
            device_name,
            current_task_id=task_id,
            current_task_progress=0
        )

    @Slot(str, str)
    def _on_task_completed(self, device_name: str, task_id: str):
        """任务完成回调"""
        self._total_tasks_completed += 1
        self.logger.debug(
            f"设备 {device_name} 的任务 {task_id} 已完成 "
            f"(总完成数: {self._total_tasks_completed})"
        )

        # 通过状态管理器更新任务完成状态
        device_status_manager.on_task_completed(device_name)

        # 更新队列状态
        self._update_queue_status(device_name)

        # 检查是否所有任务都完成了
        with QMutexLocker(self._mutex):
            executor_info = self._executors.get(device_name)
            if executor_info and executor_info.executor.get_queue_length() == 0:
                self.all_tasks_completed.emit(device_name)

    @Slot(str, str, str)
    def _on_task_failed(self, device_name: str, task_id: str, error: str):
        """任务失败回调"""
        self.logger.error(f"设备 {device_name} 的任务 {task_id} 失败: {error}")
        self.error_occurred.emit(device_name, f"任务 {task_id} 失败: {error}")

        # 更新设备状态
        device_status_manager.update_device_status(
            device_name,
            DeviceStatus.ERROR,
            error
        )

        # 更新队列状态
        self._update_queue_status(device_name)

    @Slot(str, str)
    def _on_task_canceled(self, device_name: str, task_id: str):
        """任务取消回调"""
        self.logger.info(f"设备 {device_name} 的任务 {task_id} 已取消")

        # 更新队列状态
        self._update_queue_status(device_name)

        # 如果没有其他任务在运行，更新状态为空闲
        with QMutexLocker(self._mutex):
            executor_info = self._executors.get(device_name)
            if executor_info:
                current_task = executor_info.executor._current_task
                if not current_task or current_task.id == task_id:
                    if executor_info.executor.get_queue_length() == 0:
                        device_status_manager.update_device_status(
                            device_name,
                            DeviceStatus.IDLE
                        )

    def _update_queue_status(self, device_name: str):
        """更新设备的队列状态"""
        with QMutexLocker(self._mutex):
            executor_info = self._executors.get(device_name)
            if executor_info:
                queue_length = executor_info.executor.get_queue_length()
                device_status_manager.update_queue_info(device_name, queue_length)

    @asyncSlot(str, object)
    async def submit_task(
            self,
            device_name: str,
            task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]
    ) -> Optional[Union[str, List[str]]]:
        """
        异步向特定设备的执行器提交任务。
        """
        # 获取执行器
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            error_msg = f"提交任务失败: 设备 {device_name} 的执行器未找到"
            self.logger.error(error_msg)
            self.error_occurred.emit(device_name, error_msg)
            return None

        try:
            # 记录任务信息
            task_count = len(task_data) if isinstance(task_data, list) else 1
            self.logger.info(
                f"向设备 {device_name} 提交 {task_count} 个任务"
            )

            # 提交任务 - 直接调用异步方法
            result = await executor_info.executor.submit_task(task_data)

            if result:
                # 更新统计信息
                async with self._lock:
                    executor_info.task_count += task_count
                    executor_info.last_task_time = datetime.now()
                    self._total_tasks_submitted += task_count

                # 发送信号
                if isinstance(result, list):
                    for task_id in result:
                        self.task_submitted.emit(device_name, task_id)
                else:
                    self.task_submitted.emit(device_name, result)

                # 更新队列状态
                self._update_queue_status(device_name)

                self.logger.info(
                    f"任务提交成功，设备: {device_name}, "
                    f"任务ID: {result}"
                )
                return result
            else:
                self.logger.warning(f"任务提交成功但未获取任务ID")
                return None

        except Exception as e:
            error_msg = f"向设备 {device_name} 提交任务失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 更新设备状态为错误
            device_status_manager.update_device_status(
                device_name,
                DeviceStatus.ERROR,
                str(e)
            )

            self.error_occurred.emit(device_name, str(e))
            return None

    @asyncSlot(str)
    async def stop_executor(self, device_name: str) -> bool:
        """
        异步停止特定设备的执行器。
        """
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            self.logger.error(f"停止执行器失败: 设备 {device_name} 的执行器未找到")
            return False

        try:
            self.logger.info(f"正在停止设备 {device_name} 的执行器")

            # 更新状态为停止中
            device_status_manager.update_device_status(
                device_name,
                DeviceStatus.STOPPING
            )

            # 停止执行器 - 直接调用异步方法
            await executor_info.executor.stop()

            # 从管理器中移除
            async with self._lock:
                del self._executors[device_name]

            # 更新状态为离线
            device_status_manager.update_device_status(
                device_name,
                DeviceStatus.OFFLINE
            )

            # 发送信号
            self.device_removed.emit(device_name)
            self.device_status_changed.emit(device_name, "stopped")

            self.logger.info(
                f"设备 {device_name} 的执行器已成功停止并移除 "
                f"(该设备共执行了 {executor_info.task_count} 个任务)"
            )
            return True

        except Exception as e:
            error_msg = f"停止设备 {device_name} 的执行器失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 更新状态为错误
            device_status_manager.update_device_status(
                device_name,
                DeviceStatus.ERROR,
                str(e)
            )

            self.error_occurred.emit(device_name, str(e))
            return False

    async def _get_executor_info(self, device_name: str) -> Optional[DeviceTaskInfo]:
        """
        内部辅助方法，获取特定设备的执行器信息。
        """
        async with self._lock:
            return self._executors.get(device_name)

    @asyncSlot()
    async def get_active_devices(self) -> List[str]:
        """
        异步获取所有活跃设备名称列表。
        """
        async with self._lock:
            devices = list(self._executors.keys())
            self.logger.debug(f"当前活跃设备数量: {len(devices)}")
            return devices

    @asyncSlot()
    async def stop_all(self) -> None:
        """
        异步停止所有执行器。
        """
        self.logger.info("正在停止所有任务执行器")

        # 获取所有设备名称
        async with self._lock:
            device_names = list(self._executors.keys())

        if not device_names:
            self.logger.info("没有活跃的任务执行器需要停止")
            return

        self.logger.info(
            f"找到 {len(device_names)} 个活跃的执行器需要停止: "
            f"{', '.join(device_names)}"
        )

        # 并发停止所有执行器
        tasks = [self.stop_executor(name) for name in device_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查结果
        for device_name, result in zip(device_names, results):
            if isinstance(result, Exception):
                self.logger.error(
                    f"停止设备 {device_name} 的执行器时出错: {result}"
                )

        self.logger.info("所有任务执行器已停止")

    def is_device_active(self, device_name: str) -> bool:
        """
        检查设备执行器是否处于活跃状态（同步方法）。
        """
        with QMutexLocker(self._mutex):
            return device_name in self._executors

    def get_device_queue_info(self) -> Dict[str, int]:
        """
        获取所有设备的队列状态信息（同步方法）。
        """
        with QMutexLocker(self._mutex):
            queue_info = {}
            for name, info in self._executors.items():
                queue_info[name] = info.executor.get_queue_length()
            return queue_info

    def get_executor_state(self, device_name: str):
        """获取执行器状态（同步方法）"""
        with QMutexLocker(self._mutex):
            executor_info = self._executors.get(device_name)
            if executor_info and hasattr(executor_info.executor, 'get_state'):
                return executor_info.executor.get_state()
            return None

    @asyncSlot()
    async def get_statistics(self) -> Dict[str, any]:
        """
        获取任务管理器统计信息。
        """
        async with self._lock:
            active_devices = len(self._executors)
            device_stats = []

            for name, info in self._executors.items():
                device_stats.append({
                    "name": name,
                    "task_count": info.task_count,
                    "queue_length": info.executor.get_queue_length(),
                    "created_at": info.created_at.isoformat(),
                    "last_task_time": (
                        info.last_task_time.isoformat()
                        if info.last_task_time else None
                    )
                })

            return {
                "active_devices": active_devices,
                "total_tasks_submitted": self._total_tasks_submitted,
                "total_tasks_completed": self._total_tasks_completed,
                "devices": device_stats
            }

    @asyncSlot(DeviceConfig)
    async def run_device_all_resource_task(self, device_config: DeviceConfig) -> bool:
        """
        异步一键启动：提交所有已启用资源的任务。
        """
        self.logger.info(
            f"为设备 {device_config.device_name} 一键启动所有已启用资源任务"
        )

        # 获取已启用的资源
        enabled_resources = [r for r in device_config.resources if r.enable]
        self.logger.info(
            f"设备 {device_config.device_name} 的已启用资源数: "
            f"{len(enabled_resources)}"
        )

        # 获取运行时配置
        runtime_configs = []
        for resource in enabled_resources:
            config = global_config.get_runtime_configs_for_resource(
                resource.resource_name,
                device_config.device_name
            )
            if config:
                runtime_configs.append(config)

        if not runtime_configs:
            self.logger.warning(
                f"设备 {device_config.device_name} 没有找到可用的运行时配置"
            )
            return False

        try:
            self.logger.info(
                f"设备 {device_config.device_name} 准备提交 "
                f"{len(runtime_configs)} 个资源任务"
            )

            # 确保执行器已创建
            success = await self.create_executor(device_config)
            if not success:
                error_msg = (
                    f"为设备 {device_config.device_name} 创建执行器失败，"
                    f"无法运行资源任务"
                )
                self.logger.error(error_msg)
                self.error_occurred.emit(device_config.device_name, error_msg)
                return False

            # 提交任务批次
            result = await self.submit_task(
                device_config.device_name,
                runtime_configs
            )

            if result:
                self.logger.info(
                    f"设备 {device_config.device_name} 的资源任务批次已成功提交"
                )
                return True
            else:
                self.logger.error(
                    f"设备 {device_config.device_name} 的资源任务批次提交失败"
                )
                return False

        except Exception as e:
            error_msg = (
                f"运行设备 {device_config.device_name} 的所有资源任务时出错: {e}"
            )
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(device_config.device_name, str(e))
            return False

    @asyncSlot(str, str)
    async def run_resource_task(self, device_config_name: str, resource_name: str) -> None:
        """
        提交指定资源的任务。
        """
        self.logger.info(
            f"为设备 {device_config_name} 提交资源 {resource_name} 的任务"
        )

        # 获取运行时配置
        runtime_config = global_config.get_runtime_configs_for_resource(
            resource_name,
            device_config_name
        )

        if not runtime_config:
            error_msg = (
                f"找不到设备 {device_config_name} 资源 {resource_name} "
                f"的运行时配置"
            )
            self.logger.error(error_msg)
            self.error_occurred.emit(device_config_name, error_msg)
            return

        # 获取设备配置
        device_config = global_config.get_device_config(device_config_name)
        if not device_config:
            error_msg = f"找不到设备配置: {device_config_name}"
            self.logger.error(error_msg)
            self.error_occurred.emit(device_config_name, error_msg)
            return

        try:
            # 确保执行器已创建
            success = await self.create_executor(device_config)
            if not success:
                error_msg = (
                    f"为设备 {device_config_name} 创建执行器失败，"
                    f"无法运行资源 {resource_name}"
                )
                self.logger.error(error_msg)
                self.error_occurred.emit(device_config_name, error_msg)
                return

            # 提交任务
            result = await self.submit_task(device_config.device_name, runtime_config)

            if result:
                self.logger.info(
                    f"设备 {device_config.device_name} 的资源 {resource_name} "
                    f"任务已成功提交，任务ID: {result}"
                )
            else:
                self.logger.error(
                    f"设备 {device_config.device_name} 的资源 {resource_name} "
                    f"任务提交失败"
                )

        except Exception as e:
            error_msg = (
                f"运行设备 {device_config_name} 的资源 {resource_name} "
                f"任务时出错: {e}"
            )
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(device_config_name, str(e))

    @asyncSlot(str, str)
    async def cancel_task(self, device_name: str, task_id: str) -> bool:
        """
        取消指定设备的特定任务。
        """
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            self.logger.error(f"取消任务失败: 设备 {device_name} 的执行器未找到")
            return False

        try:
            # 直接调用异步方法
            success = await executor_info.executor.cancel_task(task_id)
            if success:
                self.logger.info(f"已取消设备 {device_name} 的任务 {task_id}")
            else:
                self.logger.warning(
                    f"未能取消设备 {device_name} 的任务 {task_id} "
                    f"(任务可能已完成或不存在)"
                )
            return success

        except Exception as e:
            self.logger.error(
                f"取消设备 {device_name} 的任务 {task_id} 时出错: {e}"
            )
            return False

    @asyncSlot(str, str)
    async def get_task_status(self, device_name: str, task_id: str) -> Optional[str]:
        """
        获取指定任务的状态。
        """
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            return None

        status = executor_info.executor.get_task_status(task_id)
        return status.value if status else None


# 单例模式
task_manager = TaskerManager()