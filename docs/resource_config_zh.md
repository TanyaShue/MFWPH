
# 资源配置规范

## 主 `ResourceConfig` 结构

| 参数                           | 类型             | 描述                       |
| ---------------------------- | -------------- | ------------------------ |
| `resource_name`              | `str`          | 资源唯一标识符                  |
| `resource_version`           | `str`          | 语义化版本号（如 `"1.0.0"`）      |
| `resource_author`            | `str`          | 资源创建者                    |
| `resource_description`       | `str`          | 资源详细描述                   |
| `resource_update_service_id` | `str`          | 更新服务检查的 ID               |
| `resource_rep_url`           | `str`          | 源代码仓库 URL                |
| `resource_icon`              | `str`          | 资源图标文件路径                 |
| `agent`                      | `Agent`        | 运行时环境配置                  |
| `resource_tasks`             | `List[Task]`   | 可执行任务列表                  |
| `options`                    | `List[Option]` | 资源配置选项                   |
| `source_file`                | `str`          | （内部）原始 JSON 文件路径（不保存到输出） |

---

## 嵌套类型说明

###  Agent 配置

| 参数                  | 类型              | 默认值        | 说明                  |
| ------------------- | --------------- | ---------- | ------------------- |
| `type`              | `str`           | `"python"` | 运行时类型（如 `"python"`） |
| `version`           | `str`           | `"3.12"`   | Python 版本           |
| `agent_path`        | `str`           | `""`       | 自定义代理可执行路径          |
| `agent_params`      | `str`           | `""`       | 启动参数                |
| `requirements_path` | `str`           | `""`       | requirements.txt 路径 |
| `use_venv`          | `bool`          | `True`     | 是否使用虚拟环境            |

---

### 选项类型（Option）

所有配置项继承自基础类型 `Option`，通过 `type` 字段区分具体类型。

#### 通用字段（所有类型共用）

| 字段名                 | 类型                          | 默认值  | 说明                                |
| ------------------- | --------------------------- | ---- | --------------------------------- |
| `name`              | `str`                       | -    | 配置项名称（唯一标识）                       |
| `type`              | `Literal[...]`              | -    | 配置项类型标识（如 `"select"`、`"boole"` 等） |
| `default`           | `Any`                       | 类型相关 | 默认值                               |
| `pipeline_override` | `Dict[str, Dict[str, Any]]` | `{}` | 流水线覆盖配置（高级用法）                     |

---

#### 类型：选择项 `type: "select"`

| 字段名       | 类型             | 默认值  | 说明                  |
| --------- | -------------- | ---- | ------------------- |
| `type`    | `"select"`     | 固定值  | 类型标识                |
| `default` | `str`          | `""` | 默认选中值（对应某个 `value`） |
| `choices` | `List[Choice]` | `[]` | 可选项列表，包含名称与值        |

**`Choice` 结构：**

| 字段名     | 类型    | 描述          |
| ------- | ----- | ----------- |
| `name`  | `str` | 显示名称（用于 UI） |
| `value` | `str` | 实际传递值（用于逻辑） |

---

#### 类型：布尔项 `type: "boole"`

| 字段名       | 类型        | 默认值     | 说明     |
| --------- | --------- | ------- | ------ |
| `type`    | `"boole"` | 固定值     | 类型标识   |
| `default` | `bool`    | `False` | 默认是否启用 |

---

#### 类型：输入项 `type: "input"`

| 字段名       | 类型        | 默认值  | 说明    |
| --------- | --------- | ---- | ----- |
| `type`    | `"input"` | 固定值  | 类型标识  |
| `default` | `str`     | `""` | 默认文本值 |

---

#### 类型：设置组 `type: "settings_group"`

用于将多个配置项组合成一个逻辑分组，支持递归嵌套。

| 字段名           | 类型                 | 默认值    | 说明                    |
| ------------- | ------------------ | ------ | --------------------- |
| `type`        | `"settings_group"` | 固定值    | 类型标识                  |
| `default`     | `bool`             | `True` | 默认是否启用整个组             |
| `description` | `str`              | `""`   | 该组的描述信息               |
| `settings`    | `List[Option]`     | `[]`   | 子选项列表，支持嵌套任意类型 Option |

---

###  任务配置（Task）

| 参数           | 类型          | 描述                    |
| ------------ | ----------- | --------------------- |
| `task_name`  | `str`       | 任务唯一标识符               |
| `task_entry` | `str`       | 任务入口点（如 `"main:run"`） |
| `option`     | `List[str]` | 所依赖的选项名称列表            |

