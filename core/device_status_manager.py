# -*- coding: UTF-8 -*-
"""
设备状态管理器
作为状态管理的统一管理器，提供UI数据映射
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from app.models.logging.log_manager import log_manager
from core.device_state_machine import SimpleStateManager, DeviceState


@dataclass
class DeviceUIInfo:
    """设备UI显示信息"""
    device_name: str
    state: DeviceState
    state_text: str
    state_color: str
    button_text: str
    button_enabled: bool
    tooltip: str
    progress: int = 0
    error_message: Optional[str] = None
    task_name: Optional[str] = None
    queue_length: int = 0
    is_connected: bool = False
    is_busy: bool = False


class DeviceStatusManager(QObject):
    """
    设备状态管理器
    统一管理所有设备和任务的状态
    """

    # 状态变化信号
    state_changed = Signal(str, DeviceState, DeviceState, dict)  # name, old_state, new_state, context
    ui_info_changed = Signal(str, DeviceUIInfo)  # device_name, ui_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state_managers: Dict[str, SimpleStateManager] = {}
        self._task_managers: Dict[str, SimpleStateManager] = {}  # task_id -> SimpleStateManager
        self._mutex = QMutex()
        self.logger = log_manager.get_app_logger()

        # UI配置映射
        self._ui_config = {
            DeviceState.DISCONNECTED: {
                "text": "离线",
                "color": "#999999",
                "button": "连接",
                "enabled": True,
                "tooltip": "设备未连接"
            },
            DeviceState.CONNECTING: {
                "text": "连接中",
                "color": "#03A9F4",
                "button": "连接中...",
                "enabled": False,
                "tooltip": "正在连接设备"
            },
            DeviceState.CONNECTED: {
                "text": "就绪",
                "color": "#4CAF50",
                "button": "运行",
                "enabled": True,
                "tooltip": "设备就绪"
            },
            DeviceState.UPDATING: {
                "text": "初始化",
                "color": "#FF9800",
                "button": "初始化...",
                "enabled": False,
                "tooltip": "正在初始化agent"
            },
            DeviceState.PREPARING: {
                "text": "准备中",
                "color": "#2196F3",
                "button": "准备中...",
                "enabled": False,
                "tooltip": "准备运行任务"
            },
            DeviceState.WAITING: {
                "text": "等待执行",
                "color": "#9C27B0",
                "button": "取消",
                "enabled": True,
                "tooltip": "任务等待执行"
            },
            DeviceState.RUNNING: {
                "text": "运行中",
                "color": "#2196F3",
                "button": "停止",
                "enabled": True,
                "tooltip": "正在执行任务"
            },
            DeviceState.PAUSED: {
                "text": "已暂停",
                "color": "#607D8B",
                "button": "恢复",
                "enabled": True,
                "tooltip": "任务已暂停"
            },
            DeviceState.COMPLETED: {
                "text": "已完成",
                "color": "#4CAF50",
                "button": "运行",
                "enabled": True,
                "tooltip": "任务成功完成"
            },
            DeviceState.FAILED: {
                "text": "失败",
                "color": "#F44336",
                "button": "重试",
                "enabled": True,
                "tooltip": "任务执行失败"
            },
            DeviceState.CANCELED: {
                "text": "已取消",
                "color": "#FF9800",
                "button": "运行",
                "enabled": True,
                "tooltip": "任务已取消"
            },
            DeviceState.ERROR: {
                "text": "错误",
                "color": "#F44336",
                "button": "重连",
                "enabled": True,
                "tooltip": "设备错误"
            }
        }

    # === 设备状态管理 ===

    def get_or_create_device_manager(self, device_name: str) -> SimpleStateManager:
        """获取或创建设备状态管理器"""
        with QMutexLocker(self._mutex):
            if device_name not in self._state_managers:
                manager = SimpleStateManager(device_name, DeviceState.DISCONNECTED)
                manager.state_changed.connect(self._on_device_state_changed)
                self._state_managers[device_name] = manager
                self.logger.info(f"创建设备状态管理器: {device_name}")
            return self._state_managers[device_name]

    def get_device_manager(self, device_name: str) -> Optional[SimpleStateManager]:
        """获取设备状态管理器"""
        with QMutexLocker(self._mutex):
            return self._state_managers.get(device_name)

    def remove_device_manager(self, device_name: str):
        """移除设备状态管理器"""
        with QMutexLocker(self._mutex):
            if device_name in self._state_managers:
                manager = self._state_managers[device_name]
                manager.state_changed.disconnect(self._on_device_state_changed)
                del self._state_managers[device_name]
                self.logger.info(f"移除设备状态管理器: {device_name}")

    # === 任务状态管理 ===

    def create_task_manager(self, task_id: str, device_name: str) -> SimpleStateManager:
        """为任务创建状态管理器"""
        with QMutexLocker(self._mutex):
            if task_id in self._task_managers:
                self.logger.warning(f"任务状态管理器已存在: {task_id}")
                return self._task_managers[task_id]

            # 修改: 任务的初始状态从 QUEUED 改为 WAITING
            manager = SimpleStateManager(f"task_{task_id}", DeviceState.WAITING)
            manager.update_context(device_name=device_name, task_id=task_id)
            manager.state_changed.connect(self._on_task_state_changed)
            self._task_managers[task_id] = manager
            self.logger.debug(f"创建任务状态管理器: {task_id}")
            return manager

    def get_task_manager(self, task_id: str) -> Optional[SimpleStateManager]:
        """获取任务状态管理器"""
        with QMutexLocker(self._mutex):
            return self._task_managers.get(task_id)

    def remove_task_manager(self, task_id: str):
        """移除任务状态管理器"""
        with QMutexLocker(self._mutex):
            if task_id in self._task_managers:
                manager = self._task_managers[task_id]
                manager.state_changed.disconnect(self._on_task_state_changed)
                del self._task_managers[task_id]
                self.logger.debug(f"移除任务状态管理器: {task_id}")

    def get_device_task_count(self, device_name: str) -> int:
        """获取设备的活动任务数量"""
        with QMutexLocker(self._mutex):
            count = 0
            for manager in self._task_managers.values():
                context = manager.get_context()
                if context.get('device_name') == device_name:
                    # 修改: 将 QUEUED 替换为 WAITING
                    if manager.get_state() in [DeviceState.WAITING, DeviceState.PREPARING,
                                               DeviceState.RUNNING, DeviceState.PAUSED]:
                        count += 1
            return count


    def _on_device_state_changed(self, name: str, old_state: str, new_state: str, context: dict):
        """设备状态变化回调"""
        old_enum = DeviceState(old_state)
        new_enum = DeviceState(new_state)

        # 发送原始状态变化信号
        self.state_changed.emit(name, old_enum, new_enum, context)

        # 生成UI信息
        ui_info = self._create_ui_info(name, new_enum, context)
        self.ui_info_changed.emit(name, ui_info)

    def _on_task_state_changed(self, name: str, old_state: str, new_state: str, context: dict):
        """任务状态变化回调"""
        # 任务状态变化可能影响设备状态
        device_name = context.get('device_name')
        if device_name:
            self._update_device_from_task(device_name, DeviceState(new_state))

    def _update_device_from_task(self, device_name: str, task_state: DeviceState):
        """根据任务状态更新设备状态"""
        device_manager = self.get_device_manager(device_name)
        if not device_manager:
            return

        # 获取设备的所有活动任务数
        task_count = self.get_device_task_count(device_name)
        device_manager.update_context(queue_length=task_count)

        current_device_state = device_manager.get_state()

        # 根据任务状态智能更新设备状态
        if task_state == DeviceState.RUNNING and current_device_state != DeviceState.RUNNING:
            # 有任务开始运行，设备状态改为运行中
            device_manager.set_state(DeviceState.RUNNING)
        elif task_state in [DeviceState.COMPLETED, DeviceState.FAILED, DeviceState.CANCELED]:
            # 任务结束，检查是否还有其他活动任务
            if task_count == 0 and current_device_state == DeviceState.RUNNING:
                # 没有活动任务了，设备回到连接状态
                device_manager.set_state(DeviceState.CONNECTED)

    def _create_ui_info(self, device_name: str, state: DeviceState, context: dict) -> DeviceUIInfo:
        """创建UI显示信息"""
        config = self._ui_config[state]

        return DeviceUIInfo(
            device_name=device_name,
            state=state,
            state_text=config["text"],
            state_color=config["color"],
            button_text=config["button"],
            button_enabled=config["enabled"],
            tooltip=config["tooltip"],
            progress=context.get('progress', 0),
            error_message=context.get('error_message'),
            task_name=context.get('task_name'),
            queue_length=context.get('queue_length', 0),
            is_connected=(state not in [DeviceState.DISCONNECTED, DeviceState.CONNECTING]),
            is_busy=(state in [DeviceState.UPDATING, DeviceState.PREPARING,
                               DeviceState.RUNNING, DeviceState.PAUSED])
        )

    # === 设备操作方法（直接设置状态） ===

    def connect_device(self, device_name: str) -> bool:
        """开始连接设备"""
        manager = self.get_or_create_device_manager(device_name)
        manager.set_state(DeviceState.CONNECTING)
        return True

    def device_connected(self, device_name: str) -> bool:
        """设备连接成功"""
        manager = self.get_device_manager(device_name)
        if manager:
            manager.set_state(DeviceState.CONNECTED)
            return True
        return False

    def device_disconnected(self, device_name: str) -> bool:
        """断开设备"""
        manager = self.get_device_manager(device_name)
        if manager and not manager.is_running_task():
            manager.set_state(DeviceState.DISCONNECTED)
            return True
        return False

    def start_update(self, device_name: str) -> bool:
        """开始更新"""
        manager = self.get_device_manager(device_name)
        if manager:
            manager.set_state(DeviceState.UPDATING)
            return True
        return False

    def update_completed(self, device_name: str, has_pending_task: bool = False) -> bool:
        """更新完成"""
        manager = self.get_device_manager(device_name)
        if manager:
            # 根据是否有待处理任务决定下一个状态
            next_state = DeviceState.PREPARING if has_pending_task else DeviceState.CONNECTED
            manager.set_state(next_state)
            return True
        return False

    def set_device_error(self, device_name: str, error_message: str):
        """设置设备错误"""
        manager = self.get_device_manager(device_name)
        if manager:
            manager.set_state(DeviceState.ERROR, error_message=error_message)

    def set_device_progress(self, device_name: str, progress: int):
        """设置设备进度"""
        manager = self.get_device_manager(device_name)
        if manager:
            manager.set_progress(progress)

    def get_device_state(self, device_name: str) -> Optional[DeviceState]:
        """获取设备状态"""
        manager = self.get_device_manager(device_name)
        return manager.get_state() if manager else None

    def set_device_state(self, device_name: str, state: DeviceState, **context_updates):
        """直接设置设备状态"""
        manager = self.get_or_create_device_manager(device_name)
        manager.set_state(state, **context_updates)

    def get_device_ui_info(self, device_name: str) -> Optional[DeviceUIInfo]:
        """获取设备UI信息"""
        manager = self.get_device_manager(device_name)
        if manager:
            state = manager.get_state()
            context = manager.get_context()
            return self._create_ui_info(device_name, state, context)
        return None

    # === 任务操作方法 ===

    def queue_task(self, task_id: str, device_name: str, task_name: Optional[str] = None) -> SimpleStateManager:
        """将任务加入等待队列"""
        manager = self.create_task_manager(task_id, device_name)
        # 修改: 设置状态为 WAITING
        manager.set_state(DeviceState.WAITING, task_name=task_name)
        return manager

    def start_task(self, task_id: str):
        """开始执行任务"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.RUNNING)

    def pause_task(self, task_id: str):
        """暂停任务"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.PAUSED)

    def resume_task(self, task_id: str):
        """恢复任务"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.RUNNING)

    def complete_task(self, task_id: str):
        """任务完成"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.COMPLETED, progress=100)

    def fail_task(self, task_id: str, error_message: Optional[str] = None):
        """任务失败"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.FAILED, error_message=error_message)

    def cancel_task(self, task_id: str):
        """取消任务"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(DeviceState.CANCELED)

    def set_task_state(self, task_id: str, state: DeviceState, **context_updates):
        """直接设置任务状态"""
        manager = self.get_task_manager(task_id)
        if manager:
            manager.set_state(state, **context_updates)

    def get_task_state(self, task_id: str) -> Optional[DeviceState]:
        """获取任务状态"""
        manager = self.get_task_manager(task_id)
        return manager.get_state() if manager else None

    # === 清理 ===

    def cleanup(self):
        """清理所有状态管理器"""
        with QMutexLocker(self._mutex):
            for manager in self._state_managers.values():
                manager.state_changed.disconnect()
            for manager in self._task_managers.values():
                manager.state_changed.disconnect()
            self._state_managers.clear()
            self._task_managers.clear()
            self.logger.info("所有状态管理器已清理")


# 创建全局实例
device_status_manager = DeviceStatusManager()