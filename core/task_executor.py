# task_executor.py
# -*- coding: UTF-8 -*-
"""
任务执行器 - 使用全局Python运行时管理器
"""

import asyncio
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Union, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal, Slot
from qasync import asyncSlot
from maa.controller import AdbController, Win32Controller
from maa.notification_handler import NotificationHandler, NotificationType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit
from maa.agent_client import AgentClient

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from core.python_runtime_manager import python_runtime_manager  # 使用全局实例
from core.device_state_machine import SimpleStateManager, DeviceState
from core.device_status_manager import device_status_manager


@dataclass
class Task:
    """简化的任务数据类"""
    id: str
    data: RunTimeConfigs
    state_manager: SimpleStateManager
    created_at: datetime = field(default_factory=datetime.now)
    result: Optional[dict] = None


class TaskExecutor(QObject):
    """重构后的任务执行器 - 使用全局Python运行时管理器"""

    # 信号定义
    task_state_changed = Signal(str, DeviceState, dict)
    executor_started = Signal()
    executor_stopped = Signal()

    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logger(device_config.device_name)

        # 状态管理器
        self.device_manager = device_status_manager.get_or_create_device_manager(self.device_name)

        # 核心组件
        self._controller = None
        self._tasker = None
        self._current_resource = None
        self._current_resource_path = None
        self._agent = None
        self._agent_process = None

        # 任务管理
        self._active = False
        self._task_queue: List[Task] = []
        self._current_task: Optional[Task] = None
        self._processing_task: Optional[asyncio.Task] = None

        # 锁管理
        self._lock = asyncio.Lock()

        # 线程池
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix=f"TaskExec_{self.device_name}")

        # 通知处理器
        self._notification_handler = self._create_notification_handler()

    def _create_notification_handler(self):
        """创建通知处理器"""

        class Handler(NotificationHandler):
            def __init__(self, executor):
                super().__init__()
                self.executor = executor

            def on_node_recognition(self, noti_type: NotificationType,
                                    detail: NotificationHandler.NodeRecognitionDetail):
                if noti_type in (NotificationType.Succeeded, NotificationType.Failed):
                    self.executor.logger.debug(
                        f"识别: {detail.name} - {'成功' if noti_type == NotificationType.Succeeded else '失败'}"
                    )
                if detail and hasattr(detail, "focus"):
                    if detail.focus is not None:
                        self.executor.logger.info(f"{detail.focus}")

        return Handler(self)

    async def _run_in_executor(self, func, *args):
        """在线程池中运行阻塞操作"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    # === 生命周期管理 ===

    @asyncSlot()
    async def start(self) -> bool:
        """启动任务执行器"""
        async with self._lock:
            if self._active:
                return True

            try:
                # 设置连接中状态
                self.device_manager.set_state(DeviceState.CONNECTING)

                # 初始化Toolkit
                current_dir = os.getcwd()
                await self._run_in_executor(
                    Toolkit.init_option, os.path.join(current_dir, "assets")
                )

                if global_config.app_config.debug_model:
                    Tasker.set_debug_mode(True)

                # 初始化控制器
                if not await self._initialize_controller():
                    self.device_manager.set_state(
                        DeviceState.ERROR,
                        error_message="控制器初始化失败"
                    )
                    return False

                # 连接成功
                self.device_manager.set_state(DeviceState.CONNECTED)

                self._active = True
                self._processing_task = asyncio.create_task(self._process_tasks())

                self.logger.info(f"任务执行器 {self.device_name} 已启动")
                self.executor_started.emit()
                return True

            except Exception as e:
                self.logger.error(f"启动失败: {e}", exc_info=True)
                self.device_manager.set_state(
                    DeviceState.ERROR,
                    error_message=str(e)
                )
                self._active = False
                return False

    @asyncSlot()
    async def stop(self):
        """停止任务执行器"""
        async with self._lock:
            if not self._active:
                return

            self.logger.info(f"停止任务执行器 {self.device_name}")
            self._active = False

            # 取消所有排队任务
            for task in self._task_queue:
                task.state_manager.set_state(DeviceState.CANCELED)

            # 取消当前任务
            if self._current_task:
                self._current_task.state_manager.set_state(DeviceState.CANCELED)

            self._task_queue.clear()

        # 停止任务器
        if self._tasker:
            await self._run_in_executor(self._tasker.post_stop().wait)

        # 取消处理循环
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        # 清理Agent
        await self._cleanup_agent()

        # 关闭线程池
        self._executor.shutdown(wait=False)

        # 断开设备
        if not self.device_manager.is_running_task():
            self.device_manager.set_state(DeviceState.DISCONNECTED)

        self.logger.info("任务执行器已停止")
        self.executor_stopped.emit()

    # === 控制器和资源管理 ===

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

            # 异步连接
            await self._run_in_executor(self._controller.post_connection().wait)

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
        if self._current_resource_path == resource_path and self._current_resource:
            return self._current_resource

        try:
            self.logger.info(f"加载资源: {resource_path}")
            resource = Resource()

            await self._run_in_executor(
                lambda: resource.post_bundle(resource_path).wait()
            )

            self._current_resource = resource
            self._current_resource_path = resource_path

            return resource

        except Exception as e:
            self.logger.error(f"资源加载失败: {e}")
            raise

    async def _create_tasker(self, resource_path: str):
        """创建任务器"""
        resource = await self._load_resource(resource_path)

        resource.clear_custom_action()
        resource.clear_custom_recognition()

        self._tasker = Tasker(notification_handler=self._notification_handler)
        self._tasker.bind(resource=resource, controller=self._controller)

        if not self._tasker.inited:
            raise RuntimeError("任务执行器初始化失败")

        self.logger.info("任务执行器创建成功")


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
            if self._current_task:
                return None

            while self._task_queue:
                task = self._task_queue.pop(0)
                if task.state_manager.get_state() == DeviceState.QUEUED:
                    self._current_task = task
                    return task
                else:
                    device_status_manager.remove_task_manager(task.id)

            return None

    async def _execute_task(self, task: Task):
        """执行单个任务"""
        task_manager = task.state_manager

        try:
            # 设置任务为准备状态
            task_manager.set_state(DeviceState.PREPARING)

            # 创建任务器
            await self._create_tasker(task.data.resource_path)
            self.logger.info("开始初始化agent")
            # 设置Agent（如果需要）
            agent_success = await self._setup_agent(task)
            if not agent_success:
                self.logger.error("Agent初始化失败")
                task_manager.set_state(DeviceState.CONNECTED)

                return

            self.logger.info("Agent初始化成功")

            # 开始执行任务
            task_manager.set_state(DeviceState.RUNNING)

            # 同步设备状态到运行中
            self.device_manager.set_state(
                DeviceState.RUNNING,
                task_id=task.id,
                task_name=task.data.resource_name,
                progress=0
            )

            # 执行任务列表
            result = await self._run_tasks(task)

            # 任务成功
            task.result = result
            task_manager.set_state(DeviceState.COMPLETED, progress=100)

            self.logger.info(f"任务 {task.id} 执行成功")

        except asyncio.CancelledError:
            task_manager.set_state(DeviceState.CANCELED)
            self.logger.info(f"任务 {task.id} 被取消")

        except Exception as e:
            error_msg = str(e)
            task_manager.set_state(DeviceState.FAILED, error_message=error_msg)
            self.logger.error(f"任务 {task.id} 失败: {error_msg}", exc_info=True)

        finally:
            # 发送最终状态
            self.task_state_changed.emit(
                task.id,
                task_manager.get_state(),
                task_manager.get_context()
            )

            # 清理
            async with self._lock:
                self._current_task = None

            # 移除任务状态管理器
            device_status_manager.remove_task_manager(task.id)

            # 检查并重置设备状态
            if self.get_queue_length() == 0:
                self.device_manager.set_state(DeviceState.CONNECTED)
                self.logger.info("没有更多任务，设备状态重置为CONNECTED")

    async def _setup_agent(self, task: Task) -> bool:
        """设置Agent - 使用全局Python运行时管理器"""
        resource_config = global_config.get_resource_config(task.data.resource_name)
        if not resource_config or not resource_config.agent.agent_path:
            return True

        try:
            # 设置为更新状态
            self.device_manager.set_state(DeviceState.UPDATING)

            # 如果Agent已运行，直接返回
            if self._agent_process and self._agent_process.poll() is None:
                next_state = DeviceState.PREPARING if task else DeviceState.CONNECTED
                self.device_manager.set_state(next_state)
                return True

            # 创建Agent客户端
            if not self._agent:
                self._agent = AgentClient()
                self._agent.bind(self._current_resource)

            # 获取配置
            agent_config = resource_config.agent

            # 准备Python环境 - 使用全局管理器
            python_exe = await self._prepare_python_environment_global(
                task.data.resource_name,
                task.data.resource_path,
                agent_config.version,
                agent_config.use_venv,
                agent_config.requirements_path
            )

            if not python_exe:
                raise Exception("Python环境准备失败")

            # 启动Agent进程
            await self._start_agent_process(task, agent_config, python_exe)

            # 连接Agent
            self.logger.debug("尝试连接Agent...")
            connected = await self._run_in_executor(self._agent.connect)
            if not connected:
                raise Exception("无法连接到Agent")

            # 更新完成，准备执行任务
            self.device_manager.set_state(DeviceState.PREPARING)

            self.logger.info("Agent连接成功")
            return True

        except Exception as e:
            self.logger.error(f"Agent设置失败: {e}")
            self.device_manager.set_state(
                DeviceState.ERROR,
                error_message=str(e)
            )
            await self._cleanup_agent()
            return False

    async def _prepare_python_environment_global(
            self,
            resource_name: str,
            resource_path: str,
            python_version: str,
            use_venv: bool,
            requirements_path: str
    ) -> Optional[str]:
        """使用全局管理器准备Python环境"""
        try:
            # 确保Python已安装
            if not await python_runtime_manager.ensure_python_installed(python_version):
                # 使用系统Python
                import sys
                python_exe = sys.executable
                self.logger.info(f"使用系统Python: {python_exe}")
                use_venv = False
                return python_exe

            if use_venv:
                # 创建虚拟环境
                runtime_info = await python_runtime_manager.create_venv(
                    python_version,
                    resource_name
                )

                if not runtime_info:
                    self.logger.error("创建虚拟环境失败")
                    return None
                # 安装依赖
                if requirements_path:
                    req_file = Path(resource_path) / requirements_path
                    success = await python_runtime_manager.install_requirements(
                        python_version,
                        resource_name,
                        req_file,
                        force_reinstall=False
                    )

                    if not success:
                        self.logger.error("安装依赖失败")
                        return None

                return str(runtime_info.python_exe)
            else:
                # 直接使用Python运行时
                runtime = python_runtime_manager.get_runtime(python_version)
                python_exe = runtime.get_python_executable()

                # 如果有requirements，安装到全局Python
                if requirements_path:
                    req_file = Path(resource_path) / requirements_path
                    if req_file.exists():
                        self.logger.warning("不使用虚拟环境，依赖将安装到全局Python")
                        # 这里可以选择是否安装到全局Python
                        # 建议：对于不使用虚拟环境的情况，跳过依赖安装或给出警告

                return str(python_exe)

        except Exception as e:
            self.logger.error(f"Python环境准备失败: {e}", exc_info=True)
            return None

    async def _run_tasks(self, task: Task) -> dict:
        """执行任务列表"""
        task_list = task.data.task_list
        task_manager = task.state_manager

        self.logger.info(f"执行任务列表，共 {len(task_list)} 个子任务")

        if self.device_manager.get_state() != DeviceState.RUNNING:
            self.logger.warning(f"执行任务时设备状态异常: {self.device_manager.get_state()}")

        for i, sub_task in enumerate(task_list):
            # 检查取消状态
            if task_manager.get_state() == DeviceState.CANCELED:
                raise asyncio.CancelledError()

            self.logger.info(f"执行子任务 {i + 1}/{len(task_list)}: {sub_task.task_entry}")

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
            future = asyncio.create_task(
                self._run_in_executor(run_sub_task)
            )

            # 等待完成，同时检查取消
            while not future.done():
                if task_manager.get_state() == DeviceState.CANCELED:
                    await self._run_in_executor(self._tasker.post_stop)
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.1)

            await future

            # 更新进度
            progress = int((i + 1) / len(task_list) * 100)
            task_manager.set_progress(progress)
            self.device_manager.set_progress(progress)

            self.logger.info(f"子任务 {sub_task.task_entry} 执行完毕")

        return {"result": "success", "data": task.data}

    async def _start_agent_process(self, task: Task, agent_config, python_exe: str):
        """启动Agent进程"""
        agent_full_path = Path(task.data.resource_path) / agent_config.agent_path

        cmd = [python_exe, str(agent_full_path)]
        if agent_config.agent_params:
            cmd.extend(agent_config.agent_params.split())
        cmd.extend(["-id", self._agent.identifier])

        self.logger.debug(f"Agent启动命令: {' '.join(cmd)}")

        # 启动进程
        def start_process():
            return subprocess.Popen(
                cmd,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

        self._agent_process = await self._run_in_executor(start_process)
        self.logger.info(f"Agent进程已启动，PID: {self._agent_process.pid}")

        # 启动日志线程
        self._start_log_threads()

        await asyncio.sleep(1)

        # 检查进程状态
        if self._agent_process.poll() is not None:
            stderr = self._agent_process.stderr.read().decode('utf-8', errors='ignore')
            raise Exception(f"Agent启动失败: {stderr}")

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
                await self._run_in_executor(self._agent.disconnect)
            except Exception:
                pass

    # === 任务提交和管理 ===

    @asyncSlot(object)
    async def submit_task(self, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> Union[str, List[str]]:
        """提交任务"""
        async with self._lock:
            configs = task_data if isinstance(task_data, list) else [task_data]
            task_ids = []

            for config in configs:
                # 生成任务ID
                task_id = f"task_{datetime.now().timestamp()}_{id(config)}"

                # 创建任务状态管理器
                task_manager = device_status_manager.create_task_manager(task_id, self.device_name)
                task_manager.set_task_info(task_id, config.resource_name)

                # 创建任务
                task = Task(
                    id=task_id,
                    data=config,
                    state_manager=task_manager
                )

                self._task_queue.append(task)
                task_ids.append(task_id)

                # 更新设备队列长度
                queue_length = len(self._task_queue)
                self.device_manager.update_context(queue_length=queue_length)

                self.logger.debug(f"任务 {task_id} 已加入队列")

            return task_ids[0] if len(task_ids) == 1 else task_ids

    @asyncSlot(str)
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            # 检查当前任务
            if self._current_task and self._current_task.id == task_id:
                self._current_task.state_manager.set_state(DeviceState.CANCELED)
                return True

            # 检查队列中的任务
            for task in self._task_queue:
                if task.id == task_id:
                    task.state_manager.set_state(DeviceState.CANCELED)
                    self._task_queue.remove(task)

                    # 更新队列长度
                    self.device_manager.update_context(queue_length=len(self._task_queue))
                    return True

        return False

    def get_queue_length(self) -> int:
        """获取队列长度"""
        return len(self._task_queue)