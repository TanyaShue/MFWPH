# -*- coding: UTF-8 -*-
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Set
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from app.models.logging.log_manager import log_manager
from core.device_state_machine import DeviceStateMachine, DeviceState

class DeviceStatus(Enum):
    """设备状态枚举"""
    OFFLINE = "offline"  # 设备离线/未启动
    IDLE = "idle"  # 设备就绪
    RUNNING = "running"  # 正在执行任务
    ERROR = "error"  # 错误状态
    STOPPING = "stopping"  # 正在停止
    SCHEDULED = "scheduled"  # 已设置定时任务
    WAITING = "waiting"  # 等待执行
    CONNECTING = "connecting"  # 正在连接


@dataclass
class DeviceStatusInfo:
    """设备状态信息 - 不可变的数据类"""
    device_name: str
    status: DeviceStatus = DeviceStatus.OFFLINE
    is_active: bool = False
    is_running: bool = False
    error_message: Optional[str] = None
    queue_length: int = 0
    current_task_id: Optional[str] = None
    current_task_progress: int = 0

    # 定时任务相关
    has_scheduled_tasks: bool = False
    next_scheduled_time: Optional[datetime] = None
    scheduled_time_text: str = "未启用"

    # 统计信息
    total_tasks_completed: int = 0
    last_task_time: Optional[datetime] = None

    def __eq__(self, other):
        """比较两个状态是否相等"""
        if not isinstance(other, DeviceStatusInfo):
            return False
        return (self.device_name == other.device_name and
                self.status == other.status and
                self.is_active == other.is_active and
                self.is_running == other.is_running and
                self.error_message == other.error_message and
                self.queue_length == other.queue_length and
                self.has_scheduled_tasks == other.has_scheduled_tasks and
                self.scheduled_time_text == other.scheduled_time_text)


class DeviceStatusManager(QObject):
    """
    统一的设备状态管理器
    使用状态机管理设备状态，只负责存储和分发状态
    """
    
    # 状态变化信号 - 只有当状态真正改变时才发送
    status_changed = Signal(str, DeviceStatusInfo)  # device_name, new_status_info
    
    # 状态机状态变化信号
    state_machine_changed = Signal(str, str, str)  # device_name, old_state, new_state
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._device_status: Dict[str, DeviceStatusInfo] = {}
        self._device_state_machines: Dict[str, DeviceStateMachine] = {}
        self._mutex = QMutex()
        self.logger = log_manager.get_app_logger()
        
        # 状态到UI配置的映射（纯数据，不在状态对象中）
        self._ui_config = {
            DeviceStatus.IDLE: {
                "color": "#4CAF50",
                "tooltip": "设备就绪",
                "button_text": "运行",
                "button_enabled": True
            },
            DeviceStatus.RUNNING: {
                "color": "#2196F3",
                "tooltip": "正在执行任务",
                "button_text": "停止",
                "button_enabled": True
            },
            DeviceStatus.ERROR: {
                "color": "#F44336",
                "tooltip": "错误",
                "button_text": "运行",
                "button_enabled": True
            },
            DeviceStatus.STOPPING: {
                "color": "#FF9800",
                "tooltip": "正在停止",
                "button_text": "停止中...",
                "button_enabled": False
            },
            DeviceStatus.SCHEDULED: {
                "color": "#9C27B0",
                "tooltip": "已设置定时任务",
                "button_text": "运行",
                "button_enabled": True
            },
            DeviceStatus.WAITING: {
                "color": "#607D8B",
                "tooltip": "等待执行",
                "button_text": "停止",
                "button_enabled": True
            },
            DeviceStatus.OFFLINE: {
                "color": "#999999",
                "tooltip": "设备离线",
                "button_text": "运行",
                "button_enabled": True
            },
            DeviceStatus.CONNECTING: {
                "color": "#03A9F4",
                "tooltip": "正在连接",
                "button_text": "连接中...",
                "button_enabled": False
            },
        }
        
        # 状态机状态到设备状态的映射
        self._state_mapping = {
            DeviceState.DISCONNECTED.value: DeviceStatus.OFFLINE,
            DeviceState.CONNECTING.value: DeviceStatus.CONNECTING,
            DeviceState.CONNECTED.value: DeviceStatus.IDLE,
            DeviceState.UPDATING.value: DeviceStatus.RUNNING,
            DeviceState.PREPARING.value: DeviceStatus.RUNNING,
            DeviceState.RUNNING.value: DeviceStatus.RUNNING,
            DeviceState.PAUSED.value: DeviceStatus.RUNNING,
            DeviceState.ERROR.value: DeviceStatus.ERROR
        }

    def get_ui_config(self, status: DeviceStatus) -> dict:
        """获取状态对应的UI配置"""
        return self._ui_config.get(status, self._ui_config[DeviceStatus.OFFLINE])

    def _get_or_create_state_machine(self, device_name: str) -> DeviceStateMachine:
        """获取或创建设备状态机"""
        if device_name not in self._device_state_machines:
            self._device_state_machines[device_name] = DeviceStateMachine(device_name)
            # 连接状态机的信号
            self._device_state_machines[device_name].state_changed.connect(self._on_state_machine_changed)
        return self._device_state_machines[device_name]

    def _on_state_machine_changed(self, device_name: str, old_state: str, new_state: str):
        """状态机状态变化回调"""
        self.logger.debug(f"状态机状态变化: {device_name} {old_state} -> {new_state}")
        
        # 发送状态机状态变化信号
        self.state_machine_changed.emit(device_name, old_state, new_state)
        
        # 更新设备状态信息
        self._update_status_from_state_machine(device_name, new_state)

    def _update_status_from_state_machine(self, device_name: str, state_machine_state: str):
        """根据状态机状态更新设备状态"""
        # 映射状态机状态到设备状态
        device_status = self._state_mapping.get(state_machine_state, DeviceStatus.OFFLINE)
        
        # 获取状态机的完整状态信息
        state_machine = self._get_or_create_state_machine(device_name)
        state_info = state_machine.get_state_info()
        
        # 检查是否处于运行状态（包括准备、更新、运行、暂停等状态）
        is_running = state_machine_state in [
            DeviceState.UPDATING.value,
            DeviceState.PREPARING.value,
            DeviceState.RUNNING.value,
            DeviceState.PAUSED.value
        ]
        
        # 更新设备状态
        updates = {
            "status": device_status,
            "is_active": (device_status != DeviceStatus.OFFLINE),
            "is_running": is_running,  # 使用正确的运行状态判断
            "error_message": state_info.get('error_message')
        }
        
        # 如果有任务信息，也更新
        if state_info.get('task_id'):
            updates["current_task_id"] = state_info.get('task_id')
            
        if state_info.get('progress') is not None:
            updates["current_task_progress"] = state_info.get('progress')
        
        self.update_status(device_name, **updates)

    def register_device(self, device_name: str) -> DeviceStatusInfo:
        """注册设备并返回初始状态"""
        with QMutexLocker(self._mutex):
            # 创建状态机
            self._get_or_create_state_machine(device_name)
            
            if device_name not in self._device_status:
                self._device_status[device_name] = DeviceStatusInfo(device_name=device_name)
                self.logger.debug(f"注册设备状态: {device_name}")
            return self._device_status[device_name]

    def get_device_status(self, device_name: str) -> Optional[DeviceStatusInfo]:
        """获取设备状态信息（返回副本，保证不可变）"""
        with QMutexLocker(self._mutex):
            status = self._device_status.get(device_name)
            if status:
                # 返回数据类的副本，确保外部无法修改内部状态
                import dataclasses
                return dataclasses.replace(status)
            return None

    def update_status(self, device_name: str, **kwargs) -> bool:
        """
        更新设备状态
        返回 True 如果状态发生了变化
        """
        with QMutexLocker(self._mutex):
            current_status = self._device_status.get(device_name)
            if not current_status:
                current_status = DeviceStatusInfo(device_name=device_name)
                self._device_status[device_name] = current_status

            # 创建新的状态对象（不可变）
            import dataclasses
            new_status = dataclasses.replace(current_status, **kwargs)

            # 只有当状态真正改变时才更新和发送信号
            if new_status != current_status:
                self._device_status[device_name] = new_status
                self.logger.debug(f"设备 {device_name} 状态已更新")
                # 发送信号（在锁外面）
                self.status_changed.emit(device_name, new_status)
                return True

            return False

    def update_device_status(self, device_name: str, status: DeviceStatus,
                             error_message: Optional[str] = None):
        """便捷方法：更新设备基本状态"""
        self.update_status(
            device_name,
            status=status,
            error_message=error_message,
            is_active=(status != DeviceStatus.OFFLINE),
            is_running=(status == DeviceStatus.RUNNING)
        )

    def update_scheduled_info(self, device_name: str, has_scheduled: bool,
                              next_time: Optional[datetime] = None, time_text: str = "未启用"):
        """更新定时任务信息"""
        updates = {
            "has_scheduled_tasks": has_scheduled,
            "next_scheduled_time": next_time,
            "scheduled_time_text": time_text
        }

        # 如果有定时任务且设备离线，更新状态为SCHEDULED
        current_status = self.get_device_status(device_name)
        if current_status and has_scheduled and current_status.status == DeviceStatus.OFFLINE:
            updates["status"] = DeviceStatus.SCHEDULED

        self.update_status(device_name, **updates)

    def update_progress(self, device_name: str, progress: int):
        """更新任务进度"""
        self.update_status(device_name, current_task_progress=progress)

    def update_queue_info(self, device_name: str, queue_length: int):
        """更新队列信息"""
        self.update_status(device_name, queue_length=queue_length)

    def batch_update_queue_info(self, queue_info: Dict[str, int]):
        """批量更新队列信息"""
        for device_name, queue_length in queue_info.items():
            self.update_queue_info(device_name, queue_length)

    def on_task_completed(self, device_name: str):
        """任务完成时的状态更新"""
        current = self.get_device_status(device_name)
        if not current:
            return

        updates = {
            "total_tasks_completed": current.total_tasks_completed + 1,
            "last_task_time": datetime.now(),
            "current_task_id": None,
            "current_task_progress": 0
        }

        # 根据队列决定新状态
        if current.queue_length > 0:
            updates["status"] = DeviceStatus.WAITING
        else:
            updates["status"] = DeviceStatus.IDLE
            updates["is_running"] = False

        self.update_status(device_name, **updates)

    def clear_device(self, device_name: str):
        """清除设备状态"""
        with QMutexLocker(self._mutex):
            if device_name in self._device_status:
                del self._device_status[device_name]
                self.logger.debug(f"清除设备状态: {device_name}")
            if device_name in self._device_state_machines:
                del self._device_state_machines[device_name]
                self.logger.debug(f"清除设备状态机: {device_name}")

    # 状态机操作方法
    def connect_device(self, device_name: str):
        """连接设备"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('connect'):
            state_machine.trigger('connect')

    def device_connected(self, device_name: str):
        """设备连接成功"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('connected'):
            state_machine.trigger('connected')

    def start_update(self, device_name: str):
        """开始更新资源"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('start_update'):
            state_machine.trigger('start_update')

    def update_completed(self, device_name: str):
        """更新完成"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('update_completed'):
            state_machine.trigger('update_completed')

    def prepare_task(self, device_name: str):
        """准备任务"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('prepare_task'):
            state_machine.trigger('prepare_task')

    def start_task(self, device_name: str):
        """开始任务"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('start_task'):
            state_machine.trigger('start_task')

    def task_completed(self, device_name: str):
        """任务完成"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('task_completed'):
            state_machine.trigger('task_completed')

    def pause_task(self, device_name: str):
        """暂停任务"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('pause_task'):
            state_machine.trigger('pause_task')

    def resume_task(self, device_name: str):
        """恢复任务"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('resume_task'):
            state_machine.trigger('resume_task')

    def set_error(self, device_name: str, error_message: str):
        """设置错误状态"""
        state_machine = self._get_or_create_state_machine(device_name)
        state_machine.set_error(error_message)

    def disconnect_device(self, device_name: str):
        """断开设备连接"""
        state_machine = self._get_or_create_state_machine(device_name)
        if state_machine.can('disconnect'):
            state_machine.trigger('disconnect')

    def set_progress(self, device_name: str, progress: int):
        """设置任务进度"""
        state_machine = self._get_or_create_state_machine(device_name)
        state_machine.set_progress(progress)

    def set_task_info(self, device_name: str, task_id: Optional[str] = None, task_name: Optional[str] = None):
        """设置任务信息"""
        state_machine = self._get_or_create_state_machine(device_name)
        state_machine.set_task_info(task_id, task_name)


# 导入需要的模块
import dataclasses

# 创建全局实例
device_status_manager = DeviceStatusManager()