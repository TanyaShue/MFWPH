# task_executor.py
# -*- coding: UTF-8 -*-
"""
任务执行器 - 使用全局Python运行时管理器 (重构版)
特点:
- 短生命周期: 为每个任务批次创建和销毁。
- 无状态: 不维护内部任务队列或长期后台循环。
- 单一入口: 通过 run_task_lifecycle 方法驱动。
- 僵尸进程防护: 使用 Windows Job Object 强制管理子进程生命周期。
"""

import asyncio
import os
import re
import subprocess
import threading
import time
import ctypes
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Union, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

import psutil
from PySide6.QtCore import QObject, Signal
from maa.context import ContextEventSink
from maa.controller import AdbController, Win32Controller
from maa.event_sink import NotificationType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit
from maa.agent_client import AgentClient

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import RunTimeConfigs, global_config
from app.models.logging.log_manager import log_manager
from app.utils.device_untils import find_emulator_pid
from core.python_runtime_manager import python_runtime_manager
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
    """
    重构后的任务执行器 - 具有短生命周期，为单次任务执行而创建和销毁。
    """

    # 信号定义
    task_state_changed = Signal(str, DeviceState, dict)

    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_config = device_config
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logger(device_config.device_name)

        # 状态管理器
        self.device_manager = device_status_manager.get_or_create_device_manager(self.device_name)

        # 核心组件 (在任务执行期间初始化)
        self._controller: Optional[Union[AdbController, Win32Controller]] = None
        self._tasker: Optional[Tasker] = None
        self._current_resource: Optional[Resource] = None
        self._current_resource_path: Optional[str] = None
        self._agent: Optional[AgentClient] = None
        self._agent_process: Optional[subprocess.Popen] = None

        # Windows Job Object 句柄，用于防止僵尸进程
        self._agent_job_handle = None

        # 线程池
        self._executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix=f"TaskExec_{self.device_name}")
        # 通知处理器
        self._notification_handler = self._create_notification_handler()

        self.logger.info(f"任务执行器实例 {id(self)} 已创建")

    async def run_task_lifecycle(self, task_data: Union[RunTimeConfigs, List[RunTimeConfigs]]) -> None:
        """
        【核心方法】执行一个完整的任务生命周期：连接 -> 执行 -> 清理。
        这个方法完成后，执行器实例即可被销毁。
        """
        tasks_to_run: List[Task] = []
        try:
            # 1. 准备阶段：将任务数据转换为内部Task对象
            configs = task_data if isinstance(task_data, list) else [task_data]
            for config in configs:
                task_id = f"task_{datetime.now().timestamp()}_{id(config)}"
                task_manager = device_status_manager.create_task_manager(task_id, self.device_name)
                task_manager.set_task_info(task_id, config.resource_name)
                tasks_to_run.append(Task(id=task_id, data=config, state_manager=task_manager))
                self.logger.debug(f"任务 {task_id} 已准备好执行")

            # 2. 连接阶段：确保设备已连接
            is_ready = await self._ensure_connection()
            if not is_ready:
                raise RuntimeError("为任务准备设备连接失败，任务将标记为失败。")

            # 3. 执行阶段：依次执行所有任务
            for task in tasks_to_run:
                # 【重要】_execute_task 现在会将 CancelledError 向上抛出
                await self._execute_task(task)

        except asyncio.CancelledError:
            self.logger.warning(f"任务执行被取消 (Device: {self.device_name})")
            # 这里是最高层的处理器，确保所有受影响的任务都被标记为 CANCELED
            for task in tasks_to_run:
                if task.state_manager.get_state() not in [DeviceState.COMPLETED, DeviceState.FAILED]:
                    task.state_manager.set_state(DeviceState.CANCELED)
                    self.task_state_changed.emit(task.id, DeviceState.CANCELED, task.state_manager.get_context())
        except Exception as e:
            self.logger.error(f"任务生命周期中发生严重错误: {e}", exc_info=True)
            for task in tasks_to_run:
                if task.state_manager.get_state() not in [DeviceState.COMPLETED, DeviceState.FAILED,
                                                          DeviceState.CANCELED]:
                    task.state_manager.set_state(DeviceState.FAILED, error_message=str(e))
                    self.task_state_changed.emit(task.id, DeviceState.FAILED, task.state_manager.get_context())
        finally:
            # 4. 清理阶段：无论成功与否，都销毁所有资源
            self.logger.info("任务生命周期结束，开始清理执行器资源...")
            await self._cleanup()
            for task in tasks_to_run:
                device_status_manager.remove_task_manager(task.id)

    async def _execute_task(self, task: Task):
        """
        执行单个任务。
        """
        task_manager = task.state_manager
        try:
            task_manager.set_state(DeviceState.PREPARING)
            await self._create_tasker(task.data.resource_pack, task.data.resource_path)

            if await self._setup_agent(task):
                task_manager.set_state(DeviceState.RUNNING)
                self.device_manager.set_state(DeviceState.RUNNING, task_id=task.id, task_name=task.data.resource_name,
                                              progress=0)
                # 如果 _run_tasks 抛出 CancelledError，这里不会捕获，将直接中断并冒泡到 run_task_lifecycle
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

        except Exception as e:
            # 这个 except 不会捕获 CancelledError，因为它继承自 BaseException
            error_msg = str(e)
            task_manager.set_state(DeviceState.FAILED, error_message=error_msg)
            self.logger.error(f"任务 {task.id} 失败: {error_msg}", exc_info=True)
        finally:
            # 发送最终状态信号（无论成功、失败还是取消后的状态）
            self.task_state_changed.emit(task.id, task_manager.get_state(), task_manager.get_context())
            await self._disconnect()

    async def _cleanup(self):
        """停止所有活动并清理资源，用于执行器销毁前"""
        self.logger.info(f"正在为执行器实例 {id(self)} 执行全面清理")

        try:
            # 强制清理 Agent - 确保即使被取消也能完成基本清理
            await asyncio.wait_for(self._cleanup_agent(force_kill=True), timeout=10.0)
        except asyncio.TimeoutError:
            self.logger.warning("Agent清理超时，继续其他清理")
        except asyncio.CancelledError:
            self.logger.warning("Agent清理被取消，但继续执行关键清理步骤")
            # 即使被取消，也要尝试完成基本的Agent清理
            try:
                if self._agent_process:
                    self._agent_process.kill()
                if self._agent_job_handle:
                    ctypes.windll.kernel32.CloseHandle(self._agent_job_handle)
                    self._agent_job_handle = None
                self._agent_process = None
            except Exception as e:
                self.logger.error(f"紧急Agent清理失败: {e}")
            # 重新抛出取消异常，让调用方知道被取消了
            raise

        try:
            # 停止MAA任务
            if self._tasker:
                await self._run_in_executor(self._tasker.post_stop)
        except Exception as e:
            self.logger.warning(f"停止 MAA tasker 时出错: {e}")

        self._executor.shutdown(wait=False)

        # 断开控制器
        self._controller = None
        self.device_manager.set_state(DeviceState.DISCONNECTED)
        self.logger.info("执行器资源已完全清理")

    # -------------------------------------------------------------------------
    # Windows Job Object Implementation
    # -------------------------------------------------------------------------
        # -------------------------------------------------------------------------
        # Windows Job Object Implementation (Fixed)
        # -------------------------------------------------------------------------
    def _setup_agent_job_object(self, process: subprocess.Popen):
        """
        为 Agent 子进程配置 Windows Job Object。
        修复：使用精确的结构体定义，并处理继承冲突。
        """
        if os.name != 'nt' or not process:
            return

        try:
            # 1. 创建 Job Object
            self._agent_job_handle = ctypes.windll.kernel32.CreateJobObjectW(None, None)
            if not self._agent_job_handle:
                self.logger.warning(f"Agent Job Object 创建失败: {ctypes.GetLastError()}")
                return

            # 2. 定义精确的结构体 (修复点：使用 IO_COUNTERS 而非 c_void_p)
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ('ReadOperationCount', ctypes.c_ulonglong),
                    ('WriteOperationCount', ctypes.c_ulonglong),
                    ('OtherOperationCount', ctypes.c_ulonglong),
                    ('ReadTransferCount', ctypes.c_ulonglong),
                    ('WriteTransferCount', ctypes.c_ulonglong),
                    ('OtherTransferCount', ctypes.c_ulonglong),
                ]

            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('PerProcessUserTimeLimit', wintypes.LARGE_INTEGER),
                    ('PerJobUserTimeLimit', wintypes.LARGE_INTEGER),
                    ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t),
                    ('PriorityClass', wintypes.DWORD),
                    ('SchedulingClass', wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ('IoInfo', IO_COUNTERS),  # 这里必须是精确的 IO_COUNTERS 结构
                    ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t),
                ]

            # 3. 配置属性
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            res = ctypes.windll.kernel32.SetInformationJobObject(
                self._agent_job_handle,
                9,  # JobObjectExtendedLimitInformation
                ctypes.pointer(info),
                ctypes.sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
            )

            if not res:
                err_code = ctypes.GetLastError()
                self.logger.warning(f"无法设置 Agent Job Object 属性 (Error Code: {err_code})")
                ctypes.windll.kernel32.CloseHandle(self._agent_job_handle)
                self._agent_job_handle = None
                return

            # 4. 获取子进程句柄并绑定
            PROCESS_ALL_ACCESS = 0x1FFFFF
            process_handle = ctypes.windll.kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, process.pid)

            if not process_handle:
                self.logger.warning(f"无法获取 Agent 进程句柄 (PID: {process.pid})")
                return

            try:
                success = ctypes.windll.kernel32.AssignProcessToJobObject(self._agent_job_handle, process_handle)
                if not success:
                    # [修复] 处理 Job 冲突：
                    # 如果返回 False (Error 5: Access Denied)，通常因为主程序 (main.py) 已经把这个子进程
                    # 纳入了全局 Job Object。这是好事，说明主程序的防护生效了。
                    # 我们不需要再创建一个独立的 Job，直接忽略即可。
                    err = ctypes.GetLastError()
                    if err == 5:  # ERROR_ACCESS_DENIED
                        self.logger.info(
                            f"Agent (PID: {process.pid}) 已由全局主程序 Job Object 管理 (跳过独立绑定)。")
                        # 释放无用的 handle
                        ctypes.windll.kernel32.CloseHandle(self._agent_job_handle)
                        self._agent_job_handle = None
                    else:
                        self.logger.debug(f"绑定 Job Object 失败 (Code: {err})")
                else:
                    self.logger.info(f"Agent (PID: {process.pid}) 已成功绑定到独立 Job Object")
            finally:
                ctypes.windll.kernel32.CloseHandle(process_handle)

        except Exception as e:
            self.logger.error(f"设置 Agent Job Object 时发生错误: {e}")

    def _create_notification_handler(self):
        """创建通知处理器"""

        class Handler(ContextEventSink):
            def __init__(self, executor):
                super().__init__()
                self.executor = executor
                # 预编译正则：匹配 [info]消息内容，忽略大小写
                self._log_pattern = re.compile(r"^\[(info|debug|warning|error|critical)\](.*)", re.IGNORECASE)

            def _process_log_protocol(self, focus_data, key_map, noti_type):
                if not focus_data or not isinstance(focus_data, dict):
                    return False

                protocol_key = key_map.get(noti_type)
                if not protocol_key or protocol_key not in focus_data:
                    return False

                raw_content = focus_data[protocol_key]
                messages = raw_content if isinstance(raw_content, list) else [str(raw_content)]

                for msg in messages:
                    match = self._log_pattern.match(msg)
                    if match:
                        level_str = match.group(1).lower()
                        content = match.group(2)
                        log_func = getattr(self.executor.logger, level_str, self.executor.logger.info)
                        log_func(content)
                    else:
                        self.executor.logger.info(msg)

                return True

            def on_node_recognition(self, context, noti_type: NotificationType,
                                    detail: ContextEventSink.NodeRecognitionDetail):
                recog_key_map = {
                    NotificationType.Starting: 'Node.Recognition.Starting',
                    NotificationType.Succeeded: 'Node.Recognition.Succeeded',
                    NotificationType.Failed: 'Node.Recognition.Failed',
                }
                focus = getattr(detail, "focus", None)
                if self._process_log_protocol(focus, recog_key_map, noti_type):
                    return

            def on_node_action(self, context, noti_type: NotificationType, detail: ContextEventSink.NodeActionDetail):
                if not detail or not hasattr(detail, "focus") or not detail.focus:
                    return
                focus = detail.focus

                action_key_map = {
                    NotificationType.Starting: 'Node.Action.Starting',
                    NotificationType.Succeeded: 'Node.Action.Succeeded',
                    NotificationType.Failed: 'Node.Action.Failed',
                }

                if self._process_log_protocol(focus, action_key_map, noti_type):
                    return

                old_protocol_map = {
                    NotificationType.Succeeded: ("succeeded", self.executor.logger.info),
                    NotificationType.Failed: ("failed", self.executor.logger.error),
                    NotificationType.Starting: ("start", self.executor.logger.info),
                }

                if noti_type in old_protocol_map:
                    key, default_log_func = old_protocol_map[noti_type]
                    log_func = default_log_func
                    level_config = focus.get("level")
                    if isinstance(level_config, dict):
                        log_level_str = level_config.get(key)
                        if log_level_str:
                            log_func = getattr(self.executor.logger, log_level_str, default_log_func)

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

    async def _ensure_connection(self) -> bool:
        """确保设备连接就绪，如果未连接则尝试连接"""
        if self._controller and self._controller.connected:
            self.logger.debug("控制器已连接，跳过连接步骤。")
            return True
        self.logger.info("开始确保设备连接...")
        self.device_manager.set_state(DeviceState.CONNECTING)
        try:
            current_dir = os.getcwd()
            await self._run_in_executor(Toolkit.init_option, os.path.join(current_dir, "assets"))
            if global_config.app_config.debug_model:
                Tasker.set_debug_mode(True)
            pid = await self._manage_emulator_process()
            if not pid and self.device_config.start_command:
                error_msg = "启动或查找模拟器进程失败。"
                self.logger.error(error_msg)
                self.device_manager.set_state(DeviceState.ERROR, error_message=error_msg)
                return False
            if not await self._initialize_controller_with_retries(pid):
                return False
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
                wait_time = global_config.get_app_config().emulator_start_wait_time
                await self._wait_for_emulator_startup(wait_time)
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
                return True
            self.logger.warning(f"第 {attempt} 次控制器初始化失败。")
            if attempt < max_retries:
                if pid and self.device_config.start_command:
                    self.logger.info("将尝试重启模拟器后重试...")
                    await self._kill_emulator_process(pid)
                    new_pid = await self._start_emulator_and_wait_for_pid(self.device_config.start_command)
                    if not new_pid:
                        self.logger.error("重启模拟器失败，无法继续。")
                        break
                    pid = new_pid
                    wait_time = global_config.get_app_config().emulator_start_wait_time
                    await self._wait_for_emulator_startup(wait_time)
                else:
                    self.logger.warning("无法重启模拟器，将直接重试连接。")
                    await asyncio.sleep(5)
        self.logger.error(f"控制器在 {max_retries} 次尝试后仍初始化失败。请检查模拟器状态或ADB连接是否稳定。")
        self.device_manager.set_state(DeviceState.ERROR, error_message="控制器初始化失败")
        return False

    async def _disconnect(self):
        """断开控制器连接并清理"""
        self.logger.debug("正在断开控制器...")
        self._controller = None

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

    async def _initialize_controller(self) -> bool:
        """初始化控制器"""
        try:
            if self.device_config.device_type == DeviceType.ADB:
                cfg = self.device_config.controller_config
                self._controller = AdbController(cfg.adb_path, cfg.address, cfg.screencap_methods,
                                                 input_methods=cfg.input_methods, config=cfg.config)
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
        self._tasker = Tasker()
        self._tasker.add_context_sink(self._notification_handler)
        self._tasker.bind(resource=resource, controller=self._controller)
        if not self._tasker.inited:
            raise RuntimeError("任务执行器初始化失败")
        self.logger.info("任务执行器创建成功")

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
            python_exe = await self._prepare_python_environment_global(task.data.resource_name, task.data.resource_path,
                                                                       agent_config.version, agent_config.use_venv,
                                                                       agent_config.requirements_path)
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
            await self._cleanup_agent(force_kill=True)
            return False

    async def _prepare_python_environment_global(self, resource_name: str, resource_path: str, python_version: str,
                                                 use_venv: bool, requirements_path: str) -> Optional[str]:
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
                    success = await python_runtime_manager.install_requirements(python_version, resource_name, req_file,
                                                                                force_reinstall=False)
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
        self.logger.info(f"当前资源版本: {task.data.resource_version}")
        task_manager = task.state_manager
        self.logger.info(f"执行任务列表，共 {len(task_list)} 个子任务")
        for i, sub_task in enumerate(task_list):
            if task_manager.get_state() == DeviceState.CANCELED:
                raise asyncio.CancelledError()
            await asyncio.sleep(0)

            self.logger.info(f"执行子任务 {i + 1}/{len(task_list)}: {sub_task.task_name}")

            def run_sub_task():
                self._tasker.resource.override_pipeline(sub_task.pipeline_override)
                job = self._tasker.post_task(sub_task.task_entry)
                job.wait()
                if job.status == 4: raise Exception(f"子任务 {sub_task.task_name} 执行失败")
                return job.get()

            try:
                await self._run_in_executor(run_sub_task)
            except asyncio.CancelledError:
                self.logger.warning(f"子任务 {sub_task.task_name} 在执行中被中断")
                await self._run_in_executor(self._tasker.post_stop)
                raise  # 将异常抛给 _execute_task 的上层 run_task_lifecycle 处理

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
            common_kwargs = dict(cwd=os.getcwd(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=agent_env,
                                 text=True, encoding="utf-8", errors="replace")
            if os.name == 'nt':
                # 注意：CREATE_NEW_PROCESS_GROUP 允许发送信号，但通常不影响 Job 继承
                return subprocess.Popen(cmd,
                                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                                        **common_kwargs)
            else:
                return subprocess.Popen(cmd, preexec_fn=os.setsid, **common_kwargs)

        self._agent_process = await self._run_in_executor(start_process)
        self.logger.info(f"Agent进程已启动，PID: {self._agent_process.pid}")

        await self._run_in_executor(self._setup_agent_job_object, self._agent_process)

        if not hasattr(global_config, "agent_processes"): global_config.agent_processes = []
        global_config.agent_processes.append(self._agent_process)
        self._start_log_threads()
        await asyncio.sleep(1)
        if self._agent_process.poll() is not None:
            self.logger.error(f"Agent进程启动后立即退出了")

    def _start_log_threads(self):
        """启动日志捕获线程"""

        def log_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, ''):
                    if line: self.logger.debug(f"[Agent {prefix}] {line.rstrip()}")
            except Exception:
                pass
            finally:
                pipe.close()

        for pipe, prefix in [(self._agent_process.stdout, 'stdout'), (self._agent_process.stderr, 'stderr')]:
            threading.Thread(target=log_output, args=(pipe, prefix), daemon=True).start()

    async def _cleanup_agent(self, force_kill: bool = False):
        """
        清理Agent - 无论是否请求强制，此处均执行强制清理。
        不会尝试 terminate() 等待，直接 kill 并关闭 Job 句柄。
        """
        if self._agent_process:
            self.logger.warning(f"正在强制清理 Agent 进程 (PID: {self._agent_process.pid})...")
            try:
                self._agent_process.kill()
                # 等待进程结束，避免竞争条件
                try:
                    await asyncio.wait_for(
                        self._run_in_executor(self._agent_process.wait),
                        timeout=5.0
                    )
                    self.logger.debug(f"Agent 进程 (PID: {self._agent_process.pid}) 已确认结束")
                except asyncio.TimeoutError:
                    self.logger.warning(f"等待 Agent 进程结束超时，继续清理")
                except Exception as e:
                    self.logger.debug(f"等待进程结束时出错 (通常忽略): {e}")
            except Exception as e:
                self.logger.error(f"Kill Agent 进程时出错 (通常忽略): {e}")

            # 关闭 Job 句柄：如果进程因某种原因还活着，Job Object 会由操作系统层面进行收割
            if self._agent_job_handle:
                try:
                    self.logger.debug("正在关闭 Agent Job Object 句柄 (这将触发内核级进程清理)")
                    ctypes.windll.kernel32.CloseHandle(self._agent_job_handle)
                except Exception as e:
                    self.logger.error(f"关闭 Job Handle 失败: {e}")
                self._agent_job_handle = None

            if hasattr(global_config, "agent_processes") and self._agent_process in global_config.agent_processes:
                global_config.agent_processes.remove(self._agent_process)
            self._agent_process = None

        if self._agent:
            try:
                # 尽力通知断开，但如果不成功也不阻塞
                await self._run_in_executor(self._agent.disconnect)
            except Exception:
                pass