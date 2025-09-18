# Resource Configuration (resource_config.json) Specification

This document details the structure and all available fields for the `resource_config.json` file, which is used to define the functionality, settings, and tasks of an external resource.

## Top-Level Structure (`ResourceConfig`)

The root object of `resource_config.json` should contain the following fields:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `resource_name` | `str` | Yes | The display name of the resource, e.g., "Maa-FGO". |
| `resource_id` | `str` | Yes | A unique identifier for the resource, e.g., "maa_fgo". |
| `resource_version` | `str` | Yes | The semantic version number of the resource, e.g., `"1.0.0"`. |
| `resource_author` | `str` | Yes | The author or maintainer of the resource. |
| `resource_description`| `str` | Yes | A short description of the resource. |
| `mirror_update_service_id` | `str` | No | The ID for the mirror update service to check for updates. |
| `resource_rep_url` | `str` | No | The URL of the resource's code repository, e.g., a GitHub link. |
| `resource_icon` | `str` | No | A relative path to the resource's icon file. |
| `agent` | `Agent` | Yes | An `Agent` object that defines the environment required for the resource to run. |
| `resource_pack` | `List[Dict]` | No | A list of dictionaries defining resource packs for updates and distribution. |
| `resource_tasks` | `List[Task]` | Yes | A list of `Task` objects that define the executable tasks for the resource. |
| `options` | `List[Option]` | No | A list of `Option` objects that define user-configurable settings. |

---

## Nested Objects

### 1. `Agent` Object

Defines the environment and agent required to execute the resource's tasks.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `type` | `str` | `"python"` | The type of runtime environment. Currently, only `"python"` is supported. |
| `version` | `str` | `"3.12"` | The version of the Python interpreter, e.g., `"3.11"` or `"3.12"`. |
| `agent_path` | `str` | `""` | (Optional) A custom path to the agent's executable. |
| `agent_params` | `str` | `""` | (Optional) Extra command-line parameters to pass when starting the agent. |
| `requirements_path` | `str` | `""` | A relative path to a `requirements.txt` file. If provided, dependencies will be installed automatically on startup. |
| `use_venv` | `bool` | `True` | Whether to create and use an isolated Python virtual environment for this resource. |

### 2. `Task` Object

Defines a task that can be invoked and executed by the main application.

| Field | Type | Description |
| --- | --- | --- |
| `task_name` | `str` | The display name of the task. |
| `task_entry` | `str` | The entry point for the task. For Python, this is typically in the format `"<filename>:<function_name>"`, e.g., `"main:run"`. |
| `option` | `List[str]` | A list of strings containing the `name` of each `Option` that should be passed to this task upon execution. |

### 3. `Option` Object (Configuration Item)

All configuration items are based on a common `Option` structure and are differentiated by the `type` field. All `Option` objects share the following common fields:

**Common Fields:**

| Field | Type | Description |
| --- | --- | --- |
| `name` | `str` | The unique name (identifier) for the configuration item. |
| `type` | `str` | The type of the configuration item. Must be one of `"select"`, `"boole"`, `"input"`, or `"settings_group"`. |
| `default` | `Any` | The default value for this configuration item. |
| `doc` | `str` | (Optional) A detailed description of the configuration item, often used for tooltips in the UI. |
| `pipeline_override` | `Dict` | (Advanced) Used to override specific parameters in a pipeline. Use with caution. |

#### a. `select` (Dropdown Select Box)

Allows the user to choose one option from a predefined list.

| Field | Type | Description |
| --- | --- | --- |
| `type` | `Literal["select"]` | Must be `"select"`. |
| `choices` | `List[Choice]` | A list of `Choice` objects that define all available options. |

**`Choice` Object Structure:**

| Field | Type | Description |
| --- | --- | --- |
| `name` | `str` | The name of the option displayed in the UI. |
| `value` | `str` | The actual value passed to the task when the user selects this option. |

#### b. `boole` (Boolean Switch)

A simple true/false switch. The type is misspelled as `boole` in `resource_config.py` but should be treated as `boolean`.

| Field | Type | Description |
| --- | --- | --- |
| `type` | `Literal["boole"]` | Must be `"boole"`. |
| `default` | `bool` | The default state, `true` for on, `false` for off. |

#### c. `input` (Text Input Box)

Allows the user to enter free-form text.

| Field | Type | Description |
| --- | --- | --- |
| `type` | `Literal["input"]` | Must be `"input"`. |
| `default` | `str` | The default text displayed in the input box. |

#### d. `settings_group` (Settings Group)

Used to group multiple related `Option`s together into a collapsible logical group.

| Field | Type | Description |
| --- | --- | --- |
| `type` | `Literal["settings_group"]`| Must be `"settings_group"`. |
| `default` | `bool` | `true` indicates the group is enabled by default. |
| `description` | `str` | (Optional) A description for the entire group. |
| `settings` | `List[Option]` | A list of `Option` objects containing all sub-settings belonging to this group. |

---

## Complete Example

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
