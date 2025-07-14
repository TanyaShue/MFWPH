# python -m pip install maafw
import os

from maa.tasker import Tasker
from maa.toolkit import Toolkit
from maa.resource import Resource
from maa.controller import AdbController, Controller, Win32Controller
from maa.notification_handler import NotificationHandler, NotificationType

from app.models.config.app_config import DeviceConfig, DeviceType
from app.models.config.global_config import global_config

# for register decorator
resource = Resource()


def main():
    user_path = "./"
    resource_path = "assets/resource/MaaYYs"

    Toolkit.init_option(user_path)

    res_job = resource.post_bundle(resource_path)
    res_job.wait()

    # If not found on Windows, try running as administrator
    load_config()
    device_config=global_config.get_device_config("阴阳师1")


    controller = create_controller(device_config)

    import time
    start = time.perf_counter()
    controller.post_connection().wait()
    end = time.perf_counter()

    elapsed = end - start
    print(f"连接耗时: {elapsed:.3f} 秒")
    tasker = Tasker()
    # tasker = Tasker(notification_handler=MyNotificationHandler())
    tasker.bind(resource, controller)

    if not tasker.inited:
        print("Failed to init MAA.")
        exit()

    print("初始化成功")



class MyNotificationHandler(NotificationHandler):
    def on_resource_loading(
            self,
            noti_type: NotificationType,
            detail: NotificationHandler.ResourceLoadingDetail,
    ):
        print(f"on_resource_loading: {noti_type}, {detail}")

    def on_controller_action(
            self,
            noti_type: NotificationType,
            detail: NotificationHandler.ControllerActionDetail,
    ):
        print(f"on_controller_action: {noti_type}, {detail}")

    def on_tasker_task(
            self, noti_type: NotificationType, detail: NotificationHandler.TaskerTaskDetail
    ):
        print(f"on_tasker_task: {noti_type}, {detail}")

    def on_node_next_list(
            self,
            noti_type: NotificationType,
            detail: NotificationHandler.NodeNextListDetail,
    ):
        print(f"on_node_next_list: {noti_type}, {detail}")

    def on_node_recognition(
            self,
            noti_type: NotificationType,
            detail: NotificationHandler.NodeRecognitionDetail,
    ):
        print(f"on_node_recognition: {noti_type}, {detail}")

    def on_node_action(
            self, noti_type: NotificationType, detail: NotificationHandler.NodeActionDetail
    ):
        print(f"on_node_action: {noti_type}, {detail}")
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

def load_config():
    devices_config_path = "assets/config/app_config.json"
    # 如果文件不存在，先创建该文件并写入 "{}"
    if not os.path.exists(devices_config_path):
        # 确保父目录存在
        os.makedirs(os.path.dirname(devices_config_path), exist_ok=True)
        with open(devices_config_path, "w", encoding="utf-8") as f:
            f.write("{}")

    global_config.load_app_config(devices_config_path)

    # 设置默认窗口大小，如果配置中不存在
    app_config = global_config.get_app_config()
    if not hasattr(app_config, 'window_size') or not app_config.window_size:
        app_config.window_size = "800x600"

    resource_dir = "assets/resource/"
    # 如果目录不存在，则创建
    if not os.path.exists(resource_dir):
        os.makedirs(resource_dir)

    global_config.load_all_resources_from_directory(resource_dir)


if __name__ == "__main__":
    main()