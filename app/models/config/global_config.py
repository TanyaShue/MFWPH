import os
import json  # 导入 json 以便在加载前检查版本
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

# 导入新的 TaskInstance 和 OptionConfig
from app.models.config.app_config import AppConfig, OptionConfig
from app.models.config.resource_config import ResourceConfig, SelectOption, BoolOption, InputOption, \
    SettingsGroupOption, Task
from app.models.logging.log_manager import log_manager, app_logger


@dataclass
class RunTimeConfig:
    task_name: str
    task_entry: str
    pipeline_override: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class RunTimeConfigs:
    # --- CHANGE 1 OF 2: The RunTimeConfigs dataclass is updated as requested ---
    task_list: List[RunTimeConfig] = field(default_factory=list)
    # The type is now a single dictionary, with an empty dict as the default.
    resource_pack: Dict[str, Any] = field(default_factory=dict)
    resource_path: str = field(default_factory=Path)
    resource_name: str = field(default_factory=str)


class GlobalConfig:
    """全局配置管理类。"""

    app_config: Optional[AppConfig]
    resource_configs: Dict[str, ResourceConfig]

    def __init__(self):
        self.app_config = None
        self.resource_configs = {}

    def load_app_config(self, file_path: str) -> None:
        """
        加载 AppConfig。如果检测到是从旧版本迁移，则立即执行数据清理。
        **此方法假定 resource_configs 已经预先加载完毕。**
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # 在创建对象前，先检查文件中的版本号，判断是否需要后续清理
        is_old_version = json_data.get('config_version', 1) < 2

        # AppConfig.from_dict 执行“结构迁移”，将旧格式转为新格式（但 options 未过滤）
        self.app_config = AppConfig.from_dict(json_data)
        self.app_config.source_file = file_path

        # 如果是从旧版本迁移过来的，则立即执行“数据清理”
        if is_old_version:
            app_logger.info("检测到旧版配置文件，正在执行选项数据清理...")
            self._filter_migrated_task_options()
            app_logger.info("选项数据清理完成。")

    def _filter_migrated_task_options(self):
        """
        遍历 AppConfig，为从旧版本迁移过来的 TaskInstance 清理其 options 列表，
        只保留与该任务相关的选项。
        """
        if not self.app_config:
            return

        for settings in self.app_config.resource_settings:
            # 找到与此设置方案对应的资源定义
            resource_config = self.get_resource_config(settings.resource_name)
            if not resource_config:
                continue

            # 为该资源的每个任务创建一个“有效选项”的集合，便于快速查找
            task_options_map = {
                task.task_name: set(task.option) for task in resource_config.resource_tasks
            }

            # 遍历此设置方案中的每一个任务实例
            for instance in settings.task_instances.values():
                # 获取该任务类型所有有效的选项名称
                valid_option_names = task_options_map.get(instance.task_name)

                if valid_option_names is None:
                    # 如果在 resource_config 中找不到任务定义，跳过以防万一
                    continue

                # 核心逻辑：过滤实例的 options 列表，只保留 option_name 在有效集合中的选项
                filtered_options = [
                    opt for opt in instance.options if opt.option_name in valid_option_names
                ]
                instance.options = filtered_options

    def load_resource_config(self, file_path: str) -> None:
        resource_config: ResourceConfig = ResourceConfig.from_json_file(file_path)
        resource_config.source_file = file_path
        self.resource_configs[resource_config.resource_name] = resource_config

    def get_app_config(self) -> AppConfig:
        if self.app_config is None: raise ValueError("AppConfig 尚未加载。")
        return self.app_config

    def get_device_config(self, device_name):
        if not self.app_config: return None
        for device in self.app_config.devices:
            if device.device_name == device_name: return device
        return None

    def get_resource_config(self, resource_name: str) -> Optional[ResourceConfig]:
        return self.resource_configs.get(resource_name)

    def get_all_resource_configs(self) -> List[ResourceConfig]:
        return list(self.resource_configs.values())

    def load_all_resources_from_directory(self, directory: str) -> None:
        path: Path = Path(directory)
        if not path.is_dir(): raise ValueError(f"{directory} 不是一个有效的目录。")
        for file in path.rglob("resource_config.json"): self.load_resource_config(str(file))

    def save_all_configs(self) -> None:
        if self.app_config is not None:
            # 自动备份旧配置文件，以防万一
            source_path = Path(self.app_config.source_file)
            if source_path.exists():
                backup_path = source_path.with_suffix(source_path.suffix + '.v1.bak')
                if not backup_path.exists():
                    try:
                        os.rename(source_path, backup_path)
                        app_logger.info(f"已将旧版配置文件备份至: {backup_path}")
                    except OSError as e:
                        app_logger.error(f"备份旧版配置文件失败: {e}")

            self.app_config.to_json_file()
        else:
            raise ValueError("AppConfig 尚未加载，无法保存。")

    # --- CHANGE 2 OF 2: The get_runtime_configs_for_resource method is updated ---
    def get_runtime_configs_for_resource(self, resource_name: str, device_id: str = None) -> RunTimeConfigs | None:
        """
        获取指定资源中已启用的任务实例的RunTimeConfigs，
        并按照配置方案中定义的顺序排列。
        现在还会包含为该设备选择的资源包信息（单个字典）。
        """
        resource_config = self.get_resource_config(resource_name)
        if resource_config is None:
            print(f"Resource '{resource_name}' not found.")
            return None

        if self.app_config is None: return None

        target_settings = None
        device_resource = None  # 用于存储在设备上找到的那个 Resource 对象
        device = self.get_device_config(device_id)
        if device:
            for res in device.resources:
                if res.resource_name == resource_name and res.enable:
                    # 找到了设备上启用的资源，现在查找其引用的设置方案
                    device_resource = res  # 保存这个Resource对象，以便后续获取resource_pack
                    for settings in self.app_config.resource_settings:
                        if settings.name == res.settings_name and settings.resource_name == resource_name:
                            target_settings = settings
                            break
                    break

        # 获取选定的资源包配置
        selected_pack_config = {}  # Initialize as an empty dictionary
        if device_resource:
            # Safely get the resource_pack name to be backward compatible
            selected_pack_name = getattr(device_resource, 'resource_pack', '')
            # Ensure resource_config actually has the resource_pack list
            if selected_pack_name and hasattr(resource_config, 'resource_pack'):
                # Find the pack object (dictionary) that matches the selected name
                pack_object = next((pack for pack in resource_config.resource_pack if pack.get('name') == selected_pack_name), None)
                if pack_object:
                    # Assign the dictionary directly
                    selected_pack_config = pack_object

        resource_path = Path(resource_config.source_file).parent if resource_config.source_file else Path()

        if not target_settings:
            # If no settings found, return an empty task list but still include pack info
            return RunTimeConfigs(
                task_list=[],
                resource_path=resource_path,
                resource_name=resource_name,
                resource_pack=selected_pack_config
            )

        runtime_configs = []
        # 按照 task_order 中定义的顺序遍历任务实例
        for instance_id in target_settings.task_order:
            task_instance = target_settings.task_instances.get(instance_id)

            # 跳过不存在或未启用的任务实例
            if not task_instance or not task_instance.enabled:
                continue

            # 从 ResourceConfig 中找到任务的定义
            task_definition = next(
                (t for t in resource_config.resource_tasks if t.task_name == task_instance.task_name), None)

            if task_definition:
                # 为此任务实例生成 pipeline_override，传入它自己的 options
                pipeline_override = self._process_task_options(
                    resource_config=resource_config,
                    task=task_definition,
                    instance_options=task_instance.options  # 传入实例专属的选项
                )

                runtime_config = RunTimeConfig(
                    task_name=task_definition.task_name,
                    task_entry=task_definition.task_entry,
                    pipeline_override=pipeline_override
                )
                runtime_configs.append(runtime_config)

        return RunTimeConfigs(
            task_list=runtime_configs,
            resource_path=resource_path,
            resource_name=resource_name,
            resource_pack=selected_pack_config # Pass the found dictionary
        )

    def get_runtime_config_for_task(self, resource_name: str, task_name: str, device_id: str = None,
                                    instance_id: str = None) -> Optional[RunTimeConfig]:
        """
        获取特定资源中特定任务实例的 RunTimeConfig。
        由于任务名可重复，需要 instance_id 来精确定位。
        """
        resource_config = self.get_resource_config(resource_name)
        if resource_config is None: raise ValueError(f"Resource '{resource_name}' not found.")
        if not instance_id: raise ValueError("instance_id is required to get a specific task runtime config.")

        # 查找设备对应的 ResourceSettings
        if self.app_config is None: return None
        target_settings = None
        device = self.get_device_config(device_id)
        if device:
            for res in device.resources:
                if res.resource_name == resource_name:
                    for settings in self.app_config.resource_settings:
                        if settings.name == res.settings_name:
                            target_settings = settings
                            break
                    break

        if not target_settings: return None

        task_instance = target_settings.task_instances.get(instance_id)
        if not task_instance or task_instance.task_name != task_name: return None

        task_definition = next((t for t in resource_config.resource_tasks if t.task_name == task_instance.task_name),
                               None)
        if not task_definition: return None

        pipeline_override = self._process_task_options(resource_config, task_definition, task_instance.options)
        return RunTimeConfig(
            task_name=task_definition.task_name,
            task_entry=task_definition.task_entry,
            pipeline_override=pipeline_override
        )

    def _process_task_options(self, resource_config: ResourceConfig, task: Task,
                              instance_options: List[OptionConfig]) -> Dict[str, Any]:
        """
        处理单个任务实例的选项，生成 pipeline_override。
        现在从传入的 instance_options 获取选项值。
        """
        final_pipeline_override = {}

        def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]):
            for key, value in dict2.items():
                if isinstance(value, dict) and isinstance(dict1.get(key), dict):
                    merge_dicts(dict1[key], value)
                else:
                    dict1[key] = value

        # 性能优化：直接从传入的 instance_options 构建值查找字典
        option_values_map = {opt.option_name: opt.value for opt in instance_options}

        # 构建资源选项定义的快速查找字典
        resource_options_map = {}
        for opt in resource_config.options:
            resource_options_map[opt.name] = opt
            if isinstance(opt, SettingsGroupOption):
                for sub_opt in opt.settings:
                    # 将子选项也加入映射，方便查找
                    resource_options_map[f"{opt.name}.{sub_opt.name}"] = sub_opt

        # 处理任务定义中列出的每个选项
        for option_name in task.option:
            option_definition = resource_options_map.get(option_name)
            if option_definition is None: continue

            # 从值映射中获取用户为此实例配置的值，如果未配置，则使用定义中的默认值
            option_value = option_values_map.get(option_name, option_definition.default)

            if isinstance(option_definition, SelectOption):
                choice_value = option_value
                choice = next((c for c in option_definition.choices if c.name == option_value), None)
                if choice: choice_value = choice.value
                choice_override = option_definition.pipeline_override.get(choice_value,
                                                                          {}) if option_definition.pipeline_override else {}
                merge_dicts(final_pipeline_override, choice_override)

            elif isinstance(option_definition, BoolOption):
                if option_definition.pipeline_override:
                    bool_value = self._parse_bool_value(option_value)
                    processed_override = self._replace_placeholder(option_definition.pipeline_override,
                                                                   str(option_value), bool_value)
                    merge_dicts(final_pipeline_override, processed_override)

            elif isinstance(option_definition, InputOption):
                if option_value and option_definition.pipeline_override:
                    processed_override = self._replace_placeholder(option_definition.pipeline_override,
                                                                   str(option_value))
                    merge_dicts(final_pipeline_override, processed_override)

            elif isinstance(option_definition, SettingsGroupOption):
                group_enabled = self._parse_bool_value(option_value)
                if group_enabled:
                    if option_definition.pipeline_override:
                        merge_dicts(final_pipeline_override, option_definition.pipeline_override)

                    for sub_option in option_definition.settings:
                        sub_option_name = f"{option_name}.{sub_option.name}"
                        sub_option_value = option_values_map.get(sub_option_name, sub_option.default)

                        if isinstance(sub_option, SelectOption):
                            choice_value = sub_option_value
                            choice = next((c for c in sub_option.choices if c.name == sub_option_value), None)
                            if choice: choice_value = choice.value
                            choice_override = sub_option.pipeline_override.get(choice_value,
                                                                               {}) if sub_option.pipeline_override else {}
                            merge_dicts(final_pipeline_override, choice_override)
                        elif isinstance(sub_option, BoolOption):
                            if sub_option.pipeline_override:
                                bool_value = self._parse_bool_value(sub_option_value)
                                processed_override = self._replace_placeholder(sub_option.pipeline_override,
                                                                               str(sub_option_value), bool_value)
                                merge_dicts(final_pipeline_override, processed_override)
                        elif isinstance(sub_option, InputOption):
                            if sub_option_value and sub_option.pipeline_override:
                                processed_override = self._replace_placeholder(sub_option.pipeline_override,
                                                                               str(sub_option_value))
                                merge_dicts(final_pipeline_override, processed_override)

        return final_pipeline_override

    def _parse_bool_value(self, value: Any) -> bool:
        if isinstance(value, bool): return value
        if isinstance(value, str): return value.lower() in ('true', 'yes', 'y', '1', 'on', 'enabled', '启用', '开启')
        if isinstance(value, (int, float)): return value != 0
        return bool(value)

    def _replace_placeholder(self, pipeline: Any, value: str, bool_value: bool = None) -> Any:
        if bool_value is None: bool_value = self._parse_bool_value(value)
        if isinstance(pipeline, dict):
            result = {}
            for k, v in pipeline.items():
                if isinstance(v, str):
                    if v == "{boole}":
                        result[k] = bool_value
                    elif "{boole}" in v:
                        result[k] = v.replace("{boole}", str(bool_value).lower())
                    else:
                        result[k] = v.replace("{value}", value)
                elif isinstance(v, dict):
                    result[k] = self._replace_placeholder(v, value, bool_value)
                elif isinstance(v, list):
                    result[k] = [
                        self._replace_placeholder(item, value, bool_value)
                        if isinstance(item, (dict, list))
                        else (bool_value if item == "{boole}" else (
                            item.replace("{boole}", str(bool_value).lower()).replace("{value}", value) if isinstance(
                                item, str) else item))
                        for item in v
                    ]
                else:
                    result[k] = v
            return result
        elif isinstance(pipeline, list):
            return [self._replace_placeholder(item, value, bool_value) for item in pipeline]
        return pipeline


# 创建全局单例实例
global_config = GlobalConfig()