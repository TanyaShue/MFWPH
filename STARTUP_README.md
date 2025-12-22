# MFWPH 启动参数说明

## 概述

MFWPH 现在支持通过命令行参数启动程序，实现自动化任务执行和无窗口模式运行。

## 启动参数

### 基本参数

- `--headless`: 无窗口模式运行，不显示GUI界面（默认在任务完成后自动退出）
- `--device DEVICE` 或 `-d DEVICE`: 指定要启动的设备名称，或使用 `all` 启动所有设备
- `--config CONFIG` 或 `-c CONFIG`: 指定使用的配置方案名称（可选，默认使用当前保存的配置）
- `--exit-on-complete`: 任务完成后自动退出程序（在有窗口模式下需要显式指定，无窗口模式下为默认行为）

### 向后兼容参数

为了保持向后兼容，仍支持以下旧参数：

- `-auto`: 相当于 `--headless`
- `-s DEVICES`: 相当于 `--device DEVICES`
- `-exit_on_complete`: 相当于 `--exit-on-complete`

## 使用示例

### 1. 显示帮助信息
```bash
python main.py --help
```

### 2. 无窗口模式启动所有设备
```bash
python main.py --headless --device all
```
这将：
- 不显示GUI界面
- 启动所有设备的所有任务
- 所有任务完成后自动退出程序（无窗口模式默认行为）

### 3. 无窗口模式启动特定设备
```bash
python main.py --headless --device "我的设备"
```
这将：
- 不显示GUI界面
- 只启动指定设备的所有任务
- 任务完成后自动退出程序（无窗口模式默认行为）

### 4. 指定配置方案启动设备
```bash
python main.py --headless --device "我的设备" --config "默认配置"
```
这将：
- 使用指定的配置方案
- 启动设备的所有任务
- 任务完成后自动退出（无窗口模式默认行为）

### 5. 启动多个设备
```bash
python main.py --headless --device "设备1" "设备2" "设备3"
```

## 工作流程

1. **参数解析**: 程序解析命令行参数
2. **配置加载**: 加载设备和资源配置
3. **任务启动**: 根据参数自动启动相应设备的任务
4. **监控执行**: 监控任务执行状态
5. **自动退出**: 所有任务完成后自动退出程序（如果指定了 `--exit-on-complete`）

## 注意事项

- 无窗口模式下程序会同时输出到控制台和日志文件，便于监控
- 无窗口模式不会创建GUI组件，避免Qt相关警告和线程问题
- 任务执行过程中会显示详细的进度信息
- 如果发生错误，程序会记录错误信息并退出
- 超时时间设置为1小时，超过此时间程序会强制退出
- `--exit-on-complete` 参数在有窗口模式下仍需显式指定
- 配置文件已迁移到系统标准配置目录，不再使用 assets/config/
- Windows: `%APPDATA%\MFWPH\` (通常是 `C:\Users\<用户名>\AppData\Roaming\MFWPH\`)
- Linux: `~/.local/share/MFWPH/`
- macOS: `~/Library/Application Support/MFWPH/`
- 程序支持Ctrl+C中断，会执行快速清理后强制退出进程
- 所有功能完全兼容PyInstaller打包的exe文件

## 测试

运行 `test_startup.bat` 来查看所有可用的启动选项和示例。
