# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Union
import asyncio

from PySide6.QtCore import QObject, Signal, Slot, QMutexLocker, QRecursiveMutex, QTimer
from qasync import asyncSlot  # 使用 qasync 提供的 asyncSlot 装饰器

from app.models.config.app_config import DeviceConfig
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from core.task_executor import TaskExecutor, DeviceState


class TaskerManager(QObject):
    """
    集中管理所有设备任务执行器的管理器，使用单例模式确保整个应用中只有一个实例。
    """
    device_added = Signal(str)  # 设备添加信号
    device_removed = Signal(str)  # 设备移除信号

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._executors: Dict[str, TaskExecutor] = {}
        self._mutex = QRecursiveMutex()
        self.logger = log_manager.get_app_logger()
        self.logger.info("TaskerManager 初始化完成")
        # 定时器存储字典
        self._timers = {}

    @asyncSlot()  # 如果槽函数需要参数可以加参数类型提示
    async def create_executor(self, device_config: DeviceConfig) -> bool:
        """
        异步创建并启动设备的任务执行器。如果执行器已存在则直接返回 True。
        """
        with QMutexLocker(self._mutex):
            if device_config.device_name in self._executors:
                self.logger.debug(f"设备 {device_config.device_name} 的任务执行器已存在")
                return True

            try:
                self.logger.info(f"正在为设备 {device_config.device_name} 创建任务执行器")
                executor = TaskExecutor(device_config, parent=self)
                if executor.start():
                    self._executors[device_config.device_name] = executor
                    self.device_added.emit(device_config.device_name)
                    self.logger.info(f"设备 {device_config.device_name} 的任务执行器创建并启动成功")
                    return True
                self.logger.error(f"设备 {device_config.device_name} 的任务执行器启动失败")
                return False
            except Exception as e:
                self.logger.error(f"为设备 {device_config.device_name} 创建任务执行器失败: {e}", exc_info=True)
                return False

    @asyncSlot(object, object, object)
    async def submit_task(self, device_name: str,task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> Optional[Union[str, List[str]]]:
        """
        异步向特定设备的执行器提交任务。
        """
        with QMutexLocker(self._mutex):
            executor = self._get_executor(device_name)
            if not executor:
                self.logger.error(f"提交任务失败: 设备 {device_name} 的执行器未找到")
                return None

            try:
                if isinstance(task_data, list):
                    self.logger.info(
                        f"向设备 {device_name} 提交任务批次, 共 {len(task_data)} 个任务"
                    )
                    for i, task in enumerate(task_data):
                        self.logger.debug(f"批次任务 #{i + 1}: {task.__class__.__name__}")
                else:
                    self.logger.info(f"向设备 {device_name} 提交单个任务")
                    self.logger.debug(f"任务详情: {task_data.__class__.__name__}")

                result = executor.submit_task(task_data)
                if result:
                    if isinstance(result, list):
                        self.logger.info(f"任务批次提交成功, 获得 {len(result)} 个任务ID")
                    else:
                        self.logger.info(f"任务提交成功, 任务ID: {result}")
                else:
                    self.logger.warning(f"任务提交成功但未获取任务ID")
                return result
            except Exception as e:
                self.logger.error(f"向设备 {device_name} 提交任务失败: {e}", exc_info=True)
                return None

    @asyncSlot()
    async def stop_executor(self, device_name: str) -> bool:
        """
        异步停止特定设备的执行器。
        """
        with QMutexLocker(self._mutex):
            executor = self._get_executor(device_name)
            if not executor:
                self.logger.error(f"停止执行器失败: 设备 {device_name} 的执行器未找到")
                return False

            try:
                self.logger.info(f"正在停止设备 {device_name} 的执行器")
                executor.stop()
                del self._executors[device_name]
                self.device_removed.emit(device_name)
                self.logger.info(f"设备 {device_name} 的执行器已成功停止并移除")
                return True
            except Exception as e:
                self.logger.error(f"停止设备 {device_name} 的执行器失败: {e}", exc_info=True)
                return False

    def get_executor_state(self, device_name: str) -> Optional[DeviceState]:
        """
        获取设备执行器的当前状态（同步方法）。
        """
        with QMutexLocker(self._mutex):
            executor = self._get_executor(device_name)
            if executor:
                self.logger.debug(f"成功获取设备 {device_name} 的状态")
                return executor.get_state()
            self.logger.warning(f"获取状态失败: 设备 {device_name} 的执行器未找到")
            return None

    def _get_executor(self, device_name: str) -> Optional[TaskExecutor]:
        """
        内部辅助方法，获取特定设备的执行器（同步方法）。
        """
        executor = self._executors.get(device_name)
        if not executor:
            self.logger.debug(f"设备 {device_name} 的执行器未找到")
        return executor

    def get_active_devices(self) -> List[str]:
        """
        获取所有活跃设备名称列表（同步方法）。
        """
        with QMutexLocker(self._mutex):
            devices = list(self._executors.keys())
            self.logger.debug(f"当前活跃设备数量: {len(devices)}")
            return devices

    @Slot()
    @asyncSlot()  # Qt 信号槽中使用 asyncSlot
    async def stop_all(self) -> None:
        """
        异步停止所有执行器。
        """
        self.logger.info("正在停止所有任务执行器")
        with QMutexLocker(self._mutex):
            device_names = list(self._executors.keys())

        if not device_names:
            self.logger.info("没有活跃的任务执行器需要停止")
            return

        self.logger.info(f"找到 {len(device_names)} 个活跃的执行器需要停止: {', '.join(device_names)}")
        # 注意：这里循环中调用异步方法，可使用 await
        for device_name in device_names:
            try:
                self.logger.info(f"正在停止设备 {device_name} 的执行器")
                await self.stop_executor(device_name)
            except Exception as e:
                self.logger.error(f"停止设备 {device_name} 的执行器时出错: {e}", exc_info=True)
        self.logger.info("所有任务执行器已停止")

    def is_device_active(self, device_name: str) -> bool:
        """
        检查设备执行器是否处于活跃状态（同步方法）。
        """
        with QMutexLocker(self._mutex):
            is_active = device_name in self._executors
            self.logger.debug(f"设备 {device_name} 活跃状态: {is_active}")
            return is_active

    def get_device_queue_info(self) -> Dict[str, int]:
        """
        获取所有设备的队列状态信息（同步方法）。
        """
        with QMutexLocker(self._mutex):
            queue_info = {name: executor.get_queue_length() for name, executor in self._executors.items()}
            self.logger.debug(f"当前设备队列状态: {queue_info}")
            return queue_info

    @asyncSlot(DeviceConfig)
    async def run_device_all_resource_task(self, device_config: DeviceConfig) -> None:
        """
        异步一键启动：提交所有已启用资源的任务。
        """
        self.logger.info(f"为设备 {device_config.device_name} 一键启动所有已启用资源任务")
        enabled_resources = [r for r in device_config.resources if r.enable]
        self.logger.info(f"设备 {device_config.device_name} 的已启用资源数: {len(enabled_resources)}")

        runtime_configs = [
            global_config.get_runtime_configs_for_resource(resource.resource_name, device_config.device_name)
            for resource in enabled_resources
            if global_config.get_runtime_configs_for_resource(resource.resource_name, device_config.device_name)
        ]

        if runtime_configs:
            self.logger.info(f"设备 {device_config.device_name} 准备提交 {len(runtime_configs)} 个资源任务")
            # 异步调用创建执行器并等待完成
            await self.create_executor(device_config)
            result = await self.submit_task(device_config.device_name, runtime_configs)
            if result:
                self.logger.info(f"设备 {device_config.device_name} 的资源任务批次已成功提交")
            else:
                self.logger.error(f"设备 {device_config.device_name} 的资源任务批次提交失败")
        else:
            self.logger.warning(f"设备 {device_config.device_name} 没有找到可用的运行时配置")

    @asyncSlot(DeviceConfig,str)
    async def run_resource_task(self, device_config: DeviceConfig, resource_name: str) -> None:
        """
        提交指定资源的任务。
        此处依然为同步方法，但内部调用异步函数时可以用 asyncio.create_task 调度执行。
        """
        self.logger.info(f"为设备 {device_config.device_name} 提交资源 {resource_name} 的任务")
        runtime_config = global_config.get_runtime_configs_for_resource(resource_name, device_config.device_name)

        if not runtime_config:
            self.logger.error(f"找不到设备 {device_config.device_name} 资源 {resource_name} 的运行时配置")
            return

        # 这里启动一个任务，将异步方法调度到事件循环中
        self.logger.info(f"找到设备 {device_config.device_name} 资源 {resource_name} 的运行时配置")
        # 再次确保执行器创建成功
        success = await self.create_executor(device_config)
        if not success:
            self.logger.error(f"为设备 {device_config.device_name} 创建执行器失败，无法运行资源 {resource_name}")
            return
        result = await self.submit_task(device_config.device_name, runtime_config)
        if result:
            self.logger.info(f"设备 {device_config.device_name} 的资源 {resource_name} 任务已成功提交，任务ID: {result}")
        else:
            self.logger.error(f"设备 {device_config.device_name} 的资源 {resource_name} 任务提交失败")

    # ===== 以下是定时任务相关方法，因 QTimer 触发的回调一般为同步槽函数，

    def setup_device_scheduled_tasks(self, device_config: DeviceConfig) -> List[str]:
        """
        根据设备配置设置定时任务，自动运行所有已启用资源的任务。
        """
        if not device_config.schedule_enabled:
            self.logger.info(f"设备 {device_config.device_name} 未启用定时功能")
            return []

        if not device_config.schedule_time:
            self.logger.warning(f"设备 {device_config.device_name} 启用了定时功能但未配置时间")
            return []

        self.logger.info(f"为设备 {device_config.device_name} 配置 {len(device_config.schedule_time)} 个定时任务")
        device_timers = []

        for time_str in device_config.schedule_time:
            try:
                timer_id = f"{device_config.device_name}_{time_str}_{id(time_str)}"
                timer = QTimer(self)
                timer.setSingleShot(False)  # 重复执行

                hours, minutes = map(int, time_str.split(':'))
                next_run = self._calculate_next_run_time(hours, minutes)
                now = datetime.now()
                delay_ms = int((next_run - now).total_seconds() * 1000)

                timer.setInterval(24 * 60 * 60 * 1000)  # 每日重复

                # 捕获当前 device_config
                device_config_copy = device_config
                timer.timeout.connect(
                    lambda: self.run_device_all_resource_task(device_config_copy)
                )

                self._timers[timer_id] = {
                    'timer': timer,
                    'device_name': device_config.device_name,
                    'time': time_str,
                    'next_run': next_run
                }
                device_timers.append(timer_id)

                QTimer.singleShot(
                    delay_ms,
                    lambda t=timer, dc=device_config_copy: self._scheduled_task_first_run(t, dc)
                )

                self.logger.info(
                    f"设备 {device_config.device_name} 的定时任务已设置，将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"首次运行，之后每天 {time_str} 运行"
                )
            except Exception as e:
                self.logger.error(f"设置设备 {device_config.device_name} 的定时任务时出错: {e}", exc_info=True)

        return device_timers

    def _scheduled_task_first_run(self, timer: QTimer, device_config: DeviceConfig) -> None:
        """
        首次运行定时任务的处理函数：
        在首次触发后执行任务，并启动后续每日定时器。
        """
        self.logger.info(f"首次运行设备 {device_config.device_name} 的定时任务")
        # 调度异步任务
        asyncio.create_task(self.run_device_all_resource_task(device_config))
        timer.start()

    def _calculate_next_run_time(self, hours: int, minutes: int) -> datetime:
        """
        计算下一次运行时间。
        """
        now = datetime.now()
        target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)
        return target_time

    def cancel_device_scheduled_tasks(self, device_name: str) -> None:
        """
        取消指定设备的所有定时任务。
        """
        device_timer_ids = [tid for tid, info in self._timers.items()
                            if info['device_name'] == device_name]
        for timer_id in device_timer_ids:
            timer_info = self._timers.pop(timer_id, None)
            if timer_info and 'timer' in timer_info:
                timer_info['timer'].stop()
        self.logger.info(f"已取消设备 {device_name} 的 {len(device_timer_ids)} 个定时任务")

    def setup_all_device_scheduled_tasks(self) -> None:
        """
        从全局配置初始化所有设备的定时任务。
        """
        scheduled_devices = [d for d in global_config.get_app_config().devices if d.schedule_enabled]
        if not scheduled_devices:
            self.logger.info("没有启用定时功能的设备")
            return

        self.logger.info(f"开始配置 {len(scheduled_devices)} 个设备的定时任务")
        for device in scheduled_devices:
            self.setup_device_scheduled_tasks(device)

    def stop_all_scheduled_tasks(self) -> None:
        """
        停止所有定时任务。
        """
        for timer_info in self._timers.values():
            if 'timer' in timer_info:
                timer_info['timer'].stop()
        timer_count = len(self._timers)
        self._timers.clear()
        self.logger.info(f"已停止所有 {timer_count} 个定时任务")

    def get_scheduled_tasks_info(self) -> List[Dict]:
        """
        获取所有定时任务的信息。
        """
        tasks_info = []
        for timer_id, info in self._timers.items():
            tasks_info.append({
                'id': timer_id,
                'device_name': info['device_name'],
                'time': info['time'],
                'next_run': info['next_run'].strftime('%Y-%m-%d %H:%M:%S') if 'next_run' in info else 'Unknown'
            })
        return tasks_info

    def update_device_scheduled_tasks(self, device_config: DeviceConfig) -> None:
        """
        更新设备定时任务 - 先取消原有任务，再重新设置。
        """
        self.logger.info(f"更新设备 {device_config.device_name} 的定时任务")
        self.cancel_device_scheduled_tasks(device_config.device_name)
        if device_config.schedule_enabled:
            self.setup_device_scheduled_tasks(device_config)
        else:
            self.logger.info(f"设备 {device_config.device_name} 定时功能已禁用，不再重新设置定时任务")


# 单例模式
task_manager = TaskerManager()
