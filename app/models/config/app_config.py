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


# app_config.py - 定时任务相关的数据类 (这部分未作修改)
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
    schedule_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_ui_format(self) -> dict:
        """转换为UI所需的格式"""
        result = {
            'schedule_type': self.get_schedule_type_display(),
            'time': self.schedule_time,
            'config_scheme': self.settings_name or '默认配置',
            'notify': self.notify,
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

    # 移除了旧的 selected_tasks 和 options 属性，因为它们已不再 ResourceSettings 中
    # 访问任务实例现在需要通过 self._app_config 获取对应的 ResourceSettings

    def set_app_config(self, app_config: 'AppConfig'):
        """设置对 AppConfig 的引用。"""
        self._app_config = app_config


def schedule_task_to_dict(schedule: ScheduleTask) -> Dict[str, Any]:
    """辅助函数，将 ScheduleTask 对象转换为字典。"""
    result = {
        'device_name': schedule.device_name,
        'resource_name': schedule.resource_name,
        'enabled': schedule.enabled,
        'schedule_time': schedule.schedule_time,
        'schedule_type': schedule.schedule_type,
        'settings_name': schedule.settings_name,
        'notify': schedule.notify
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

    # 新增：用于存储每个特定资源的更新方法
    resource_update_methods: Dict[str, str] = field(default_factory=dict)

    update_method: str = field(default="github")
    receive_beta_update: bool = False
    auto_check_update: bool = False
    window_size: str = field(default="800x600")
    window_position: str = field(default="center")
    debug_model: bool = False
    minimize_to_tray_on_close: Optional[bool] = False

    def get_resource_update_method(self, resource_name: str) -> str:
        """
        获取指定资源的更新方法。
        如果为该资源设置了特定的更新方法，则返回它。
        否则，返回全局默认的更新方法。
        """
        return self.resource_update_methods.get(resource_name, self.update_method)

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
        """从 JSON 文件加载 AppConfig 并记录来源文件路径。"""
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        config = cls.from_dict(json_data)
        config.source_file = file_path
        return config

    def to_json_file(self, file_path: str = None, indent=4):
        """将 AppConfig 导出为 JSON 文件。"""
        if file_path is None:
            if not self.source_file:
                raise ValueError("未提供保存路径且未记录原始文件路径。")
            file_path = self.source_file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)

    @staticmethod
    def _filter_kwargs_for_class(target_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤字典，仅保留目标 dataclass 中定义的字段。"""
        if not hasattr(target_class, '__dataclass_fields__'):
            return data
        valid_keys = target_class.__dataclass_fields__.keys()
        return {key: value for key, value in data.items() if key in valid_keys}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建 AppConfig 对象，并处理向后兼容的数据迁移。"""
        # 检查配置版本，如果不存在则默认为1 (旧版本)
        config_version = data.get('config_version', 1)

        # 加载资源设置，并根据版本进行迁移
        resource_settings_data = data.get('resource_settings', [])
        resource_settings = []
        for settings_data in resource_settings_data:
            # **核心迁移逻辑**
            # 如果是旧版本且包含 'selected_tasks'，则执行迁移
            if config_version < 2 and 'selected_tasks' in settings_data:
                # 这是一个旧版 ResourceSettings，需要转换
                migrated_instances = {}
                migrated_order = []

                # 旧版的 options 是共享的
                options_data = settings_data.get('options', [])
                shared_options = [OptionConfig(**cls._filter_kwargs_for_class(OptionConfig, opt_data)) for opt_data in
                                  options_data]

                for task_name in settings_data.get('selected_tasks', []):
                    instance_id = uuid.uuid4().hex
                    new_instance = TaskInstance(
                        instance_id=instance_id,
                        task_name=task_name,
                        enabled=True,  # 旧版任务默认启用
                        options=shared_options  # 所有任务实例共享旧的options
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
                # 这是一个新版 ResourceSettings，正常加载
                task_instances_data = settings_data.get('task_instances', {})
                instances = {
                    inst_id: TaskInstance(
                        **{**inst_data, 'options': [OptionConfig(**opt) for opt in inst_data.get('options', [])]}
                    )
                    for inst_id, inst_data in task_instances_data.items()
                }

                settings_kwargs = {
                    'name': settings_data.get('name', ''),
                    'resource_name': settings_data.get('resource_name', ''),
                    'task_instances': instances,
                    'task_order': settings_data.get('task_order', list(instances.keys()))  # 兼容没有task_order的早期v2版本
                }
                resource_settings.append(ResourceSettings(**settings_kwargs))

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

        # 创建 AppConfig 实例
        config = AppConfig(
            devices=device_configs,
            resource_settings=resource_settings,
            schedule_tasks=schedule_tasks
        )

        # 在内存中将版本号更新为最新版 (2)
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

        config.resource_update_methods = data.get('resource_update_methods', {})

        config.update_method = data.get('update_method', 'github')
        config.receive_beta_update = data.get('receive_beta_update', False)
        config.auto_check_update = data.get('auto_check_update', False)
        config.window_size = data.get('window_size', "800x600")
        config.window_position = data.get('window_position', "center")
        config.debug_model = data.get('debug_model', False)
        config.minimize_to_tray_on_close = data.get('minimize_to_tray_on_close', False)

        config.link_resources_to_config()
        return config

    def to_dict(self) -> Dict[str, Any]:
        """将 AppConfig 对象转换为字典，使用新的数据结构。"""
        result = {"config_version": self.config_version}  # 写入最新的版本号
        if self.CDK: result["encrypted_cdk"] = self._encrypt_cdk()
        if self.github_token: result["encrypted_github_token"] = self._encrypt_github_token()
        # 修改：将 resource_update_methods 字典保存到结果中
        result["resource_update_methods"] = self.resource_update_methods

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
        return result


def device_config_to_dict(device: DeviceConfig) -> Dict[str, Any]:
    # ... (此函数及以下辅助函数未作修改) ...
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
    result = {
        'resource_name': resource.resource_name,
        'settings_name': resource.settings_name,
        'resource_pack': resource.resource_pack,
        'enable': resource.enable
    }
    return result


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]: return option.__dict__


def task_instance_to_dict(instance: TaskInstance) -> Dict[str, Any]:
    """辅助函数，将 TaskInstance 对象转换为字典。"""
    instance_dict = instance.__dict__.copy()
    instance_dict['options'] = [option_config_to_dict(opt) for opt in instance.options]
    return instance_dict


def resource_settings_to_dict(settings: ResourceSettings) -> Dict[str, Any]:
    """辅助函数，将 ResourceSettings 对象转换为字典（新结构）。"""
    return {
        'name': settings.name,
        'resource_name': settings.resource_name,
        'task_instances': {inst_id: task_instance_to_dict(inst) for inst_id, inst in settings.task_instances.items()},
        'task_order': settings.task_order
    }