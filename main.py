# --- main.py ---
import asyncio
import os
import sys
import argparse
import multiprocessing
import signal
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QTimer, QStandardPaths
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtWidgets import QApplication, QStyleFactory
import qasync

from app.main_window import MainWindow
from app.models.logging.log_manager import LogManager, log_manager
from app.models.config.global_config import global_config
from app.utils.notification_manager import notification_manager
from app.utils.until import (
    clean_up_old_pyinstaller_temps,
    load_light_palette,
    StartupResourceUpdateChecker,
    kill_processes,
)

from core.tasker_manager import task_manager

# logger 会在 main 函数中初始化
logger = None

_job_handle = None


async def force_exit_cleanup():
    """强制退出清理函数"""
    logger.info("开始强制退出清理...")

    try:
        # 快速停止所有任务（最多等待2秒）
        logger.info("停止所有任务...")
        await asyncio.wait_for(task_manager.stop_all(), timeout=2.0)
        logger.info("任务管理器已停止")
    except asyncio.TimeoutError:
        logger.warning("任务停止超时，继续退出")
    except Exception as e:
        logger.error(f"停止任务时出错: {e}")

    try:
        # 快速清理子进程
        kill_processes()
        logger.info("子进程已清理")
    except Exception as e:
        logger.error(f"清理子进程时出错: {e}")

    logger.info("强制退出进程...")
    os._exit(1)


def load_and_migrate_config():
    """
    加载并迁移配置文件
    使用 QStandardPaths 获取配置路径，实现配置文件的统一管理
    """
    try:
        # 加载资源目录（支持PyInstaller打包环境）
        if getattr(sys, 'frozen', False):
            # PyInstaller打包环境
            base_path = sys._MEIPASS
        else:
            # 开发环境
            base_path = os.path.dirname(os.path.abspath(__file__))

        resource_dir = os.path.join(base_path, "assets", "resource")
        if not os.path.exists(resource_dir):
            os.makedirs(resource_dir)
        global_config.load_all_resources_from_directory(resource_dir)
        logger.info(f"资源目录加载完成: {resource_dir}")
    except OSError as e:
        logger.error(f"创建或访问资源目录时发生操作系统错误: {e}")
    except Exception as e:
        logger.error(f"从资源目录加载时发生未知错误: {e}")

    try:
        # 使用 QStandardPaths 获取配置目录
        # AppDataLocation 返回 %APPDATA% (Windows) 或 ~/.local/share (Linux) 或 ~/Library/Application Support (macOS)
        config_locations = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.AppDataLocation)
        if config_locations:
            config_base_dir = os.path.join(config_locations[0], "MFWPH")
        else:
            # fallback to platform-specific locations
            if os.name == 'nt':  # Windows
                config_base_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "MFWPH")
            elif sys.platform == 'darwin':  # macOS
                config_base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "MFWPH")
            else:  # Linux and others
                config_base_dir = os.path.join(os.path.expanduser("~"), ".config", "MFWPH")

        # 确保配置目录存在
        if not os.path.exists(config_base_dir):
            os.makedirs(config_base_dir)
            logger.info(f"创建配置目录: {config_base_dir}")

        # 配置文件路径
        config_file_path = os.path.join(config_base_dir, "app_config.json")
        logger.info(f"使用配置文件路径: {config_file_path}")

        # 检查新位置是否有配置文件
        if os.path.exists(config_file_path):
            logger.info("在新位置找到配置文件，直接加载")
            global_config.load_app_config(config_file_path)
        else:
            logger.info("新位置没有配置文件，尝试迁移")

            # 检查旧位置的配置文件
            old_config_path = "assets/config/app_config.json"
            old_config_dir = os.path.dirname(old_config_path)

            if os.path.exists(old_config_path):
                logger.info(f"从旧位置迁移配置文件: {old_config_path} -> {config_file_path}")
                # 复制配置文件到新位置
                import shutil
                shutil.copy2(old_config_path, config_file_path)
                global_config.load_app_config(config_file_path)
                logger.info("配置文件迁移完成")
            else:
                logger.info("旧位置也没有配置文件，创建默认配置")
                # 创建默认配置文件
                if not os.path.exists(old_config_dir):
                    os.makedirs(old_config_dir)

                # 创建空的配置文件
                with open(config_file_path, "w", encoding="utf-8") as f:
                    f.write("{}")

                global_config.load_app_config(config_file_path)
                logger.info("创建并加载默认配置文件")

        # 设置配置文件的新路径
        global_config.get_app_config().source_file = config_file_path

    except (OSError, IOError) as e:
        logger.error(f"处理应用配置文件时发生IO错误: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"解析应用配置文件失败: {e}")
    except Exception as e:
        logger.error(f"加载应用配置时发生未知错误: {e}")

    try:
        # 设置默认窗口大小
        app_config = global_config.get_app_config()
        if not hasattr(app_config, 'window_size') or not app_config.window_size:
            app_config.window_size = "800x600"
            logger.info("设置默认窗口大小: 800x600")
    except Exception as e:
        logger.error(f"获取或处理应用配置时出错: {e}")


async def start_tasks_on_startup(args):
    """
    根据启动参数自动启动任务
    """
    try:
        logger.info(f"启动参数: device={args.device}, config={args.config}, exit_on_complete={args.exit_on_complete}")

        # 等待配置加载完成
        await asyncio.sleep(1)

        devices_to_start = args.device

        # 处理"all"参数
        if "all" in devices_to_start:
            app_config = global_config.get_app_config()
            devices_to_start = [device.device_name for device in app_config.devices]
            logger.info(f"启动所有设备: {devices_to_start}")
        else:
            logger.info(f"启动指定设备: {devices_to_start}")

        # 为每个设备启动任务
        for device_name in devices_to_start:
            device_config = global_config.get_device_config(device_name)
            if not device_config:
                logger.error(f"找不到设备配置: {device_name}")
                continue

            logger.info(f"启动设备 {device_name} 的所有任务")

            # 如果指定了配置方案，先切换配置
            if args.config:
                logger.info(f"为设备 {device_name} 使用配置方案: {args.config}")
                # 这里可以添加配置切换逻辑，如果需要的话

            # 启动设备的所有任务
            success = await task_manager.run_device_all_resource_task(device_config)
            if success:
                logger.info(f"设备 {device_name} 任务启动成功")
            else:
                logger.warning(f"设备 {device_name} 任务启动失败")

        # 如果设置了退出参数，监听任务完成
        if args.exit_on_complete:
            logger.info("等待所有任务完成...")
            await wait_for_all_tasks_complete(devices_to_start)

    except Exception as e:
        logger.error(f"启动任务时发生错误: {e}")
        if args.exit_on_complete:
            os._exit(1)  # 出错时直接退出


async def wait_for_all_tasks_complete(device_names):
    """
    等待指定设备的所有任务完成
    """
    try:
        completed_devices = set()
        timeout_seconds = 3600  # 1小时超时
        start_time = asyncio.get_event_loop().time()

        def on_device_completed(device_name):
            if device_name in device_names:
                logger.info(f"设备 {device_name} 所有任务已完成")
                completed_devices.add(device_name)

                # 检查是否所有设备都已完成
                if completed_devices >= set(device_names):
                    logger.info("所有设备任务都已完成，准备退出程序")
                    # 获取当前的app和loop
                    try:
                        app = QApplication.instance()
                        loop = asyncio.get_event_loop()
                        window = None
                        if hasattr(app, '_main_window'):
                            window = app._main_window
                        asyncio.create_task(perform_graceful_shutdown(loop, app, window))
                    except Exception as e:
                        logger.error(f"获取应用实例失败，直接退出: {e}")
                        os._exit(0)

        # 连接任务完成信号
        task_manager.all_tasks_completed.connect(on_device_completed)

        # 等待任务完成或超时
        while completed_devices < set(device_names):
            await asyncio.sleep(5)

            # 检查超时
            current_time = asyncio.get_event_loop().time()
            if current_time - start_time > timeout_seconds:
                logger.warning(f"等待任务完成超时 ({timeout_seconds}秒)，强制退出")
                os._exit(1)

            # 检查是否还有活跃的任务处理器
            active_devices = [name for name in device_names if task_manager.is_device_active(name)]
            if not active_devices and completed_devices < set(device_names):
                logger.warning("没有活跃的任务处理器但任务未完成，可能出现异常")
                # 等待一段时间再检查
                await asyncio.sleep(10)

        logger.info("任务完成等待结束")

    except Exception as e:
        logger.error(f"等待任务完成时发生错误: {e}")
        os._exit(1)


# -----------------------------------------------------------------------------
# Windows Job Object（保持）
# -----------------------------------------------------------------------------
def setup_windows_job_object():
    if sys.platform != "win32":
        return

    global _job_handle
    try:
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
        h_job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not h_job:
            return

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ctypes.windll.kernel32.SetInformationJobObject(
            h_job, 9, ctypes.pointer(info), ctypes.sizeof(info)
        )
        ctypes.windll.kernel32.AssignProcessToJobObject(
            h_job, ctypes.windll.kernel32.GetCurrentProcess()
        )

        _job_handle = h_job
        logger.info("Windows Job Object enabled.")

    except Exception as e:
        logger.error(f"Job Object setup failed: {e}")


def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# -----------------------------------------------------------------------------
# ✅ 真正可靠的退出流程（必达）
# -----------------------------------------------------------------------------
async def perform_graceful_shutdown(loop, app, window):
    logger.info("🛑 Graceful shutdown started")

    # 1️⃣ UI 立刻消失（如果有窗口的话）
    try:
        if window:
            window.hide()
        if app:
            app.processEvents()
    except Exception:
        pass

    # 2️⃣ 尝试优雅关闭后台任务（最多 3 秒）
    try:
        logger.info("Stopping task manager (timeout=3s)...")
        await asyncio.wait_for(task_manager.stop_all(), timeout=3)
        logger.info("Task manager stopped cleanly.")
    except asyncio.TimeoutError:
        logger.warning("Task manager shutdown timed out.")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    # 3️⃣ 清理子进程兜底
    try:
        kill_processes()
    except Exception:
        pass

    # 4️⃣ 停止事件循环
    try:
        loop.stop()
    except Exception:
        pass

    # 5️⃣ Qt quit + OS 级强退（双保险）
    logger.info("💀 Forcing process exit.")
    try:
        if app:
            app.quit()
    except Exception:
        pass

    os._exit(0)  # 最终兜底，确保不留后台


# -----------------------------------------------------------------------------
# 关闭事件 Patch（修复版）
# -----------------------------------------------------------------------------
def patch_mainwindow_exit_logic(window: MainWindow, loop, app):
    def save_window_config():
        try:
            size = window.size()
            pos = window.pos()
            app_config = global_config.get_app_config()
            app_config.window_size = f"{size.width()}x{size.height()}"
            app_config.window_position = f"{pos.x()},{pos.y()}"
            global_config.save_all_configs()
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def patched_close_event(event: QCloseEvent):
        app_config = global_config.get_app_config()

        # 👉 仅“最小化到托盘”时阻止关闭
        if app_config.minimize_to_tray_on_close:
            event.ignore()
            window.hide()
            return

        # 👉 真正退出
        logger.info("User requested exit (window close).")
        save_window_config()

        event.accept()  # 允许 Qt 关闭窗口
        asyncio.create_task(
            perform_graceful_shutdown(loop, app, window)
        )

    def patched_force_quit():
        logger.info("User requested exit (tray).")
        save_window_config()
        asyncio.create_task(
            perform_graceful_shutdown(loop, app, window)
        )

    window.closeEvent = patched_close_event
    window.force_quit = patched_force_quit

    logger.info("MainWindow exit logic patched (safe-exit mode).")


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------
def main():
    multiprocessing.freeze_support()

    base_path = get_base_path()
    clean_up_old_pyinstaller_temps()
    os.chdir(base_path)

    # 解析参数以确定是否启用Qt功能
    parser = argparse.ArgumentParser(description="MFWPH - 多设备任务管理器")
    parser.add_argument("--headless", action="store_true",
                        help="无窗口模式运行，不显示GUI界面")
    parser.add_argument("--device", "-d", nargs="+",
                        help="指定要启动的设备名称，或使用 'all' 启动所有设备")
    parser.add_argument("--config", "-c",
                        help="指定使用的配置方案名称（可选，默认使用当前保存的配置）")
    parser.add_argument("--exit-on-complete", action="store_true",
                        help="任务完成后自动退出程序")

    # 保持向后兼容的旧参数
    parser.add_argument("-auto", action="store_true")
    parser.add_argument("-s", nargs="+", default=["all"])
    parser.add_argument("-exit_on_complete", action="store_true")

    args = parser.parse_args()

    # 处理参数兼容性
    if args.auto and not args.headless:
        args.headless = True
    if args.s != ["all"] and not args.device:
        args.device = args.s
    if args.exit_on_complete and not args.exit_on_complete:
        args.exit_on_complete = args.exit_on_complete

    # 无窗口模式默认启用退出行为
    if args.headless and not args.exit_on_complete:
        args.exit_on_complete = True

    # 根据模式初始化日志管理器
    global log_manager
    if args.headless:
        # 无头模式：禁用Qt功能以避免线程问题
        log_manager = LogManager(enable_qt=False)
    else:
        # 有窗口模式：启用完整功能
        log_manager = LogManager(enable_qt=True)

    global logger
    logger = log_manager.get_app_logger()

    # 现在logger已初始化，可以安全调用需要logger的函数
    setup_windows_job_object()

    # 加载并迁移配置文件
    load_and_migrate_config()

    # 在无头模式下使用offscreen平台避免Qt警告
    if args.headless:
        # 设置环境变量使用offscreen平台
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'

    app = QApplication(sys.argv)

    # ❗ 关键：允许 Qt 正常在窗口关闭时退出
    app.setQuitOnLastWindowClosed(True)

    # 只在有窗口模式下设置样式和调色板
    if not args.headless:
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(load_light_palette())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # 设置信号处理器来处理Ctrl+C
    def signal_handler(signum, frame):
        logger.info("接收到中断信号，正在强制退出...")
        # 直接强制退出，不依赖Qt事件循环
        try:
            # 尝试优雅退出
            asyncio.create_task(force_exit_cleanup())
        except:
            # 如果asyncio不可用，直接强制退出
            logger.info("强制退出进程...")
            os._exit(1)

    # 注册SIGINT处理器 (Ctrl+C)
    signal.signal(signal.SIGINT, signal_handler)

    # 根据模式创建不同的组件
    if not args.headless:
        # 有窗口模式：设置图标，创建窗口等
        icon_path = os.path.join(base_path, "assets", "icons", "app", "logo.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

        window = MainWindow()
        notification_manager.set_reference_window(window)

        patch_mainwindow_exit_logic(window, loop, app)

        window.show()

        startup_checker = StartupResourceUpdateChecker(window)
        QTimer.singleShot(1000, startup_checker.check_for_updates)
    else:
        logger.info("运行在无窗口模式")
        # 无头模式：不创建窗口，避免Qt组件问题
        window = None

    # 如果指定了设备参数，在事件循环内启动任务
    if args.device:
        # 创建一个协程来延迟启动任务
        async def delayed_start():
            await asyncio.sleep(0.1)  # 短暂延迟确保事件循环稳定
            await start_tasks_on_startup(args)

        # 使用asyncio.ensure_future来确保任务在事件循环中被调度
        # 这个函数可以在事件循环启动前调用，它会在loop可用时启动任务
        asyncio.ensure_future(delayed_start())

    try:
        with loop:
            loop.run_forever()
    except KeyboardInterrupt:
        logger.info("检测到KeyboardInterrupt，正在强制退出...")
        # 直接强制退出，不依赖Qt事件循环
        try:
            asyncio.create_task(force_exit_cleanup())
        except:
            logger.info("强制退出进程...")
            os._exit(1)
    except Exception as e:
        logger.error(f"事件循环异常: {e}")
        logger.info("因异常强制退出进程...")
        os._exit(1)


if __name__ == "__main__":
    main()
