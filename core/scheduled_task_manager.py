# -*- coding: UTF-8 -*-
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QTimer, QMutexLocker, QRecursiveMutex
from qasync import asyncSlot

from app.models.config.app_config import DeviceConfig, Resource
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.tasker_manager import task_manager, TaskerManager



class ScheduledTaskManager(QObject):
    """
    独立的定时任务管理器，负责管理所有设备的定时任务。
    """

    # 信号定义
    scheduled_task_added = Signal(str, str)  # 设备定时任务添加信号（设备名称，任务ID）
    scheduled_task_removed = Signal(str, str)  # 设备定时任务删除信号（设备名称，任务ID）
    scheduled_task_modified = Signal(str, str)  # 设备定时任务修改信号（设备名称，任务ID）
    scheduled_task_triggered = Signal(str, str, str)  # 定时任务触发信号（设备名称，资源名称，设置名称）

    def __init__(self, tasker_manager: 'TaskerManager', parent=None):
        super().__init__(parent)
        self._tasker_manager = tasker_manager
        self._timers: Dict[str, Dict] = {}  # 定时器存储字典
        self._mutex = QRecursiveMutex()
        self.logger = log_manager.get_app_logger()
        self.logger.info("ScheduledTaskManager 初始化完成")

        # 连接信号
        self.scheduled_task_triggered.connect(self._on_scheduled_task_triggered)

    def setup_all_device_scheduled_tasks(self) -> None:
        """从全局配置初始化所有设备的资源级定时任务"""
        all_devices = global_config.get_app_config().devices
        self.logger.info(f"开始检查 {len(all_devices)} 个设备的资源级定时任务")

        for device in all_devices:
            self.setup_device_scheduled_tasks(device)

    def setup_device_scheduled_tasks(self, device_config: DeviceConfig) -> List[str]:
        """为设备配置所有资源级定时任务"""
        timer_ids = []

        for resource in device_config.resources:
            if resource.schedules_enable:
                resource_timer_ids = self.setup_resource_scheduled_tasks(device_config, resource)
                timer_ids.extend(resource_timer_ids)
            else:
                self.logger.debug(f"资源 {resource.resource_name} 定时任务未启用")

        if timer_ids:
            self.logger.info(f"设备 {device_config.device_name} 已设置 {len(timer_ids)} 个定时任务")

        return timer_ids

    def setup_resource_scheduled_tasks(self, device_config: DeviceConfig, resource: Resource) -> List[str]:
        """根据资源配置设置资源级别的定时任务"""
        if not resource.schedules_enable or not resource.schedules or not any(
                schedule.enabled for schedule in resource.schedules):
            self.logger.info(f"资源 {resource.resource_name} 在设备 {device_config.device_name} 中没有启用的定时任务")
            return []

        resource_timers = []

        for schedule in resource.schedules:
            if not schedule.enabled or not schedule.schedule_time:
                continue

            self.logger.info(f"为设备 {device_config.device_name} 中的资源 {resource.resource_name} "
                             f"配置定时任务，时间为 {schedule.schedule_time}，使用设置 {schedule.settings_name}")

            try:
                # 生成唯一的定时器ID
                timer_id = f"{device_config.device_name}_{resource.resource_name}_{schedule.settings_name}_{schedule.schedule_time}_{id(schedule)}"
                timer = QTimer(self)
                timer.setSingleShot(False)  # 重复执行

                # 解析时间
                if isinstance(schedule.schedule_time, str):
                    hours, minutes = map(int, schedule.schedule_time.split(':'))
                else:
                    self.logger.error(f"资源定时任务时间格式无效: {schedule.schedule_time}")
                    continue

                next_run = self._calculate_next_run_time(hours, minutes)
                now = datetime.now()
                delay_ms = int((next_run - now).total_seconds() * 1000)

                timer.setInterval(24 * 60 * 60 * 1000)  # 每日重复

                # 捕获当前设备和资源信息
                device_name = device_config.device_name
                resource_name = resource.resource_name
                settings_name = schedule.settings_name

                # 使用lambda捕获变量值
                timer.timeout.connect(
                    lambda dn=device_name, rn=resource_name, sn=settings_name:
                    self.scheduled_task_triggered.emit(dn, rn, sn)
                )

                with QMutexLocker(self._mutex):
                    self._timers[timer_id] = {
                        'id': timer_id,
                        'timer': timer,
                        'device_name': device_config.device_name,
                        'resource_name': resource.resource_name,
                        'settings_name': schedule.settings_name,
                        'time': schedule.schedule_time,
                        'next_run': next_run,
                        'type': 'resource'
                    }

                resource_timers.append(timer_id)

                # 设置首次运行的单次定时器
                QTimer.singleShot(
                    delay_ms,
                    lambda t=timer, dn=device_name, rn=resource_name, sn=settings_name, tid=timer_id:
                    self._scheduled_task_first_run(t, dn, rn, sn, tid)
                )

                time_display = f"{hours}:{minutes:02d}"
                self.logger.info(
                    f"设备 {device_config.device_name} 中资源 {resource.resource_name} 的定时任务 "
                    f"(使用设置 {schedule.settings_name}) 已设置，将在 "
                    f"{next_run.strftime('%Y-%m-%d %H:%M:%S')} 首次运行，之后每天 {time_display} 运行"
                )

                # 发出任务添加信号
                self.scheduled_task_added.emit(device_config.device_name, timer_id)

            except Exception as e:
                self.logger.error(
                    f"设置设备 {device_config.device_name} 中资源 {resource.resource_name} 的定时任务时出错: {e}",
                    exc_info=True)

        return resource_timers

    def update_device_scheduled_tasks(self, device_config: DeviceConfig) -> None:
        """更新设备定时任务 - 先取消原有任务，再重新设置"""
        self.logger.info(f"更新设备 {device_config.device_name} 的资源级定时任务")

        # 保存旧定时任务列表
        old_task_ids = [tid for tid, info in self._timers.items()
                        if info['device_name'] == device_config.device_name]

        # 取消旧定时任务
        self.cancel_device_scheduled_tasks(device_config.device_name)

        # 设置新定时任务
        new_task_ids = self.setup_device_scheduled_tasks(device_config)

        # 如果有变化，发出修改信号
        if old_task_ids or new_task_ids:
            for task_id in new_task_ids:
                self.scheduled_task_modified.emit(device_config.device_name, task_id)

            self.logger.info(
                f"设备 {device_config.device_name} 的定时任务已更新，移除 {len(old_task_ids)} 个，添加 {len(new_task_ids)} 个")

    def update_resource_scheduled_task(self, device_config: DeviceConfig, resource_name: str,
                                       old_schedule_id: str, new_schedule_time: str,
                                       settings_name: str = None) -> bool:
        """更新资源的定时任务"""
        self.logger.info(f"更新设备 {device_config.device_name} 资源 {resource_name} 的定时任务 {old_schedule_id}")

        with QMutexLocker(self._mutex):
            # 查找现有定时任务
            if old_schedule_id not in self._timers:
                self.logger.error(f"找不到定时任务 {old_schedule_id}")
                return False

            timer_info = self._timers[old_schedule_id]

            # 验证设备和资源匹配
            if timer_info['device_name'] != device_config.device_name or timer_info['resource_name'] != resource_name:
                self.logger.error(f"定时任务 {old_schedule_id} 与指定的设备或资源不匹配")
                return False

        try:
            # 停止旧定时器
            old_timer = timer_info['timer']
            old_timer.stop()

            # 解析新时间
            hours, minutes = map(int, new_schedule_time.split(':'))
            next_run = self._calculate_next_run_time(hours, minutes)

            # 使用新设置或保留旧设置
            actual_settings_name = settings_name if settings_name else timer_info['settings_name']

            # 生成新的定时器ID
            new_timer_id = f"{device_config.device_name}_{resource_name}_{actual_settings_name}_{new_schedule_time}_{id(next_run)}"

            # 创建新定时器
            timer = QTimer(self)
            timer.setSingleShot(False)
            timer.setInterval(24 * 60 * 60 * 1000)

            # 捕获当前设备和资源信息
            device_name = device_config.device_name

            timer.timeout.connect(
                lambda dn=device_name, rn=resource_name, sn=actual_settings_name:
                self.scheduled_task_triggered.emit(dn, rn, sn)
            )

            # 更新定时器信息字典
            with QMutexLocker(self._mutex):
                self._timers.pop(old_schedule_id)
                self._timers[new_timer_id] = {
                    'id': new_timer_id,
                    'timer': timer,
                    'device_name': device_config.device_name,
                    'resource_name': resource_name,
                    'settings_name': actual_settings_name,
                    'time': new_schedule_time,
                    'next_run': next_run,
                    'type': 'resource'
                }

            # 设置首次运行的单次定时器
            now = datetime.now()
            delay_ms = int((next_run - now).total_seconds() * 1000)

            QTimer.singleShot(
                delay_ms,
                lambda t=timer, dn=device_name, rn=resource_name, sn=actual_settings_name, tid=new_timer_id:
                self._scheduled_task_first_run(t, dn, rn, sn, tid)
            )

            self.logger.info(
                f"设备 {device_config.device_name} 中资源 {resource_name} 的定时任务已更新，"
                f"新时间: {new_schedule_time}，设置: {actual_settings_name}，"
                f"将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 首次运行"
            )

            # 发出任务修改信号
            self.scheduled_task_modified.emit(device_config.device_name, new_timer_id)

            return True

        except Exception as e:
            self.logger.error(f"更新定时任务时出错: {e}", exc_info=True)
            return False

    def cancel_device_scheduled_tasks(self, device_name: str) -> None:
        """取消指定设备的所有定时任务"""
        with QMutexLocker(self._mutex):
            device_timer_ids = [tid for tid, info in self._timers.items()
                                if info['device_name'] == device_name]

            for timer_id in device_timer_ids:
                timer_info = self._timers.pop(timer_id, None)
                if timer_info and 'timer' in timer_info:
                    timer_info['timer'].stop()
                    # 发出任务移除信号
                    self.scheduled_task_removed.emit(device_name, timer_id)

        self.logger.info(f"已取消设备 {device_name} 的 {len(device_timer_ids)} 个资源级定时任务")

    def stop_all_scheduled_tasks(self) -> None:
        """停止所有定时任务"""
        with QMutexLocker(self._mutex):
            for timer_info in self._timers.values():
                if 'timer' in timer_info:
                    timer_info['timer'].stop()
                    # 发出任务移除信号
                    device_name = timer_info.get('device_name')
                    timer_id = timer_info.get('id')
                    if device_name and timer_id:
                        self.scheduled_task_removed.emit(device_name, timer_id)

            timer_count = len(self._timers)
            self._timers.clear()
            self.logger.info(f"已停止所有 {timer_count} 个定时任务")

    def get_scheduled_tasks_info(self) -> List[Dict]:
        """获取所有定时任务的信息"""
        with QMutexLocker(self._mutex):
            tasks_info = []
            for timer_id, info in self._timers.items():
                task_info = {
                    'id': timer_id,
                    'device_name': info['device_name'],
                    'time': info['time'],
                    'next_run': info['next_run'].strftime('%Y-%m-%d %H:%M:%S') if 'next_run' in info else 'Unknown',
                    'resource_name': info.get('resource_name'),
                    'settings_name': info.get('settings_name'),
                    'type': info.get('type', 'unknown')
                }
                tasks_info.append(task_info)
            return tasks_info

    def get_device_scheduled_tasks(self, device_name: str) -> List[Dict]:
        """获取特定设备的所有定时任务信息"""
        with QMutexLocker(self._mutex):
            device_tasks = []
            for timer_id, info in self._timers.items():
                if info['device_name'] == device_name:
                    task_info = {
                        'id': timer_id,
                        'device_name': info['device_name'],
                        'time': info['time'],
                        'next_run': info['next_run'].strftime('%Y-%m-%d %H:%M:%S') if 'next_run' in info else 'Unknown',
                        'resource_name': info.get('resource_name'),
                        'settings_name': info.get('settings_name'),
                        'type': info.get('type', 'unknown')
                    }
                    device_tasks.append(task_info)
            return device_tasks

    def _calculate_next_run_time(self, hours: int, minutes: int) -> datetime:
        """计算下一次运行时间"""
        now = datetime.now()
        target_time = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)
        return target_time

    def _scheduled_task_first_run(self, timer: QTimer, device_name: str, resource_name: str,
                                  settings_name: str, timer_id: str) -> None:
        """首次运行资源级定时任务的处理函数"""
        self.logger.info(
            f"首次运行设备 {device_name} 中资源 {resource_name} 的定时任务 (使用设置 {settings_name})")

        try:
            # 触发定时任务
            self.scheduled_task_triggered.emit(device_name, resource_name, settings_name)

            # 启动定时器以进行后续运行
            timer.start()

            # 更新下一次运行时间
            with QMutexLocker(self._mutex):
                if timer_id in self._timers:
                    timer_info = self._timers[timer_id]

                    # 计算下一次运行时间
                    if isinstance(timer_info['time'], str):
                        time_parts = timer_info['time'].split(':')
                        hours = int(time_parts[0])
                        minutes = int(time_parts[1])

                        next_run = datetime.now() + timedelta(days=1)
                        next_run = next_run.replace(hour=hours, minute=minutes, second=0, microsecond=0)

                        timer_info['next_run'] = next_run

        except Exception as e:
            self.logger.error(f"定时任务首次运行失败: {e}", exc_info=True)

    @asyncSlot(str, str, str)
    async def _on_scheduled_task_triggered(self, device_name: str, resource_name: str, settings_name: str):
        """处理定时任务触发事件"""
        self.logger.info(f"定时任务触发：设备 {device_name}，资源 {resource_name}，设置 {settings_name}")

        try:
            # 获取设备配置
            device_config = global_config.get_device_config(device_name)
            if not device_config:
                self.logger.error(f"找不到设备配置: {device_name}")
                return

            # 查找资源
            resource = next((r for r in device_config.resources if r.resource_name == resource_name), None)
            if not resource:
                self.logger.error(f"在设备 {device_name} 中找不到资源 {resource_name}")
                return

            # 临时修改资源的settings_name
            original_settings_name = resource.settings_name
            try:
                resource.settings_name = settings_name

                # 获取运行时配置
                runtime_config = global_config.get_runtime_configs_for_resource(resource_name, device_name)

                if not runtime_config:
                    self.logger.error(
                        f"无法获取设备 {device_name} 中资源 {resource_name} 的运行时配置 (使用设置 {settings_name})")
                    return

                # 创建执行器（如果需要）
                await self._tasker_manager.create_executor(device_config)

                # 提交任务
                result = await self._tasker_manager.submit_task(device_name, runtime_config)
                if result:
                    self.logger.info(
                        f"成功提交设备 {device_name} 中资源 {resource_name} 的任务 (使用设置 {settings_name})，任务ID: {result}")
                else:
                    self.logger.error(
                        f"提交设备 {device_name} 中资源 {resource_name} 的任务失败 (使用设置 {settings_name})")

            finally:
                # 恢复原始settings_name
                resource.settings_name = original_settings_name

        except Exception as e:
            self.logger.error(f"运行定时任务时出错: {e}", exc_info=True)


# -*- coding: UTF-8 -*-
from datetime import datetime
from typing import Dict, List
from PySide6.QtCore import QObject, Slot
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.device_status_manager import device_status_manager


class ScheduledInfoUpdater(QObject):
    """
    定时任务信息更新器
    负责监听定时任务变化并更新设备状态管理器中的定时任务信息
    """

    def __init__(self, scheduled_task_manager, parent=None):
        super().__init__(parent)
        self.scheduled_task_manager = scheduled_task_manager
        self.logger = log_manager.get_app_logger()

        # 连接信号
        self._connect_signals()

        # 初始化时更新所有设备的定时任务信息
        self.update_all_devices()

    def _connect_signals(self):
        """连接定时任务管理器的信号"""
        self.scheduled_task_manager.scheduled_task_added.connect(self.on_task_changed)
        self.scheduled_task_manager.scheduled_task_removed.connect(self.on_task_changed)
        self.scheduled_task_manager.scheduled_task_modified.connect(self.on_task_changed)

    @Slot(str, str)
    def on_task_changed(self, device_name: str, task_id: str):
        """当定时任务发生变化时更新对应设备的信息"""
        self.update_device_scheduled_info(device_name)

    def update_device_scheduled_info(self, device_name: str):
        """更新指定设备的定时任务信息"""
        try:
            # 获取设备配置
            device_config = global_config.get_device_config(device_name)
            if not device_config:
                return

            # 检查是否有启用的定时任务
            has_enabled_schedules = any(
                r.schedules_enable and r.schedules and any(s.enabled for s in r.schedules)
                for r in device_config.resources
            )

            if has_enabled_schedules:
                # 获取设备的定时任务信息
                tasks_info = self.scheduled_task_manager.get_scheduled_tasks_info()
                device_tasks = [task for task in tasks_info if task['device_name'] == device_name]

                if device_tasks:
                    # 解析下次运行时间
                    next_run_times = []
                    for task in device_tasks:
                        if task.get('next_run') and task.get('next_run') != 'Unknown':
                            try:
                                next_time = datetime.strptime(task['next_run'], '%Y-%m-%d %H:%M:%S')
                                next_run_times.append(next_time)
                            except Exception as e:
                                self.logger.warning(f"解析定时任务时间失败: {e}")

                    if next_run_times:
                        next_time = min(next_run_times)
                        schedule_text = next_time.strftime('%H:%M')
                        device_status_manager.update_scheduled_info(
                            device_name,
                            True,
                            next_time,
                            schedule_text
                        )
                    else:
                        device_status_manager.update_scheduled_info(
                            device_name,
                            True,
                            None,
                            "已启用"
                        )
                else:
                    device_status_manager.update_scheduled_info(
                        device_name,
                        True,
                        None,
                        "已启用"
                    )
            else:
                device_status_manager.update_scheduled_info(
                    device_name,
                    False,
                    None,
                    "未启用"
                )

        except Exception as e:
            self.logger.error(f"更新设备 {device_name} 定时任务信息时出错: {e}")
            device_status_manager.update_scheduled_info(
                device_name,
                False,
                None,
                "更新失败"
            )

    def update_all_devices(self):
        """更新所有设备的定时任务信息"""
        try:
            all_devices = global_config.get_app_config().devices
            for device in all_devices:
                self.update_device_scheduled_info(device.device_name)
        except Exception as e:
            self.logger.error(f"更新所有设备定时任务信息时出错: {e}")




def init_scheduled_info_updater(scheduled_task_manager):
    """初始化定时任务信息更新器"""
    global scheduled_info_updater
    scheduled_info_updater = ScheduledInfoUpdater(scheduled_task_manager)
    return scheduled_info_updater

scheduled_task_manager = ScheduledTaskManager(task_manager)

# 初始化定时任务信息更新器
scheduled_info_updater = init_scheduled_info_updater(scheduled_task_manager)