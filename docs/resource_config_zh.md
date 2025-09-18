# 资源配置 (resource_config.json) 规范

本文档详细说明了 `resource_config.json` 文件的结构和所有可用字段，该文件用于定义外部资源的功能、设置和任务。

## 顶层结构 (`ResourceConfig`)

`resource_config.json` 的根对象应包含以下字段：

| 字段名 | 类型 | 是否必须 | 描述                                 |
| --- | --- | --- |------------------------------------|
| `resource_name` | `str` | 是 | 资源的显示名称，例如 “Maa-FGO”。              |
| `resource_id` | `str` | 是 | 资源的唯一标识符，例如 “maa_fgo”。             |
| `resource_version` | `str` | 是 | 资源的语义化版本号，例如 `"1.0.0"`。            |
| `resource_author` | `str` | 是 | 资源的作者或维护者。                         |
| `resource_description`| `str` | 是 | 对资源的简短描述。                          |
| `mirror_update_service_id` | `str` | 否 | 用于检查更新的镜像服务 ID。                    |
| `resource_rep_url` | `str` | 否 | 资源的代码仓库 URL，例如 Github 链接。          |
| `resource_icon` | `str` | 否 | 指向资源图标文件的相对路径。                     |
| `agent` | `Agent` | 是 | 定义资源运行所需环境的 `Agent` 对象。            |
| `resource_pack` | `List[Dict]` | 否 | 定义不同的资源包,如国服资源包和日服资源包,后加载的会覆盖前面加载的 |
| `resource_tasks` | `List[Task]` | 是 | 一个 `Task` 对象列表，定义了资源可执行的任务。        |
| `options` | `List[Option]` | 否 | 一个 `Option` 对象列表，定义了用户可配置的设置项。     |

---

## 嵌套对象

### 1. `Agent` 对象

定义了执行资源任务所需的环境和代理。

| 字段名 | 类型 | 默认值 | 描述 |
| --- | --- | --- | --- |
| `type` | `str` | `"python"` | 运行时环境的类型。目前仅支持 `"python"`。 |
| `version` | `str` | `"3.12"` | Python 解释器的版本，例如 `"3.11"` 或 `"3.12"`。 |
| `agent_path` | `str` | `""` | （可选）自定义代理可执行文件的路径。 |
| `agent_params` | `str` | `""` | （可选）启动代理时传递的额外命令行参数。 |
| `requirements_path` | `str` | `""` | 指向 `requirements.txt` 文件的相对路径。如果提供，将在启动时自动安装依赖。 |
| `use_venv` | `bool` | `True` | 是否为该资源创建并使用独立的 Python 虚拟环境。 |

### 2. `Task` 对象

定义一个可由主程序调用和执行的任务。

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `task_name` | `str` | 任务的显示名称。 |
| `task_entry` | `str` | 任务的入口点。对于 Python，通常是 `"<文件名>:<函数名>"` 的格式，例如 `"main:run"`。 |
| `option` | `List[str]` | 一个字符串列表，其中包含此任务执行时需要传递的 `Option` 的 `name`。 |

### 3. `Option` 对象 (配置项)

所有配置项都基于一个通用的 `Option` 结构，并通过 `type` 字段来区分不同的输入类型。所有 `Option` 对象共享以下通用字段：

**通用字段:**

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `name` | `str` | 配置项的唯一名称（标识符）。 |
| `type` | `str` | 配置项的类型。必须是 `"select"`、`"boole"`、`"input"` 或 `"settings_group"` 之一。 |
| `default` | `Any` | 该配置项的默认值。 |
| `doc` | `str` | （可选）对该配置项的详细说明，通常用于在 UI 中显示提示信息。 |
| `pipeline_override` | `Dict` | （高级）用于覆盖流水线中的特定参数，谨慎使用。 |

#### a. `select` (下拉选择框)

允许用户从预定义的列表中选择一个选项。

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `type` | `Literal["select"]` | 固定为 `"select"`。 |
| `choices` | `List[Choice]` | 一个 `Choice` 对象列表，定义了所有可选项。 |

**`Choice` 对象结构:**

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `name` | `str` | 在 UI 中显示的选项名称。 |
| `value` | `str` | 当用户选择此项时，传递给任务的实际值。 |

#### b. `boole` (布尔开关)

一个简单的 true/false 开关。在 `resource_config.py` 中类型被错误地拼写为 `boole`，但在使用时应视为 `boolean`。

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `type` | `Literal["boole"]` | 固定为 `"boole"`。 |
| `default` | `bool` | 默认状态，`true` 为开启，`false` 为关闭。 |

#### c. `input` (文本输入框)

允许用户输入自由格式的文本。

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `type` | `Literal["input"]` | 固定为 `"input"`。 |
| `default` | `str` | 输入框中默认显示的文本。 |

#### d. `settings_group` (设置组)

用于将多个相关的 `Option` 组合在一起，形成一个可折叠的逻辑分组。

| 字段名 | 类型 | 描述 |
| --- | --- | --- |
| `type` | `Literal["settings_group"]`| 固定为 `"settings_group"`。 |
| `default` | `bool` | `true` 表示默认情况下组是启用的。 |
| `description` | `str` | （可选）对整个组的描述。 |
| `settings` | `List[Option]` | 一个 `Option` 对象列表，包含所有属于该组的子设置项。 |

---

## 完整示例

```json
{
  "resource_name": "My Awesome Resource",
  "resource_id": "my_awesome_resource",
  "resource_version": "1.2.0",
  "resource_author": "John Doe",
  "resource_description": "This is a demonstration of a complex resource configuration.",
  "mirror_update_service_id": "my-awesome-resource-mirror",
  "resource_rep_url": "https://github.com/johndoe/my-awesome-resource",
  "resource_icon": "assets/icon.png",
  "agent": {
    "type": "python",
    "version": "3.12",
    "agent_path": "",
    "agent_params": "",
    "requirements_path": "requirements.txt",
    "use_venv": true
  },
  "resource_pack": [
    {
      "source": "path/to/source",
      "destination": "path/to/destination"
    }
  ],
  "resource_tasks": [
    {
      "task_name": "Run Main Task",
      "task_entry": "main:run",
      "option": [
        "task_mode",
        "enable_feature_x",
        "user_name"
      ]
    }
  ],
  "options": [
    {
      "name": "task_mode",
      "type": "select",
      "default": "mode1",
      "doc": "Select the operating mode.",
      "choices": [
        {
          "name": "Mode 1",
          "value": "mode1"
        },
        {
          "name": "Mode 2",
          "value": "mode2"
        }
      ]
    },
    {
      "name": "enable_feature_x",
      "type": "boole",
      "default": true,
      "doc": "Enable or disable Feature X."
    },
    {
      "name": "advanced_settings",
      "type": "settings_group",
      "default": true,
      "description": "Advanced settings for power users.",
      "settings": [
        {
          "name": "user_name",
          "type": "input",
          "default": "default_user",
          "doc": "Enter your username."
        }
      ]
    }
  ]
}
```