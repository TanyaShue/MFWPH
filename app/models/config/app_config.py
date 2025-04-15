import base64
import hashlib
import os
from dataclasses import dataclass, field
from typing import List, Dict, Any

from cryptography.fernet import Fernet


@dataclass
class AdbDevice:
    """ADB device configuration dataclass."""
    name: str
    adb_path: str  # 路径使用 str 类型，匹配 JSON 中的字符串路径
    address: str
    screencap_methods: int
    input_methods: int
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Resource:
    """Resource configuration within a device."""
    resource_name: str
    enable: bool = False
    selected_tasks: List[str] = field(default_factory=list)
    options: List['OptionConfig'] = field(default_factory=list)  # 使用前向引用


@dataclass
class OptionConfig:
    """Option configuration for a task or resource."""
    option_name: str
    value: Any


@dataclass
class DeviceConfig:
    """Device configuration dataclass."""
    device_name: str
    adb_config: AdbDevice
    resources: List[Resource] = field(default_factory=list)
    schedule_enabled: bool = False
    schedule_time: List[str] = field(default_factory=list)
    start_command: str = ""


from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List
import json


# 假设 DeviceConfig、AdbDevice、Resource 和 OptionConfig 均已定义

@dataclass
class AppConfig:
    """主设备配置数据类，包含顶层版本信息和设备列表。"""
    devices: List['DeviceConfig'] = field(default_factory=list)
    version: str = ""
    build_time: str = ""
    source_file: str = ""  # 用于记录加载的文件路径，但不保存到输出 JSON 中
    CDK: str = ""
    update_method: str = field(default="github")

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
        devices_data = data.get('devices', [])
        device_configs = []

        for device_data in devices_data:
            adb_config_data = device_data.get('adb_config', {})
            adb_config = AdbDevice(**adb_config_data)  # 创建 AdbDevice 对象

            resources_data = device_data.get('resources', [])
            resources = []
            for resource_data in resources_data:
                options_data = resource_data.get('options', [])
                options = [OptionConfig(**option_data) for option_data in options_data]  # 创建 OptionConfig 对象列表
                # 排除 options 字段后创建 Resource 对象，并传入 options 参数
                resource_kwargs = {k: v for k, v in resource_data.items() if k != 'options'}
                resources.append(Resource(**resource_kwargs, options=options))
            # 排除 adb_config 与 resources 字段后创建 DeviceConfig 对象，并传入相应参数
            device_kwargs = {k: v for k, v in device_data.items() if k not in ('adb_config', 'resources')}
            device_configs.append(DeviceConfig(**device_kwargs, adb_config=adb_config, resources=resources))

        # 创建 AppConfig
        config = AppConfig(devices=device_configs)

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

        return config

    def to_dict(self) -> Dict[str, Any]:
        """将 AppConfig 对象转换为字典，不包含 source_file 属性。"""
        result = {
            "devices": [device_config_to_dict(device) for device in self.devices],
        }

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
        return result

    def update_version(self, version: str):
        """更新顶层版本信息。"""
        self.version = version
        self.build_time = datetime.now().strftime("%Y%m%d_%H%M%S")

def device_config_to_dict(device: DeviceConfig) -> Dict[str, Any]:
    """辅助函数，将 DeviceConfig 对象转换为字典。"""
    device_dict = device.__dict__.copy()
    device_dict['adb_config'] = adb_device_to_dict(device.adb_config)
    device_dict['resources'] = [resource_to_dict(resource) for resource in device.resources]
    return device_dict


def adb_device_to_dict(adb_device: AdbDevice) -> Dict[str, Any]:
    """辅助函数，将 AdbDevice 对象转换为字典。"""
    return adb_device.__dict__


def resource_to_dict(resource: Resource) -> Dict[str, Any]:
    """辅助函数，将 Resource 对象转换为字典。"""
    resource_dict = resource.__dict__.copy()
    resource_dict['options'] = [option_config_to_dict(option) for option in resource.options]
    return resource_dict


def option_config_to_dict(option: OptionConfig) -> Dict[str, Any]:
    """辅助函数，将 OptionConfig 对象转换为字典。"""
    return option.__dict__