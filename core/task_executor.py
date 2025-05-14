# -*- coding: UTF-8 -*-
import importlib.util
import os
import subprocess
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, List

import maa
from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QRunnable, QMutexLocker, QRecursiveMutex, Qt
from maa.agent_client import AgentClient
from maa.controller import AdbController, Win32Controller
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager


class TaskStatus(Enum):
    """任务执行状态枚举"""
    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 执行失败
    CANCELED = "canceled"  # 已取消


class Task:
    """统一任务表示"""

    def __init__(self, task_data: RunTimeConfigs):
        self.id = f"task_{id(self)}"  # 唯一任务ID
        self.data = task_data  # 任务数据
        self.status = TaskStatus.PENDING  # 任务状态
        self.created_at = datetime.now()  # 创建时间
        self.started_at = None  # 开始时间
        self.completed_at = None  # 完成时间
        self.error = None  # 错误信息
        self.runner = None  # 任务执行器引用


class DeviceStatus(Enum):
    """设备状态枚举"""
    IDLE = "idle"  # 空闲状态
    RUNNING = "running"  # 运行状态
    SCHEDULED = "scheduled"  # 已设置定时任务状态
    WAITING = "waiting"  # 等待定时任务执行
    ERROR = "error"  # 错误状态
    STOPPING = "stopping"  # 正在停止
    DISCONNECTED = "disconnected"  # 未连接状态
    CONNECTING = "connecting"  # 连接中


class DeviceState(QObject):
    """设备状态类"""
    status_changed = Signal(str)  # 状态变化信号
    error_occurred = Signal(str)  # 错误信号
    scheduled_task_added = Signal(str)  # 添加定时任务信号
    scheduled_task_removed = Signal(str)  # 移除定时任务信号
    scheduled_task_modified = Signal(str)  # 修改定时任务信号

    def __init__(self):
        super().__init__()
        self.status = DeviceStatus.IDLE  # 初始状态为空闲
        self.created_at = datetime.now()  # 创建时间
        self.last_active = datetime.now()  # 最后活动时间
        self.current_task = None  # 当前任务
        self.error = None  # 错误信息
        self.scheduled_tasks = {}  # 定时任务信息 {task_id: task_info}
        self.next_scheduled_run = None  # 下一次定时任务执行时间

    def update_status(self, status: DeviceStatus, error=None):
        """更新设备状态"""
        self.status = status
        self.last_active = datetime.now()
        self.status_changed.emit(status.value)
        if error:
            self.error = error
            self.error_occurred.emit(error)

    def add_scheduled_task(self, task_id: str, task_info: dict):
        """添加定时任务"""
        self.scheduled_tasks[task_id] = task_info
        self.scheduled_task_added.emit(task_id)
        self._update_next_scheduled_run()

        # 如果设备空闲且有定时任务，将状态更新为已设置定时任务
        if self.status == DeviceStatus.IDLE and self.scheduled_tasks:
            self.update_status(DeviceStatus.SCHEDULED)

    def remove_scheduled_task(self, task_id: str):
        """移除定时任务"""
        if task_id in self.scheduled_tasks:
            del self.scheduled_tasks[task_id]
            self.scheduled_task_removed.emit(task_id)
            self._update_next_scheduled_run()

            # 如果没有定时任务且设备状态为已设置定时任务，则将状态更新为空闲
            if not self.scheduled_tasks and self.status == DeviceStatus.SCHEDULED:
                self.update_status(DeviceStatus.IDLE)

    def modify_scheduled_task(self, task_id: str, task_info: dict):
        """修改定时任务"""
        # 如果需要修改现有任务ID对应的信息
        if task_id in self.scheduled_tasks:
            # 更新任务信息
            self.scheduled_tasks[task_id] = task_info
            # 更新下一次运行时间
            self._update_next_scheduled_run()
            # 发送修改信号
            self.scheduled_task_modified.emit(task_id)
        # 如果是新ID替换旧ID的情况
        elif 'old_task_id' in task_info and task_info['old_task_id'] in self.scheduled_tasks:
            old_task_id = task_info['old_task_id']
            # 删除旧ID的记录
            del self.scheduled_tasks[old_task_id]
            # 移除old_task_id字段，避免冗余存储
            if 'old_task_id' in task_info:
                del task_info['old_task_id']
            # 添加新ID的记录
            self.scheduled_tasks[task_id] = task_info
            # 更新下一次运行时间
            self._update_next_scheduled_run()
            # 发送修改信号
            self.scheduled_task_modified.emit(task_id)
        else:
            # 如果找不到对应的任务，则作为新任务添加
            self.add_scheduled_task(task_id, task_info)

    def _update_next_scheduled_run(self):
        """更新下一次定时任务执行时间"""
        if not self.scheduled_tasks:
            self.next_scheduled_run = None
            return

        # 找出所有定时任务中最早的执行时间
        next_runs = [task_info.get('next_run') for task_info in self.scheduled_tasks.values()
                     if task_info.get('next_run')]
        if next_runs:
            self.next_scheduled_run = min(next_runs)
        else:
            self.next_scheduled_run = None

    def get_info(self) -> Dict:
        """获取设备状态的详细信息"""
        info = {
            'status': self.status.value,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'last_active': self.last_active.strftime('%Y-%m-%d %H:%M:%S'),
            'current_task': self.current_task.id if self.current_task else None,
            'error': self.error,
            'scheduled_tasks_count': len(self.scheduled_tasks),
            'has_scheduled_tasks': bool(self.scheduled_tasks),
            'next_scheduled_run': self.next_scheduled_run.strftime(
                '%Y-%m-%d %H:%M:%S') if self.next_scheduled_run else None
        }
        return info

    def get_scheduled_tasks_info(self) -> List[Dict]:
        """获取设备所有定时任务的信息"""
        tasks_info = []
        for task_id, info in self.scheduled_tasks.items():
            task_info = {
                'id': task_id,
                'device_name': info.get('device_name'),
                'resource_name': info.get('resource_name'),
                'settings_name': info.get('settings_name'),
                'time': info.get('time'),
                'next_run': info.get('next_run').strftime('%Y-%m-%d %H:%M:%S') if info.get('next_run') else 'Unknown',
                'type': info.get('type', 'unknown')
            }
            tasks_info.append(task_info)
        return tasks_info

class TaskExecutor(QObject):
    # 核心信号定义
    task_started = Signal(str)  # 任务开始信号
    task_completed = Signal(str, object)  # 任务完成信号
    task_failed = Signal(str, str)  # 任务失败信号
    task_canceled = Signal(str)  # 任务取消信号
    progress_updated = Signal(str, int)  # 任务进度更新信号
    executor_started = Signal()  # 执行器启动信号
    executor_stopped = Signal()  # 执行器停止信号
    task_queued = Signal(str)  # 任务入队信号
    process_next_task_signal = Signal()  # 触发下一个任务处理的信号
    scheduled_task_added = Signal(str, dict)  # 定时任务添加信号
    scheduled_task_removed = Signal(str)  # 定时任务移除信号

    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.agent_identifier = None
        self.agent = None
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logs(self.device_name)
        self.device_config = device_config
        self.resource_path: Optional[str] = None

        # 根据设备类型选择不同的控制器
        if device_config.device_type == DeviceType.ADB:
            # ADB控制器
            adb_config = device_config.controller_config
            self._controller = AdbController(
                adb_config.adb_path,
                adb_config.address,
                adb_config.screencap_methods,
                adb_config.input_methods,
                adb_config.config,
                agent_path=adb_config.agent_path,
                notification_handler=adb_config.notification_handler
            )
        elif device_config.device_type == DeviceType.WIN32:
            # Win32控制器
            win32_config = device_config.controller_config
            self._controller = Win32Controller(
                win32_config.hWnd,
                notification_handler=win32_config.notification_handler
            )
        else:
            raise ValueError(f"不支持的设备类型: {device_config.device_type}")

        # Device state management
        self.state = DeviceState()
        self._tasker: Optional[Tasker] = Tasker()

        # Use global thread pool
        self.thread_pool = QThreadPool.globalInstance()

        # Mutex and status control
        self._active = False
        self._mutex = QRecursiveMutex()

        # Task management
        self._running_task = None
        self._task_queue = []

        self.logger = log_manager.get_device_logger(device_config.device_name)
        # Get app logger for common operations
        self.app_logger = log_manager.get_app_logger()

        # Signal connections
        self.task_completed.connect(self._handle_task_completed)
        self.task_failed.connect(self._handle_task_failed)
        self.process_next_task_signal.connect(self._process_next_task, Qt.QueuedConnection)
        self.scheduled_task_added.connect(self._handle_scheduled_task_added)
        self.scheduled_task_removed.connect(self._handle_scheduled_task_removed)

    def start(self):
        """Start task executor"""
        with QMutexLocker(self._mutex):
            if self._active:
                return True

            try:
                self._active = True
                self.state.update_status(DeviceStatus.IDLE)
                self.logger.debug(f"任务执行器 {self.device_name} 已启动")
                self.executor_started.emit()
                return True
            except Exception as e:
                error_msg = f"启动任务执行器失败: {e}"
                self.state.update_status(DeviceStatus.ERROR, error_msg)
                self.logger.error(error_msg)
                return False

    def _initialize_resources(self, resource_path: str) -> bool:
        """Initialize MAA resources"""
        try:
            self.resource_path = resource_path
            self.resource = Resource()
            self.resource.post_bundle(resource_path).wait()
            self.logger.debug(f"资源初始化成功: {resource_path}")
            return True
        except Exception as e:
            error_msg = f"资源初始化失败: {e}"
            self.logger.error(error_msg)
            raise

    @Slot(str, dict)
    def _handle_scheduled_task_added(self, task_id, task_info):
        """处理定时任务添加"""
        with QMutexLocker(self._mutex):
            self.state.add_scheduled_task(task_id, task_info)
            self.logger.debug(f"设备 {self.device_name} 添加定时任务 {task_id}")

    @Slot(str)
    def _handle_scheduled_task_removed(self, task_id):
        """处理定时任务移除"""
        with QMutexLocker(self._mutex):
            self.state.remove_scheduled_task(task_id)
            self.logger.debug(f"设备 {self.device_name} 移除定时任务 {task_id}")

    def add_scheduled_task(self, task_id: str, task_info: dict):
        """添加定时任务"""
        with QMutexLocker(self._mutex):
            self.scheduled_task_added.emit(task_id, task_info)

    def remove_scheduled_task(self, task_id: str):
        """移除定时任务"""
        with QMutexLocker(self._mutex):
            self.scheduled_task_removed.emit(task_id)

    @Slot()
    def _process_next_task(self):
        """Process the next task in the queue"""
        with QMutexLocker(self._mutex):
            # Check executor status and task queue
            if not self._active or self._running_task or not self._task_queue:
                if not self._task_queue and self._active and not self._running_task:
                    # 如果有定时任务，设为SCHEDULED，否则设为IDLE
                    if self.state.scheduled_tasks:
                        self.state.update_status(DeviceStatus.SCHEDULED)
                    else:
                        self.state.update_status(DeviceStatus.IDLE)
                    self.state.current_task = None
                return

            task = self._task_queue.pop(0)
            self._running_task = task
            current_dir = os.getcwd()
            Toolkit.init_option(os.path.join(current_dir, "assets"))

            # Initialize resources and controller
            if self.resource_path != task.data.resource_path:
                self._initialize_resources(task.data.resource_path)

            if self._controller:
                self._controller.post_connection().wait()

            self.resource.clear_custom_action()
            self.resource.clear_custom_recognition()

            self._tasker.bind(resource=self.resource, controller=self._controller)


            if self.create_agent():
                print(f"agent 初始化成功")

            # Create and start the task runner
            runner = TaskRunner(task, self)
            runner.setAutoDelete(True)
            self.thread_pool.start(runner)

            # Update device status
            self.state.update_status(DeviceStatus.RUNNING)
            self.state.current_task = task
            self.logger.debug(f"设备 {self.device_name} 开始执行任务 {task.id}")

    def create_agent(self) -> bool:
        """Create and start MAA Agent process"""
        try:
            # Ensure we have a running task
            if not self._running_task:
                self.logger.error("Cannot create agent: No running task")
                return False

            # Get resource configuration
            from app.models.config.global_config import global_config
            resource_config = global_config.get_resource_config(self._running_task.data.resource_name)

            if not resource_config:
                self.logger.error(f"Resource config not found for {self._running_task.data.resource_name}")
                return False

            custom_path = resource_config.custom_path
            custom_params = resource_config.custom_prams  # Note: This field has a typo in the original code

            # Create agent client if not exists
            if not self.agent:
                self.agent = AgentClient()
                self.agent.bind(self.resource)

            # Create socket identifier if not exists
            if not self.agent_identifier:
                self.agent_identifier = self.agent.identifier()
                if not self.agent_identifier:
                    self.logger.error("Failed to create agent socket")
                    return False

            # Resource path is the directory containing the resource files
            resource_dir = self._running_task.data.resource_path

            # Build the command with parameters
            cmd = ["python", custom_path]

            # Add custom parameters if provided
            if custom_params:
                cmd.extend(custom_params.split())

            # Add socket ID parameter
            cmd.extend(["-id", self.agent_identifier])

            self.logger.debug(f"Starting Agent process with command: {' '.join(cmd)} in directory {resource_dir}")

            # Start the Agent process with pipe redirection - removed bufsize parameter
            # Prepare creation flags based on the platform

            creation_flags = subprocess.CREATE_NO_WINDOW

            self.agent_process = subprocess.Popen(
                cmd,
                cwd=resource_dir,  # Set working directory to resource path
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Binary mode for output handling
                creationflags=creation_flags  # Hide console window on Windows
            )
            # Start threads to capture and log output
            self._start_output_capture_threads()

            # Wait briefly for the process to start
            time.sleep(1)

            # Check if process started correctly
            if self.agent_process.poll() is not None:
                # Process terminated prematurely
                error_msg = f"Agent process failed to start with exit code: {self.agent_process.returncode}"
                self.logger.error(error_msg)
                return False

            # Now connect to the agent
            connection_result = self.agent.connect()
            if not connection_result:
                self.logger.error("Failed to connect to agent")
                self._terminate_agent_process()
                return False

            self.logger.debug("Agent connected successfully")

            return self.agent._api_properties_initialized

        except Exception as e:
            error_msg = f"Agent initialization error: {str(e)}"
            self.logger.error(error_msg)
            self._terminate_agent_process()
            return False

    def _start_output_capture_threads(self):
        """Start threads to capture and log subprocess output"""
        import threading

        # Flag to signal threads to stop
        self._stop_output_capture = False

        # Function to read from a pipe and log it
        def log_output(pipe, prefix):
            try:
                for line in iter(lambda: pipe.readline(), b''):
                    if self._stop_output_capture:
                        break
                    if line:
                        try:
                            # Try UTF-8 first with error handling
                            decoded_line = line.decode('utf-8', errors='replace')
                            self.logger.debug(f"[Agent {prefix}] {decoded_line.rstrip()}")
                        except Exception as e:
                            # If decoding fails, log the error and continue
                            self.logger.warning(f"Error decoding Agent output: {e}")
            except Exception as e:
                self.logger.error(f"Error in output capture thread: {e}")
            finally:
                pipe.close()

        # Create and start stdout thread
        self.stdout_thread = threading.Thread(
            target=log_output,
            args=(self.agent_process.stdout, 'stdout'),
            daemon=True
        )
        self.stdout_thread.start()

        # Create and start stderr thread
        self.stderr_thread = threading.Thread(
            target=log_output,
            args=(self.agent_process.stderr, 'stderr'),
            daemon=True
        )
        self.stderr_thread.start()

    def _terminate_agent_process(self):
        """Terminate the agent process if it exists"""
        if hasattr(self, 'agent_process') and self.agent_process:
            try:
                # Signal output capture threads to stop
                if hasattr(self, '_stop_output_capture'):
                    self._stop_output_capture = True

                self.logger.debug("Terminating agent process")
                self.agent_process.terminate()

                # Wait for process to terminate
                try:
                    self.agent_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if process doesn't terminate
                    self.logger.warning("Agent process did not terminate, forcing kill")
                    self.agent_process.kill()

                # Wait for output threads to finish (with timeout)
                if hasattr(self, 'stdout_thread') and self.stdout_thread.is_alive():
                    self.stdout_thread.join(timeout=1)
                if hasattr(self, 'stderr_thread') and self.stderr_thread.is_alive():
                    self.stderr_thread.join(timeout=1)

                self.agent_process = None
                self.logger.debug("Agent process terminated")
            except Exception as e:
                self.logger.error(f"Error terminating agent process: {e}")
    @Slot(str, object)
    def _handle_task_completed(self, task_id):
        """Task completion handler"""
        with QMutexLocker(self._mutex):
            if self._running_task and self._running_task.id == task_id:
                self.logger.debug(f"任务 {task_id} 完成")
                self._running_task = None

                # 更新设备状态 - 如果有定时任务，设为SCHEDULED，否则设为IDLE
                if self.state.scheduled_tasks:
                    self.state.update_status(DeviceStatus.SCHEDULED)
                else:
                    self.state.update_status(DeviceStatus.IDLE)

                self.process_next_task_signal.emit()

    @Slot(str, str)
    def _handle_task_failed(self, task_id, error):
        """Task failure handler"""
        with QMutexLocker(self._mutex):
            if self._running_task and self._running_task.id == task_id:
                self.logger.error(f"任务 {task_id} 失败: {error}")
                self._running_task = None

                # 更新设备状态为错误
                self.state.update_status(DeviceStatus.ERROR, error)

                self.process_next_task_signal.emit()

    def submit_task(self, task_data: RunTimeConfigs | list[RunTimeConfigs]) -> str | list[str]:
        """Submit task to execution queue

        If task_data is a single RunTimeConfigs, returns the task id (str),
        If task_data is a list, creates a task for each config and returns a list of task ids.
        """
        with QMutexLocker(self._mutex):
            if not self._active:
                error_msg = "任务执行器未运行"
                self.logger.error(error_msg)
                raise RuntimeError(error_msg)

            task_ids = []
            # If the input is a list, create tasks for each config
            if isinstance(task_data, list):
                for data in task_data:
                    task = Task(data)
                    self._task_queue.append(task)
                    self.task_queued.emit(task.id)
                    self.logger.debug(f"任务 {task.id} 已提交到设备 {self.device_name} 队列")
                    task_ids.append(task.id)
            else:
                task = Task(task_data)
                self._task_queue.append(task)
                self.task_queued.emit(task.id)
                self.logger.debug(f"任务 {task.id} 已提交到设备 {self.device_name} 队列")
                task_ids.append(task.id)

            # 如果设备空闲/有定时任务但没有运行中任务，状态改为WAITING
            if not self._running_task and (
                    self.state.status == DeviceStatus.IDLE or self.state.status == DeviceStatus.SCHEDULED):
                self.state.update_status(DeviceStatus.WAITING)

            # If no task is currently running, trigger task processing
            if not self._running_task:
                self.process_next_task_signal.emit()

            # Return a single id if there's only one task, otherwise return the id list
            return task_ids[0] if len(task_ids) == 1 else task_ids

    def stop(self):
        """Stop task executor"""
        with QMutexLocker(self._mutex):
            if not self._active:
                return

            self.logger.debug(f"正在停止任务执行器 {self.device_name}")
            self._active = False
            self.state.update_status(DeviceStatus.STOPPING)

            # Terminate the agent process if it exists
            self._terminate_agent_process()

            # Cancel all tasks in the queue
            for task in self._task_queue:
                task.status = TaskStatus.CANCELED
                self.task_canceled.emit(task.id)
                self.logger.debug(f"任务 {task.id} 已取消")
            self._task_queue.clear()

            # 清除定时任务信息
            self.state.scheduled_tasks.clear()
            self.state.next_scheduled_run = None

            self.logger.debug(f"任务执行器 {self.device_name} 已停止")
            self.executor_stopped.emit()

    def get_state(self):
        """Get the current executor state"""
        with QMutexLocker(self._mutex):
            return self.state

    def get_queue_length(self):
        """Get the number of tasks waiting in the queue"""
        with QMutexLocker(self._mutex):
            return len(self._task_queue)


class TaskRunner(QRunnable):
    """Task runner, run in QThreadPool"""

    def __init__(self, task: Task, executor: TaskExecutor):
        super().__init__()
        self.task = task
        self.executor = executor
        self.tasker = executor._tasker
        self.canceled = False
        self.task.runner = self
        self.device_name = executor.device_name
        self.logger = executor.logger

    def run(self):
        """Run the task"""
        self.task.status = TaskStatus.RUNNING
        self.task.started_at = datetime.now()
        self.executor.task_started.emit(self.task.id)

        self.logger.debug(f"开始执行任务 {self.task.id}")

        try:
            # Check if already canceled
            if self.canceled:
                self.task.status = TaskStatus.CANCELED
                self.logger.debug(f"任务 {self.task.id} 已取消")
                self.executor.task_canceled.emit(self.task.id)
                return

            # Execute the task
            result = self.execute_task(self.task.data)

            # Task completed successfully
            self.task.status = TaskStatus.COMPLETED
            self.task.completed_at = datetime.now()
            self.logger.debug(f"任务 {self.task.id} 成功完成")
            self.executor.task_completed.emit(self.task.id, result)

        except Exception as e:
            if self.canceled:
                self.task.status = TaskStatus.CANCELED
                self.logger.debug(f"任务 {self.task.id} 已取消")
                self.executor.task_canceled.emit(self.task.id)
            else:
                # Task execution failed
                self.task.status = TaskStatus.FAILED
                self.task.error = str(e)
                self.task.completed_at = datetime.now()
                self.logger.error(f"任务 {self.task.id} 失败: {e}")
                self.executor.task_failed.emit(self.task.id, str(e))

    def execute_task(self, task_data):
        """Method to execute specific task"""
        # Execute all tasks in the task list
        self.logger.info(f"执行任务列表，共 {len(task_data.task_list)} 个子任务")

        for i, task in enumerate(task_data.task_list):
            self.logger.info(f"执行子任务 {i + 1}/{len(task_data.task_list)}: {task.task_entry}")
            self.tasker.post_task(task.task_entry, task.pipeline_override).wait()
            self.logger.info(f"子任务 {i + 1} 完成")

        # Send progress update signal
        self.executor.progress_updated.emit(self.task.id, 100)

        # Simple delay to ensure task has time to execute
        time.sleep(0.5)

        return {"result": "success", "data": task_data}