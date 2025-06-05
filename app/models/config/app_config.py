import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Union, Optional

from cryptography.fernet import Fernet


class DeviceType(Enum):
    """Enum for device controller types."""
    ADB = "adb"
    WIN32 = "win32"


@dataclass
class AdbDevice:
    """ADB device configuration dataclass."""
    name: str
    adb_path: str  # 路径使用 str 类型，匹配 JSON 中的字符串路径
    address: str
    screencap_methods: int
    input_methods: int
    agent_path: Optional[str] = None  # New field
    notification_handler: Optional[Any] = None  # New field
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Win32Device:
    """Win32 device configuration dataclass."""
    hWnd: int
    screencap_method: int
    input_method: int
    notification_handler: Optional[Any] = None


@dataclass
class OptionConfig:
    """Option configuration for a task or resource."""
    option_name: str
    value: Any


@dataclass
class ResourceSettings:
    """Settings configuration for a resource."""
    name: str  # 设置的唯一名称
    resource_name: str  # 表示这个设置属于哪种资源
    selected_tasks: List[str] = field(default_factory=list)
    options: List[OptionConfig] = field(default_factory=list)

# 首先，创建一个新的数据类来表示资源的定时任务配置
@dataclass
class ResourceSchedule:
    """资源的定时任务配置。"""
    enabled: bool = False
    schedule_time: str = ""  # Changed from List[str] to a single string
    settings_name: str = ""  # 该定时任务启用的配置文件

# 修改 Resource 类，添加schedules字段
@dataclass
class Resource:
    """Resource configuration within a device."""
    resource_name: str
    settings_name: str  # 引用 ResourceSettings 的名称
    enable: bool = False
    schedules_enable: bool = False  # New attribute to enable/disable resource schedules
    schedules: List[ResourceSchedule] = field(default_factory=list)  # 资源的定时任务列表
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
    def options(self) -> List[OptionConfig]:
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

@dataclass
class DeviceConfig:
    """Device configuration dataclass."""
    device_name: str
    device_type: DeviceType  # New field to indicate controller type
    controller_config: Union[AdbDevice, Win32Device]  # Changed from adb_config
    resources: List[Resource] = field(default_factory=list)
    start_command: str = ""


@dataclass
class AppConfig:
    """主设备配置数据类，包含顶层版本信息和设备列表。"""
    devices: List[DeviceConfig] = field(default_factory=list)
    resource_settings: List[ResourceSettings] = field(default_factory=list)  # 新字段
    source_file: str = ""  # 用于记录加载的文件路径，但不保存到输出 JSON 中
    CDK: str = ""
    update_method: str = field(default="github")
    receive_beta_update: bool = False
    auto_check_update: bool = False
    window_size:"str"=field(default="800x600")
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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建 AppConfig 对象。"""
        # 首先加载资源设置
        resource_settings_data = data.get('resource_settings', [])
        resource_settings = []
        for settings_data in resource_settings_data:
            options_data = settings_data.get('options', [])
            options = [OptionConfig(**option_data) for option_data in options_data]
            settings_kwargs = {k: v for k, v in settings_data.items() if k != 'options'}
            resource_settings.append(ResourceSettings(**settings_kwargs, options=options))

        # 加载设备
        devices_data = data.get('devices', [])
        device_configs = []

        for device_data in devices_data:
            # 确定设备类型
            device_type_str = device_data.get('device_type', 'adb')  # 默认为adb类型以兼容旧配置
            try:
                device_type = DeviceType(device_type_str)  # 尝试将字符串转换为枚举
            except ValueError:
                # 如果转换失败(无效的设备类型字符串)，默认为ADB
                device_type = DeviceType.ADB

            # 根据设备类型创建对应的配置
            if device_type == DeviceType.ADB:
                controller_config_data = device_data.get('controller_config', device_data.get('adb_config', {}))
                controller_config = AdbDevice(**controller_config_data)
            else:  # WIN32
                controller_config_data = device_data.get('controller_config', {})
                controller_config = Win32Device(**controller_config_data)

            resources_data = device_data.get('resources', [])
            resources = []
            for resource_data in resources_data:
                # 处理资源的定时任务
                schedules = []
                resource_data_copy = resource_data.copy()
                if 'schedules' in resource_data_copy:
                    for schedule_data in resource_data_copy['schedules']:
                        schedules.append(ResourceSchedule(**schedule_data))

                    # 从resource_data中移除schedules，避免传递给Resource构造函数
                    del resource_data_copy['schedules']

                # 检查是否为旧式资源（直接包含selected_tasks和options）
                is_old_style = 'selected_tasks' in resource_data_copy or 'options' in resource_data_copy

                if is_old_style:
                    # 为向后兼容，创建新的设置
                    settings_name = f"{resource_data_copy['resource_name']}_settings"
                    options_data = resource_data_copy.get('options', [])
                    selected_tasks = resource_data_copy.get('selected_tasks', [])

                    # 检查设置是否已存在
                    existing_settings = next((s for s in resource_settings if s.name == settings_name), None)
                    if not existing_settings:
                        # 创建新设置
                        options = [OptionConfig(**option_data) for option_data in options_data]
                        resource_settings.append(ResourceSettings(
                            name=settings_name,
                            resource_name=resource_data_copy['resource_name'],
                            selected_tasks=selected_tasks,
                            options=options
                        ))

                    # 创建引用设置的资源
                    resource_kwargs = {k: v for k, v in resource_data_copy.items()
                                       if k not in ('options', 'selected_tasks')}
                    resources.append(Resource(**resource_kwargs, settings_name=settings_name, schedules=schedules))
                else:
                    # 新式资源与settings_name引用
                    resources.append(Resource(**resource_data_copy, schedules=schedules))

            # 排除 controller_config/adb_config 与 resources 字段后创建 DeviceConfig 对象
            device_kwargs = {k: v for k, v in device_data.items()
                             if k not in ('controller_config', 'adb_config', 'resources', 'device_type')}
            device_configs.append(DeviceConfig(
                **device_kwargs,
                device_type=device_type,
                controller_config=controller_config,
                resources=resources
            ))

        # 创建 AppConfig
        config = AppConfig(
            devices=device_configs,
            resource_settings=resource_settings
        )


        # 处理加密的CDK
        encrypted_cdk = data.get('encrypted_cdk', '')
        if encrypted_cdk:
            config.CDK = cls._decrypt_cdk(encrypted_cdk)
        else:
            # 向后兼容：如果存在明文CDK，则使用它
            config.CDK = data.get('CDK', '')

        config.update_method = data.get('update_method', 'github')
        config.receive_beta_update = data.get('receive_beta_update', False)
        config.auto_check_update = data.get('auto_check_update', False)
        config.window_size = data.get('window_size', "800x600")
        config.debug_model=data.get('debug_model', False)

        # 将资源链接到AppConfig
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
        result["window_size"]= self.window_size
        result["debug_model"]=self.debug_model
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


# 修改 resource_to_dict 函数，处理资源级定时任务
def resource_to_dict(resource: Resource) -> Dict[str, Any]:
    """辅助函数，将 Resource 对象转换为字典。"""
    # 从序列化中排除 _app_config
    result = {
        'resource_name': resource.resource_name,
        'settings_name': resource.settings_name,
        'enable': resource.enable,
        'schedules_enable': resource.schedules_enable  # Add the new field
    }

    # 如果有定时任务，则添加到结果中
    if resource.schedules:
        result['schedules'] = [resource_schedule_to_dict(schedule) for schedule in resource.schedules]

    return result
# 添加新的辅助函数，将 ResourceSchedule 对象转换为字典
def resource_schedule_to_dict(schedule: ResourceSchedule) -> Dict[str, Any]:
    """辅助函数，将 ResourceSchedule 对象转换为字典。"""
    return schedule.__dict__

def resource_settings_to_dict(settings: ResourceSettings) -> Dict[str, Any]:
    """辅助函数，将 ResourceSettings 对象转换为字典。"""
    settings_dict = settings.__dict__.copy()
    settings_dict['options'] = [option_config_to_dict(option) for option in settings.options]
    return settings_dict


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]:
    """辅助函数，将 OptionConfig 对象转换为字典。"""
    return option.__dict__
