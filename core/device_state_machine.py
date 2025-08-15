# -*- coding: UTF-8 -*-
"""
简化的设备和任务状态管理
直接设置状态，无需复杂的状态机转换
"""

from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from PySide6.QtCore import QObject, Signal
from app.models.logging.log_manager import log_manager


class DeviceState(Enum):
    """统一的设备和任务状态枚举"""
    # 设备状态
    DISCONNECTED = "disconnected"  # 设备未连接
    CONNECTING = "connecting"  # 正在连接设备
    CONNECTED = "connected"  # 设备已连接但空闲

    # 任务准备状态
    UPDATING = "updating"  # 正在更新资源
    PREPARING = "preparing"  # 准备运行任务

    # 任务执行状态
    WAITING = "waiting"  # 新增: 等待执行
    RUNNING = "running"  # 正在运行任务
    PAUSED = "paused"  # 任务暂停

    # 完成状态
    COMPLETED = "completed"  # 任务成功完成
    FAILED = "failed"  # 任务失败
    CANCELED = "canceled"  # 任务被取消
    ERROR = "error"  # 设备或任务出错


class SimpleStateManager(QObject):
    """
    简化的状态管理器
    直接管理状态，无需复杂的状态机转换
    """

    # 状态变更信号 (实体名, 旧状态, 新状态, 额外数据)
    state_changed = Signal(str, str, str, dict)

    def __init__(self, name: str, initial_state: DeviceState = DeviceState.DISCONNECTED, parent=None):
        super().__init__(parent)
        self.name = name
        self.logger = log_manager.get_app_logger()

        # 当前状态
        self._current_state = initial_state

        # 状态信息上下文
        self.context: Dict[str, Any] = {
            'name': name,
            'error_message': None,
            'progress': 0,
            'task_id': None,
            'task_name': None,
            'queue_position': 0,
            'queue_length': 0,
            'last_updated': datetime.now(),
            'metadata': {}
        }

        self.logger.info(f"状态管理器已创建: {name}, 初始状态: {initial_state.value}")

    # === 核心方法 ===

    def set_state(self, new_state: DeviceState, **context_updates):
        """
        直接设置状态

        Args:
            new_state: 新的状态
            **context_updates: 要更新的上下文信息
        """
        old_state = self._current_state

        # 如果状态没有变化且没有上下文更新，直接返回
        if old_state == new_state and not context_updates:
            return

        # 更新状态
        self._current_state = new_state

        # 更新上下文
        if context_updates:
            self.context.update(context_updates)

        # 更新时间戳
        self.context['last_updated'] = datetime.now()

        # 根据新状态自动调整某些上下文
        self._auto_adjust_context(new_state)

        # 记录日志
        if old_state != new_state:
            self.logger.info(f"[{self.name}] 状态已变更: {old_state.value} -> {new_state.value}")

        # 发送状态变更信号
        self.state_changed.emit(
            self.name,
            old_state.value,
            new_state.value,
            self.context.copy()
        )

    def get_state(self) -> DeviceState:
        """获取当前状态枚举"""
        return self._current_state

    def get_state_value(self) -> str:
        """获取当前状态值"""
        return self._current_state.value

    # === 上下文管理 ===

    def get_context(self) -> Dict[str, Any]:
        """获取完整的上下文信息"""
        return self.context.copy()

    def update_context(self, **kwargs):
        """
        仅更新上下文信息，不改变状态

        Args:
            **kwargs: 要更新的上下文键值对
        """
        self.context.update(kwargs)
        self.context['last_updated'] = datetime.now()

        # 发送信号（状态不变）
        self.state_changed.emit(
            self.name,
            self._current_state.value,
            self._current_state.value,
            self.context.copy()
        )

    def set_progress(self, progress: int):
        """设置进度（0-100）"""
        self.update_context(progress=min(100, max(0, progress)))

    def set_task_info(self, task_id: str, task_name: Optional[str] = None):
        """设置任务信息"""
        self.update_context(task_id=task_id, task_name=task_name)

    def set_error_message(self, message: str):
        """设置错误消息"""
        self.update_context(error_message=message)

    def clear_error(self):
        """清除错误消息"""
        self.update_context(error_message=None)

    def set_queue_info(self, position: int = 0, length: int = 0):
        """设置队列信息"""
        self.update_context(queue_position=position, queue_length=length)

    # === 状态查询 ===

    def is_connected(self) -> bool:
        """检查设备是否已连接"""
        return self._current_state not in [
            DeviceState.DISCONNECTED,
            DeviceState.CONNECTING
        ]

    def is_idle(self) -> bool:
        """检查是否空闲"""
        return self._current_state == DeviceState.CONNECTED

    def is_busy(self) -> bool:
        """检查是否忙碌"""
        return self._current_state in [
            DeviceState.UPDATING,
            DeviceState.PREPARING,
            DeviceState.RUNNING,
            DeviceState.PAUSED
        ]

    def is_running_task(self) -> bool:
        """检查是否正在运行任务"""
        return self._current_state in [
            DeviceState.PREPARING,
            DeviceState.RUNNING,
            DeviceState.PAUSED
        ]

    # === 私有方法 ===

    def _auto_adjust_context(self, new_state: DeviceState):
        """根据新状态自动调整上下文"""
        # 清理某些状态的错误信息
        if new_state in [DeviceState.CONNECTED, DeviceState.RUNNING]:
            self.context['error_message'] = None

        # 完成状态设置进度为100%
        if new_state == DeviceState.COMPLETED:
            self.context['progress'] = 100

        # 断开连接时清理任务信息
        if new_state == DeviceState.DISCONNECTED:
            self.context['task_id'] = None
            self.context['task_name'] = None
            self.context['progress'] = 0
            self.context['queue_position'] = 0


# 为了兼容性，保留StateMachine别名
StateMachine = SimpleStateManager