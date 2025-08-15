import base64
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union, Optional, Type

from cryptography.fernet import Fernet

from app.utils.notification_manager import notification_manager


class DeviceType(Enum):
    """设备控制器类型的枚举。"""
    ADB = "adb"
    WIN32 = "win32"


@dataclass
class AdbDevice:
    """ADB设备配置的数据类。"""
    name: str
    adb_path: str  # 路径使用 str 类型，匹配 JSON 中的字符串路径
    address: str
    screencap_methods: int
    input_methods: int
    agent_path: Optional[str] = None  # 新字段
    notification_handler: Optional[Any] = None  # 新字段
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
class ResourceSettings:
    """资源的设置配置。"""
    name: str  # 设置的唯一名称
    resource_name: str  # 表示这个设置属于哪种资源
    selected_tasks: List[str] = field(default_factory=list)
    options: List[OptionConfig] = field(default_factory=list)


# app_config.py - 定时任务相关的数据类
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
    enable: bool = False
    # 内部引用，不会被序列化
    _app_config: Optional['AppConfig'] = field(default=None, repr=False, compare=False)

    @property
    def selected_tasks(self) -> List[str]:
        """从引用的设置中获取 selected_tasks。"""
        if not self._app_config:
            return []
        for settings in self._app_config.resource_settings:
            if settings.name == self.settings_name and settings.resource_name == self.resource_name:
                return settings.selected_tasks
        return []

    @property
    def options(self) -> List['OptionConfig']:
        """从引用的设置中获取 options。"""
        if not self._app_config:
            return []
        for settings in self._app_config.resource_settings:
            if settings.name == self.settings_name and settings.resource_name == self.resource_name:
                return settings.options
        return []

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
    device_type: DeviceType  # 新字段，用于指示控制器类型
    controller_config: Union[AdbDevice, Win32Device]  # 从 adb_config 更改而来
    resources: List[Resource] = field(default_factory=list)
    start_command: str = ""


@dataclass
class AppConfig:
    """主应用配置数据类，包含顶层设备列表和全局设置。"""
    devices: List[DeviceConfig] = field(default_factory=list)
    resource_settings: List[ResourceSettings] = field(default_factory=list)
    schedule_tasks: List[ScheduleTask] = field(default_factory=list)  # 新字段，用于应用级别的定时任务
    source_file: str = ""  # 用于记录加载的文件路径，但不保存到输出 JSON 中
    CDK: str = ""
    update_method: str = field(default="github")
    receive_beta_update: bool = False
    auto_check_update: bool = False
    window_size:"str"=field(default="800x600")
    window_position: str = field(default="center")  # 新增字段，记录窗口位置（x,y）
    debug_model:bool = False

    def link_resources_to_config(self):
        """将所有资源链接到此 AppConfig 实例。"""
        for device in self.devices:
            for resource in device.resources:
                resource.set_app_config(self)

    @staticmethod
    def _get_encryption_key() -> bytes:
        """获取加密密钥。优先从环境变量获取，如果不存在则使用应用程序名称生成一个固定密钥。"""
        env_key = os.environ.get('APP_CONFIG_ENCRYPTION_KEY')
        if env_key:
            try:
                # 尝试将环境变量中的密钥解码为有效的Fernet密钥
                key_bytes = base64.urlsafe_b64decode(env_key + '=' * (-len(env_key) % 4))
                if len(key_bytes) == 32:
                    return env_key.encode()
            except Exception:
                pass  # 如果解码失败，则继续使用默认密钥

        # 如果环境变量不存在或不是有效的Fernet密钥，则使用应用程序名称生成一个固定密钥
        default_phrase = "app-config-default-encryption-key"
        hash_object = hashlib.sha256(default_phrase.encode())
        key = base64.urlsafe_b64encode(hash_object.digest())
        return key

    def _encrypt_cdk(self) -> str:
        """加密CDK"""
        if not self.CDK:
            return ""
        key = self._get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(self.CDK.encode('utf-8'))
        return base64.urlsafe_b64encode(encrypted).decode('utf-8')

    @classmethod
    def _decrypt_cdk(cls, encrypted_cdk: str) -> str:
        """解密CDK"""
        if not encrypted_cdk:
            return ""
        key = cls._get_encryption_key()
        f = Fernet(key)
        try:
            decrypted = f.decrypt(base64.urlsafe_b64decode(encrypted_cdk))
            return decrypted.decode('utf-8')
        except Exception as e:
            print(f"解密CDK失败: {e}")
            return ""

    @classmethod
    def from_json_file(cls, file_path: str) -> 'AppConfig':
        """从 JSON 文件加载 AppConfig 并记录来源文件路径。"""
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        config = cls.from_dict(json_data)
        config.source_file = file_path  # 记录来源文件路径
        return config

    def to_json_file(self, file_path: str = None, indent=4):
        """将 AppConfig 导出为 JSON 文件。

        如果未传入 file_path，则使用记录的 source_file 进行保存。
        注意：输出的 JSON 文件中不包含 source_file 属性。
        """
        if file_path is None:
            if not self.source_file:
                raise ValueError("未提供保存路径且未记录原始文件路径。")
            file_path = self.source_file
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)

    @staticmethod
    def _filter_kwargs_for_class(target_class: Type, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        过滤字典，仅保留目标 dataclass 中定义的字段。
        这可以防止在用旧配置文件启动新版程序时，因字段不匹配而报错。
        """
        if not hasattr(target_class, '__dataclass_fields__'):
            return data  # 如果不是 dataclass，则返回原始数据

        valid_keys = target_class.__dataclass_fields__.keys()
        return {key: value for key, value in data.items() if key in valid_keys}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建 AppConfig 对象，会自动跳过无法识别的属性。"""
        # 首先加载资源设置
        resource_settings_data = data.get('resource_settings', [])
        resource_settings = []
        for settings_data in resource_settings_data:
            options_data = settings_data.get('options', [])
            options = [OptionConfig(**cls._filter_kwargs_for_class(OptionConfig, option_data)) for option_data in
                       options_data]

            settings_kwargs = {k: v for k, v in settings_data.items() if k != 'options'}
            filtered_settings_kwargs = cls._filter_kwargs_for_class(ResourceSettings, settings_kwargs)
            resource_settings.append(ResourceSettings(**filtered_settings_kwargs, options=options))

        # 加载设备并迁移旧的定时任务
        devices_data = data.get('devices', [])
        device_configs = []
        migrated_schedules = []

        for device_data in devices_data:
            device_type_str = device_data.get('device_type', 'adb')
            try:
                device_type = DeviceType(device_type_str)
            except ValueError:
                device_type = DeviceType.ADB

            if device_type == DeviceType.ADB:
                controller_config_data = device_data.get('controller_config', device_data.get('adb_config', {}))
                controller_config = AdbDevice(**cls._filter_kwargs_for_class(AdbDevice, controller_config_data))
            else:  # WIN32
                controller_config_data = device_data.get('controller_config', {})
                controller_config = Win32Device(**cls._filter_kwargs_for_class(Win32Device, controller_config_data))

            resources_data = device_data.get('resources', [])
            resources = []
            for resource_data in resources_data:
                resource_data_copy = resource_data.copy()

                # 向后兼容：将定时任务从资源迁移到应用级别
                if 'schedules' in resource_data_copy:
                    for schedule_data in resource_data_copy['schedules']:
                        # 使用旧的ResourceSchedule的字段来创建新的ScheduleTask
                        schedule_kwargs = cls._filter_kwargs_for_class(ScheduleTask, schedule_data)
                        # 添加设备和资源上下文
                        schedule_kwargs['device_name'] = device_data.get('device_name')
                        schedule_kwargs['resource_name'] = resource_data_copy.get('resource_name')
                        migrated_schedules.append(ScheduleTask(**schedule_kwargs))
                    del resource_data_copy['schedules']
                # 移除其他旧的与定时任务相关的字段
                resource_data_copy.pop('schedules_enable', None)

                is_old_style = 'selected_tasks' in resource_data_copy or 'options' in resource_data_copy

                if is_old_style:
                    settings_name = f"{resource_data_copy['resource_name']}_settings"
                    options_data = resource_data_copy.get('options', [])
                    selected_tasks = resource_data_copy.get('selected_tasks', [])

                    existing_settings = next((s for s in resource_settings if s.name == settings_name), None)
                    if not existing_settings:
                        options = [OptionConfig(**cls._filter_kwargs_for_class(OptionConfig, option_data)) for
                                   option_data in options_data]
                        resource_settings.append(ResourceSettings(
                            name=settings_name,
                            resource_name=resource_data_copy['resource_name'],
                            selected_tasks=selected_tasks,
                            options=options
                        ))

                    resource_kwargs = {k: v for k, v in resource_data_copy.items() if
                                       k not in ('options', 'selected_tasks')}
                    filtered_resource_kwargs = cls._filter_kwargs_for_class(Resource, resource_kwargs)
                    resources.append(
                        Resource(**filtered_resource_kwargs, settings_name=settings_name))
                else:
                    filtered_resource_kwargs = cls._filter_kwargs_for_class(Resource, resource_data_copy)
                    resources.append(Resource(**filtered_resource_kwargs))

            device_kwargs = {k: v for k, v in device_data.items()
                             if k not in ('controller_config', 'adb_config', 'resources', 'device_type')}
            filtered_device_kwargs = cls._filter_kwargs_for_class(DeviceConfig, device_kwargs)
            device_configs.append(DeviceConfig(
                **filtered_device_kwargs,
                device_type=device_type,
                controller_config=controller_config,
                resources=resources
            ))

        # 加载新的应用级别定时任务
        schedule_tasks_data = data.get('schedule_tasks', [])
        schedule_tasks = [ScheduleTask(**cls._filter_kwargs_for_class(ScheduleTask, task_data)) for task_data in
                          schedule_tasks_data]

        # 将新的定时任务与迁移的合并
        schedule_tasks.extend(migrated_schedules)

        # 创建 AppConfig
        config = AppConfig(
            devices=device_configs,
            resource_settings=resource_settings,
            schedule_tasks=schedule_tasks
        )

        encrypted_cdk = data.get('encrypted_cdk', '')
        if encrypted_cdk:
            config.CDK = cls._decrypt_cdk(encrypted_cdk)
        else:
            config.CDK = data.get('CDK', '')

        config.update_method = data.get('update_method', 'github')
        config.receive_beta_update = data.get('receive_beta_update', False)
        config.auto_check_update = data.get('auto_check_update', False)
        config.window_size = data.get('window_size', "800x600")
        config.window_position = data.get('window_position', "center")
        config.debug_model = data.get('debug_model', False)

        config.link_resources_to_config()

        return config

    def to_dict(self) -> Dict[str, Any]:
        """将 AppConfig 对象转换为字典，不包含 source_file 属性。"""
        result = {}
        if self.CDK:
            # 加密CDK而不是直接保存
            result["encrypted_cdk"] = self._encrypt_cdk()
        if self.update_method:
            result["update_method"] = self.update_method
        result["receive_beta_update"] = getattr(self, "receive_beta_update", False)
        result["auto_check_update"] = getattr(self, "auto_check_update", False)
        result["devices"] = [device_config_to_dict(device) for device in self.devices]
        result["resource_settings"] = [resource_settings_to_dict(settings) for settings in self.resource_settings]
        result["schedule_tasks"] = [schedule_task_to_dict(task) for task in self.schedule_tasks]  # 序列化 schedule_tasks
        result["window_size"] = self.window_size
        result["window_position"] = self.window_position
        result["debug_model"] = self.debug_model
        return result


def device_config_to_dict(device: DeviceConfig) -> Dict[str, Any]:
    """辅助函数，将 DeviceConfig 对象转换为字典。"""
    device_dict = device.__dict__.copy()

    # 处理控制器配置
    if device.device_type == DeviceType.ADB:
        device_dict['controller_config'] = adb_device_to_dict(device.controller_config)
    else:  # WIN32
        device_dict['controller_config'] = win32_device_to_dict(device.controller_config)

    # 将 device_type 转换为字符串
    device_dict['device_type'] = device.device_type.value

    device_dict['resources'] = [resource_to_dict(resource) for resource in device.resources]
    return device_dict


def adb_device_to_dict(adb_device: AdbDevice) -> Dict[str, Any]:
    """辅助函数，将 AdbDevice 对象转换为字典。"""
    return adb_device.__dict__


def win32_device_to_dict(win32_device: Win32Device) -> Dict[str, Any]:
    """辅助函数，将 Win32Device 对象转换为字典。"""
    return win32_device.__dict__


def resource_to_dict(resource: Resource) -> Dict[str, Any]:
    """辅助函数，将 Resource 对象转换为字典。"""
    # 从序列化中排除 _app_config
    # 与定时任务相关的字段已被移除
    result = {
        'resource_name': resource.resource_name,
        'settings_name': resource.settings_name,
        'enable': resource.enable,
    }
    return result


def resource_settings_to_dict(settings: ResourceSettings) -> Dict[str, Any]:
    """辅助函数，将 ResourceSettings 对象转换为字典。"""
    settings_dict = settings.__dict__.copy()
    settings_dict['options'] = [option_config_to_dict(option) for option in settings.options]
    return settings_dict


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]:
    """辅助函数，将 OptionConfig 对象转换为字典。"""
    return option.__dict__