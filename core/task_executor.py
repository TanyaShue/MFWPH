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

from PySide6.QtCore import QObject, Signal, Slot, Qt
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
        if self.status == TaskStatus.PENDING:
            self.status = TaskStatus.CANCELED
        self._cancel_event.set()

    @property
    def is_canceled(self) -> bool:
        """检查任务是否被取消"""
        return self._cancel_event.is_set() or self.status == TaskStatus.CANCELED


class TaskExecutor(QObject):
    """优化后的任务执行器"""

    # 核心信号定义
    task_started = Signal(str)
    task_completed = Signal(str, object)
    task_failed = Signal(str, str)
    task_canceled = Signal(str)
    progress_updated = Signal(str, int)
    executor_started = Signal()
    executor_stopped = Signal()
    task_queued = Signal(str)

    # 任务状态变化信号
    task_status_changed = Signal(str, str)  # task_id, status

    class NotificationHandlerImpl(NotificationHandler):
        def __init__(self, logger):
            super().__init__()
            self.logger = logger
            self.on_recognized: Optional[callable] = None

        def on_node_recognition(
                self,
                noti_type: NotificationType,
                detail: NotificationHandler.NodeRecognitionDetail,
        ):
            if noti_type in (NotificationType.Succeeded, NotificationType.Failed):
                if self.on_recognized:
                    self.on_recognized(
                        detail.reco_id,
                        detail.name,
                        noti_type == NotificationType.Succeeded
                    )

    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logger(device_config.device_name)
        self.app_logger = log_manager.get_app_logger()

        # 初始化控制器（固定的）
        self._controller = self._create_controller()

        # 初始化任务器和资源
        self._tasker: Optional[Tasker] = None
        self._resources: Dict[str, Resource] = {}  # 资源缓存
        self._current_resource_path: Optional[str] = None

        # Agent相关
        self.agent: Optional[AgentClient] = None
        self.agent_process: Optional[subprocess.Popen] = None
        self._agent_lock = asyncio.Lock()

        # 任务管理
        self._active = False
        self._task_queue: List[Task] = []
        self._current_task: Optional[Task] = None
        self._task_lock = asyncio.Lock()

        # 连接标志
        self._controller_connected = False
        self._controller_lock = asyncio.Lock()

        # 任务处理循环
        self._processing_task: Optional[asyncio.Task] = None

        # 初始化通知处理器
        self.notification_handler = self.NotificationHandlerImpl(self.logger)
        self.notification_handler.on_recognized = self._on_recognized

        # 初始化完成标志
        self._initialized = False
        self._init_lock = asyncio.Lock()

    def _create_controller(self):
        """根据设备类型创建控制器"""
        if self.device_config.device_type == DeviceType.ADB:
            adb_config = self.device_config.controller_config
            return AdbController(
                adb_config.adb_path,
                adb_config.address,
                adb_config.screencap_methods,
                adb_config.input_methods,
                adb_config.config,
                agent_path=adb_config.agent_path
            )
        elif self.device_config.device_type == DeviceType.WIN32:
            win32_config = self.device_config.controller_config
            return Win32Controller(win32_config.hWnd)
        else:
            raise ValueError(f"不支持的设备类型: {self.device_config.device_type}")

    def _on_recognized(self, reco_id: int, name: str, hit: bool):
        """识别回调"""
        self.logger.debug(f"识别结果 - ID: {reco_id}, 名称: {name}, 命中: {hit}")

    async def _ensure_initialized(self) -> bool:
        """确保执行器已初始化"""
        async with self._init_lock:
            if self._initialized:
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

                # 连接控制器
                await self._connect_controller()

                # 创建Tasker
                self._tasker = Tasker(notification_handler=self.notification_handler)

                self._initialized = True
                self.logger.info("任务执行器初始化成功")
                return True

            except Exception as e:
                self.logger.error(f"初始化失败: {e}")
                return False

    @asyncSlot()
    async def start(self) -> bool:
        """异步启动任务执行器"""
        if self._active:
            return True

        try:
            # 确保已初始化
            if not await self._ensure_initialized():
                return False

            self._active = True

            # 启动任务处理循环
            loop = asyncio.get_event_loop()
            self._processing_task = loop.create_task(self._task_processing_loop())

            # 添加异常处理回调
            def handle_task_exception(task):
                try:
                    task.result()
                except asyncio.CancelledError:
                    self.logger.debug("任务处理循环被取消")
                except Exception as e:
                    self.logger.error(f"任务处理循环异常: {e}", exc_info=True)
                    self._active = False

            self._processing_task.add_done_callback(handle_task_exception)

            self.logger.info(f"任务执行器 {self.device_name} 已启动")
            self.executor_started.emit()
            return True

        except Exception as e:
            self.logger.error(f"启动任务执行器失败: {e}", exc_info=True)
            self._active = False

            # 如果任务已创建但出错，确保它被取消
            if hasattr(self, '_processing_task') and self._processing_task:
                self._processing_task.cancel()

            return False

    async def _connect_controller(self):
        """异步连接控制器"""
        async with self._controller_lock:
            if self._controller_connected:
                return

            self.logger.info("正在连接控制器...")
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._controller.post_connection().wait()
            )
            self._controller_connected = True
            self.logger.info("控制器连接成功")

    async def _get_or_create_resource(self, resource_path: str) -> Resource:
        """获取或创建资源（带缓存）"""
        if resource_path in self._resources:
            self.logger.debug(f"使用缓存的资源: {resource_path}")
            return self._resources[resource_path]

        try:
            self.logger.info(f"正在加载新资源: {resource_path}")
            resource = Resource()

            # 异步加载资源
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: resource.post_bundle(resource_path).wait()
            )

            # 缓存资源
            self._resources[resource_path] = resource

            # 清理过多的缓存（保留最近5个）
            if len(self._resources) > 5:
                oldest_path = next(iter(self._resources))
                del self._resources[oldest_path]
                self.logger.debug(f"清理旧资源缓存: {oldest_path}")

            self.logger.info(f"资源加载成功: {resource_path}")
            return resource

        except Exception as e:
            self.logger.error(f"资源加载失败: {e}")
            raise

    async def _bind_resource_to_tasker(self, resource_path: str):
        """绑定资源到Tasker"""
        resource = await self._get_or_create_resource(resource_path)

        # 清理自定义动作和识别
        resource.clear_custom_action()
        resource.clear_custom_recognition()

        # 绑定到Tasker
        self._tasker.bind(resource=resource, controller=self._controller)
        self._current_resource_path = resource_path

    async def _task_processing_loop(self):
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
                self.logger.error(f"任务处理循环出错: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _get_next_task(self) -> Optional[Task]:
        """获取下一个待处理任务"""
        async with self._task_lock:
            if self._current_task or not self._task_queue:
                return None

            # 查找第一个未取消的任务
            while self._task_queue:
                task = self._task_queue[0]
                if task.status == TaskStatus.CANCELED:
                    self._task_queue.pop(0)
                    continue

                self._current_task = self._task_queue.pop(0)
                return self._current_task

            return None

    async def _execute_task(self, task: Task):
        """异步执行任务"""
        task.started_at = datetime.now()
        task.status = TaskStatus.RUNNING
        self.task_started.emit(task.id)
        self.task_status_changed.emit(task.id, task.status.value)

        try:
            # 检查任务是否已取消
            if task.is_canceled:
                raise asyncio.CancelledError("任务已取消")

            # 绑定资源到Tasker
            await self._bind_resource_to_tasker(task.data.resource_path)

            # 初始化Agent（如果需要）
            if await self._ensure_agent_initialized(task):
                self.logger.info("Agent初始化成功")

            # 执行任务列表
            result = await self._run_task_list(task)

            # 任务完成
            task.completed_at = datetime.now()
            task.status = TaskStatus.COMPLETED
            task.result = result
            self.logger.info(f"任务 {task.id} 成功完成")
            self.task_completed.emit(task.id, result)
            self.task_status_changed.emit(task.id, task.status.value)

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELED
            self.logger.info(f"任务 {task.id} 已取消")
            self.task_canceled.emit(task.id)
            self.task_status_changed.emit(task.id, task.status.value)
        except Exception as e:
            task.error = str(e)
            task.completed_at = datetime.now()
            task.status = TaskStatus.FAILED
            self.logger.error(f"任务 {task.id} 失败: {e}", exc_info=True)
            self.task_failed.emit(task.id, str(e))
            self.task_status_changed.emit(task.id, task.status.value)
        finally:
            async with self._task_lock:
                self._current_task = None

    async def _run_task_list(self, task: Task) -> dict:
        """异步执行任务列表（优化版）"""
        task_list = task.data.task_list
        self.logger.info(f"执行任务列表，共 {len(task_list)} 个子任务")

        loop = asyncio.get_event_loop()

        for i, sub_task in enumerate(task_list):
            # 检查任务是否被取消
            if task.is_canceled:
                self.logger.info("任务已取消，停止执行")
                raise asyncio.CancelledError("任务已取消")

            self.logger.info(f"执行子任务 {i + 1}/{len(task_list)}: {sub_task.task_entry}")

            # 定义阻塞任务逻辑：post -> wait -> check -> get
            def run_blocking_sub_task():
                job = self._tasker.post_task(sub_task.task_entry, sub_task.pipeline_override)
                job.wait()
                if job.status == 4:  # MaaTasker_Status_Failed
                    raise Exception(f"子任务 {sub_task.task_entry} 执行失败")
                return job.get()

            # 提交任务执行到线程池
            future = loop.run_in_executor(None, run_blocking_sub_task)

            # 等待任务完成，期间检查取消状态
            while not future.done():
                if task.is_canceled:
                    self.logger.info("任务取消中，尝试停止子任务")
                    await loop.run_in_executor(None, self._tasker.post_stop)
                    raise asyncio.CancelledError("任务已取消")
                await asyncio.sleep(0.1)

            # 获取子任务结果（可能触发异常）
            await future

            self.logger.info(f"子任务 {i + 1} 完成")

            # 更新进度
            progress = int((i + 1) / len(task_list) * 100)
            self.progress_updated.emit(task.id, progress)

        return {"result": "success", "data": task.data}

    async def _ensure_agent_initialized(self, task: Task) -> bool:
        """确保Agent已初始化"""
        resource_config = global_config.get_resource_config(task.data.resource_name)
        if not resource_config or not resource_config.custom_path:
            return False

        async with self._agent_lock:
            try:
                # 如果Agent进程已存在且正在运行，则无需重新初始化
                if self.agent_process and self.agent_process.poll() is None:
                    return True

                # 创建新的Agent
                if not self.agent:
                    self.agent = AgentClient()
                    self.agent.bind(self._resources.get(task.data.resource_path))

                # 查找Python可执行文件
                python_executable = self._find_runtime_python(task.data.resource_path)
                if not python_executable:
                    python_executable = "python"

                # 构建命令
                cmd = [python_executable, resource_config.custom_path]
                if resource_config.custom_prams:
                    cmd.extend(resource_config.custom_prams.split())
                cmd.extend(["-id", self.agent.identifier])

                # 异步启动Agent进程
                loop = asyncio.get_event_loop()
                self.agent_process = await loop.run_in_executor(
                    None,
                    lambda: subprocess.Popen(
                        cmd,
                        cwd=task.data.resource_path,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=False,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                )

                # 启动输出捕获线程
                self._start_output_capture_threads()

                # 等待进程启动
                await asyncio.sleep(1)

                # 检查进程状态
                if self.agent_process.poll() is not None:
                    raise Exception(f"Agent进程启动失败，退出码: {self.agent_process.returncode}")

                # 连接到Agent
                connected = await loop.run_in_executor(None, self.agent.connect)
                if not connected:
                    raise Exception("无法连接到Agent")

                return self.agent._api_properties_initialized

            except Exception as e:
                self.logger.error(f"Agent初始化失败: {e}")
                await self._terminate_agent()
                return False

    def _find_runtime_python(self, base_dir: str) -> Optional[str]:
        """查找运行时Python可执行文件"""
        # 策略1：读取python_config.json
        config_paths = [
            os.path.join(base_dir, "runtime", "python_config.json"),
            os.path.join(os.path.dirname(base_dir), "runtime", "python_config.json"),
        ]

        for config_path in config_paths:
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
                                self.logger.debug(f"从配置文件找到Python: {abs_path}")
                                return abs_path
                except Exception as e:
                    self.logger.warning(f"读取python_config.json失败: {e}")

        # 策略2：检查常见位置
        search_dirs = [
            base_dir,
            os.path.dirname(base_dir),
            os.path.dirname(os.path.dirname(base_dir))
        ]

        for search_dir in search_dirs:
            for exe_name in ["python.exe", "python.bat", "python"]:
                path = os.path.join(search_dir, "runtime", "python", exe_name)
                if os.path.exists(path):
                    self.logger.debug(f"找到Python: {path}")
                    return path

        return None

    def _start_output_capture_threads(self):
        """启动输出捕获线程"""
        self._stop_output_capture = False

        def log_output(pipe, prefix):
            try:
                for line in iter(lambda: pipe.readline(), b''):
                    if self._stop_output_capture:
                        break
                    if line:
                        try:
                            decoded = line.decode('utf-8', errors='replace').rstrip()
                            self.logger.debug(f"[Agent {prefix}] {decoded}")
                        except Exception as e:
                            self.logger.warning(f"解码Agent输出失败: {e}")
            except Exception as e:
                self.logger.error(f"输出捕获线程错误: {e}")
            finally:
                pipe.close()

        # 创建并启动线程
        threading.Thread(
            target=log_output,
            args=(self.agent_process.stdout, 'stdout'),
            daemon=True
        ).start()

        threading.Thread(
            target=log_output,
            args=(self.agent_process.stderr, 'stderr'),
            daemon=True
        ).start()

    async def _terminate_agent(self):
        """异步终止Agent进程"""
        if not self.agent_process:
            return

        try:
            self._stop_output_capture = True
            self.logger.info("正在终止Agent进程")

            loop = asyncio.get_event_loop()

            # 终止进程
            await loop.run_in_executor(None, self.agent_process.terminate)

            # 等待进程结束
            try:
                await asyncio.wait_for(
                    loop.run_in_executor(None, self.agent_process.wait),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                self.logger.warning("Agent进程未响应，强制终止")
                await loop.run_in_executor(None, self.agent_process.kill)

            # 断开Agent连接
            if self.agent:
                await loop.run_in_executor(None, self.agent.disconnect)

            self.agent_process = None
            self.logger.info("Agent进程已终止")

        except Exception as e:
            self.logger.error(f"终止Agent进程时出错: {e}")

    @asyncSlot(object)
    async def submit_task(self, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> Union[str, List[str]]:
        """异步提交任务"""
        if not self._active:
            # raise RuntimeError("任务执行器未运行")
            pass
        task_ids = []

        async with self._task_lock:
            # 处理任务数据
            configs = task_data if isinstance(task_data, list) else [task_data]

            for config in configs:
                task = Task(data=config)
                self._task_queue.append(task)
                task_ids.append(task.id)
                self.task_queued.emit(task.id)
                self.logger.debug(f"任务 {task.id} 已加入队列")

        # 返回结果
        return task_ids[0] if len(task_ids) == 1 else task_ids

    @asyncSlot()
    async def stop(self):
        """异步停止任务执行器"""
        if not self._active:
            return

        self.logger.info(f"正在停止任务执行器 {self.device_name}")
        self._active = False

        # 取消处理循环
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                self.logger.debug("任务处理循环已取消")

        # 取消当前任务
        async with self._task_lock:
            # 取消队列中的任务
            for task in self._task_queue:
                task.cancel()
                self.task_canceled.emit(task.id)
            self._task_queue.clear()
        self._tasker.post_stop().wait()

        # 终止Agent
        await self._terminate_agent()

        self.logger.info(f"任务执行器 {self.device_name} 已停止")
        self.executor_stopped.emit()

    def get_queue_length(self) -> int:
        """获取队列长度"""
        return len(self._task_queue)

    @asyncSlot(str)
    async def cancel_task(self, task_id: str) -> bool:
        """取消指定任务"""
        async with self._task_lock:
            # 检查是否是当前任务
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

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        if self._current_task and self._current_task.id == task_id:
            return self._current_task.status

        for task in self._task_queue:
            if task.id == task_id:
                return task.status

        return None