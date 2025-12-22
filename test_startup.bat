@echo off
REM MFWPH 启动参数测试脚本

echo ========================================
echo MFWPH 启动参数测试
echo ========================================

echo.
echo 测试1: 显示帮助信息
python main.py --help

echo.
echo 测试2: 无窗口模式启动所有设备
echo (这将启动所有设备的所有任务，完成后自动退出)
echo 命令: python main.py --headless --device all
echo.

echo 测试3: 无窗口模式启动特定设备
echo (这将启动指定设备的所有任务，完成后自动退出)
echo 命令: python main.py --headless --device "设备名称"
echo.

echo 测试4: 指定配置方案启动设备
echo (这将使用指定配置启动设备，完成后自动退出)
echo 命令: python main.py --headless --device "设备名称" --config "配置方案名"
echo.

echo ========================================
echo 使用说明：
echo ========================================
echo --headless          无窗口模式运行（默认任务完成后自动退出）
echo --device DEVICE     指定设备名称，或使用 'all' 启动所有设备
echo --config CONFIG     指定使用的配置方案（可选）
echo --exit-on-complete  任务完成后自动退出（有窗口模式下需要显式指定）
echo.
echo 示例：
echo python main.py --headless --device all
echo python main.py --headless --device "我的设备" --config "默认配置"
echo ========================================
