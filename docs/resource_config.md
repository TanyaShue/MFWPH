# Resource Configuration Specification

## Main `ResourceConfig` Structure

| Parameter | Type | Description |
|-----------|------|-------------|
| `resource_name` | `str` | Unique resource identifier |
| `resource_version` | `str` | Semantic version (e.g. `"1.0.0"`) |
| `resource_author` | `str` | Creator of the resource |
| `resource_description` | `str` | Detailed description of the resource |
| `resource_update_service_id` | `str` | ID for update service checks |
| `resource_rep_url` | `str` | Repository URL for source code |
| `resource_icon` | `str` | Path to resource icon file |
| `agent` | `Agent` | Runtime environment configuration |
| `resource_tasks` | `List[Task]` | List of executable tasks |
| `options` | `List[Option]` | Configuration options for the resource |
| `source_file` | `str` | (Internal) Original JSON file path (not saved in output) |

---

## Nested Types

### Agent Configuration

| Parameter | Type | Default | Description |
|-----------|-------|----------|-------------|
| `type` | `str` | `"python"` | Runtime type (e.g. `"python"`) |
| `version` | `str` | `"3.12"` | Python version |
| `agent_path` | `str` | `""` | Custom agent executable path |
| `agent_params` | `str` | `""` | Launch parameters |
| `requirements_path` | `str` | `""` | Path to requirements.txt |
| `use_venv` | `bool` | `True` | Use virtual environment |
| `pip_index_url` | `Optional[str]` | `None` | Custom PyPI mirror URL |

---

### Option Types

All configuration items inherit from base `Option`, distinguished by `type` field.

#### Common Fields (Shared by All Types)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | - | Configuration item name (unique identifier) |
| `type` | `Literal[...]` | - | Type identifier (e.g. `"select"`, `"boole"`) |
| `default` | `Any` | Type-specific | Default value |
| `pipeline_override` | `Dict[str, Dict[str, Any]]` | `{}` | Pipeline override configuration (advanced) |

---

#### Type: Select Option `type: "select"`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `"select"` | Fixed | Type identifier |
| `default` | `str` | `""` | Default selected value (corresponds to `value`) |
| `choices` | `List[Choice]` | `[]` | Options list containing names and values |

**`Choice` Structure:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Display name (for UI) |
| `value` | `str` | Actual value (for logic) |

---

#### Type: Boolean Option `type: "boole"`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `"boole"` | Fixed | Type identifier |
| `default` | `bool` | `False` | Default enabled state |

---

#### Type: Input Option `type: "input"`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `"input"` | Fixed | Type identifier |
| `default` | `str` | `""` | Default text value |

---

#### Type: Settings Group `type: "settings_group"`

Used to group multiple configuration items into logical units with recursive nesting support.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | `"settings_group"` | Fixed | Type identifier |
| `default` | `bool` | `True` | Default group enabled state |
| `description` | `str` | `""` | Group description |
| `settings` | `List[Option]` | `[]` | Sub-options list supporting nested Options |

---

### Task Configuration

| Parameter | Type | Description |
|-----------|------|-------------|
| `task_name` | `str` | Unique task identifier |
| `task_entry` | `str` | Entry point (e.g. `"main:run"`) |
| `option` | `List[str]` | Required option names list |