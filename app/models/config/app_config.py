import base64
import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union, Optional, Type

from cryptography.fernet import Fernet


class DeviceType(Enum):
    """设备控制器类型的枚举。"""
    ADB = "adb"
    WIN32 = "win32"


@dataclass
class AdbDevice:
    """ADB设备配置的数据类。"""
    name: str
    adb_path: str
    address: str
    screencap_methods: int
    input_methods: int
    agent_path: Optional[str] = None
    notification_handler: Optional[Any] = None
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Win32Device:
    """Win32设备配置的数据类。"""
    hWnd: int
    screencap_method: int
    input_method: int
    notification_handler: Optional[Any] = None


@dataclass
class OptionConfig:
    """任务或资源的选项配置。"""
    option_name: str
    value: Any


@dataclass
class TaskInstance:
    """
    代表一个具体的、已配置的任务实例。
    取代了旧的 selected_tasks 和共享的 options 概念。
    """
    task_name: str
    enabled: bool = True
    options: List[OptionConfig] = field(default_factory=list)
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class ResourceSettings:
    """
    资源的设置配置（配置方案）。
    现在包含一个任务实例字典和一个定义执行顺序的列表。
    """
    name: str
    resource_name: str
    # 使用字典存储任务实例，以 instance_id 为键，实现快速访问
    task_instances: Dict[str, TaskInstance] = field(default_factory=dict)
    # 使用列表存储 instance_id，以定义和保持任务的执行顺序
    task_order: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceSettings':
        """从字典创建 ResourceSettings 对象，封装解析逻辑。"""
        task_instances_data = data.get('task_instances', {})
        instances = {
            inst_id: TaskInstance(
                **{**inst_data, 'options': [OptionConfig(**opt) for opt in inst_data.get('options', [])]}
            )
            for inst_id, inst_data in task_instances_data.items()
        }

        raw_task_order = data.get('task_order', list(instances.keys()))

        cleaned_task_order = [inst_id for inst_id in raw_task_order if inst_id in instances]

        # 如果清理后 task_order 为空，则使用所有实例ID
        if not cleaned_task_order:
            cleaned_task_order = list(instances.keys())

        settings_kwargs = {
            'name': data.get('name', ''),
            'resource_name': data.get('resource_name', ''),
            'task_instances': instances,
            'task_order': cleaned_task_order
        }
        return cls(**settings_kwargs)


@dataclass
class ScheduleTask:
    """定时任务配置。"""
    device_name: str  # 此任务所属的设备
    resource_name: str  # 此任务所属的资源
    enabled: bool = False
    schedule_time: str = ""  # 格式: "HH:mm:ss"
    schedule_type: str = "daily"  # "once", "daily", "weekly"
    week_days: List[str] = field(default_factory=list)  # 周执行时的星期列表 ["周一", "周二", ...]
    settings_name: str = ""  # 使用的配置方案
    notify: bool = False  # 是否发送通知
    force_stop: bool = False  # 运行前是否强制停止所有任务
    schedule_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_ui_format(self) -> dict:
        result = {
            'schedule_type': self.get_schedule_type_display(),
            'time': self.schedule_time,
            'config_scheme': self.settings_name or '默认配置',
            'notify': self.notify,
            'force_stop': self.force_stop,
            'enabled': self.enabled
        }
        if self.schedule_type == 'weekly' and self.week_days:
            result['week_days'] = self.week_days
        if self.schedule_id:
            result['id'] = self.schedule_id
        return result

    def get_schedule_type_display(self) -> str:
        """获取显示用的调度类型"""
        type_map = {
            'once': '单次执行',
            'daily': '每日执行',
            'weekly': '每周执行'
        }
        return type_map.get(self.schedule_type, '每日执行')

    @staticmethod
    def from_ui_format(ui_data: dict, device_name: str, resource_name: str) -> 'ScheduleTask':
        """从UI格式创建ScheduleTask对象"""
        schedule_type_map = {
            '单次执行': 'once',
            '每日执行': 'daily',
            '每周执行': 'weekly'
        }

        init_args = {
            'device_name': device_name,
            'resource_name': resource_name,
            'enabled': ui_data.get('status', '活动') == '活动',
            'schedule_time': ui_data.get('time', ''),
            'schedule_type': schedule_type_map.get(ui_data.get('schedule_type', '每日执行'), 'daily'),
            'week_days': ui_data.get('week_days', []),
            'settings_name': ui_data.get('config_scheme', '默认配置'),
            'notify': ui_data.get('notify', False),
            'force_stop': ui_data.get('force_stop', False),
        }
        if ui_data.get('id'):
            init_args['schedule_id'] = ui_data['id']
        return ScheduleTask(**init_args)


@dataclass
class Resource:
    """设备内的资源配置。"""
    resource_name: str
    settings_name: str  # 引用 ResourceSettings 的名称
    resource_pack: str = ""
    enable: bool = False
    # 内部引用，不会被序列化
    _app_config: Optional['AppConfig'] = field(default=None, repr=False, compare=False)

    def set_app_config(self, app_config: 'AppConfig'):
        """设置对 AppConfig 的引用。"""
        self._app_config = app_config


@dataclass
class ResourceUpdateConfig:
    """记录资源的更新方式和更新频道。"""
    method: str
    channel: str = "stable"  # 默认为稳定版


def schedule_task_to_dict(schedule: ScheduleTask) -> Dict[str, Any]:
    """辅助函数，将 ScheduleTask 对象转换为字典。"""
    result = {
        'device_name': schedule.device_name,
        'resource_name': schedule.resource_name,
        'enabled': schedule.enabled,
        'schedule_time': schedule.schedule_time,
        'schedule_type': schedule.schedule_type,
        'settings_name': schedule.settings_name,
        'notify': schedule.notify,
        'force_stop': schedule.force_stop
    }
    if schedule.week_days:
        result['week_days'] = schedule.week_days
    if schedule.schedule_id:
        result['schedule_id'] = schedule.schedule_id
    return result


@dataclass
class DeviceConfig:
    """设备配置的数据类。"""
    device_name: str
    device_type: DeviceType
    controller_config: Union[AdbDevice, Win32Device]
    resources: List[Resource] = field(default_factory=list)
    start_command: str = ""
    auto_start_emulator: bool = False  # 是否自动启动模拟器
    auto_close_emulator: bool = False  # 是否自动关闭模拟器
    # emulator_start_wait_time 已从此移除


@dataclass
class AppConfig:
    """主应用配置数据类，包含顶层设备列表和全局设置。"""
    # 新增版本号，用于控制和触发迁移逻辑。默认为1代表旧版本。
    config_version: int = 1
    devices: List[DeviceConfig] = field(default_factory=list)
    resource_settings: List[ResourceSettings] = field(default_factory=list)
    schedule_tasks: List[ScheduleTask] = field(default_factory=list)
    source_file: str = ""
    CDK: str = ""
    github_token: str = ""

    # 修改：用于存储每个特定资源的更新方法和频道
    resource_update_methods: Dict[str, ResourceUpdateConfig] = field(default_factory=dict)

    update_method: str = field(default="github")
    receive_beta_update: bool = False
    auto_check_update: bool = False
    window_size: str = field(default="800x600")
    window_position: str = field(default="center")
    debug_model: bool = False
    minimize_to_tray_on_close: Optional[bool] = False
    emulator_start_wait_time: int = 30  # 通用参数：模拟器启动等待时间（秒）

    def add_or_update_resource_setting(self, setting_data: Dict[str, Any]):
        """
        添加一个新的配置方案或更新一个现有的。
        它接收一个字典，将其解析为 ResourceSettings 对象。
        通过 (resource_name, name) 的组合来判断是更新还是添加。
        """
        if not isinstance(setting_data, dict):
            return

        new_setting = ResourceSettings.from_dict(setting_data)

        # 如果关键信息缺失，则无法进行有效匹配，跳过此项
        if not new_setting.resource_name or not new_setting.name:
            return

        # 遍历现有列表，查找匹配项
        for i, existing_setting in enumerate(self.resource_settings):
            if (existing_setting.resource_name == new_setting.resource_name and
                    existing_setting.name == new_setting.name):
                self.resource_settings[i] = new_setting  # 找到了，直接覆盖
                return  # 完成操作，退出方法

        # 如果循环结束都没有找到，说明是新的，添加到列表末尾
        self.resource_settings.append(new_setting)

    def add_or_update_schedule_task(self, task_data: Dict[str, Any]):
        """
        添加一个新的定时任务或更新一个现有的。
        它接收一个字典，将其解析为 ScheduleTask 对象。
        通过 schedule_id 来判断是更新还是添加。
        """
        if not isinstance(task_data, dict):
            return

        # 过滤掉无关字段，避免创建对象时出错
        filtered_task_data = self._filter_kwargs_for_class(ScheduleTask, task_data)
        new_task = ScheduleTask(**filtered_task_data)

        # 确保任务有一个ID
        if not new_task.schedule_id:
            new_task.schedule_id = uuid.uuid4().hex[:8]

        # 遍历现有列表，查找匹配项
        for i, existing_task in enumerate(self.schedule_tasks):
            if hasattr(existing_task, 'schedule_id') and existing_task.schedule_id == new_task.schedule_id:
                self.schedule_tasks[i] = new_task  # 找到了，直接覆盖
                return  # 完成操作，退出方法

        # 如果循环结束都没有找到，说明是新的，添加到列表末尾
        self.schedule_tasks.append(new_task)

    def get_resource_update_method(self, resource_name: str) -> str:
        specific_config = self.resource_update_methods.get(resource_name)
        if specific_config:
            return specific_config.method
        return self.update_method

    def get_resource_update_channel(self, resource_name: str) -> str:
        """
        获取指定资源的更新频道。
        如果设置了特定频道，则返回它。
        否则，根据全局设置（receive_beta_update）决定。
        """
        specific_config = self.resource_update_methods.get(resource_name)
        if specific_config:
            return specific_config.channel
        return "beta" if self.receive_beta_update else "stable"

    def link_resources_to_config(self):
        """将所有资源链接到此 AppConfig 实例。"""
        for device in self.devices:
            for resource in device.resources:
                resource.set_app_config(self)

    @staticmethod
    def _get_encryption_key() -> bytes:
        env_key = os.environ.get('APP_CONFIG_ENCRYPTION_KEY')
        if env_key:
            try:
                key_bytes = base64.urlsafe_b64decode(env_key + '=' * (-len(env_key) % 4))
                if len(key_bytes) == 32:
                    return env_key.encode()
            except Exception:
                pass
        default_phrase = "app-config-default-encryption-key"
        hash_object = hashlib.sha256(default_phrase.encode())
        key = base64.urlsafe_b64encode(hash_object.digest())
        return key

    def _encrypt_cdk(self) -> str:
        if not self.CDK: return ""
        key = self._get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(self.CDK.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')

    def _encrypt_github_token(self) -> str:
        if not self.github_token: return ""
        key = self._get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(self.github_token.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')

    @classmethod
    def _decrypt_cdk(cls, encrypted_cdk: str) -> str:
        if not encrypted_cdk: return ""
        key = cls._get_encryption_key()
        f = Fernet(key)
        try:
            decrypted = f.decrypt(base64.urlsafe_b64decode(encrypted_cdk))
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"解密CDK失败: {e}")
            return ""

    @classmethod
    def _decrypt_github_token(cls, encrypted_token: str) -> str:
        if not encrypted_token: return ""
        key = cls._get_encryption_key()
        f = Fernet(key)
        try:
            decrypted = f.decrypt(base64.urlsafe_b64decode(encrypted_token))
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"解密 GitHub Token 失败: {e}")
            return ""

    @classmethod
    def from_json_file(cls, file_path: str) -> 'AppConfig':
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        config = cls.from_dict(json_data)
        config.source_file = file_path
        return config

    def to_json_file(self, file_path: str = None, indent=4):
        if file_path is None:
            if not self.source_file:
                raise ValueError("未提供保存路径且未记录原始文件路径。")
            file_path = self.source_file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)

    @staticmethod
    def _filter_kwargs_for_class(target_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
        if not hasattr(target_class, '__dataclass_fields__'):
            return data
        valid_keys = target_class.__dataclass_fields__.keys()
        return {key: value for key, value in data.items() if key in valid_keys}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        config_version = data.get('config_version', 1)
        resource_settings_data = data.get('resource_settings', [])
        resource_settings = []
        for settings_data in resource_settings_data:
            if config_version < 2 and 'selected_tasks' in settings_data:
                migrated_instances = {}
                migrated_order = []
                options_data = settings_data.get('options', [])
                shared_options = [OptionConfig(**cls._filter_kwargs_for_class(OptionConfig, opt_data)) for opt_data in
                                  options_data]
                for task_name in settings_data.get('selected_tasks', []):
                    instance_id = uuid.uuid4().hex
                    new_instance = TaskInstance(
                        instance_id=instance_id,
                        task_name=task_name,
                        enabled=True,
                        options=shared_options
                    )
                    migrated_instances[instance_id] = new_instance
                    migrated_order.append(instance_id)
                settings_kwargs = {
                    'name': settings_data.get('name', ''),
                    'resource_name': settings_data.get('resource_name', ''),
                    'task_instances': migrated_instances,
                    'task_order': migrated_order
                }
                resource_settings.append(ResourceSettings(**settings_kwargs))
            else:
                resource_settings.append(ResourceSettings.from_dict(settings_data))
        devices_data = data.get('devices', [])
        device_configs = []
        for device_data in devices_data:
            device_type_str = device_data.get('device_type', 'adb')
            try:
                device_type = DeviceType(device_type_str)
            except ValueError:
                device_type = DeviceType.ADB
            if device_type == DeviceType.ADB:
                controller_config_data = device_data.get('controller_config', device_data.get('adb_config', {}))
                controller_config = AdbDevice(**cls._filter_kwargs_for_class(AdbDevice, controller_config_data))
            else:
                controller_config_data = device_data.get('controller_config', {})
                controller_config = Win32Device(**cls._filter_kwargs_for_class(Win32Device, controller_config_data))
            resources_data = device_data.get('resources', [])
            resources = [Resource(**cls._filter_kwargs_for_class(Resource, res_data)) for res_data in resources_data]
            device_kwargs = {k: v for k, v in device_data.items() if
                             k not in ('controller_config', 'adb_config', 'resources', 'device_type')}
            filtered_device_kwargs = cls._filter_kwargs_for_class(DeviceConfig, device_kwargs)
            device_configs.append(
                DeviceConfig(**filtered_device_kwargs, device_type=device_type, controller_config=controller_config,
                             resources=resources))

        schedule_tasks_data = data.get('schedule_tasks', [])
        schedule_tasks = [ScheduleTask(**cls._filter_kwargs_for_class(ScheduleTask, task_data)) for task_data in
                          schedule_tasks_data]
        config = AppConfig(
            devices=device_configs,
            resource_settings=resource_settings,
            schedule_tasks=schedule_tasks
        )
        config.config_version = 2
        encrypted_cdk = data.get('encrypted_cdk', '')
        if encrypted_cdk:
            config.CDK = cls._decrypt_cdk(encrypted_cdk)
        else:
            config.CDK = data.get('CDK', '')
        encrypted_github_token = data.get('encrypted_github_token', '')
        if encrypted_github_token:
            config.github_token = cls._decrypt_github_token(encrypted_github_token)
        else:
            config.github_token = data.get('github_token', '')
        raw_update_methods = data.get('resource_update_methods', {})
        migrated_update_methods = {}
        for name, value in raw_update_methods.items():
            if isinstance(value, str):
                migrated_update_methods[name] = ResourceUpdateConfig(method=value, channel="stable")
            elif isinstance(value, dict):
                migrated_update_methods[name] = ResourceUpdateConfig(
                    method=value.get('method', ''),
                    channel=value.get('channel', 'stable')
                )
        config.resource_update_methods = migrated_update_methods
        config.update_method = data.get('update_method', 'github')
        config.receive_beta_update = data.get('receive_beta_update', False)
        config.auto_check_update = data.get('auto_check_update', False)
        config.window_size = data.get('window_size', "800x600")
        config.window_position = data.get('window_position', "center")
        config.debug_model = data.get('debug_model', False)
        config.minimize_to_tray_on_close = data.get('minimize_to_tray_on_close', False)
        # 从配置字典中读取通用等待时间，如果不存在则默认为 30
        config.emulator_start_wait_time = data.get('emulator_start_wait_time', 30)

        config.link_resources_to_config()
        return config

    def to_dict(self) -> Dict[str, Any]:
        result = {"config_version": self.config_version}
        if self.CDK: result["encrypted_cdk"] = self._encrypt_cdk()
        if self.github_token: result["encrypted_github_token"] = self._encrypt_github_token()
        result["resource_update_methods"] = {
            name: resource_update_config_to_dict(config)
            for name, config in self.resource_update_methods.items()
        }
        if self.update_method: result["update_method"] = self.update_method
        result["receive_beta_update"] = getattr(self, "receive_beta_update", False)
        result["auto_check_update"] = getattr(self, "auto_check_update", False)
        result["devices"] = [device_config_to_dict(device) for device in self.devices]
        result["resource_settings"] = [resource_settings_to_dict(settings) for settings in self.resource_settings]
        result["schedule_tasks"] = [schedule_task_to_dict(task) for task in self.schedule_tasks]
        result["window_size"] = self.window_size
        result["window_position"] = self.window_position
        result["debug_model"] = self.debug_model
        result["minimize_to_tray_on_close"] = self.minimize_to_tray_on_close
        # 将通用等待时间写入配置字典
        result["emulator_start_wait_time"] = self.emulator_start_wait_time
        return result


def device_config_to_dict(device: DeviceConfig) -> Dict[str, Any]:
    device_dict = device.__dict__.copy()
    if device.device_type == DeviceType.ADB:
        device_dict['controller_config'] = adb_device_to_dict(device.controller_config)
    else:
        device_dict['controller_config'] = win32_device_to_dict(device.controller_config)
    device_dict['device_type'] = device.device_type.value
    device_dict['resources'] = [resource_to_dict(resource) for resource in device.resources]
    return device_dict


def adb_device_to_dict(adb_device: AdbDevice) -> Dict[str, Any]: return adb_device.__dict__


def win32_device_to_dict(win32_device: Win32Device) -> Dict[str, Any]: return win32_device.__dict__


def resource_to_dict(resource: Resource) -> Dict[str, Any]:
    return {
        'resource_name': resource.resource_name,
        'settings_name': resource.settings_name,
        'resource_pack': resource.resource_pack,
        'enable': resource.enable
    }


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]: return option.__dict__


def task_instance_to_dict(instance: TaskInstance) -> Dict[str, Any]:
    instance_dict = instance.__dict__.copy()
    instance_dict['options'] = [option_config_to_dict(opt) for opt in instance.options]
    return instance_dict


def resource_update_config_to_dict(config: ResourceUpdateConfig) -> Dict[str, str]:
    return config.__dict__


def resource_settings_to_dict(settings: ResourceSettings) -> Dict[str, Any]:
    return {
        'name': settings.name,
        'resource_name': settings.resource_name,
        'task_instances': {inst_id: task_instance_to_dict(inst) for inst_id, inst in settings.task_instances.items()},
        'task_order': settings.task_order
    }