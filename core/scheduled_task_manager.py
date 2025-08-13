# scheduled_task_manager.py - 重构版本
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TYPE_CHECKING
from PySide6.QtCore import QObject, Signal, QTimer, QMutexLocker, QRecursiveMutex
from qasync import asyncSlot

from app.models.config.app_config import DeviceConfig, Resource, ResourceSchedule
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager


class ScheduledTaskManager(QObject):
    """统一的定时任务管理器，负责管理所有设备的定时任务。"""

    # 信号定义
    task_added = Signal(dict)  # 任务添加信号(task_info)
    task_removed = Signal(str)  # 任务删除信号(task_id)
    task_modified = Signal(str, dict)  # 任务修改信号(task_id, task_info)
    task_triggered = Signal(str, str, str)  # 任务触发信号(device_name, resource_name, settings_name)
    task_status_changed = Signal(str, bool)  # 任务状态改变信号(task_id, enabled)

    # 用于UI的信号
    scheduled_task_added = Signal(str, str)  # 兼容旧信号（设备名称，任务ID）
    scheduled_task_removed = Signal(str, str)  # 兼容旧信号（设备名称，任务ID）
    scheduled_task_modified = Signal(str, str)  # 兼容旧信号（设备名称，任务ID）
    scheduled_task_triggered = Signal(str, str, str)  # 兼容旧信号

    def __init__(self, tasker_manager: 'TaskerManager', parent=None):
        super().__init__(parent)
        self._tasker_manager = tasker_manager
        self._timers: Dict[str, Dict] = {}  # 定时器存储字典 {task_id: timer_info}
        self._mutex = QRecursiveMutex()
        self.logger = log_manager.get_app_logger()
        self._task_counter = 0

        # 连接信号
        self.task_triggered.connect(self._on_scheduled_task_triggered)
        self.scheduled_task_triggered.connect(self._on_scheduled_task_triggered)

        self.logger.info("ScheduledTaskManager 初始化完成")

    def initialize_from_config(self) -> List[dict]:
        """从配置初始化所有定时任务，返回任务列表供UI显示"""
        all_tasks = []
        all_devices = global_config.get_app_config().devices
        self.logger.info(f"开始从配置加载定时任务，共 {len(all_devices)} 个设备")

        for device in all_devices:
            for resource in device.resources:
                if not resource.schedules_enable or not resource.schedules:
                    continue

                for schedule in resource.schedules:
                    # 创建任务信息
                    task_info = self._create_task_info_from_schedule(
                        device.device_name,
                        resource.resource_name,
                        schedule
                    )

                    # 如果任务启用，设置定时器
                    if schedule.enabled:
                        self._setup_timer(task_info)

                    # 保存任务信息到内存
                    with QMutexLocker(self._mutex):
                        self._timers[task_info['id']] = task_info

                    # 添加到返回列表
                    all_tasks.append(task_info)

        self.logger.info(f"从配置中加载了 {len(all_tasks)} 个定时任务")
        return all_tasks

    def add_task(self, task_info: dict) -> str:
        """添加新的定时任务"""
        with QMutexLocker(self._mutex):
            # 生成任务ID
            self._task_counter += 1
            task_id = str(self._task_counter)
            task_info['id'] = task_id

            # 确保必要字段
            task_info['status'] = task_info.get('status', '活动')
            task_info['device_name'] = task_info.get('device', task_info.get('device_name'))
            task_info['resource_name'] = task_info.get('resource', task_info.get('resource_name'))
            task_info['settings_name'] = task_info.get('config_scheme', task_info.get('settings_name', '默认配置'))

            # 更新配置
            self._update_config_add_task(task_info)

            # 设置定时器
            if task_info['status'] == '活动':
                self._setup_timer(task_info)

            # 保存任务信息
            self._timers[task_id] = task_info

            # 发出信号
            self.task_added.emit(task_info)
            self.scheduled_task_added.emit(task_info['device_name'], task_id)

            self.logger.info(f"添加定时任务: ID={task_id}, 设备={task_info['device_name']}, "
                             f"资源={task_info['resource_name']}")
            return task_id

    def remove_task(self, task_id: str) -> bool:
        """删除定时任务"""
        with QMutexLocker(self._mutex):
            if task_id not in self._timers:
                return False

            timer_info = self._timers.pop(task_id)

            # 停止定时器
            if 'timer' in timer_info:
                timer_info['timer'].stop()
                timer_info['timer'].deleteLater()

            # 更新配置
            self._update_config_remove_task(timer_info)

            # 发出信号
            self.task_removed.emit(task_id)
            self.scheduled_task_removed.emit(timer_info['device_name'], task_id)

            self.logger.info(f"删除定时任务: {task_id}")
            return True

    def toggle_task_status(self, task_id: str, enabled: bool) -> bool:
        """切换任务状态（启用/禁用）"""
        with QMutexLocker(self._mutex):
            if task_id not in self._timers:
                return False

            timer_info = self._timers[task_id]
            old_status = timer_info.get('status', '暂停')
            new_status = '活动' if enabled else '暂停'

            if old_status == new_status:
                return True  # 状态未改变

            timer_info['status'] = new_status

            if enabled:
                # 启用任务 - 设置定时器
                self._setup_timer(timer_info)
            else:
                # 禁用任务 - 停止定时器
                if 'timer' in timer_info:
                    timer_info['timer'].stop()

            # 更新配置
            self._update_config_task_status(timer_info, enabled)

            # 发出信号
            self.task_status_changed.emit(task_id, enabled)
            self.scheduled_task_modified.emit(timer_info['device_name'], task_id)

            self.logger.info(f"任务 {task_id} 状态更改为: {new_status}")
            return True

    def update_task_config(self, task_id: str, config_scheme: str) -> bool:
        """更新任务的配置方案"""
        with QMutexLocker(self._mutex):
            if task_id not in self._timers:
                return False

            timer_info = self._timers[task_id]
            timer_info['config_scheme'] = config_scheme
            timer_info['settings_name'] = config_scheme

            # 更新配置
            self._update_config_task_settings(timer_info, config_scheme)

            # 发出信号
            self.task_modified.emit(task_id, timer_info)
            self.scheduled_task_modified.emit(timer_info['device_name'], task_id)

            return True

    def update_task_notify(self, task_id: str, notify: bool) -> bool:
        """更新任务的通知设置"""
        with QMutexLocker(self._mutex):
            if task_id not in self._timers:
                return False

            timer_info = self._timers[task_id]
            timer_info['notify'] = notify

            # 更新配置
            self._update_config_task_notify(timer_info, notify)

            # 发出信号
            self.task_modified.emit(task_id, timer_info)

            return True

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务信息供UI显示"""
        with QMutexLocker(self._mutex):
            tasks = []
            for task_id, timer_info in self._timers.items():
                # 复制任务信息，确保UI需要的字段都存在
                task_data = {
                    'id': task_id,
                    'device': timer_info.get('device_name', timer_info.get('device')),
                    'resource': timer_info.get('resource_name', timer_info.get('resource')),
                    'schedule_type': timer_info.get('schedule_type', '每日执行'),
                    'time': timer_info.get('time', '00:00:00'),
                    'config_scheme': timer_info.get('config_scheme', timer_info.get('settings_name', '默认配置')),
                    'notify': timer_info.get('notify', False),
                    'status': timer_info.get('status', '活动')
                }

                if 'week_days' in timer_info:
                    task_data['week_days'] = timer_info['week_days']

                tasks.append(task_data)
            return tasks

    def get_device_scheduled_tasks(self, device_name: str) -> List[Dict]:
        """获取特定设备的所有定时任务信息"""
        with QMutexLocker(self._mutex):
            device_tasks = []
            for task_id, timer_info in self._timers.items():
                if timer_info.get('device_name') == device_name:
                    task_info = {
                        'id': task_id,
                        'device_name': timer_info['device_name'],
                        'time': timer_info.get('time', ''),
                        'next_run': timer_info.get('next_run', datetime.now()).strftime('%Y-%m-%d %H:%M:%S'),
                        'resource_name': timer_info.get('resource_name'),
                        'settings_name': timer_info.get('settings_name'),
                        'type': timer_info.get('type', 'resource')
                    }
                    device_tasks.append(task_info)
            return device_tasks

    def get_scheduled_tasks_info(self) -> List[Dict]:
        """获取所有定时任务的信息（兼容旧接口）"""
        return self.get_device_scheduled_tasks("")

    def stop_all_scheduled_tasks(self) -> None:
        """停止所有定时任务"""
        with QMutexLocker(self._mutex):
            for timer_info in self._timers.values():
                if 'timer' in timer_info:
                    timer_info['timer'].stop()
                    timer_info['timer'].deleteLater()
                    # 发出任务移除信号
                    device_name = timer_info.get('device_name')
                    timer_id = timer_info.get('id')
                    if device_name and timer_id:
                        self.scheduled_task_removed.emit(device_name, timer_id)

            timer_count = len(self._timers)
            self._timers.clear()
            self.logger.info(f"已停止所有 {timer_count} 个定时任务")

    def _create_task_info_from_schedule(self, device_name: str, resource_name: str,
                                        schedule: ResourceSchedule) -> dict:
        """从ResourceSchedule创建任务信息字典"""
        if schedule.task_id:
            # 如果已有task_id，使用它
            task_id = schedule.task_id
        else:
            # 生成新的task_id
            self._task_counter += 1
            task_id = str(self._task_counter)
            schedule.task_id = task_id  # 保存到schedule中

        task_info = {
            'id': task_id,
            'device': device_name,
            'resource': resource_name,
            'device_name': device_name,  # 兼容旧代码
            'resource_name': resource_name,  # 兼容旧代码
            'schedule_type': schedule.get_schedule_type_display(),
            'time': schedule.schedule_time,
            'config_scheme': schedule.settings_name or '默认配置',
            'settings_name': schedule.settings_name,  # 兼容旧代码
            'notify': schedule.notify,
            'status': '活动' if schedule.enabled else '暂停',
            'type': 'resource'  # 任务类型
        }

        if schedule.schedule_type == 'weekly' and schedule.week_days:
            task_info['week_days'] = schedule.week_days

        return task_info

    def _setup_timer(self, task_info: dict):
        """设置定时器"""
        task_id = task_info['id']

        # 如果已存在定时器，先停止并删除
        if task_id in self._timers and 'timer' in self._timers[task_id]:
            old_timer = self._timers[task_id]['timer']
            old_timer.stop()
            old_timer.deleteLater()

        # 创建新定时器
        timer = QTimer(self)

        # 解析时间
        time_str = task_info.get('time', '00:00:00')
        try:
            parts = time_str.split(':')
            hours = int(parts[0]) if parts[0] else 0
            minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            seconds = int(parts[2]) if len(parts) > 2 and parts[2] else 0
        except (ValueError, IndexError) as e:
            self.logger.error(f"无法解析时间 '{time_str}': {e}")
            return

        # 计算下次运行时间
        next_run = self._calculate_next_run_time(hours, minutes, seconds)
        now = datetime.now()
        delay_ms = int((next_run - now).total_seconds() * 1000)

        # 根据任务类型设置定时器
        schedule_type = task_info.get('schedule_type', '每日执行')
        if schedule_type == '单次执行':
            timer.setSingleShot(True)
        else:
            timer.setSingleShot(False)
            timer.setInterval(24 * 60 * 60 * 1000)  # 24小时

        # 捕获变量并连接信号
        device_name = task_info['device_name']
        resource_name = task_info['resource_name']
        settings_name = task_info.get('settings_name', '')

        timer.timeout.connect(
            lambda dn=device_name, rn=resource_name, sn=settings_name:
            self.task_triggered.emit(dn, rn, sn)
        )

        # 保存定时器信息
        task_info['timer'] = timer
        task_info['next_run'] = next_run

        # 设置首次运行
        if delay_ms > 0:
            QTimer.singleShot(
                delay_ms,
                lambda t=timer, tid=task_id: self._first_run_task(t, tid)
            )
        else:
            # 如果时间已过，设置为明天
            next_run = next_run + timedelta(days=1)
            delay_ms = int((next_run - now).total_seconds() * 1000)
            task_info['next_run'] = next_run
            QTimer.singleShot(
                delay_ms,
                lambda t=timer, tid=task_id: self._first_run_task(t, tid)
            )

        self.logger.info(f"定时任务 {task_id} 已设置，将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 首次运行")

    def _first_run_task(self, timer: QTimer, task_id: str):
        """首次运行任务"""
        with QMutexLocker(self._mutex):
            if task_id not in self._timers:
                return

            timer_info = self._timers[task_id]

            # 触发任务
            self.task_triggered.emit(
                timer_info['device_name'],
                timer_info['resource_name'],
                timer_info.get('settings_name', '')
            )

            # 如果不是单次任务，启动定时器
            if timer_info.get('schedule_type') != '单次执行':
                timer.start()
                # 更新下次运行时间
                time_str = timer_info.get('time', '00:00:00')
                parts = time_str.split(':')
                hours = int(parts[0]) if parts[0] else 0
                minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                seconds = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                timer_info['next_run'] = self._calculate_next_run_time(hours, minutes, seconds)

    def _calculate_next_run_time(self, hours: int, minutes: int, seconds: int = 0) -> datetime:
        """计算下次运行时间"""
        now = datetime.now()
        target_time = now.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)
        return target_time

    def _update_config_add_task(self, task_info: dict):
        """更新配置 - 添加任务"""
        try:
            device_name = task_info.get('device', task_info.get('device_name'))
            resource_name = task_info.get('resource', task_info.get('resource_name'))

            device_config = global_config.get_device_config(device_name)
            if not device_config:
                self.logger.error(f"找不到设备配置: {device_name}")
                return

            resource = next((r for r in device_config.resources
                             if r.resource_name == resource_name), None)
            if not resource:
                self.logger.error(f"找不到资源配置: {resource_name}")
                return

            # 创建新的schedule
            schedule = ResourceSchedule.from_ui_format(task_info)
            schedule.task_id = task_info['id']

            # 添加到资源配置
            if not resource.schedules:
                resource.schedules = []
            resource.schedules.append(schedule)
            resource.schedules_enable = True

            # 保存配置
            global_config.save()
            self.logger.info(f"已将任务 {task_info['id']} 添加到配置")

        except Exception as e:
            self.logger.error(f"更新配置失败: {e}", exc_info=True)

    def _update_config_remove_task(self, timer_info: dict):
        """更新配置 - 删除任务"""
        try:
            device_name = timer_info.get('device_name')
            resource_name = timer_info.get('resource_name')
            task_id = timer_info.get('id')

            device_config = global_config.get_device_config(device_name)
            if not device_config:
                return

            resource = next((r for r in device_config.resources
                             if r.resource_name == resource_name), None)
            if not resource or not resource.schedules:
                return

            # 删除对应的schedule
            resource.schedules = [s for s in resource.schedules if s.task_id != task_id]

            # 如果没有schedule了，禁用schedules_enable
            if not resource.schedules:
                resource.schedules_enable = False

            # 保存配置
            global_config.save()
            self.logger.info(f"已从配置中删除任务 {task_id}")

        except Exception as e:
            self.logger.error(f"删除任务配置失败: {e}", exc_info=True)

    def _update_config_task_status(self, timer_info: dict, enabled: bool):
        """更新配置 - 任务状态"""
        try:
            device_name = timer_info.get('device_name')
            resource_name = timer_info.get('resource_name')
            task_id = timer_info.get('id')

            device_config = global_config.get_device_config(device_name)
            if not device_config:
                return

            resource = next((r for r in device_config.resources
                             if r.resource_name == resource_name), None)
            if not resource or not resource.schedules:
                return

            # 更新对应schedule的enabled状态
            for schedule in resource.schedules:
                if schedule.task_id == task_id:
                    schedule.enabled = enabled
                    break

            # 保存配置
            global_config.save()

        except Exception as e:
            self.logger.error(f"更新任务状态配置失败: {e}", exc_info=True)

    def _update_config_task_settings(self, timer_info: dict, config_scheme: str):
        """更新配置 - 任务设置"""
        try:
            device_name = timer_info.get('device_name')
            resource_name = timer_info.get('resource_name')
            task_id = timer_info.get('id')

            device_config = global_config.get_device_config(device_name)
            if not device_config:
                return

            resource = next((r for r in device_config.resources
                             if r.resource_name == resource_name), None)
            if not resource or not resource.schedules:
                return

            # 更新对应schedule的settings_name
            for schedule in resource.schedules:
                if schedule.task_id == task_id:
                    schedule.settings_name = config_scheme
                    break

            # 保存配置
            global_config.save()

        except Exception as e:
            self.logger.error(f"更新任务设置配置失败: {e}", exc_info=True)

    def _update_config_task_notify(self, timer_info: dict, notify: bool):
        """更新配置 - 通知设置"""
        try:
            device_name = timer_info.get('device_name')
            resource_name = timer_info.get('resource_name')
            task_id = timer_info.get('id')

            device_config = global_config.get_device_config(device_name)
            if not device_config:
                return

            resource = next((r for r in device_config.resources
                             if r.resource_name == resource_name), None)
            if not resource or not resource.schedules:
                return

            # 更新对应schedule的notify
            for schedule in resource.schedules:
                if schedule.task_id == task_id:
                    schedule.notify = notify
                    break

            # 保存配置
            global_config.save()

        except Exception as e:
            self.logger.error(f"更新任务通知配置失败: {e}", exc_info=True)

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

                    # 如果启用了通知，发送通知
                    task_info = self._find_task_by_device_resource(device_name, resource_name, settings_name)
                    if task_info and task_info.get('notify'):
                        from app.utils.notification_manager import notification_manager
                        notification_manager.show_success(
                            f"定时任务已执行",
                            f"设备: {device_name}\n资源: {resource_name}",
                            3000
                        )
                else:
                    self.logger.error(
                        f"提交设备 {device_name} 中资源 {resource_name} 的任务失败 (使用设置 {settings_name})")

            finally:
                # 恢复原始settings_name
                resource.settings_name = original_settings_name

        except Exception as e:
            self.logger.error(f"运行定时任务时出错: {e}", exc_info=True)

    def _find_task_by_device_resource(self, device_name: str, resource_name: str, settings_name: str) -> Optional[dict]:
        """根据设备、资源和设置查找任务"""
        with QMutexLocker(self._mutex):
            for task_info in self._timers.values():
                if (task_info.get('device_name') == device_name and
                        task_info.get('resource_name') == resource_name and
                        task_info.get('settings_name') == settings_name):
                    return task_info
        return None


# 兼容性代码
from core.device_status_manager import device_status_manager


class ScheduledInfoUpdater(QObject):
    """定时任务信息更新器 - 用于兼容旧代码"""

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
                pass
                # device_status_manager.update_scheduled_info(
                #     device_name,
                #     False,
                #     None,
                #     "未启用"
                # )

        except Exception as e:
            self.logger.error(f"更新设备 {device_name} 定时任务信息时出错: {e}")
            # device_status_manager.update_scheduled_info(
            #     device_name,
            #     False,
            #     None,
            #     "更新失败"
            # )

    def update_all_devices(self):
        """更新所有设备的定时任务信息"""
        try:
            all_devices = global_config.get_app_config().devices
            for device in all_devices:
                self.update_device_scheduled_info(device.device_name)
        except Exception as e:
            self.logger.error(f"更新所有设备定时任务信息时出错: {e}")


# 全局实例创建
def init_scheduled_info_updater(scheduled_task_manager):
    """初始化定时任务信息更新器"""
    global scheduled_info_updater
    scheduled_info_updater = ScheduledInfoUpdater(scheduled_task_manager)
    return scheduled_info_updater


# 创建全局实例
from core.tasker_manager import task_manager

scheduled_task_manager = ScheduledTaskManager(task_manager)

# 初始化定时任务信息更新器
scheduled_info_updater = init_scheduled_info_updater(scheduled_task_manager)