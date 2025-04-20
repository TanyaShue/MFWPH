import base64
import hashlib
import os
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Union, Optional, Tuple
from enum import Enum
from pathlib import Path
from cryptography.fernet import Fernet


class DeviceType(Enum):
    """Enum for device controller types."""
    ADB = "adb"
    WIN32 = "win32"


@dataclass
class AdbDevice:
    """ADB device configuration dataclass."""
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
class ResourceProfile:
    """Independent resource profile that can be shared across devices."""
    resource_type: str  # The type/name of resource this profile belongs to
    profile_name: str  # A unique name for this profile
    selected_tasks: List[str] = field(default_factory=list)
    options: List[OptionConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceProfile':
        """Create ResourceProfile from dictionary."""
        options_data = data.get('options', [])
        options = [OptionConfig(**option_data) for option_data in options_data]
        
        return cls(
            resource_type=data.get('resource_type', ''),
            profile_name=data.get('profile_name', ''),
            selected_tasks=data.get('selected_tasks', []),
            options=options
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert ResourceProfile to dictionary."""
        return {
            'resource_type': self.resource_type,
            'profile_name': self.profile_name,
            'selected_tasks': self.selected_tasks,
            'options': [option.__dict__ for option in self.options]
        }

    @classmethod
    def from_json_file(cls, file_path: str) -> 'ResourceProfile':
        """Load ResourceProfile from a JSON file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        return cls.from_dict(json_data)

    def to_json_file(self, file_path: str, indent=4):
        """Save ResourceProfile to a JSON file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=indent, ensure_ascii=False)


@dataclass
class Resource:
    """Resource configuration within a device."""
    resource_name: str
    enable: bool = False
    # 配置名称，而不是文件名
    profile_name: str = ""  
    # 对于向后兼容，使用私有变量存储本地数据
    _selected_tasks: List[str] = field(default_factory=list)
    _options: List[OptionConfig] = field(default_factory=list)
    # 引用AppConfig实例，用于加载和保存配置文件
    _app_config: Optional[Any] = field(default=None, repr=False)
    
    def __post_init__(self):
        # 确保_selected_tasks和_options为空列表而不是None
        if self._selected_tasks is None:
            self._selected_tasks = []
        if self._options is None:
            self._options = []
    
    @property
    def selected_tasks(self) -> List[str]:
        """获取selected_tasks，如果profile_name存在则从配置文件获取"""
        if self.profile_name and self._app_config:
            profile = self._app_config.load_resource_profile(self.resource_name, self.profile_name)
            if profile:
                return profile.selected_tasks
        return self._selected_tasks
    
    @selected_tasks.setter
    def selected_tasks(self, value: List[str]):
        """设置selected_tasks，如果profile_name存在则更新配置文件"""
        if self.profile_name and self._app_config:
            profile = self._app_config.load_resource_profile(self.resource_name, self.profile_name)
            if profile:
                profile.selected_tasks = value
                self._app_config.save_resource_profile(profile)
                return
        self._selected_tasks = value
    
    @property
    def options(self) -> List[OptionConfig]:
        """获取options，如果profile_name存在则从配置文件获取"""
        if self.profile_name and self._app_config:
            profile = self._app_config.load_resource_profile(self.resource_name, self.profile_name)
            if profile:
                return profile.options
        return self._options
    
    @options.setter
    def options(self, value: List[OptionConfig]):
        """设置options，如果profile_name存在则更新配置文件"""
        if self.profile_name and self._app_config:
            profile = self._app_config.load_resource_profile(self.resource_name, self.profile_name)
            if profile:
                profile.options = value
                self._app_config.save_resource_profile(profile)
                return
        self._options = value


@dataclass
class DeviceConfig:
    """Device configuration dataclass."""
    device_name: str
    device_type: DeviceType
    controller_config: Union[AdbDevice, Win32Device]
    resources: List[Resource] = field(default_factory=list)
    schedule_enabled: bool = False
    schedule_time: List[str] = field(default_factory=list)
    start_command: str = ""


@dataclass
class AppConfig:
    """主设备配置数据类，包含顶层版本信息、设备列表和资源配置管理。"""
    devices: List['DeviceConfig'] = field(default_factory=list)
    # 资源配置映射: {resource_type: [profile_names]}
    resource_profiles: Dict[str, List[str]] = field(default_factory=dict)
    version: str = ""
    build_time: str = ""
    source_file: str = ""  # 用于记录加载的文件路径，但不保存到输出 JSON 中
    CDK: str = ""
    update_method: str = field(default="github")
    receive_beta_update: bool = False
    auto_check_update: bool = False
    # 配置文件目录
    config_dir: str = field(default="configs")

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
        print(config)
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
                # 新的资源配置只需要名称和是否启用，以及配置文件的引用
                resources.append(Resource(
                    resource_name=resource_data.get('resource_name', ''),
                    enable=resource_data.get('enable', False),
                    profile_name=resource_data.get('profile_name', '')
                ))

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
        config = AppConfig(devices=device_configs)

        # 添加资源配置映射
        config.resource_profiles = data.get('resource_profiles', {})
        
        # 添加配置文件目录
        config.config_dir = data.get('config_dir', 'configs')

        # 添加版本信息
        config.version = data.get('version', '')
        config.build_time = data.get('build_time', '')

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

        return config

    def to_dict(self) -> Dict[str, Any]:
        """将 AppConfig 对象转换为字典，不包含 source_file 属性。"""
        result = {}
        # 添加版本信息（如果存在）
        if self.version:
            result["version"] = self.version
        if self.build_time:
            result["build_time"] = self.build_time
        if self.CDK:
            # 加密CDK而不是直接保存
            result["encrypted_cdk"] = self._encrypt_cdk()
        if self.update_method:
            result["update_method"] = self.update_method
        result["receive_beta_update"] = getattr(self, "receive_beta_update", False)
        result["auto_check_update"] = getattr(self, "auto_check_update", False)
        result["devices"] = [device_config_to_dict(device) for device in self.devices]
        result["resource_profiles"] = self.resource_profiles
        result["config_dir"] = self.config_dir
        return result

    def update_version(self, version: str):
        """更新顶层版本信息。"""
        self.version = version
        self.build_time = datetime.now().strftime("%Y%m%d_%H%M%S")

    def get_profile_file_path(self, profile_name: str) -> str:
        """获取资源配置文件的完整路径"""
        base_dir = os.path.dirname(self.source_file) if self.source_file else ""
        config_dir = os.path.join(base_dir, self.config_dir)
        
        # 确保配置目录存在
        os.makedirs(config_dir, exist_ok=True)
        
        # 如果profile_name不带.json后缀，添加它
        if not profile_name.endswith('.json'):
            profile_name = f"{profile_name}.json"
            
        return os.path.join(config_dir, profile_name)
    
    def load_resource_profile(self, resource_type: str, profile_name: str) -> Optional[ResourceProfile]:
        """加载指定资源类型的配置文件"""
        try:
            file_path = self.get_profile_file_path(profile_name)
            if not os.path.exists(file_path):
                return None
            
            profile = ResourceProfile.from_json_file(file_path)
            # 验证资源类型是否匹配
            if profile.resource_type != resource_type:
                print(f"警告: 配置文件 {profile_name} 的资源类型 ({profile.resource_type}) 与预期类型 ({resource_type}) 不匹配")
            print(f"加载资源{profile_name}成功,{profile.profile_name}")
            return profile
        except Exception as e:
            print(f"加载资源配置 {profile_name} 失败: {e}")
            return None
    
    def save_resource_profile(self, profile: ResourceProfile) -> str:
        """保存资源配置并返回文件名(不带路径)"""
        # 确保profile_name非空
        if not profile.profile_name:
            raise ValueError("配置名称不能为空")
            
        # 如果配置名称不含扩展名，添加.json扩展名
        profile_filename = profile.profile_name
        if not profile_filename.endswith('.json'):
            profile_filename = f"{profile_filename}.json"
            
        # 确保资源类型在映射中存在
        if profile.resource_type not in self.resource_profiles:
            self.resource_profiles[profile.resource_type] = []
            
        # 添加到映射中（如果尚未添加）
        if profile.profile_name not in self.resource_profiles[profile.resource_type]:
            self.resource_profiles[profile.resource_type].append(profile.profile_name)
            
        # 保存配置文件
        file_path = self.get_profile_file_path(profile_filename)
        profile.to_json_file(file_path)
        
        return profile.profile_name
    
    def migrate_old_resources(self):
        """迁移旧版本的资源配置到新的独立配置文件"""
        # 确保配置目录存在
        base_dir = os.path.dirname(self.source_file) if self.source_file else ""
        config_dir = os.path.join(base_dir, self.config_dir)
        os.makedirs(config_dir, exist_ok=True)
        
        # 临时存储已创建的配置文件，格式: {resource_type: {resource_profile_hash: profile_name}}
        created_profiles = {}
        
        for device in self.devices:
            for resource in device.resources:
                # 如果已经有配置引用，则跳过
                if resource.profile_name:
                    continue
                
                # 确保资源有对AppConfig的引用
                resource._app_config = self
                
                # 如果有旧的selected_tasks和options，则创建新的配置文件
                if resource._selected_tasks or resource._options:
                    
                    # 创建资源配置对象
                    profile = ResourceProfile(
                        resource_type=resource.resource_name,
                        profile_name=f"{device.device_name}_{resource.resource_name}_profile",
                        selected_tasks=resource._selected_tasks,
                        options=resource._options
                    )
                    
                    # 生成配置内容的哈希值，用于检测重复
                    profile_hash = hash(tuple(sorted([
                        (task, ) for task in profile.selected_tasks
                    ] + [
                        (opt.option_name, str(opt.value)) for opt in profile.options
                    ])))
                    
                    # 检查是否已有相同内容的配置文件
                    if (resource.resource_name in created_profiles and 
                        profile_hash in created_profiles[resource.resource_name]):
                        # 复用已有配置
                        resource.profile_name = created_profiles[resource.resource_name][profile_hash]
                    else:
                        # 保存为新配置文件
                        profile_name = self.save_resource_profile(profile)
                        resource.profile_name = profile_name
                        
                        # 记录已创建的配置
                        if resource.resource_name not in created_profiles:
                            created_profiles[resource.resource_name] = {}
                        created_profiles[resource.resource_name][profile_hash] = profile_name
                else:
                    # 没有配置信息，创建默认配置
                    resource.profile_name = self.create_default_profile(resource.resource_name)
    
    def create_default_profile(self, resource_type: str) -> str:
        """为资源类型创建默认的配置文件"""
        profile = ResourceProfile(
            resource_type=resource_type,
            profile_name=f"{resource_type}_default",
            selected_tasks=[],
            options=[]
        )
        return self.save_resource_profile(profile)
    
    def get_resource_profiles(self, resource_type: str) -> List[Tuple[str, ResourceProfile]]:
        """获取指定资源类型的所有配置及其内容"""
        result = []
        if resource_type not in self.resource_profiles:
            return result
            
        for profile_name in self.resource_profiles[resource_type]:
            profile = self.load_resource_profile(resource_type, profile_name)
            if profile:
                result.append((profile_name, profile))
                
        return result
        
    # 兼容旧版API
    def get_config_file_path(self, config_file: str) -> str:
        """兼容旧版API"""
        return self.get_profile_file_path(config_file)
        
    def load_resource_config(self, resource_type: str, config_file: str) -> Optional[ResourceProfile]:
        """兼容旧版API"""
        return self.load_resource_profile(resource_type, config_file)
        
    def save_resource_config(self, config) -> str:
        """兼容旧版API"""
        # 转换旧的ResourceConfig为新的ResourceProfile
        if not hasattr(config, 'profile_name'):
            profile = ResourceProfile(
                resource_type=config.resource_type,
                profile_name=config.config_name,
                selected_tasks=config.selected_tasks,
                options=config.options
            )
            return self.save_resource_profile(profile)
        return self.save_resource_profile(config)
        
    def create_default_config(self, resource_type: str) -> str:
        """兼容旧版API"""
        return self.create_default_profile(resource_type)
        
    def get_resource_configs(self, resource_type: str) -> List[Tuple[str, Any]]:
        """兼容旧版API"""
        return self.get_resource_profiles(resource_type)


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
    # 创建新字典而不是修改__dict__
    resource_dict = {
        'resource_name': resource.resource_name,
        'enable': resource.enable,
        'profile_name': resource.profile_name
    }
    
    # 保留向后兼容性，如果资源没有profile_name，但有selected_tasks和options，
    # 则保留这些字段到输出中
    if not resource.profile_name:
        resource_dict['selected_tasks'] = resource.selected_tasks  # 使用property获取
        resource_dict['options'] = [option_config_to_dict(opt) for opt in resource.options]
    
    return resource_dict


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]:
    """辅助函数，将 OptionConfig 对象转换为字典。"""
    return option.__dict__