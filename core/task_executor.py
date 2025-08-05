# -*- coding: UTF-8 -*-
import asyncio
import json
import os
import subprocess
import threading
from datetime import datetime
from typing import Optional, Dict, List, Union
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtCore import QObject, Signal, Slot
from maa.define import MaaAdbInputMethodEnum
from qasync import asyncSlot
from maa.agent_client import AgentClient
from maa.controller import AdbController, Win32Controller
from maa.notification_handler import NotificationHandler, NotificationType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class Task:
    """统一任务表示"""
    data: RunTimeConfigs
    id: str = field(default_factory=lambda: f"task_{datetime.now().timestamp()}_{id(object())}")
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[dict] = None
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self):
        """取消任务"""
        self._cancel_event.set()
        if self.status == TaskStatus.PENDING:
            self.status = TaskStatus.CANCELED

    @property
    def is_canceled(self) -> bool:
        """检查任务是否被取消"""
        return self._cancel_event.is_set()


class TaskExecutor(QObject):
    """优化后的任务执行器"""

    # 信号定义
    task_started = Signal(str)
    task_completed = Signal(str, object)
    task_failed = Signal(str, str)
    task_canceled = Signal(str)
    progress_updated = Signal(str, int)
    executor_started = Signal()
    executor_stopped = Signal()
    task_queued = Signal(str)
    task_status_changed = Signal(str, str)

    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logger(device_config.device_name)

        # 核心组件
        self._controller = None
        self._tasker = None
        self._current_resource = None
        self._current_resource_path = None

        # Agent相关
        self._agent = None
        self._agent_process = None

        # 任务管理
        self._active = False
        self._task_queue: List[Task] = []
        self._current_task: Optional[Task] = None
        self._processing_task: Optional[asyncio.Task] = None

        # 单一锁管理
        self._lock = asyncio.Lock()

        # 通知处理器
        self._notification_handler = self._create_notification_handler()

    def _create_notification_handler(self):
        """创建通知处理器"""

        class Handler(NotificationHandler):
            def __init__(self, logger):
                super().__init__()
                self.logger = logger

            def on_node_recognition(self, noti_type: NotificationType,
                                    detail: NotificationHandler.NodeRecognitionDetail):
                if noti_type in (NotificationType.Succeeded, NotificationType.Failed):
                    self.logger.debug(
                        f"识别结果 - ID: {detail.reco_id}, "
                        f"名称: {detail.name}, "
                        f"命中: {noti_type == NotificationType.Succeeded}"
                    )

        return Handler(self.logger)

    async def _initialize_controller(self):
        """初始化控制器"""
        if self._controller and self._controller.connected:
            return True

        try:
            # 创建控制器
            if self.device_config.device_type == DeviceType.ADB:
                cfg = self.device_config.controller_config
                self._controller = AdbController(
                    cfg.adb_path,
                    cfg.address,
                    cfg.screencap_methods,
                    input_methods=cfg.input_methods,
                    config=cfg.config
                )
            elif self.device_config.device_type == DeviceType.WIN32:
                cfg = self.device_config.controller_config
                self._controller = Win32Controller(cfg.hWnd)
            else:
                raise ValueError(f"不支持的设备类型: {self.device_config.device_type}")

            # 连接控制器
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._controller.post_connection().wait)

            if self._controller.connected:
                self.logger.info("控制器连接成功")
                return True
            else:
                self.logger.error("控制器连接失败")
                return False

        except Exception as e:
            self.logger.error(f"控制器初始化失败: {e}")
            return False

    async def _load_resource(self, resource_path: str) -> Resource:
        """加载资源"""
        # 如果是相同路径，复用当前资源
        if self._current_resource_path == resource_path and self._current_resource:
            return self._current_resource

        try:
            self.logger.info(f"加载资源: {resource_path}")
            resource = Resource()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: resource.post_bundle(resource_path).wait()
            )

            # 更新当前资源
            self._current_resource = resource
            self._current_resource_path = resource_path

            return resource

        except Exception as e:
            self.logger.error(f"资源加载失败: {e}")
            raise

    async def _create_tasker(self, resource_path: str):
        """创建任务器"""
        resource = await self._load_resource(resource_path)

        # 清理自定义动作和识别
        resource.clear_custom_action()
        resource.clear_custom_recognition()

        # 创建新的Tasker
        self._tasker = Tasker(notification_handler=self._notification_handler)
        self._tasker.bind(resource=resource, controller=self._controller)

        if not self._tasker.inited:
            raise RuntimeError("任务执行器初始化失败")

        self.logger.info("任务执行器创建成功")

    @asyncSlot()
    async def start(self) -> bool:
        """启动任务执行器"""
        async with self._lock:
            if self._active:
                return True

            try:
                # 初始化Toolkit
                current_dir = os.getcwd()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, Toolkit.init_option, os.path.join(current_dir, "assets")
                )

                if global_config.app_config.debug_model:
                    Tasker.set_debug_mode(True)

                # 初始化控制器
                if not await self._initialize_controller():
                    return False

                self._active = True

                # 启动任务处理循环
                self._processing_task = asyncio.create_task(self._process_tasks())

                self.logger.info(f"任务执行器 {self.device_name} 已启动")
                self.executor_started.emit()
                return True

            except Exception as e:
                self.logger.error(f"启动失败: {e}", exc_info=True)
                self._active = False
                return False

    async def _process_tasks(self):
        """任务处理主循环"""
        self.logger.info("任务处理循环已启动")

        while self._active:
            try:
                # 获取下一个任务
                task = await self._get_next_task()
                if not task:
                    await asyncio.sleep(0.1)
                    continue

                # 执行任务
                await self._execute_task(task)

            except asyncio.CancelledError:
                self.logger.info("任务处理循环被取消")
                break
            except Exception as e:
                self.logger.error(f"任务处理错误: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _get_next_task(self) -> Optional[Task]:
        """获取下一个待处理任务"""
        async with self._lock:
            # 如果有正在执行的任务，返回None
            if self._current_task:
                return None

            # 查找第一个未取消的任务
            while self._task_queue:
                task = self._task_queue.pop(0)
                if not task.is_canceled:
                    self._current_task = task
                    return task

            return None

    async def _execute_task(self, task: Task):
        """执行单个任务"""
        # 更新任务状态
        task.started_at = datetime.now()
        task.status = TaskStatus.RUNNING
        self.task_started.emit(task.id)
        self.task_status_changed.emit(task.id, task.status.value)

        try:
            # 检查取消状态
            if task.is_canceled:
                raise asyncio.CancelledError()

            # 创建任务器
            await self._create_tasker(task.data.resource_path)

            # 初始化Agent（如果需要）
            if await self._setup_agent(task):
                self.logger.info("Agent初始化成功")

            # 执行任务列表
            result = await self._run_tasks(task)

            # 任务成功
            task.completed_at = datetime.now()
            task.status = TaskStatus.COMPLETED
            task.result = result
            self.task_completed.emit(task.id, result)

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELED
            self.task_canceled.emit(task.id)

        except Exception as e:
            task.error = str(e)
            task.completed_at = datetime.now()
            task.status = TaskStatus.FAILED
            self.logger.error(f"任务失败: {e}", exc_info=True)
            self.task_failed.emit(task.id, str(e))

        finally:
            self.task_status_changed.emit(task.id, task.status.value)
            async with self._lock:
                self._current_task = None

    async def _run_tasks(self, task: Task) -> dict:
        """执行任务列表"""
        task_list = task.data.task_list
        self.logger.info(f"执行任务列表，共 {len(task_list)} 个子任务")

        loop = asyncio.get_event_loop()

        for i, sub_task in enumerate(task_list):
            # 检查取消状态
            if task.is_canceled:
                raise asyncio.CancelledError()

            self.logger.info(
                f"执行子任务 {i + 1}/{len(task_list)}: {sub_task.task_entry}"
            )

            # 异步执行子任务
            def run_sub_task():
                job = self._tasker.post_task(
                    sub_task.task_entry,
                    sub_task.pipeline_override
                )
                job.wait()
                if job.status == 4:  # Failed
                    raise Exception(f"子任务 {sub_task.task_entry} 执行失败")
                return job.get()

            # 在线程池中执行
            future = loop.run_in_executor(None, run_sub_task)

            # 等待完成，同时检查取消状态
            while not future.done():
                if task.is_canceled:
                    await loop.run_in_executor(None, self._tasker.post_stop)
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.1)

            # 获取结果
            await future

            # 更新进度
            progress = int((i + 1) / len(task_list) * 100)
            self.progress_updated.emit(task.id, progress)

        return {"result": "success", "data": task.data}

    async def _setup_agent(self, task: Task) -> bool:
        """设置Agent"""
        resource_config = global_config.get_resource_config(task.data.resource_name)
        if not resource_config or not resource_config.agent_path:
            return False

        try:
            # 如果Agent已运行，直接返回
            if self._agent_process and self._agent_process.poll() is None:
                return True

            # 创建Agent客户端
            if not self._agent:
                self._agent = AgentClient()
                self._agent.bind(self._current_resource)

            # 启动Agent进程
            python_exe = self._find_python(task.data.resource_path) or "python"
            cmd = [python_exe, resource_config.agent_path]
            if resource_config.custom_prams:
                cmd.extend(resource_config.custom_prams.split())
            cmd.extend(["-id", self._agent.identifier])

            loop = asyncio.get_event_loop()
            self._agent_process = await loop.run_in_executor(
                None,
                lambda: subprocess.Popen(
                    cmd,
                    cwd=task.data.resource_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
            )

            # 启动日志线程
            self._start_log_threads()

            # 等待启动
            await asyncio.sleep(1)

            # 检查进程状态
            if self._agent_process.poll() is not None:
                raise Exception(f"Agent启动失败: {self._agent_process.returncode}")

            # 连接Agent
            connected = await loop.run_in_executor(None, self._agent.connect)
            if not connected:
                raise Exception("无法连接到Agent")

            return True

        except Exception as e:
            self.logger.error(f"Agent设置失败: {e}")
            await self._cleanup_agent()
            return False

    def _find_python(self, base_dir: str) -> Optional[str]:
        """查找Python可执行文件"""
        # 尝试从配置文件读取
        config_path = os.path.join(base_dir, "runtime", "python_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    python_path = config.get('python_path')
                    if python_path:
                        abs_path = os.path.abspath(
                            os.path.join(os.path.dirname(config_path), "..", python_path)
                        )
                        if os.path.exists(abs_path):
                            return abs_path
            except Exception:
                pass

        # 检查常见位置
        for exe in ["python.exe", "python"]:
            path = os.path.join(base_dir, "runtime", "python", exe)
            if os.path.exists(path):
                return path

        return None

    def _start_log_threads(self):
        """启动日志捕获线程"""

        def log_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, b''):
                    if line:
                        decoded = line.decode('utf-8', errors='replace').rstrip()
                        self.logger.debug(f"[Agent {prefix}] {decoded}")
            except Exception:
                pass
            finally:
                pipe.close()

        for pipe, prefix in [(self._agent_process.stdout, 'stdout'),
                             (self._agent_process.stderr, 'stderr')]:
            threading.Thread(
                target=log_output,
                args=(pipe, prefix),
                daemon=True
            ).start()

    async def _cleanup_agent(self):
        """清理Agent"""
        if self._agent_process:
            try:
                self._agent_process.terminate()
                await asyncio.sleep(0.5)
                if self._agent_process.poll() is None:
                    self._agent_process.kill()
            except Exception:
                pass
            self._agent_process = None

        if self._agent:
            try:
                self._agent.disconnect()
            except Exception:
                pass

    @asyncSlot(object)
    async def submit_task(self, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> Union[str, List[str]]:
        """提交任务"""
        async with self._lock:
            configs = task_data if isinstance(task_data, list) else [task_data]
            task_ids = []

            for config in configs:
                task = Task(data=config)
                self._task_queue.append(task)
                task_ids.append(task.id)
                self.task_queued.emit(task.id)
                self.logger.debug(f"任务 {task.id} 已加入队列")

            return task_ids[0] if len(task_ids) == 1 else task_ids

    @asyncSlot(str)
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            # 检查当前任务
            if self._current_task and self._current_task.id == task_id:
                self._current_task.cancel()
                return True

            # 检查队列中的任务
            for task in self._task_queue:
                if task.id == task_id:
                    task.cancel()
                    self.task_canceled.emit(task_id)
                    return True

        return False

    @asyncSlot()
    async def stop(self):
        """停止任务执行器"""
        async with self._lock:
            if not self._active:
                return

            self.logger.info(f"停止任务执行器 {self.device_name}")
            self._active = False

            # 取消所有任务
            if self._current_task:
                self._current_task.cancel()

            for task in self._task_queue:
                task.cancel()
                self.task_canceled.emit(task.id)

            self._task_queue.clear()

        # 停止任务器
        if self._tasker:
            await asyncio.get_event_loop().run_in_executor(
                None, self._tasker.post_stop().wait
            )

        # 取消处理循环
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        # 清理Agent
        await self._cleanup_agent()

        self.logger.info("任务执行器已停止")
        self.executor_stopped.emit()

    def get_queue_length(self) -> int:
        """获取队列长度"""
        return len(self._task_queue)

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        if self._current_task and self._current_task.id == task_id:
            return self._current_task.status

        for task in self._task_queue:
            if task.id == task_id:
                return task.status

        return None