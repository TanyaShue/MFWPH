# -*- coding: UTF-8 -*-
"""
设备状态管理器
作为状态机的统一管理器，提供UI数据映射
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from app.models.logging.log_manager import log_manager
from core.device_state_machine import StateMachine, DeviceState


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
    统一管理所有设备和任务的状态机
    """

    # 状态变化信号
    state_changed = Signal(str, DeviceState, DeviceState, dict)  # name, old_state, new_state, context
    ui_info_changed = Signal(str, DeviceUIInfo)  # device_name, ui_info

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state_machines: Dict[str, StateMachine] = {}
        self._task_machines: Dict[str, StateMachine] = {}  # task_id -> StateMachine
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
                "text": "更新中",
                "color": "#FF9800",
                "button": "更新中...",
                "enabled": False,
                "tooltip": "正在更新资源"
            },
            DeviceState.PREPARING: {
                "text": "准备中",
                "color": "#2196F3",
                "button": "准备中...",
                "enabled": False,
                "tooltip": "准备运行任务"
            },
            DeviceState.QUEUED: {
                "text": "排队中",
                "color": "#9C27B0",
                "button": "取消",
                "enabled": True,
                "tooltip": "任务排队中"
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

    # === 设备状态机管理 ===

    def get_or_create_device_machine(self, device_name: str) -> StateMachine:
        """获取或创建设备状态机"""
        with QMutexLocker(self._mutex):
            if device_name not in self._state_machines:
                machine = StateMachine(device_name, DeviceState.DISCONNECTED)
                machine.state_changed.connect(self._on_device_state_changed)
                self._state_machines[device_name] = machine
                self.logger.info(f"创建设备状态机: {device_name}")
            return self._state_machines[device_name]

    def get_device_machine(self, device_name: str) -> Optional[StateMachine]:
        """获取设备状态机"""
        with QMutexLocker(self._mutex):
            return self._state_machines.get(device_name)

    def remove_device_machine(self, device_name: str):
        """移除设备状态机"""
        with QMutexLocker(self._mutex):
            if device_name in self._state_machines:
                machine = self._state_machines[device_name]
                machine.state_changed.disconnect(self._on_device_state_changed)
                del self._state_machines[device_name]
                self.logger.info(f"移除设备状态机: {device_name}")

    # === 任务状态机管理 ===

    def create_task_machine(self, task_id: str, device_name: str) -> StateMachine:
        """为任务创建状态机"""
        with QMutexLocker(self._mutex):
            if task_id in self._task_machines:
                self.logger.warning(f"任务状态机已存在: {task_id}")
                return self._task_machines[task_id]

            machine = StateMachine(f"task_{task_id}", DeviceState.QUEUED)
            machine.update_context(device_name=device_name, task_id=task_id)
            machine.state_changed.connect(self._on_task_state_changed)
            self._task_machines[task_id] = machine
            self.logger.debug(f"创建任务状态机: {task_id}")
            return machine

    def get_task_machine(self, task_id: str) -> Optional[StateMachine]:
        """获取任务状态机"""
        with QMutexLocker(self._mutex):
            return self._task_machines.get(task_id)

    def remove_task_machine(self, task_id: str):
        """移除任务状态机"""
        with QMutexLocker(self._mutex):
            if task_id in self._task_machines:
                machine = self._task_machines[task_id]
                machine.state_changed.disconnect(self._on_task_state_changed)
                del self._task_machines[task_id]
                self.logger.debug(f"移除任务状态机: {task_id}")

    def get_device_task_count(self, device_name: str) -> int:
        """获取设备的任务数量"""
        with QMutexLocker(self._mutex):
            count = 0
            for machine in self._task_machines.values():
                context = machine.get_context()
                if context.get('device_name') == device_name:
                    if machine.get_state() in [DeviceState.QUEUED, DeviceState.PREPARING,
                                               DeviceState.RUNNING, DeviceState.PAUSED]:
                        count += 1
            return count

    # === 回调处理 ===

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
        device_machine = self.get_device_machine(device_name)
        if not device_machine:
            return

        # 获取设备的所有活动任务数
        task_count = self.get_device_task_count(device_name)
        device_machine.update_context(queue_length=task_count)

        # 如果有任务在运行，更新设备状态
        if task_state == DeviceState.RUNNING and device_machine.get_state() != DeviceState.RUNNING:
            device_machine.safe_trigger('start_task')
        elif task_state in [DeviceState.COMPLETED, DeviceState.FAILED, DeviceState.CANCELED]:
            # 检查是否还有其他任务
            if task_count == 0 and device_machine.get_state() == DeviceState.RUNNING:
                device_machine.safe_trigger('task_success')
                device_machine.safe_trigger('reset_to_connected')

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


    def connect_device(self, device_name: str) -> bool:
        """连接设备"""
        machine = self.get_or_create_device_machine(device_name)
        return machine.safe_trigger('connect')

    def device_connected(self, device_name: str) -> bool:
        """设备连接成功"""
        machine = self.get_device_machine(device_name)
        return machine.safe_trigger('connection_success') if machine else False

    def device_disconnected(self, device_name: str) -> bool:
        """断开设备"""
        machine = self.get_device_machine(device_name)
        return machine.safe_trigger('disconnect') if machine else False

    def start_update(self, device_name: str) -> bool:
        """开始更新"""
        machine = self.get_device_machine(device_name)
        return machine.safe_trigger('start_update') if machine else False

    def update_completed(self, device_name: str) -> bool:
        """更新完成"""
        machine = self.get_device_machine(device_name)
        return machine.safe_trigger('update_success') if machine else False

    def set_device_error(self, device_name: str, error_message: str):
        """设置设备错误"""
        machine = self.get_device_machine(device_name)
        if machine:
            machine.set_error_message(error_message)
            machine.safe_trigger('set_error')

    def set_device_progress(self, device_name: str, progress: int):
        """设置设备进度"""
        machine = self.get_device_machine(device_name)
        if machine:
            machine.set_progress(progress)

    def get_device_state(self, device_name: str) -> Optional[DeviceState]:
        """获取设备状态"""
        machine = self.get_device_machine(device_name)
        return machine.get_state() if machine else None

    def get_device_ui_info(self, device_name: str) -> Optional[DeviceUIInfo]:
        """获取设备UI信息"""
        machine = self.get_device_machine(device_name)
        if machine:
            state = machine.get_state()
            context = machine.get_context()
            return self._create_ui_info(device_name, state, context)
        return None

    def cleanup(self):
        """清理所有状态机"""
        with QMutexLocker(self._mutex):
            for machine in self._state_machines.values():
                machine.state_changed.disconnect()
            for machine in self._task_machines.values():
                machine.state_changed.disconnect()
            self._state_machines.clear()
            self._task_machines.clear()
            self.logger.info("所有状态机已清理")


# 创建全局实例
device_status_manager = DeviceStatusManager()