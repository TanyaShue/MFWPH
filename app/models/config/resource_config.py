import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Literal, Optional

__all__ = ['Choice', 'Option', 'SelectOption', 'BoolOption', 'InputOption', 'SettingsGroupOption', 'Task',
           'Agent', 'ResourceConfig']


@dataclass
class Choice:
    """Choice option for select type."""
    name: str
    value: str


@dataclass
class Option:
    """Base class for options."""
    name: str
    type: str
    default: Any
    doc: str=""
    pipeline_override: Dict[str, Dict[str, Any]] = field(
        default_factory=dict)  # PipelineOverride 直接使用 Dict[str, Dict[str, Any]]

@dataclass
class SelectOption(Option):
    """Select option dataclass."""
    type: Literal["select"] = "select"
    default: str = ""
    choices: List[Choice] = field(default_factory=list)


@dataclass
class BoolOption(Option):
    """Boolean option dataclass."""
    type: Literal["boole"] = "boole"
    default: bool = False


@dataclass
class InputOption(Option):
    """Input option dataclass."""
    type: Literal["input"] = "input"
    default: str = ""


@dataclass
class SettingsGroupOption(Option):
    """Settings group option dataclass."""
    type: Literal["settings_group"] = "settings_group"
    default: bool = True  # 默认是否启用整个组
    description: str = ""  # 组的描述
    settings: List[Option] = field(default_factory=list)  # 组内的设置项


@dataclass
class Task:
    """Resource task dataclass."""
    task_name: str
    task_entry: str
    option: List[str] = field(default_factory=list)


@dataclass
class Agent:
    """Agent configuration dataclass."""
    type: str = "python"
    version: str = "3.12"
    agent_path: str = ""
    agent_params: str = ""
    requirements_path: str = ""
    use_venv: bool = True


@dataclass
class ResourceConfig:
    """Main resource configuration dataclass."""
    resource_name: str
    resource_id: str
    resource_version: str
    resource_author: str
    resource_description: str
    mirror_update_service_id: str
    resource_rep_url: str
    resource_icon: str
    agent: Agent
    platform_release_names: Dict[str, str] = field(default_factory=dict)
    resource_pack: List[Dict[str, Any]] = field(default_factory=list)
    resource_tasks: List[Task] = field(default_factory=list)
    options: List[Option] = field(default_factory=list)
    source_file: str = ""  # 用于记录加载的文件路径，但不保存到输出 JSON 中

    @classmethod
    def from_json_file(cls, file_path: str) -> 'ResourceConfig':
        """Load ResourceConfig from a JSON file and record the source file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        config = cls.from_dict(json_data)
        config.source_file = file_path  # 记录来源文件路径
        return config

    def to_json_file(self, file_path: Optional[str] = None, indent=4):
        """Export ResourceConfig to a JSON file.

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
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceConfig':
        """Create ResourceConfig object from a dictionary."""
        tasks_data = data.get('resource_tasks', [])
        options_data = data.get('options', [])
        agent_data = data.get('agent', {})

        tasks = [Task(**task_data) for task_data in tasks_data]
        agent = Agent(**agent_data) if agent_data else Agent()

        options = []
        for option_data in options_data:
            option_type = option_data.get('type')
            if option_type == 'select':
                choices_data = option_data.get('choices', [])
                choices = [Choice(**choice_data) for choice_data in choices_data]
                # 排除 choices 字段，避免重复赋值
                options.append(
                    SelectOption(**{k: v for k, v in option_data.items() if k != 'choices'}, choices=choices)
                )
            elif option_type == 'boole':
                options.append(BoolOption(**option_data))
            elif option_type == 'input':
                options.append(InputOption(**option_data))
            elif option_type == 'settings_group':
                # 处理设置组
                settings_data = option_data.get('settings', [])
                # 递归处理组内的设置
                sub_options = []
                for sub_option_data in settings_data:
                    sub_type = sub_option_data.get('type')
                    if sub_type == 'select':
                        sub_choices_data = sub_option_data.get('choices', [])
                        sub_choices = [Choice(**choice_data) for choice_data in sub_choices_data]
                        sub_options.append(
                            SelectOption(**{k: v for k, v in sub_option_data.items() if k != 'choices'},
                                         choices=sub_choices)
                        )
                    elif sub_type == 'boole':
                        sub_options.append(BoolOption(**sub_option_data))
                    elif sub_type == 'input':
                        sub_options.append(InputOption(**sub_option_data))
                    else:
                        sub_options.append(Option(**sub_option_data))

                options.append(
                    SettingsGroupOption(
                        **{k: v for k, v in option_data.items() if k != 'settings'},
                        settings=sub_options
                    )
                )
            else:
                options.append(Option(**option_data))  # Fallback to base Option if type is unknown

        return ResourceConfig(
            resource_name=data.get('resource_name', ''),
            resource_id=data.get('resource_id', ''),
            resource_version=data.get('resource_version', ''),
            resource_author=data.get('resource_author', ''),
            mirror_update_service_id=data.get('mirror_update_service_id', ''),
            resource_rep_url=data.get('resource_rep_url', ''),
            resource_description=data.get('resource_description', ''),
            resource_icon=data.get('resource_icon', ''),
            platform_release_names=data.get('platform_release_names', {}),  # 读取新增的配置
            resource_pack=data.get('resource_pack', []),
            agent=agent,
            resource_tasks=tasks,
            options=options
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert ResourceConfig object to a dictionary, excluding source_file."""
        return {
            "resource_name": self.resource_name,
            "resource_id": self.resource_id,
            "resource_version": self.resource_version,
            "resource_author": self.resource_author,
            "mirror_update_service_id": self.mirror_update_service_id,
            "resource_rep_url": self.resource_rep_url,
            "resource_description": self.resource_description,
            "resource_icon": self.resource_icon,
            "platform_release_names": self.platform_release_names,  # 导出新增的配置
            # 在序列化时写入 resource_pack
            "resource_pack": self.resource_pack,
            "agent": {
                "type": self.agent.type,
                "version": self.agent.version,
                "agent_path": self.agent.agent_path,
                "agent_params": self.agent.agent_params,
                "requirements_path":self.agent.requirements_path,
                "use_venv": self.agent.use_venv,
            },
            "resource_tasks": [task.__dict__ for task in self.resource_tasks],
            "options": [option_to_dict(option) for option in self.options],
        }


def option_to_dict(option: Option) -> Dict[str, Any]:
    """Helper function to convert Option and its subclasses to dictionary."""
    option_dict = option.__dict__.copy()
    if isinstance(option, SelectOption):
        option_dict['choices'] = [choice.__dict__ for choice in option.choices]
    elif isinstance(option, SettingsGroupOption):
        option_dict['settings'] = [option_to_dict(setting) for setting in option.settings]
    return option_dict