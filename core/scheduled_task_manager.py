# scheduled_task_manager.py - 重构版本
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal, QTimer, QMutexLocker, QRecursiveMutex
from qasync import asyncSlot

# 直接使用新的 ScheduleTask 模型
from app.models.config.app_config import ScheduleTask
from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from core.tasker_manager import task_manager


class ScheduledTaskManager(QObject):
    """统一的定时任务管理器，直接管理AppConfig中的全局定时任务。"""

    # 信号定义
    task_added = Signal(dict)  # 任务添加信号(task_info)
    task_removed = Signal(str)  # 任务删除信号(schedule_id)
    task_modified = Signal(str, dict)  # 任务修改信号(schedule_id, task_info)
    task_triggered = Signal(str, str, str)  # 任务触发信号(device_name, resource_name, settings_name)
    task_status_changed = Signal(str, bool)  # 任务状态改变信号(schedule_id, enabled)

    def __init__(self, tasker_manager: 'TaskerManager', parent=None):
        super().__init__(parent)
        self._tasker_manager = tasker_manager
        self._timers: Dict[str, Dict] = {}  # 定时器存储字典 {schedule_id: task_info}
        self._mutex = QRecursiveMutex()
        self.logger = log_manager.get_app_logger()

        # 连接信号
        self.task_triggered.connect(self._on_scheduled_task_triggered)

        self.logger.info("ScheduledTaskManager 初始化完成")

    def initialize_from_config(self) -> List[dict]:
        """从AppConfig初始化所有定时任务，返回任务列表供UI显示"""
        all_tasks_for_ui = []
        app_config = global_config.get_app_config()
        self.logger.info(f"开始从全局配置加载定时任务，共 {len(app_config.schedule_tasks)} 个任务")

        for task in app_config.schedule_tasks:
            # 创建任务信息
            task_info = self._create_task_info_from_task(task)

            # 如果任务启用，设置定时器
            if task.enabled:
                self._setup_timer(task_info)

            # 保存任务信息到内存
            with QMutexLocker(self._mutex):
                self._timers[task.schedule_id] = task_info

            # 添加到返回列表
            all_tasks_for_ui.append(task_info)

        self.logger.info(f"从配置中加载了 {len(all_tasks_for_ui)} 个定时任务")
        return all_tasks_for_ui

    def add_task(self, task_info: dict) -> str:
        """添加新的定时任务"""
        with QMutexLocker(self._mutex):
            # 从UI数据创建ScheduleTask对象，这将自动生成一个ID
            new_task = ScheduleTask.from_ui_format(
                task_info,
                task_info['device_name'],
                task_info['resource_name']
            )

            # 更新配置
            self._update_config_add_task(new_task)

            # 将新任务转换为内部格式
            internal_task_info = self._create_task_info_from_task(new_task)

            # 设置定时器
            if new_task.enabled:
                self._setup_timer(internal_task_info)

            # 保存任务信息
            self._timers[new_task.schedule_id] = internal_task_info

            # 发出信号
            self.task_added.emit(internal_task_info)

            self.logger.info(f"添加定时任务: ID={new_task.schedule_id}, 设备={new_task.device_name}, "
                             f"资源={new_task.resource_name}")
            return new_task.schedule_id

    def remove_task(self, schedule_id: str) -> bool:
        """删除定时任务"""
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                return False

            task_info = self._timers.pop(schedule_id)

            # 停止定时器
            if 'timer' in task_info:
                task_info['timer'].stop()
                task_info['timer'].deleteLater()

            # 更新配置
            self._update_config_remove_task(schedule_id)

            # 发出信号
            self.task_removed.emit(schedule_id)

            self.logger.info(f"删除定时任务: {schedule_id}")
            return True

    def toggle_task_status(self, schedule_id: str, enabled: bool) -> bool:
        """切换任务状态（启用/禁用）"""
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                return False

            task_info = self._timers[schedule_id]
            new_status_str = '活动' if enabled else '暂停'

            if task_info['status'] == new_status_str:
                return True  # 状态未改变

            task_info['status'] = new_status_str

            if enabled:
                self._setup_timer(task_info)
            elif 'timer' in task_info:
                task_info['timer'].stop()

            # 更新配置
            self._update_config_task_status(schedule_id, enabled)

            # 发出信号
            self.task_status_changed.emit(schedule_id, enabled)

            self.logger.info(f"任务 {schedule_id} 状态更改为: {new_status_str}")
            return True

    def update_task_config(self, schedule_id: str, config_scheme: str) -> bool:
        """更新任务的配置方案"""
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                return False

            task_info = self._timers[schedule_id]
            task_info['config_scheme'] = config_scheme

            # 更新配置
            self._update_config_task_settings(schedule_id, config_scheme)

            # 发出信号
            self.task_modified.emit(schedule_id, task_info)
            return True

    def update_task_notify(self, schedule_id: str, notify: bool) -> bool:
        """更新任务的通知设置"""
        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                return False

            task_info = self._timers[schedule_id]
            task_info['notify'] = notify

            # 更新配置
            self._update_config_task_notify(schedule_id, notify)

            # 发出信号
            self.task_modified.emit(schedule_id, task_info)
            return True

    def get_all_tasks(self) -> List[dict]:
        """获取所有任务信息供UI显示"""
        with QMutexLocker(self._mutex):
            # 直接返回值，因为self._timers中的格式就是UI所需的格式
            return list(self._timers.values())

    def stop_all_scheduled_tasks(self) -> None:
        """停止所有定时任务"""
        with QMutexLocker(self._mutex):
            for task_info in self._timers.values():
                if 'timer' in task_info:
                    task_info['timer'].stop()
                    task_info['timer'].deleteLater()

            timer_count = len(self._timers)
            self._timers.clear()
            self.logger.info(f"已停止所有 {timer_count} 个定时任务")

    def _create_task_info_from_task(self, task: ScheduleTask) -> dict:
        """从ScheduleTask对象创建用于内部管理和UI显示的字典"""
        task_info = {
            'id': task.schedule_id,
            'device_name': task.device_name,
            'resource_name': task.resource_name,
            'schedule_type': task.get_schedule_type_display(),
            'time': task.schedule_time,
            'config_scheme': task.settings_name or '默认配置',
            'notify': task.notify,
            'status': '活动' if task.enabled else '暂停',
        }
        if task.schedule_type == 'weekly' and task.week_days:
            task_info['week_days'] = task.week_days
        return task_info

    def _setup_timer(self, task_info: dict):
        """为指定的任务信息设置定时器"""
        schedule_id = task_info['id']

        # 如果已存在定时器，先停止并删除
        if schedule_id in self._timers and 'timer' in self._timers[schedule_id]:
            old_timer = self._timers[schedule_id]['timer']
            old_timer.stop()
            old_timer.deleteLater()

        timer = QTimer(self)
        time_str = task_info.get('time', '00:00:00')
        try:
            parts = list(map(int, time_str.split(':')))
            hours, minutes, seconds = parts[0], parts[1], parts[2] if len(parts) > 2 else 0
        except (ValueError, IndexError) as e:
            self.logger.error(f"无法解析时间 '{time_str}': {e}，任务ID: {schedule_id}")
            return

        next_run = self._calculate_next_run_time(hours, minutes, seconds)
        now = datetime.now()
        delay_ms = int((next_run - now).total_seconds() * 1000)

        # 如果延迟为负（时间已过），计算第二天的延迟
        if delay_ms <= 0:
            next_run += timedelta(days=1)
            delay_ms = int((next_run - now).total_seconds() * 1000)

        # 绑定触发事件
        device_name = task_info['device_name']
        resource_name = task_info['resource_name']
        settings_name = task_info.get('config_scheme', '')

        timer.timeout.connect(
            lambda dn=device_name, rn=resource_name, sn=settings_name: self.task_triggered.emit(dn, rn, sn)
        )

        task_info['timer'] = timer
        task_info['next_run'] = next_run

        # 定义首次运行的逻辑
        def first_run_and_schedule_next():
            with QMutexLocker(self._mutex):
                if schedule_id not in self._timers:
                    return  # 任务可能已被删除

                # 触发任务
                self.task_triggered.emit(device_name, resource_name, settings_name)

                # 如果是周期性任务，设置下一次运行
                if task_info.get('schedule_type') != '单次执行':
                    # 重新计算下一次运行时间
                    next_run_time = self._calculate_next_run_time(hours, minutes, seconds)
                    task_info['next_run'] = next_run_time
                    delay = int((next_run_time - datetime.now()).total_seconds() * 1000)
                    if delay <= 0: delay += 24 * 60 * 60 * 1000  # 确保是未来的时间
                    timer.start(delay)
                else:
                    # 单次任务，从配置中禁用它
                    self.toggle_task_status(schedule_id, False)

        # 启动首次运行的单次定时器
        QTimer.singleShot(delay_ms, first_run_and_schedule_next)
        self.logger.info(f"定时任务 {schedule_id} 已设置，将在 {next_run.strftime('%Y-%m-%d %H:%M:%S')} 首次运行")

    def _calculate_next_run_time(self, hours: int, minutes: int, seconds: int = 0) -> datetime:
        """计算下一个最近的运行时间点"""
        now = datetime.now()
        target_time = now.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
        if target_time <= now:
            target_time += timedelta(days=1)
        return target_time

    def _update_config_add_task(self, new_task: ScheduleTask):
        """更新配置 - 添加任务"""
        try:
            app_config = global_config.get_app_config()
            app_config.schedule_tasks.append(new_task)
            global_config.save()
            self.logger.info(f"已将任务 {new_task.schedule_id} 添加到全局配置")
        except Exception as e:
            self.logger.error(f"更新配置以添加任务时失败: {e}", exc_info=True)

    def _update_config_remove_task(self, schedule_id: str):
        """更新配置 - 删除任务"""
        try:
            app_config = global_config.get_app_config()
            app_config.schedule_tasks = [t for t in app_config.schedule_tasks if t.schedule_id != schedule_id]
            global_config.save()
            self.logger.info(f"已从全局配置中删除任务 {schedule_id}")
        except Exception as e:
            self.logger.error(f"更新配置以删除任务时失败: {e}", exc_info=True)

    def _update_config_task_status(self, schedule_id: str, enabled: bool):
        """更新配置 - 任务状态"""
        self._update_task_field_in_config(schedule_id, 'enabled', enabled)

    def _update_config_task_settings(self, schedule_id: str, config_scheme: str):
        """更新配置 - 任务设置"""
        self._update_task_field_in_config(schedule_id, 'settings_name', config_scheme)

    def _update_config_task_notify(self, schedule_id: str, notify: bool):
        """更新配置 - 通知设置"""
        self._update_task_field_in_config(schedule_id, 'notify', notify)

    def _update_task_field_in_config(self, schedule_id: str, field_name: str, value: Any):
        """通用方法，用于更新配置中特定任务的单个字段"""
        try:
            app_config = global_config.get_app_config()
            task_found = False
            for task in app_config.schedule_tasks:
                if task.schedule_id == schedule_id:
                    setattr(task, field_name, value)
                    task_found = True
                    break

            if task_found:
                global_config.save()
            else:
                self.logger.warning(f"尝试更新配置失败，未找到任务ID: {schedule_id}")
        except Exception as e:
            self.logger.error(f"更新配置中任务 {schedule_id} 的字段 '{field_name}' 时失败: {e}", exc_info=True)

    @asyncSlot(str, str, str)
    async def _on_scheduled_task_triggered(self, device_name: str, resource_name: str, settings_name: str):
        """处理定时任务触发事件"""
        self.logger.info(f"定时任务触发：设备 {device_name}，资源 {resource_name}，设置 {settings_name}")
        try:
            device_config = global_config.get_device_config(device_name)
            if not device_config:
                self.logger.error(f"找不到设备配置: {device_name}")
                return

            resource = next((r for r in device_config.resources if r.resource_name == resource_name), None)
            if not resource:
                self.logger.error(f"在设备 {device_name} 中找不到资源 {resource_name}")
                return

            original_settings_name = resource.settings_name
            try:
                # 临时将资源的设置方案切换为任务指定的方案
                resource.settings_name = settings_name
                runtime_config = global_config.get_runtime_configs_for_resource(resource_name, device_name)

                if not runtime_config:
                    self.logger.error(
                        f"无法获取设备 {device_name} 中资源 {resource_name} 的运行时配置 (使用设置 {settings_name})")
                    return

                await self._tasker_manager.create_executor(device_config)
                result = await self._tasker_manager.submit_task(device_name, runtime_config)

                if result:
                    self.logger.info(
                        f"成功提交设备 {device_name} 中资源 {resource_name} 的任务 (使用设置 {settings_name})，任务ID: {result}")
                    # 检查是否需要发送通知
                    task_info = self._find_task_by_details(device_name, resource_name, settings_name)
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
                # 恢复资源原始的设置方案
                resource.settings_name = original_settings_name
        except Exception as e:
            self.logger.error(f"运行定时任务时出错: {e}", exc_info=True)

    def _find_task_by_details(self, device_name: str, resource_name: str, settings_name: str) -> Optional[dict]:
        """根据设备、资源和设置查找内存中的任务信息"""
        with QMutexLocker(self._mutex):
            for task_info in self._timers.values():
                if (task_info.get('device_name') == device_name and
                        task_info.get('resource_name') == resource_name and
                        task_info.get('config_scheme') == settings_name):
                    return task_info
        return None

    def update_task(self, task_info: dict) -> bool:
        """
        全面更新一个定时任务。
        此方法用于处理编辑后的保存操作。
        """
        schedule_id = task_info.get('id')
        if not schedule_id:
            self.logger.error("更新任务失败：缺少任务ID")
            return False

        with QMutexLocker(self._mutex):
            if schedule_id not in self._timers:
                self.logger.error(f"更新任务失败：找不到任务ID {schedule_id}")
                return False

            # 1. 更新配置
            try:
                app_config = global_config.get_app_config()
                task_updated = False
                for i, task in enumerate(app_config.schedule_tasks):
                    if task.schedule_id == schedule_id:
                        # 从UI格式更新任务对象
                        updated_task = ScheduleTask.from_ui_format(
                            task_info,
                            task_info['device_name'],
                            task_info['resource_name']
                        )
                        updated_task.schedule_id = schedule_id  # 保持ID不变
                        app_config.schedule_tasks[i] = updated_task
                        task_updated = True
                        break

                if task_updated:
                    global_config.save()
                else:
                    self.logger.warning(f"尝试更新配置失败，未找到任务ID: {schedule_id}")
                    return False
            except Exception as e:
                self.logger.error(f"更新配置文件时出错: {e}", exc_info=True)
                return False

            # 2. 更新内存中的任务信息
            # 注意：task_info的键名可能与内部使用的不完全一致，需要转换
            internal_task_info = self._timers[schedule_id]
            internal_task_info.update({
                'schedule_type': task_info.get('schedule_type'),
                'time': task_info.get('time'),
                'config_scheme': task_info.get('config_scheme'),
                'notify': task_info.get('notify', False),
                'week_days': task_info.get('week_days', [])
            })

            # 3. 重置定时器以应用更改
            if internal_task_info['status'] == '活动':
                self._setup_timer(internal_task_info)

            # 4. 发出信号
            self.task_modified.emit(schedule_id, internal_task_info)
            self.logger.info(f"任务 {schedule_id} 已成功更新")
            return True


# 创建全局单例
scheduled_task_manager = ScheduledTaskManager(task_manager)