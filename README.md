<p align="center">
  <img alt="MFWPH Logo" src="assets/icons/app/logo.png" width="256" height="256" />
</p>

<div align="center">
  <h1>MFWPH</h1>
  <p>基于 MaaFramework 的 UI 启动器，可加载与管理多种自动化资源脚本</p>
</div>

---

## 目录
- [简介](#简介)
- [功能特点](#功能特点)
- [安装与使用](#安装与使用)
  - [快速开始](#快速开始)
  - [开发者](#开发者)
  - [命令行参数详解](#命令行参数详解)
- [资源脚本结构说明](#资源脚本结构说明)
- [自动化部署](#自动化部署)
- [常见问题](#常见问题)
- [鸣谢](#鸣谢)
- [许可协议](#许可协议)

---

## 简介

**MFWPH**（MaaFramework with Plugin Host）是基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 构建的一款资源脚本加载器与统一 UI 启动平台。  
能更方便的帮你管理maafw的资源文件

---

## 功能特点

- **🔄 多设备多任务并行处理**  
  支持同时管理多个设备，智能调度任务并行执行，提高整体效率。

- **🎯 灵活的自动化控制**  
  提供丰富的命令行参数，支持无窗口模式、定时任务和自定义超时控制。

- **⏰ 智能超时管理**  
  可配置的超时时间，从5分钟到无限制，支持各种场景的长时间任务。

- **🔇 服务器友好**  
  无窗口模式完美支持服务器环境，避免GUI相关问题。

- **📊 详细监控日志**  
  完整的执行状态监控，实时日志记录和错误追踪。

- **🛡️ 安全退出机制**  
  优雅的资源清理和强制退出保护，确保系统稳定。

- **🎨 现代化UI界面**  
  基于 Qt 构建的现代化界面设计，直观易用。

- **🔄 动态资源管理**  
  自动检测资源变化，支持热加载和动态更新。

---

## 安装与使用

### 快速开始

#### GUI模式（推荐新用户）

1. **下载全量包**  
   请访问 [Releases 页面](https://github.com/TanyaShue/MFWPH/releases) 下载最新版本的全量包。

2. **解压与运行**  
   解压下载包后，直接运行 `MFWPH.exe`（或适用于你操作系统的启动文件）。

3. **添加资源**  
   - 通过左侧导航栏中的【资源管理】功能添加资源。
   - 或手动将资源脚本复制到项目内的 `assets/resource` 文件夹中，重启程序后即可自动加载。

#### 命令行模式

MFWPH支持丰富的命令行参数，适合自动化部署和服务器环境：

```bash
# 查看所有可用参数
python main.py --help

# 无窗口模式启动所有设备（1小时超时）
python main.py --headless --device all

# 启动特定设备，2小时超时
python main.py --headless --device "我的设备" --timeout 7200

# 无限制超时，适合超长时间任务
python main.py --headless --device all --timeout 0

# 指定配置方案启动
python main.py --headless --device "服务器1" --config "生产环境配置"
```

**参数说明：**
- `--headless`: 无窗口模式，适合服务器环境
- `--device`: 指定设备名称，或使用 `all` 启动所有设备
- `--timeout`: 超时时间（秒），0表示无限制
- `--config`: 指定使用的配置方案
- `--exit-on-complete`: 任务完成后自动退出

**使用场景：**
- **CI/CD集成**: `python main.py --headless --device all --timeout 1800`
- **定时任务**: `python main.py --headless --device "生产服务器" --timeout 0`
- **测试环境**: `python main.py --headless --device "测试设备" --timeout 300`

---

### 开发者

如果你希望添加新的自动化脚本或参与二次开发，请按下列步骤进行：

1. **克隆项目**

   ```bash
   git clone https://github.com/TanyaShue/MFWPH.git
   ```

2. **添加资源脚本**

   在 `assets/resource` 目录下添加你所开发或第三方的自动化脚本。例如，使用 Git 克隆：

   ```bash
   cd MFWPH/assets/resource
   git clone https://github.com/YourRepo/YourScript.git
   ```

3. **安装依赖**

   切换到项目根目录后，安装所需依赖包：

   ```bash
   pip install -r requirements.txt
   ```

4. **启动程序**

   **GUI模式启动：**
   ```bash
   python main.py
   ```

   **命令行模式启动：**
   ```bash
   # 开发测试
   python main.py --headless --device "测试设备" --timeout 300

   # 生产环境
   python main.py --headless --device all --timeout 0
   ```

   或在 IDE（例如 VSCode）中进行调试运行。

---

## 资源脚本结构说明

每个资源脚本应遵循以下目录结构，以便 MFWPH 正确识别并加载相关内容：

```
YourResource/
├── resource_config.json       # [必需] 资源元信息（名称、图标、描述等）
├── model/                     # 模型文件目录（如 AI 模型、识图模型等）
├── pipeline/                  # 自动化流程主逻辑代码
├── image/                     # 脚本使用的图像资源（截图、素材等）
├── agent/                     # 自定义扩展目录
│   ├── agent.py               # 自定义动作模块（如点击、滑动等逻辑）
│   ├── custom_action/         # 自定义动作模块（如点击、滑动等逻辑）
│   └── custom_recognition/    # 自定义图像识别模块（如自定义 OCR、特征匹配等）
└── ...                        # 可根据需要添加的其他目录或文件（如文档、日志等）
```

**示例配置文件（`resource_config.json`）：**

可参考 [MaaYYs 的 resource_config.json](https://github.com/TanyaShue/MaaYYs/blob/main/resource_config.json) 文件。  
该文件用于定义资源名称、描述、图标路径以及其他元数据信息，使得平台在加载时能正确展示资源信息。
可查看具体文档[resource_config_zh.md](docs/resource_config_zh.md)[doc/]以及示例文件[resource_config.example.json](docs/example/resource_config.example.json)

---

## 命令行参数详解

MFWPH 提供了丰富的命令行参数，支持各种自动化场景：

### 参数列表

| 参数 | 简写 | 类型 | 默认值 | 描述 |
|------|------|------|--------|------|
| `--headless` | 无 | 布尔 | False | 无窗口模式运行 |
| `--device` | `-d` | 字符串列表 | 无 | 设备名称，或使用 `all` |
| `--config` | `-c` | 字符串 | 当前配置 | 使用的配置方案 |
| `--timeout` | `-t` | 整数 | 3600 | 超时时间（秒），0表示无限制 |
| `--exit-on-complete` | 无 | 布尔 | False | 任务完成后自动退出 |

### 向后兼容参数

| 旧参数 | 等价新参数 |
|--------|------------|
| `-auto` | `--headless` |
| `-s DEVICES` | `--device DEVICES` |
| `-exit_on_complete` | `--exit-on-complete` |

### 使用示例

#### 基础用法
```bash
# GUI模式启动
python main.py

# 查看帮助
python main.py --help
```

#### 无窗口模式
```bash
# 启动所有设备，默认1小时超时
python main.py --headless --device all

# 启动特定设备，30分钟超时
python main.py --headless --device "服务器1" --timeout 1800

# 多设备并发
python main.py --headless --device "设备1" "设备2" "设备3"
```

#### 超时控制
```bash
# 5分钟测试
python main.py --headless --device test --timeout 300

# 2小时批量处理
python main.py --headless --device all --timeout 7200

# 无限制超时（适合超长任务）
python main.py --headless --device all --timeout 0
```

#### 高级配置
```bash
# 指定配置方案
python main.py --headless --device all --config "生产环境配置"

# 有窗口但任务后退出
python main.py --device all --exit-on-complete --timeout 3600
```
---

## 常见问题

### 基本使用

**Q: 是否可以同时添加多个脚本项目？**  
A: 可以。MFWPH 会自动扫描 `assets/resource` 目录下的所有资源，并在左侧导航栏中展示。

**Q: 资源脚本无法运行怎么办？**  
A: 请确认脚本遵循了 MaaFramework 的开发规范，并检查 `resource_config.json` 文件是否正确配置。

**Q: UI 无法启动或运行异常？**  
A: 请确保已正确安装所有依赖，并使用 Python 3.9 及以上版本运行项目。如果问题仍然存在，请查阅项目文档或提交 Issue。

### 命令行使用

**Q: 如何在服务器环境使用MFWPH？**  
A: 使用 `--headless` 参数启动无窗口模式：
```bash
python main.py --headless --device all --timeout 0
```

**Q: 任务执行时间很长怎么办？**  
A: 使用 `--timeout 0` 参数禁用超时限制：
```bash
python main.py --headless --device all --timeout 0
```

**Q: 如何查看所有可用的命令行参数？**  
A: 运行 `python main.py --help` 查看完整参数列表和说明。

**Q: 程序启动后立即退出怎么办？**  
A: 检查是否使用了 `--exit-on-complete` 参数，或者检查日志文件了解具体错误原因。

### 故障排除

**Q: 日志文件在哪里？**  
A: 日志文件存储在 `logs/` 目录下，包括 `app.log`（主程序日志）和各设备的专门日志文件。

**Q: 如何调试命令行启动问题？**  
A: 1. 检查Python环境和依赖安装
2. 查看控制台输出和日志文件
3. 使用短超时时间进行测试：`--timeout 60`
4. 确认设备配置正确

**Q: 内存使用过高怎么办？**  
A: 1. 减少并发设备数量
2. 定期清理临时文件
3. 监控系统资源使用情况
4. 考虑使用 `--timeout` 参数限制执行时间

### 性能优化

**Q: 如何提高多设备并发性能？**  
A: 1. 确保系统有足够的CPU和内存资源
2. 合理分配设备任务，避免资源竞争
3. 使用SSD存储提升I/O性能
4. 定期维护和清理日志文件

---

## 鸣谢

- 本项目基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 提供的核心架构和功能支持。
- 感谢所有为自动化脚本生态建设做出贡献的开发者与用户，正是你们的参与使得该项目不断完善与进步。

---

## 许可协议

本项目遵循 **MIT 许可证**。详细信息请查看 [LICENSE 文件](LICENSE)。

## 联系我们

- **项目主页**: https://github.com/TanyaShue/MFWPH
- **问题反馈**: [GitHub Issues](https://github.com/TanyaShue/MFWPH/issues)
- **讨论交流**: [GitHub Discussions](https://github.com/TanyaShue/MFWPH/discussions)
