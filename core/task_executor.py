# -*- coding: UTF-8 -*-
import importlib.util
import os
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QRunnable, QMutexLocker, QRecursiveMutex, Qt
from maa.controller import AdbController, Win32Controller
from maa.custom_action import CustomAction
from maa.custom_recognition import CustomRecognition
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import RunTimeConfigs
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
    IDLE = "idle"                   # 空闲状态
    RUNNING = "running"             # 运行状态
    ERROR = "error"                 # 错误状态
    STOPPING = "stopping"           # 正在停止
    DISCONNECTED = "disconnected"   # 未连接状态
    CONNECTING = "connecting"       # 连接中


class DeviceState(QObject):
    """设备状态类"""
    status_changed = Signal(str)  # 状态变化信号
    error_occurred = Signal(str)  # 错误信号

    def __init__(self):
        super().__init__()
        self.status = DeviceStatus.IDLE  # 初始状态为空闲
        self.created_at = datetime.now()  # 创建时间
        self.last_active = datetime.now()  # 最后活动时间
        self.current_task = None  # 当前任务
        self.error = None  # 错误信息

    def update_status(self, status: DeviceStatus, error=None):
        """更新设备状态"""
        self.status = status
        self.last_active = datetime.now()
        self.status_changed.emit(status.value)
        if error:
            self.error = error
            self.error_occurred.emit(error)


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
    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_name = device_config.device_name
        self.logger=log_manager.get_device_logs(self.device_name)
        self.device_config = device_config
        self.device_config = device_config
        self.resource_path: Optional[str] = None

        # Initialize ADB controller
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

    def start(self):
        """Start task executor"""
        with QMutexLocker(self._mutex):
            if self._active:
                return True

            try:
                self._active = True
                self.state.update_status(DeviceStatus.IDLE)
                self.logger.debug( f"任务执行器 {self.device_name} 已启动")
                self.executor_started.emit()
                return True
            except Exception as e:
                error_msg = f"启动任务执行器失败: {e}"
                self.state.update_status(DeviceStatus.ERROR, error_msg)
                self.logger.error( error_msg)
                return False

    def _initialize_resources(self, resource_path: str) -> bool:
        """Initialize MAA resources"""
        try:
            self.resource_path = resource_path
            self.resource = Resource()
            self.resource.post_bundle(resource_path).wait()
            self.logger.debug( f"资源初始化成功: {resource_path}")
            return True
        except Exception as e:
            error_msg = f"资源初始化失败: {e}"
            self.logger.error( error_msg)
            raise

    def load_custom_objects(self, custom_dir):
        if not os.path.exists(custom_dir):
            self.logger.debug( f"自定义文件夹 {custom_dir} 不存在")
            return

        if not os.listdir(custom_dir):
            self.logger.debug( f"自定义文件夹 {custom_dir} 为空")
            return

        # Traverse module type folders
        for module_type, base_class in [("custom_actions", CustomAction),
                                        ("custom_recognition", CustomRecognition)]:
            module_type_dir = os.path.join(custom_dir, module_type)

            if not os.path.exists(module_type_dir):
                self.logger.debug( f"{module_type} 文件夹不存在于 {custom_dir}")
                continue

            self.logger.debug( f"开始加载 {module_type} 模块")

            # Traverse all Python files in the directory
            for file in os.listdir(module_type_dir):
                file_path = os.path.join(module_type_dir, file)

                # Ensure it's a file and a Python file
                if os.path.isfile(file_path) and file.endswith('.py'):
                    try:
                        # Use the file name as the module name (without .py extension)
                        module_name = os.path.splitext(file)[0]
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)

                        # Iterate through all attributes in the module
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)

                            # Check if it's a class and a subclass of the base class (but not the base class itself)
                            if isinstance(attr, type) and issubclass(attr, base_class) and attr != base_class:

                                # Use the class name as the registration name
                                class_name = attr.__name__
                                instance = attr()

                                if module_type == "custom_actions":
                                    if self.resource.register_custom_action(class_name, instance):
                                        self.logger.debug(
                                                                    f"加载自定义动作 {class_name} 成功")

                                elif module_type == "custom_recognition":
                                    if self.resource.register_custom_recognition(class_name, instance):
                                        self.logger.debug(
                                                                    f"加载自定义识别器 {class_name} 成功")

                    except Exception as e:
                        self.logger.error( f"加载自定义内容时发生错误 {file_path}: {e}")

    @Slot()
    def _process_next_task(self):
        """Process the next task in the queue"""
        with QMutexLocker(self._mutex):
            # Check executor status and task queue
            if not self._active or self._running_task or not self._task_queue:
                if not self._task_queue and self._active and not self._running_task:
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

            self.load_custom_objects(os.path.join(task.data.resource_path, "custom_dir"))

            # Create and start the task runner
            runner = TaskRunner(task, self)
            runner.setAutoDelete(True)
            self.thread_pool.start(runner)

            # Update device status
            self.state.update_status(DeviceStatus.RUNNING)
            self.state.current_task = task
            self.logger.debug( f"设备 {self.device_name} 开始执行任务 {task.id}")

    @Slot(str, object)
    def _handle_task_completed(self, task_id):
        """Task completion handler"""
        with QMutexLocker(self._mutex):
            if self._running_task and self._running_task.id == task_id:
                self.logger.debug( f"任务 {task_id} 完成")
                self._running_task = None
                self.process_next_task_signal.emit()

    @Slot(str, str)
    def _handle_task_failed(self, task_id, error):
        """Task failure handler"""
        with QMutexLocker(self._mutex):
            if self._running_task and self._running_task.id == task_id:
                self.logger.error( f"任务 {task_id} 失败: {error}")
                self._running_task = None
                self.process_next_task_signal.emit()

    def submit_task(self, task_data: RunTimeConfigs | list[RunTimeConfigs]) -> str | list[str]:
        """Submit task to execution queue

        If task_data is a single RunTimeConfigs, returns the task id (str),
        If task_data is a list, creates a task for each config and returns a list of task ids.
        """
        with QMutexLocker(self._mutex):
            if not self._active:
                error_msg = "任务执行器未运行"
                self.logger.error( error_msg)
                raise RuntimeError(error_msg)

            task_ids = []
            # If the input is a list, create tasks for each config
            if isinstance(task_data, list):
                for data in task_data:
                    task = Task(data)
                    self._task_queue.append(task)
                    self.task_queued.emit(task.id)
                    self.logger.debug(
                                                f"任务 {task.id} 已提交到设备 {self.device_name} 队列")
                    task_ids.append(task.id)
            else:
                task = Task(task_data)
                self._task_queue.append(task)
                self.task_queued.emit(task.id)
                self.logger.debug(
                                            f"任务 {task.id} 已提交到设备 {self.device_name} 队列")
                task_ids.append(task.id)

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

            self.logger.debug( f"正在停止任务执行器 {self.device_name}")
            self._active = False
            self.state.update_status(DeviceStatus.STOPPING)

            # Cancel all tasks in the queue
            for task in self._task_queue:
                task.status = TaskStatus.CANCELED
                self.task_canceled.emit(task.id)
                self.logger.debug( f"任务 {task.id} 已取消")
            self._task_queue.clear()

            self.logger.debug( f"任务执行器 {self.device_name} 已停止")
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

        self.logger.debug( f"开始执行任务 {self.task.id}")

        try:
            # Check if already canceled
            if self.canceled:
                self.task.status = TaskStatus.CANCELED
                self.logger.debug( f"任务 {self.task.id} 已取消")
                self.executor.task_canceled.emit(self.task.id)
                return

            # Execute the task
            result = self.execute_task(self.task.data)

            # Task completed successfully
            self.task.status = TaskStatus.COMPLETED
            self.task.completed_at = datetime.now()
            self.logger.debug( f"任务 {self.task.id} 成功完成")
            self.executor.task_completed.emit(self.task.id, result)

        except Exception as e:
            if self.canceled:
                self.task.status = TaskStatus.CANCELED
                self.logger.debug( f"任务 {self.task.id} 已取消")
                self.executor.task_canceled.emit(self.task.id)
            else:
                # Task execution failed
                self.task.status = TaskStatus.FAILED
                self.task.error = str(e)
                self.task.completed_at = datetime.now()
                self.logger.error( f"任务 {self.task.id} 失败: {e}")
                self.executor.task_failed.emit(self.task.id, str(e))

    def execute_task(self, task_data):
        """Method to execute specific task"""
        # Execute all tasks in the task list
        self.logger.info( f"执行任务列表，共 {len(task_data.task_list)} 个子任务")

        for i, task in enumerate(task_data.task_list):
            self.logger.info(f"执行子任务 {i + 1}/{len(task_data.task_list)}: {task.task_entry}")
            self.tasker.post_task(task.task_entry, task.pipeline_override).wait()
            self.logger.info( f"子任务 {i + 1} 完成")

        # Send progress update signal
        self.executor.progress_updated.emit(self.task.id, 100)

        # Simple delay to ensure task has time to execute
        time.sleep(0.5)

        return {"result": "success", "data": task_data}
