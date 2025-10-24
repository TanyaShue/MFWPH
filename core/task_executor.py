# task_executor.py
# -*- coding: UTF-8 -*-
"""
任务执行器 - 使用全局Python运行时管理器
"""

import asyncio
import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Union, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

import psutil
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
from app.utils.device_untils import find_emulator_pid
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
        self._controller: Optional[Union[AdbController, Win32Controller]] = None
        self._tasker: Optional[Tasker] = None
        self._current_resource: Optional[Resource] = None
        self._current_resource_path: Optional[str] = None
        self._agent: Optional[AgentClient] = None
        self._agent_process: Optional[subprocess.Popen] = None

        # 任务管理
        self._active = False
        self._task_queue: List[Task] = []
        self._current_task: Optional[Task] = None
        self._processing_task: Optional[asyncio.Task] = None

        # 锁管理
        self._lock = asyncio.Lock()

        # 线程池
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix=f"TaskExec_{self.device_name}")

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

            def on_node_action(self, noti_type: NotificationType, detail: NotificationHandler.NodeActionDetail):
                if not detail or not hasattr(detail, "focus") or not detail.focus:
                    return

                focus = detail.focus

                # 映射每种通知类型到 focus key 和日志函数
                type_to_log = {
                    NotificationType.Succeeded: ("succeeded", self.executor.logger.info),
                    NotificationType.Failed: ("failed", self.executor.logger.error),
                    NotificationType.Starting: ("start", self.executor.logger.info),
                }

                if noti_type in type_to_log:
                    key, log_func = type_to_log[noti_type]
                    if key in focus:
                        values = focus[key]
                        if isinstance(values, list):
                            for v in values:
                                log_func(str(v))
                        else:
                            log_func(str(values))

        return Handler(self)

    async def _run_in_executor(self, func, *args):
        """在线程池中运行阻塞操作"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    # === 生命周期管理 ===
    @asyncSlot()
    async def start(self) -> bool:
        """启动任务执行器，只初始化后台循环"""
        async with self._lock:
            if self._active:
                return True

            try:
                self._active = True
                # 设置初始状态为断开，等待任务触发连接
                self.device_manager.set_state(DeviceState.DISCONNECTED)
                self._processing_task = asyncio.create_task(self._process_tasks())
                self.logger.info(f"任务执行器 {self.device_name} 已启动，等待任务...")
                self.executor_started.emit()
                return True
            except Exception as e:
                self.logger.error(f"启动任务执行器失败: {e}", exc_info=True)
                self.device_manager.set_state(DeviceState.ERROR, error_message=str(e))
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

            # 取消队列中和进行中的所有任务
            for task in self._task_queue:
                task.state_manager.set_state(DeviceState.CANCELED)
            if self._current_task:
                self._current_task.state_manager.set_state(DeviceState.CANCELED)
            self._task_queue.clear()

        # 停止MAA任务
        if self._tasker and self._tasker.running:
            await self._run_in_executor(self._tasker.post_stop().wait)

        # 取消后台处理循环
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        await self._cleanup_agent()
        self._executor.shutdown(wait=False)

        self._controller = None
        self.device_manager.set_state(DeviceState.DISCONNECTED)
        self.logger.info("任务执行器已完全停止")
        self.executor_stopped.emit()

    async def _ensure_connection(self) -> bool:
        """【重构核心】确保设备连接就绪，如果未连接则尝试连接"""
        # 如果已连接，直接返回成功
        if self._controller and self._controller.connected:
            self.logger.debug("控制器已连接，跳过连接步骤。")
            return True

        self.logger.info("开始确保设备连接...")
        self.device_manager.set_state(DeviceState.CONNECTING)

        try:
            # 初始化MAA Toolkit
            current_dir = os.getcwd()
            await self._run_in_executor(Toolkit.init_option, os.path.join(current_dir, "assets"))
            if global_config.app_config.debug_model:
                Tasker.set_debug_mode(True)

            # 检查和启动模拟器
            pid = await self._manage_emulator_process()
            if not pid and self.device_config.start_command:
                error_msg = "启动或查找模拟器进程失败。"
                self.logger.error(error_msg)
                self.device_manager.set_state(DeviceState.ERROR, error_message=error_msg)
                return False

            # 初始化控制器
            if not await self._initialize_controller_with_retries(pid):
                return False

            self.device_manager.set_state(DeviceState.CONNECTED)
            self.logger.info("设备连接成功并准备就绪。")
            return True

        except Exception as e:
            self.logger.error(f"确保设备连接失败: {e}", exc_info=True)
            self.device_manager.set_state(DeviceState.ERROR, error_message=str(e))
            return False

    async def _manage_emulator_process(self) -> Optional[int]:
        """管理模拟器进程的启动和等待"""
        if not self.device_config.start_command:
            self.logger.info("未配置启动命令，跳过模拟器状态检查。")
            return None

        self.logger.info(f"正在为设备 '{self.device_name}' 检查模拟器状态...")
        pid = await self._run_in_executor(find_emulator_pid, self.device_config.start_command)

        if pid:
            self.logger.info(f"检测到模拟器已在运行。PID: {pid}")
            return pid

        if getattr(self.device_config, 'auto_start_emulator', False):
            self.logger.info("模拟器未运行，将根据配置尝试启动...")
            pid = await self._start_emulator_and_wait_for_pid(self.device_config.start_command)
            if pid:
                await self._wait_for_emulator_startup(20)
                return pid
        else:
            self.logger.warning("模拟器未运行，且自动启动选项未开启。")

        return None

    async def _initialize_controller_with_retries(self, pid: Optional[int]) -> bool:
        """带重试逻辑的控制器初始化"""
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            self.logger.info(f"正在进行第 {attempt}/{max_retries} 次控制器初始化尝试...")
            if await self._initialize_controller():
                return True  # 初始化成功

            self.logger.warning(f"第 {attempt} 次控制器初始化失败。")
            if attempt < max_retries:
                if pid and self.device_config.start_command:
                    self.logger.info("将尝试重启模拟器后重试...")
                    await self._kill_emulator_process(pid)
                    new_pid = await self._start_emulator_and_wait_for_pid(self.device_config.start_command)
                    if not new_pid:
                        self.logger.error("重启模拟器失败，无法继续。")
                        break
                    pid = new_pid  # 更新PID
                    await self._wait_for_emulator_startup(20)
                else:
                    self.logger.warning("无法重启模拟器，将直接重试连接。")
                    await asyncio.sleep(5)

        self.logger.error(f"控制器在 {max_retries} 次尝试后仍初始化失败。请检查模拟器状态或ADB连接是否稳定。")
        self.device_manager.set_state(DeviceState.ERROR, error_message="控制器初始化失败")
        return False

    async def _disconnect(self):
        """【新增】断开控制器连接并清理"""
        self.logger.debug("正在断开控制器...")
        self._controller = None
        # Agent和Tasker等资源在每个任务开始时都会重新创建，所以这里只需清理控制器

    # === 模拟器进程管理 (辅助方法) ===
    async def _kill_emulator_process(self, pid: int):
        """安全地终止指定PID的进程"""
        self.logger.info(f"正在尝试终止模拟器进程，PID: {pid}")
        try:
            def kill_sync(p_id):
                if not psutil.pid_exists(p_id):
                    self.logger.info(f"进程 {p_id} 不存在，可能已被关闭。")
                    return
                try:
                    proc = psutil.Process(p_id)
                    proc.terminate()
                    proc.wait(timeout=3)
                    self.logger.info(f"进程 {p_id} 已成功终止。")
                except psutil.TimeoutExpired:
                    self.logger.warning(f"进程 {p_id} 未能友好退出，将强制终止。")
                    proc.kill()
                    self.logger.info(f"进程 {p_id} 已被强制终止。")
                except psutil.NoSuchProcess:
                    self.logger.info(f"在尝试终止时，进程 {p_id} 已消失。")

            await self._run_in_executor(kill_sync, pid)
        except Exception as e:
            self.logger.error(f"终止进程 {pid} 时发生错误: {e}", exc_info=True)

    async def _start_emulator_and_wait_for_pid(self, start_command: str, timeout: int = 60) -> Optional[int]:
        """在后台启动模拟器并等待其进程出现"""
        self.logger.info(f"执行启动命令: {start_command}")
        def _launch():
            creationflags = subprocess.DETACHED_PROCESS if os.name == 'nt' else 0
            subprocess.Popen(start_command, shell=True, creationflags=creationflags)
        try:
            await self._run_in_executor(_launch)
        except Exception as e:
            self.logger.error(f"执行模拟器启动命令失败: {e}", exc_info=True)
            return None

        self.logger.info("命令已执行，开始轮询等待进程 PID...")
        start_time = time.time()
        while time.time() - start_time < timeout:
            pid = await self._run_in_executor(find_emulator_pid, start_command)
            if pid:
                self.logger.info(f"成功找到模拟器进程，PID: {pid}")
                return pid
            await asyncio.sleep(1)

        self.logger.error(f"等待模拟器启动超时（{timeout}秒）")
        return None

    async def _wait_for_emulator_startup(self, wait_time: int = 20):
        """等待固定的时间以确保模拟器完全启动"""
        self.logger.info(f"模拟器已启动，将等待 {wait_time} 秒以确保其服务完全可用...")
        countdown_points = {10, 5, 3}
        for i in range(wait_time, 0, -1):
            if i in countdown_points:
                self.logger.info(f"等待模拟器初始化... 剩余 {i} 秒")
            await asyncio.sleep(1)
        self.logger.info("等待结束，继续执行任务。")

    # === 控制器和资源管理 ===
    async def _initialize_controller(self) -> bool:
        """初始化控制器"""
        try:
            if self.device_config.device_type == DeviceType.ADB:
                cfg = self.device_config.controller_config
                self._controller = AdbController(cfg.adb_path, cfg.address, cfg.screencap_methods, input_methods=cfg.input_methods, config=cfg.config)
            elif self.device_config.device_type == DeviceType.WIN32:
                cfg = self.device_config.controller_config
                self._controller = Win32Controller(cfg.hWnd)
            else:
                raise ValueError(f"不支持的设备类型: {self.device_config.device_type}")

            await self._run_in_executor(self._controller.post_connection().wait)
            if not self._controller.connected:
                self.logger.error("控制器连接失败")
                return False

            await self._run_in_executor(lambda: self._controller.post_screencap().wait().get())
            self.logger.info("控制器连接和截图测试成功")
            return True
        except Exception as e:
            self.logger.error(f"控制器初始化过程中发生异常: {e}", exc_info=True)
            return False

    async def _load_resource(self, resource_pack: Dict[str, Any], resource_path: str) -> Resource:
        """加载资源"""
        if self._current_resource_path == resource_path and self._current_resource:
            return self._current_resource
        try:
            self.logger.info(f"开始加载资源，根路径: {resource_path}")
            resource = Resource()
            base_path = Path(resource_path)
            paths_to_load = []
            if resource_pack and resource_pack.get('path'):
                pack_name = resource_pack.get('name', 'Unknown')
                self.logger.info(f"检测到资源包 '{pack_name}'，将按顺序加载其路径...")
                relative_paths = resource_pack.get('path', [])
                paths_to_load = [str(base_path / rel_path) for rel_path in relative_paths]
            else:
                self.logger.info("未检测到有效资源包，仅加载资源根路径。")
                paths_to_load = [resource_path]

            for i, path in enumerate(paths_to_load):
                self.logger.debug(f"正在加载路径 ({i + 1}/{len(paths_to_load)}): {path}")
                try:
                    await self._run_in_executor(lambda p=path: resource.post_bundle(p).wait())
                    self.logger.debug(f"成功加载路径: {path}")
                except Exception as e:
                    self.logger.error(f"加载路径 {path} 时发生错误: {e}")

            self.logger.info("所有资源路径加载完成。")
            self._current_resource = resource
            self._current_resource_path = resource_path
            return resource
        except Exception as e:
            self.logger.error(f"资源加载过程中发生严重错误: {e}")
            raise

    async def _create_tasker(self, resource_pack, resource_path: str):
        """创建任务器"""
        resource = await self._load_resource(resource_pack, resource_path)
        resource.clear_custom_action()
        resource.clear_custom_recognition()
        self._tasker = Tasker(notification_handler=self._notification_handler)
        self._tasker.bind(resource=resource, controller=self._controller)
        if not self._tasker.inited:
            raise RuntimeError("任务执行器初始化失败")
        self.logger.info("任务执行器创建成功")

    # === 任务处理 ===
    async def _process_tasks(self):
        """【重构】任务处理主循环，包含连接管理"""
        self.logger.info("任务处理循环已启动")
        while self._active:
            try:
                task = await self._get_next_task()
                if not task:
                    await asyncio.sleep(0.1)
                    continue

                # 步骤1: 确保为当前任务准备好连接
                is_ready = await self._ensure_connection()
                if not is_ready:
                    error_msg = "为任务准备设备连接失败，任务将标记为失败。"
                    self.logger.error(f"{error_msg} (Task ID: {task.id})")
                    task.state_manager.set_state(DeviceState.FAILED, error_message=error_msg)
                    # 发送失败信号并清理
                    self.task_state_changed.emit(task.id, DeviceState.FAILED, task.state_manager.get_context())
                    async with self._lock:
                        self._current_task = None
                    device_status_manager.remove_task_manager(task.id)
                    await asyncio.sleep(5) # 等待一段时间再试下一个任务
                    continue

                # 步骤2: 执行任务
                await self._execute_task(task)

            except asyncio.CancelledError:
                self.logger.info("任务处理循环被取消")
                break
            except Exception as e:
                self.logger.error(f"任务处理循环发生未捕获的错误: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _get_next_task(self) -> Optional[Task]:
        """获取下一个待处理任务"""
        async with self._lock:
            if self._current_task:
                return None
            while self._task_queue:
                task = self._task_queue.pop(0)
                if task.state_manager.get_state() not in (DeviceState.CANCELED, DeviceState.FAILED, DeviceState.COMPLETED):
                    self._current_task = task
                    return task
                else: # 清理已取消的任务
                    device_status_manager.remove_task_manager(task.id)
            return None

    async def _execute_task(self, task: Task):
        """执行单个任务"""
        task_manager = task.state_manager
        try:
            task_manager.set_state(DeviceState.PREPARING)
            await self._create_tasker(task.data.resource_pack, task.data.resource_path)

            if await self._setup_agent(task):
                task_manager.set_state(DeviceState.RUNNING)
                self.device_manager.set_state(DeviceState.RUNNING, task_id=task.id, task_name=task.data.resource_name, progress=0)
                result = await self._run_tasks(task)
                task.result = result
                task_manager.set_state(DeviceState.COMPLETED, progress=100)
                self.logger.info(f"任务 {task.id} 执行成功")

                if getattr(self.device_config, 'auto_close_emulator', False):
                    self.logger.info("配置了自动关闭模拟器，正在执行...")
                    pid_to_close = await self._run_in_executor(find_emulator_pid, self.device_config.start_command)
                    if pid_to_close:
                        await self._kill_emulator_process(pid_to_close)
            else:
                raise Exception("Agent设置失败，任务无法继续")

        except asyncio.CancelledError:
            task_manager.set_state(DeviceState.CANCELED)
            self.logger.info(f"任务 {task.id} 被取消")
        except Exception as e:
            error_msg = str(e)
            task_manager.set_state(DeviceState.FAILED, error_message=error_msg)
            self.logger.error(f"任务 {task.id} 失败: {error_msg}", exc_info=True)
        finally:
            self.task_state_changed.emit(task.id, task_manager.get_state(), task_manager.get_context())
            async with self._lock:
                self._current_task = None
            device_status_manager.remove_task_manager(task.id)

            # 【重构】任务结束后断开连接，为下一个任务做准备
            await self._disconnect()

            # 根据队列情况更新设备状态
            if self.get_queue_length() == 0:
                self.device_manager.set_state(DeviceState.DISCONNECTED)
                self.logger.info("任务完成，队列为空，设备状态重置为 DISCONNECTED。")
            else:
                self.device_manager.set_state(DeviceState.CONNECTED)
                self.logger.info(f"任务完成，队列中还有 {self.get_queue_length()} 个任务，准备处理下一个。")

    async def _setup_agent(self, task: Task) -> bool:
        """设置Agent - 使用全局Python运行时管理器"""
        resource_config = global_config.get_resource_config(task.data.resource_name)
        if not resource_config or not resource_config.agent.agent_path:
            return True
        try:
            self.device_manager.set_state(DeviceState.UPDATING)
            if not self._agent:
                self._agent = AgentClient()
                self._agent.bind(self._current_resource)
            agent_config = resource_config.agent
            python_exe = await self._prepare_python_environment_global(task.data.resource_name, task.data.resource_path, agent_config.version, agent_config.use_venv, agent_config.requirements_path)
            if not python_exe:
                raise Exception("Python环境准备失败")
            await self._start_agent_process(task, agent_config, python_exe)
            self.logger.debug("尝试连接Agent...")
            connected = await self._run_in_executor(self._agent.connect)
            if not connected:
                raise Exception("无法连接到Agent")
            self.device_manager.set_state(DeviceState.PREPARING)
            self.logger.info("Agent连接成功")
            return True
        except Exception as e:
            self.logger.error(f"Agent设置失败: {e}")
            self.device_manager.set_state(DeviceState.ERROR, error_message=str(e))
            await self._cleanup_agent()
            return False

    async def _prepare_python_environment_global(self,resource_name: str,resource_path: str,python_version: str,use_venv: bool,requirements_path: str) -> Optional[str]:
        """使用全局管理器准备Python环境"""
        try:
            if not await python_runtime_manager.ensure_python_installed(python_version):
                import sys
                python_exe = sys.executable
                self.logger.info(f"使用系统Python: {python_exe}")
                use_venv = False
                return python_exe
            if use_venv:
                runtime_info = await python_runtime_manager.create_venv(python_version, resource_name)
                if not runtime_info:
                    self.logger.error("创建虚拟环境失败")
                    return None
                if requirements_path:
                    req_file = Path(resource_path) / requirements_path
                    success = await python_runtime_manager.install_requirements(python_version, resource_name, req_file, force_reinstall=False)
                    if not success:
                        self.logger.error("安装依赖失败")
                        return None
                return str(runtime_info.python_exe)
            else:
                runtime = python_runtime_manager.get_runtime(python_version)
                python_exe = runtime.get_python_executable()
                if requirements_path:
                    req_file = Path(resource_path) / requirements_path
                    if req_file.exists():
                        self.logger.warning("不使用虚拟环境，依赖将安装到全局Python")
                return str(python_exe)
        except Exception as e:
            self.logger.error(f"Python环境准备失败: {e}", exc_info=True)
            return None

    async def _run_tasks(self, task: Task) -> dict:
        """执行任务列表"""
        task_list = task.data.task_list
        task_manager = task.state_manager
        self.logger.info(f"执行任务列表，共 {len(task_list)} 个子任务")
        for i, sub_task in enumerate(task_list):
            if task_manager.get_state() == DeviceState.CANCELED:
                raise asyncio.CancelledError()
            self.logger.info(f"执行子任务 {i + 1}/{len(task_list)}: {sub_task.task_name}")
            def run_sub_task():
                self._tasker.resource.override_pipeline(sub_task.pipeline_override)
                job = self._tasker.post_task(sub_task.task_entry)
                job.wait()
                if job.status == 4: raise Exception(f"子任务 {sub_task.task_name} 执行失败")
                return job.get()
            future = asyncio.create_task(self._run_in_executor(run_sub_task))
            while not future.done():
                if task_manager.get_state() == DeviceState.CANCELED:
                    await self._run_in_executor(self._tasker.post_stop)
                    raise asyncio.CancelledError()
                await asyncio.sleep(0.1)
            await future
            progress = int((i + 1) / len(task_list) * 100)
            task_manager.set_progress(progress)
            self.device_manager.set_progress(progress)
            self.logger.info(f"子任务 {sub_task.task_entry} 执行完毕")
        return {"result": "success", "data": task.data}

    async def _start_agent_process(self, task: Task, agent_config, python_exe: str):
        """启动Agent进程"""
        agent_full_path = Path(task.data.resource_path) / agent_config.agent_path
        cmd = [python_exe, "-u", str(agent_full_path)]
        if agent_config.agent_params: cmd.extend(agent_config.agent_params.split())
        cmd.extend(["-device", self.device_name, "-id", self._agent.identifier])
        self.logger.debug(f"Agent启动命令: {' '.join(cmd)}")
        def start_process():
            agent_env = os.environ.copy()
            agent_env["PYTHONUTF8"] = "1"
            common_kwargs = dict(cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=agent_env, text=True, encoding="utf-8", errors="replace")
            if os.name == 'nt': return subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW, **common_kwargs)
            else: return subprocess.Popen(cmd, preexec_fn=os.setsid, **common_kwargs)
        self._agent_process = await self._run_in_executor(start_process)
        self.logger.info(f"Agent进程已启动，PID: {self._agent_process.pid}")
        if not hasattr(global_config, "agent_processes"): global_config.agent_processes = []
        global_config.agent_processes.append(self._agent_process)
        self._start_log_threads()
        await asyncio.sleep(1)
        if self._agent_process.poll() is not None:
            stderr = self._agent_process.stderr.read()
            raise Exception(f"Agent启动失败: {stderr}")

    def _start_log_threads(self):
        """启动日志捕获线程"""
        def log_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, ''):
                    if line: self.logger.debug(f"[Agent {prefix}] {line.rstrip()}")
            except Exception: pass
            finally: pipe.close()
        for pipe, prefix in [(self._agent_process.stdout, 'stdout'), (self._agent_process.stderr, 'stderr')]:
            threading.Thread(target=log_output, args=(pipe, prefix), daemon=True).start()

    async def _cleanup_agent(self):
        """清理Agent"""
        if self._agent_process:
            try:
                self._agent_process.terminate()
                await asyncio.sleep(0.5)
                if self._agent_process.poll() is None: self._agent_process.kill()
            except Exception: pass
            if hasattr(global_config, "agent_processes") and self._agent_process in global_config.agent_processes:
                global_config.agent_processes.remove(self._agent_process)
            self._agent_process = None
        if self._agent:
            try: await self._run_in_executor(self._agent.disconnect)
            except Exception: pass

    # === 任务提交和管理 ===
    @asyncSlot(object)
    async def submit_task(self, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> Union[str, List[str]]:
        """提交任务"""
        async with self._lock:
            configs = task_data if isinstance(task_data, list) else [task_data]
            task_ids = []
            for config in configs:
                task_id = f"task_{datetime.now().timestamp()}_{id(config)}"
                task_manager = device_status_manager.create_task_manager(task_id, self.device_name)
                task_manager.set_task_info(task_id, config.resource_name)
                task = Task(id=task_id, data=config, state_manager=task_manager)
                self._task_queue.append(task)
                task_ids.append(task_id)
                self.device_manager.update_context(queue_length=len(self._task_queue))
                self.logger.debug(f"任务 {task_id} 已加入队列")
            return task_ids[0] if len(task_ids) == 1 else task_ids

    @asyncSlot(str)
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            if self._current_task and self._current_task.id == task_id:
                self._current_task.state_manager.set_state(DeviceState.CANCELED)
                # 触发任务循环中的取消逻辑
                if self._tasker:
                    await self._run_in_executor(self._tasker.post_stop)
                return True
            for task in self._task_queue:
                if task.id == task_id:
                    task.state_manager.set_state(DeviceState.CANCELED)
                    return True
        return False

    def get_queue_length(self) -> int:
        """获取队列长度"""
        return len(self._task_queue)