from typing import Optional

from PySide6.QtCore import QThreadPool
from maa.controller import AdbController, Win32Controller, Controller
from maa.resource import Resource
from maa.tasker import Tasker

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.logging.log_manager import log_manager,app_logger


class MaaFw:
    def __init__(self, device_config: DeviceConfig, parent=None):
        super().__init__(parent)
        self.device_name = device_config.device_name
        self.logger = log_manager.get_device_logs(self.device_name)
        self.thread_pool = QThreadPool.globalInstance()
        self._controller:Optional[Controller] = create_controller(device_config)
        self._resource:Optional[Resource] =None
        self._tasker:Optional[Tasker]=None


    def run_task(self,task_entry,pipeline_override) -> bool:
        if self._controller is None or not self._controller.connected:
            return False
        if self._resource is None:
            return False
        if self._tasker is None or not self._tasker.inited:
            return False

        self._tasker.bind(self._resource, self._controller)
        self.logger.info(f"开始执行任务: {task_entry}")
        self._tasker.post_task(task_entry, pipeline_override).wait()
        self.logger.info(f"任务: {task_entry} 执行完毕")
        return True



def create_controller(device_config: DeviceConfig) ->Controller:
    if device_config.device_type == DeviceType.ADB:
        adb_config = device_config.controller_config
        return AdbController(
            adb_config.adb_path,
            adb_config.address,
            adb_config.screencap_methods,
            adb_config.input_methods,
            adb_config.config,
            agent_path=adb_config.agent_path
        )
    elif device_config.device_type == DeviceType.WIN32:
        win32_config = device_config.controller_config
        return Win32Controller(
            win32_config.hWnd,
            win32_config.screencap_method,
            win32_config.input_methods
        )
    else:
        raise ValueError(f"不支持的设备类型: {device_config.device_type}")
