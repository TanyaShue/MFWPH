# scheduled_task_manager.py
import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal, QTimer, QMutexLocker, QRecursiveMutex
from qasync import asyncSlot

from app.models.config.app_config import ScheduleTask
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.tasker_manager import task_manager


class ScheduledTaskManager(QObject):
    """统一的定时任务管理器，直接管理AppConfig中的全局定时任务。"""

    task_added = Signal(dict)
    task_removed = Signal(str)
    task_modified = Signal(str, dict)
    task_triggered = Signal(str, str, str, bool)
    task_status_changed = Signal(str, bool)

    def __init__(self, tasker_manager: 'TaskerManager', parent=None):
        super().__init__(parent)
        self._tasker_manager = tasker_manager
        self._timers: Dict[str, Dict] = {}
        self._mutex = QRecursiveMutex()
        self.logger = log_manager.get_app_logger()
        self.task_triggered.connect(self._on_scheduled_task_triggered)
        self.logger.info("ScheduledTaskManager 初始化完成")

    async def _save_config_async(self):
        """异步保存配置到磁盘，避免阻塞UI线程"""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, global_config.save_all_configs)
            self.logger.debug("全局配置已异步保存到磁盘。")
        except Exception as e:
            self.logger.error(f"异步保存配置失败: {e}", exc_info=True)

    def initialize_from_config(self) -> List[dict]:
        all_tasks_for_ui = []
        app_config = global_config.get_app_config()
        self.logger.info(f"开始从全局配置加载定时任务，共 {len(app_config.schedule_tasks)} 个任务")

        for task in app_config.schedule_tasks:
            task_info = self._create_task_info_from_task(task)
            if task.enabled:
                self._setup_timer(task_info)
            with QMutexLocker(self._mutex):
                self._timers[task.schedule_id] = task_info
            all_tasks_for_ui.append(task_info)

        # 按设定时间 time 升序排序
        all_tasks_for_ui.sort(key=lambda x: x.get('time', '00:00:00'))

        self.logger.info(f"从配置中加载了 {len(all_tasks_for_ui)} 个定时任务")
        return all_tasks_for_ui

    def get_tasks_for_device(self, device_name: str) -> List[dict]:
        with QMutexLocker(self._mutex):
            return [
                task_info.copy() for task_info in self._timers.values()
                if task_info.get('device_name') == device_name
            ]

    @asyncSlot(dict, result=str)
    async def add_task(self, task_info: dict) -> str:
        with QMutexLocker(self._mutex):
            new_task = ScheduleTask.from_ui_format(
                task_info,
                task_info['device_name'],
                task_info['resource_name']
            )
            self.logger.debug(f"正在添加新任务: {new_task}")

            app_config = global_config.get_app_config()
            app_config.schedule_tasks.append(new_task)

            internal_task_info = self._create_task_info_from_task(new_task)
            if new_task.enabled:
                self._setup_timer(internal_task_info)
            self._timers[new_task.schedule_id] = internal_task_info

        await self._save_config_async()
        self.task_added.emit(internal_task_info)
        self.logger.info(f"添加定时任务成功: ID={new_task.schedule_id}, 设备={new_task.device_name}")
        return new_task.schedule_id

    @asyncSlot(str, result=bool)
    async def remove_task(self, schedule_id: str) -> bool:
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers: return False
            task_info = self._timers.pop(schedule_id)
            if 'timer' in task_info and task_info.get('timer'):
                task_info['timer'].stop()
                task_info['timer'].deleteLater()

            app_config = global_config.get_app_config()
            app_config.schedule_tasks = [t for t in app_config.schedule_tasks if t.schedule_id != schedule_id]

        await self._save_config_async()
        self.task_removed.emit(schedule_id)
        self.logger.info(f"删除定时任务成功: ID={schedule_id}")
        return True

    @asyncSlot(str, bool, result=bool)
    async def toggle_task_status(self, schedule_id: str, enabled: bool) -> bool:
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers: return False
            task_info = self._timers[schedule_id]
            new_status_str = '活动' if enabled else '暂停'
            if task_info['status'] == new_status_str: return True

            self.logger.debug(f"任务 {schedule_id} 状态切换: {task_info['status']} -> {new_status_str}")
            task_info['status'] = new_status_str

            if enabled:
                self._setup_timer(task_info)
            elif 'timer' in task_info and task_info.get('timer'):
                task_info['timer'].stop()

            self._update_task_field_in_config(schedule_id, 'enabled', enabled, save=False)

        await self._save_config_async()
        self.task_status_changed.emit(schedule_id, enabled)
        self.logger.info(f"任务 {schedule_id} 状态已更改为: {new_status_str}")
        return True

    @asyncSlot(dict, result=bool)
    async def update_task(self, task_info: dict) -> bool:
        schedule_id = task_info.get('id')
        if not schedule_id:
            self.logger.error("更新任务失败：缺少任务ID")
            return False

        updated_task_obj = None
        new_internal_info = None
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                self.logger.error(f"更新任务失败：找不到任务ID {schedule_id}")
                return False

            old_task_info = self._timers[schedule_id]
            self.logger.debug(f"开始更新任务 {schedule_id}...")

            try:
                app_config = global_config.get_app_config()
                task_found = False
                for i, task in enumerate(app_config.schedule_tasks):
                    if task.schedule_id == schedule_id:
                        updated_task_obj = ScheduleTask.from_ui_format(
                            task_info,
                            task_info['device_name'],
                            task_info['resource_name']
                        )
                        updated_task_obj.schedule_id = schedule_id
                        app_config.schedule_tasks[i] = updated_task_obj
                        task_found = True
                        break

                if not task_found:
                    self.logger.warning(f"尝试更新配置失败，未找到任务ID: {schedule_id}")
                    return False
            except Exception as e:
                self.logger.error(f"更新配置对象时出错: {e}", exc_info=True)
                return False

            new_internal_info = self._create_task_info_from_task(updated_task_obj)
            self._timers[schedule_id] = new_internal_info

            if new_internal_info['status'] == '活动':
                self._setup_timer(new_internal_info)
            elif 'timer' in old_task_info and old_task_info.get('timer'):
                old_task_info['timer'].stop()

        await self._save_config_async()
        if new_internal_info:
            self.task_modified.emit(schedule_id, new_internal_info)
        self.logger.info(f"任务 {schedule_id} 已成功更新")
        return True

    def _setup_timer(self, task_info: dict):
        schedule_id = task_info['id']
        with QMutexLocker(self._mutex):
            if schedule_id in self._timers and 'timer' in self._timers[schedule_id] and self._timers[schedule_id].get(
                    'timer'):
                self._timers[schedule_id]['timer'].stop()
                self._timers[schedule_id]['timer'].deleteLater()

            timer = QTimer(self)
            task_info['timer'] = timer

        next_run = self._calculate_next_run_time(task_info)
        if not next_run:
            self.logger.warning(
                f"无法为任务 {schedule_id} 计算下次运行时间（可能是每周任务未选择日期），任务将转为暂停状态。")
            asyncio.ensure_future(self.toggle_task_status(schedule_id, False))
            return

        now = datetime.now()
        delay_ms = max(0, int((next_run - now).total_seconds() * 1000))

        timer.timeout.connect(lambda: self._run_task_and_reschedule(schedule_id))
        task_info['next_run'] = next_run

        timer.setSingleShot(True)
        timer.start(delay_ms)
        self.logger.info(
            f"定时任务 {schedule_id} ({task_info['device_name']}) 已设置，将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 首次运行 (延迟: {delay_ms} ms)")

    def _run_task_and_reschedule(self, schedule_id: str):
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers: return
            task_info = self._timers[schedule_id]

            self.logger.info(
                f"触发定时任务 {schedule_id}：设备='{task_info['device_name']}', 资源='{task_info['resource_name']}'")
            self.task_triggered.emit(
                task_info['device_name'],
                task_info['resource_name'],
                task_info.get('config_scheme', ''),
                task_info.get('force_stop', False)
            )

            if task_info.get('schedule_type') == '单次执行':
                self.logger.info(f"单次任务 {schedule_id} 已执行，状态将变为暂停。")
                asyncio.ensure_future(self.toggle_task_status(schedule_id, False))
            else:
                self.logger.debug(f"周期性任务 {schedule_id} 已执行，正在安排下一次运行。")
                self._setup_timer(task_info)

    def _calculate_next_run_time(self, task_info: dict) -> Optional[datetime]:
        try:
            time_str = task_info.get('time', '00:00:00')
            schedule_type = task_info.get('schedule_type', '每日执行')
            target_time = time.fromisoformat(time_str)
            now = datetime.now()

            self.logger.debug(
                f"开始为任务 {task_info['id']} 计算下次时间。当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %A')}, 目标时间: {target_time}, 类型: {schedule_type}")

            if schedule_type in ['每日执行', '单次执行']:
                target_datetime = now.replace(hour=target_time.hour, minute=target_time.minute,
                                              second=target_time.second, microsecond=0)
                if target_datetime <= now:
                    target_datetime += timedelta(days=1)
                return target_datetime

            elif schedule_type == '每周执行':
                week_days = task_info.get('week_days', [])
                if not week_days: return None
                day_map = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6}
                target_weekdays = {day_map[day] for day in week_days if day in day_map}
                if not target_weekdays: return None

                self.logger.debug(f"每周任务，目标星期: {target_weekdays} (周一=0)")

                for i in range(8):
                    next_day_candidate = now + timedelta(days=i)
                    if next_day_candidate.weekday() in target_weekdays:
                        target_datetime = datetime.combine(next_day_candidate.date(), target_time)
                        if target_datetime > now:
                            self.logger.debug(
                                f"找到下一个匹配时间点: {target_datetime.strftime('%Y-%m-%d %H:%M:%S %A')}")
                            return target_datetime
                return None
            else:
                return None
        except Exception as e:
            self.logger.error(f"计算下次运行时间时出错: {e}", exc_info=True)
            return None

    @asyncSlot(str, str, str, bool)
    async def _on_scheduled_task_triggered(self, device_name: str, resource_name: str, settings_name: str, force_stop: bool):
        self.logger.info(f"处理任务触发：设备 {device_name}，资源 {resource_name}，设置 {settings_name}")
        try:
            device_config = global_config.get_device_config(device_name)
            if not device_config:
                self.logger.error(f"找不到设备配置: {device_name}")
                return
            resource = next((r for r in device_config.resources if r.resource_name == resource_name), None)
            if not resource:
                self.logger.error(f"在设备 {device_name} 中找不到资源 {resource_name}")
                return

            # 为了确保任务使用指定的配置方案，我们临时修改资源配置
            original_settings_name = resource.settings_name
            try:
                # 如果配置了强制停止，先杀掉当前设备的执行器
                if force_stop:
                    self.logger.warning(f"定时任务配置了强制停止。正在停止设备 {device_name} 的所有任务...")
                    await self._tasker_manager.stop_device_processing(device_name)
                    await asyncio.sleep(2)

                resource.settings_name = settings_name
                runtime_config = global_config.get_runtime_configs_for_resource(resource_name, device_name)

                if not runtime_config:
                    self.logger.error(f"无法获取运行时配置 (设备 {device_name}, 资源 {resource_name})")
                    return

                # 【修改】移除 create_executor 调用，直接提交任务
                # TaskerManager 的 submit_task 现在会处理所有启动逻辑
                await self._tasker_manager.submit_task(device_name, runtime_config)
                self.logger.info(f"成功将定时任务加入队列 (设备 {device_name}, 资源 {resource_name})")

            finally:
                # 无论成功与否，都恢复原始的配置方案
                resource.settings_name = original_settings_name
        except Exception as e:
            self.logger.error(f"运行定时任务时出错: {e}", exc_info=True)

    def _create_task_info_from_task(self, task: ScheduleTask) -> dict:
        task_info = {
            'id': task.schedule_id,
            'device_name': task.device_name,
            'resource_name': task.resource_name,
            'schedule_type': task.get_schedule_type_display(),
            'time': task.schedule_time,
            'config_scheme': task.settings_name or '默认配置',
            'notify': task.notify,
            'force_stop': task.force_stop,
            'status': '活动' if task.enabled else '暂停',
        }
        if task.schedule_type == 'weekly' and task.week_days:
            task_info['week_days'] = task.week_days
        return task_info

    def _update_task_field_in_config(self, schedule_id: str, field_name: str, value: Any, save: bool = True):
        try:
            app_config = global_config.get_app_config()
            task_found = False
            for task in app_config.schedule_tasks:
                if task.schedule_id == schedule_id:
                    setattr(task, field_name, value)
                    task_found = True
                    break
            if task_found and save:
                # This sync save is now only called if needed, but async is preferred.
                global_config.save_all_configs()
            elif not task_found:
                self.logger.warning(f"尝试更新配置失败，未找到任务ID: {schedule_id}")
        except Exception as e:
            self.logger.error(f"更新配置中任务 {schedule_id} 的字段 '{field_name}' 时失败: {e}", exc_info=True)


scheduled_task_manager = ScheduledTaskManager(task_manager)