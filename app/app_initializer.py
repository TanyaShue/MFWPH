# --- app/app_initializer.py ---
"""
应用初始化模块
负责Qt应用和窗口的初始化
"""

import os
import signal
import asyncio

import qasync
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyleFactory

from app.main_window import MainWindow
from app.models.logging.log_manager import LogManager
from app.utils.notification_manager import notification_manager
from app.utils.until import load_light_palette, StartupResourceUpdateChecker
from app.utils.global_logger import get_logger
from app.exit_handler import force_exit_cleanup


logger = get_logger()


def parse_arguments():
    """解析命令行参数"""
    import argparse

    parser = argparse.ArgumentParser(description="MFWPH - 多设备任务管理器")
    parser.add_argument("--headless", action="store_true",
                        help="无窗口模式运行，不显示GUI界面")
    parser.add_argument("--device", "-d", nargs="+",
                        help="指定要启动的设备名称，或使用 'all' 启动所有设备")
    parser.add_argument("--config", "-c",
                        help="指定使用的配置方案名称（可选，默认使用当前保存的配置）")
    parser.add_argument("--exit-on-complete", action="store_true",
                        help="任务完成后自动退出程序")
    parser.add_argument("--timeout", "-t", type=int, default=3600,
                        help="等待任务完成的超时时间（秒），0表示无限制 (默认: 3600)")

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

    return args


def initialize_logging_manager(args):
    """初始化日志管理器"""
    global log_manager, logger

    if args.headless:
        # 无头模式：禁用Qt功能以避免线程问题
        log_manager = LogManager(enable_qt=False)
    else:
        # 有窗口模式：启用完整功能
        log_manager = LogManager(enable_qt=True)

    logger = log_manager.get_app_logger()
    return log_manager


def initialize_application(args, base_path):
    """初始化Qt应用程序"""
    # 在无头模式下使用offscreen平台避免Qt警告
    if args.headless:
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'

    app = QApplication([])  # 使用空列表而不是sys.argv，避免参数冲突

    # ❗ 关键：允许 Qt 正常在窗口关闭时退出
    app.setQuitOnLastWindowClosed(True)

    # 只在有窗口模式下设置样式和调色板
    if not args.headless:
        app.setStyle(QStyleFactory.create("Fusion"))
        app.setPalette(load_light_palette())

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    return app, loop


def setup_signal_handlers():
    """设置信号处理器"""
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


def create_main_window(app, loop, base_path):
    """创建主窗口（有窗口模式）"""
    icon_path = os.path.join(base_path, "assets", "icons", "app", "logo.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    notification_manager.set_reference_window(window)

    from app.main_window_patch import patch_mainwindow_exit_logic
    patch_mainwindow_exit_logic(window, loop, app)
    window.show()

    startup_checker = StartupResourceUpdateChecker(window)
    QTimer.singleShot(1000, startup_checker.check_for_updates)

    return window


def schedule_task_startup(args):
    """调度任务启动"""
    if args.device:
        # 创建一个协程来延迟启动任务
        async def delayed_start():
            await asyncio.sleep(0.1)  # 短暂延迟确保事件循环稳定
            from app.task.task_manager import start_tasks_on_startup
            await start_tasks_on_startup(args)

        # 使用asyncio.ensure_future来确保任务在事件循环中被调度
        asyncio.ensure_future(delayed_start())


def run_event_loop(loop):
    """运行事件循环"""
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
