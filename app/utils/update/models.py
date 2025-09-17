from dataclasses import dataclass
from enum import Enum, auto


class UpdateSource(Enum):
    """更新源类型枚举"""
    MIRROR = auto()
    GITHUB = auto()
    APP = auto()  # <-- 新增：用于标识主程序


@dataclass
class UpdateInfo:
    """
    封装所有更新信息的标准数据类。
    它在检查器、下载器和安装器之间传递，确保数据一致性。
    """
    resource_name: str
    current_version: str
    new_version: str
    download_url: str
    update_type: str
    source: UpdateSource
