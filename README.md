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
- [资源脚本结构说明](#资源脚本结构说明)
- [常见问题](#常见问题)
- [鸣谢](#鸣谢)
- [许可协议](#许可协议)

---

## 简介

**MFWPH**（MaaFramework with Plugin Host）是基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 构建的一款资源脚本加载器与统一 UI 启动平台。  
该平台致力于帮助用户集中管理各类自动化资源脚本（例如 MaaYYs 等），以简化使用流程并提升脚本管理效率。  
MFWPH 提供直观的图形化界面，使非开发人员也能轻松添加、管理和运行自动化任务。

---

## 功能特点

- 📦 **资源脚本插件化加载**  
  支持自定义行为脚本加载，无需修改主程序代码即可接入更多自动化工具。

- 🧩 **多脚本共存运行**  
  可同时加载并管理多个自动化项目，在左侧导航栏中自动展示所有已添加的资源。

- 🖥️ **图形化界面**  
  基于 Qt 构建的现代化界面设计，直观易用。

- 🔄 **动态资源更新**  
  当在资源目录下添加、删除或更新资源。

---

## 安装与使用

### 快速开始

1. **下载全量包**  
   请访问 [Releases 页面](https://github.com/TanyaShue/MFWPH/releases) 下载最新版本的全量包。

2. **解压与运行**  
   解压下载包后，直接运行 `MFWPH.exe`（或适用于你操作系统的启动文件）。

3. **添加资源**  
   - 通过左侧导航栏中的【资源管理】功能添加资源。
   - 或手动将资源脚本复制到项目内的 `assets/resource` 文件夹中，重启程序后即可自动加载。

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

   直接运行主程序：

   ```bash
   python main.py
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
├── custom_dir/                # 自定义扩展目录
│   ├── custom_action/         # 自定义动作模块（如点击、滑动等逻辑）
│   └── custom_recognition/    # 自定义图像识别模块（如自定义 OCR、特征匹配等）
└── ...                        # 可根据需要添加的其他目录或文件（如文档、日志等）
```

**示例配置文件（`resource_config.json`）：**

可参考 [MaaYYs 的 resource_config.json](https://github.com/TanyaShue/MaaYYs/blob/main/resource_config.json) 文件。  
该文件用于定义资源名称、描述、图标路径以及其他元数据信息，使得平台在加载时能正确展示资源信息。

---

## 常见问题

**Q: 是否可以同时添加多个脚本项目？**  
A: 可以。MFWPH 会自动扫描 `assets/resource` 目录下的所有资源，并在左侧导航栏中展示。

**Q: 资源脚本无法运行怎么办？**  
A: 请确认脚本遵循了 MaaFramework 的开发规范，并检查 `resource_config.json` 文件是否正确配置。

**Q: UI 无法启动或运行异常？**  
A: 请确保已正确安装所有依赖，并使用 Python 3.9 及以上版本运行项目。如果问题仍然存在，请查阅项目文档或提交 Issue。

---

## 鸣谢

- 本项目基于 [MaaFramework](https://github.com/MaaXYZ/MaaFramework) 提供的核心架构和功能支持。
- 感谢所有为自动化脚本生态建设做出贡献的开发者与用户，正是你们的参与使得该项目不断完善与进步。

---

## 许可协议

本项目遵循 **MIT 许可证**。详细信息请查看 [LICENSE 文件](LICENSE)。
