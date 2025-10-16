# -*- coding: UTF-8 -*-
"""
任务管理器
集中管理所有设备的任务执行器，使用简化的状态管理
"""

from typing import Dict, Optional, List, Union
import asyncio
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QObject, Signal, Slot, QMutex, QMutexLocker
from qasync import asyncSlot

from app.models.config.app_config import DeviceConfig, Resource
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from core.task_executor import TaskExecutor
from core.device_state_machine import DeviceState
from core.device_status_manager import device_status_manager


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
    集中管理所有设备任务执行器的管理器
    使用简化的状态管理器管理所有状态
    """
    # 设备相关信号
    device_added = Signal(str)  # 设备添加信号
    device_removed = Signal(str)  # 设备移除信号
    device_state_changed = Signal(str, DeviceState)  # 设备状态变化信号

    # 任务相关信号
    task_submitted = Signal(str, str)  # 任务提交信号 (device_name, task_id)
    all_tasks_completed = Signal(str)  # 设备所有任务完成信号

    # 错误信号
    error_occurred = Signal(str, str)  # 错误发生信号

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._executors: Dict[str, DeviceTaskInfo] = {}
        self._mutex = QMutex()
        self._lock = asyncio.Lock()
        self.logger = log_manager.get_app_logger()

        # 任务统计
        self._total_tasks_submitted = 0
        self._total_tasks_completed = 0

        # 连接状态管理器信号
        self._connect_status_manager_signals()

        self.logger.info("TaskerManager 初始化完成")

    def _connect_status_manager_signals(self):
        """连接状态管理器的信号"""
        device_status_manager.state_changed.connect(self._on_device_state_changed)

    @Slot(str, object, object, dict)
    def _on_device_state_changed(self, name: str, old_state: DeviceState, new_state: DeviceState, context: dict):
        """设备状态变化回调"""
        self.device_state_changed.emit(name, new_state)

        # 记录重要状态变化
        if new_state == DeviceState.ERROR:
            error_msg = context.get('error_message', '未知错误')
            self.logger.error(f"设备 {name} 进入错误状态: {error_msg}")
            self.error_occurred.emit(name, error_msg)

    @asyncSlot(DeviceConfig)
    async def create_executor(self, device_config: DeviceConfig) -> bool:
        """
        异步创建并启动设备的任务执行器
        """
        async with self._lock:
            if device_config.device_name in self._executors:
                self.logger.debug(f"设备 {device_config.device_name} 的任务执行器已存在")
                return True

        try:
            self.logger.info(f"正在为设备 {device_config.device_name} 创建任务执行器")

            # 创建执行器
            executor = TaskExecutor(device_config, parent=self)

            # 连接执行器信号
            self._connect_executor_signals(executor, device_config.device_name)

            # 启动执行器
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

                self.device_added.emit(device_config.device_name)
                self.logger.info(
                    f"设备 {device_config.device_name} 的任务执行器创建并启动成功"
                )
                return True
            else:
                self.logger.error(
                    f"设备 {device_config.device_name} 的任务执行器启动失败"
                )
                return False

        except Exception as e:
            error_msg = f"为设备 {device_config.device_name} 创建任务执行器失败: {e}"
            self.logger.error(error_msg, exc_info=True)

            # 使用状态管理器设置错误
            device_status_manager.set_device_error(device_config.device_name, str(e))
            self.error_occurred.emit(device_config.device_name, str(e))
            return False

    def _connect_executor_signals(self, executor: TaskExecutor, device_name: str):
        """连接执行器信号"""
        # 任务状态变化时更新
        executor.task_state_changed.connect(
            lambda task_id, state, context: self._on_task_state_changed(
                device_name, task_id, state, context
            )
        )

    @Slot(str, str, object, dict)
    def _on_task_state_changed(self, device_name: str, task_id: str,
                               state: DeviceState, context: dict):
        """任务状态变化回调"""
        self.logger.debug(f"任务 {task_id} 状态变为: {state.value}")

        if state == DeviceState.RUNNING:
            # 任务开始运行
            self.logger.info(f"设备 {device_name} 的任务 {task_id} 已开始")

        elif state == DeviceState.COMPLETED:
            # 任务完成
            self._total_tasks_completed += 1

            # 检查是否所有任务都完成了
            with QMutexLocker(self._mutex):
                executor_info = self._executors.get(device_name)
                if executor_info and executor_info.executor.get_queue_length() == 0:
                    self.all_tasks_completed.emit(device_name)

        elif state == DeviceState.FAILED:
            # 任务失败
            error_msg = context.get('error_message', '未知错误')
            self.logger.error(f"设备 {device_name} 的任务 {task_id} 失败: {error_msg}")
            self.error_occurred.emit(device_name, f"任务 {task_id} 失败: {error_msg}")

        elif state == DeviceState.CANCELED:
            # 任务取消
            self.logger.info(f"设备 {device_name} 的任务 {task_id} 已取消")

        # 更新队列信息
        self._update_queue_status(device_name)

    def _update_queue_status(self, device_name: str):
        """更新设备的队列状态"""
        with QMutexLocker(self._mutex):
            executor_info = self._executors.get(device_name)
            if executor_info:
                queue_length = executor_info.executor.get_queue_length()
                # 更新设备状态管理器的队列信息
                device_manager = device_status_manager.get_device_manager(device_name)
                if device_manager:
                    device_manager.update_context(queue_length=queue_length)

    @asyncSlot(str, object)
    async def submit_task(
            self,
            device_name: str,
            task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]
    ) -> Optional[Union[str, List[str]]]:
        """
        异步向特定设备的执行器提交任务
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

            # 提交任务
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

            # 使用状态管理器设置错误
            device_status_manager.set_device_error(device_name, str(e))
            self.error_occurred.emit(device_name, str(e))
            return None

    @asyncSlot(str)
    async def stop_executor(self, device_name: str) -> bool:
        """
        异步停止特定设备的执行器
        """
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            self.logger.error(f"停止执行器失败: 设备 {device_name} 的执行器未找到")
            return False

        try:
            self.logger.info(f"正在停止设备 {device_name} 的执行器")

            # 停止执行器
            await executor_info.executor.stop()

            # 从管理器中移除
            async with self._lock:
                del self._executors[device_name]

            # 发送信号
            self.device_removed.emit(device_name)

            self.logger.info(
                f"设备 {device_name} 的执行器已成功停止并移除 "
                f"(该设备共执行了 {executor_info.task_count} 个任务)"
            )
            return True

        except Exception as e:
            error_msg = f"停止设备 {device_name} 的执行器失败: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(device_name, str(e))
            return False

    async def _get_executor_info(self, device_name: str) -> Optional[DeviceTaskInfo]:
        """
        内部辅助方法，获取特定设备的执行器信息
        """
        async with self._lock:
            return self._executors.get(device_name)

    @asyncSlot()
    async def get_active_devices(self) -> List[str]:
        """
        异步获取所有活跃设备名称列表
        """
        async with self._lock:
            devices = list(self._executors.keys())
            self.logger.debug(f"当前活跃设备数量: {len(devices)}")
            return devices

    @asyncSlot()
    async def stop_all(self) -> None:
        """
        异步停止所有执行器
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
        检查设备执行器是否处于活跃状态（同步方法）
        """
        with QMutexLocker(self._mutex):
            return device_name in self._executors

    def get_device_queue_info(self) -> Dict[str, int]:
        """
        获取所有设备的队列状态信息（同步方法）
        """
        with QMutexLocker(self._mutex):
            queue_info = {}
            for name, info in self._executors.items():
                queue_info[name] = info.executor.get_queue_length()
            return queue_info

    def get_device_state(self, device_name: str) -> Optional[DeviceState]:
        """获取设备状态（同步方法）"""
        device_manager = device_status_manager.get_device_manager(device_name)
        if device_manager:
            return device_manager.get_state()
        return None

    @asyncSlot()
    async def get_statistics(self) -> Dict[str, any]:
        """
        获取任务管理器统计信息
        """
        async with self._lock:
            active_devices = len(self._executors)
            device_stats = []

            for name, info in self._executors.items():
                # 获取设备状态
                state = self.get_device_state(name)

                device_stats.append({
                    "name": name,
                    "state": state.value if state else "unknown",
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
        异步一键启动：提交所有已启用资源的任务，不阻塞 UI
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

        def get_all_runtime_configs():
            result = []
            for resource in enabled_resources:
                config = global_config.get_runtime_configs_for_resource(
                    resource.resource_name,
                    device_config.device_name
                )
                if config:
                    result.append(config)
            return result

        runtime_configs = await asyncio.to_thread(get_all_runtime_configs)
        self.logger.debug(f"为设备创建运行时配置:{runtime_configs} ")

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
        提交指定资源的任务
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
            self.logger.debug(f"为设备创建运行时配置:{runtime_config} ")
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
        取消指定设备的特定任务
        """
        executor_info = await self._get_executor_info(device_name)
        if not executor_info:
            self.logger.error(f"取消任务失败: 设备 {device_name} 的执行器未找到")
            return False

        try:
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

    @asyncSlot(str)
    async def pause_device(self, device_name: str) -> bool:
        """
        暂停设备的当前任务
        """
        device_manager = device_status_manager.get_device_manager(device_name)
        if device_manager and device_manager.get_state() == DeviceState.RUNNING:
            device_manager.set_state(DeviceState.PAUSED)
            return True
        return False

    @asyncSlot(str)
    async def resume_device(self, device_name: str) -> bool:
        """
        恢复设备的暂停任务
        """
        device_manager = device_status_manager.get_device_manager(device_name)
        if device_manager and device_manager.get_state() == DeviceState.PAUSED:
            device_manager.set_state(DeviceState.RUNNING)
            return True
        return False


# 单例模式
task_manager = TaskerManager()