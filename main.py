# --- main.py ---
"""
MFWPH 主入口文件
多设备任务管理器
"""

import multiprocessing
import os
import sys

# 导入各个模块
from app.app_initializer import (
    parse_arguments,
    initialize_logging_manager,
    initialize_application,
    setup_signal_handlers,
    create_main_window,
    schedule_task_startup,
    run_event_loop,
)
from app.config.config_manager import load_and_migrate_config
from app.utils.global_logger import initialize_global_logger
from app.utils.until import clean_up_old_pyinstaller_temps


def get_base_path():
    """获取基础路径"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_windows_job_object():
    """设置Windows Job Object（仅Windows）"""
    if sys.platform != "win32":
        return

    import ctypes
    from ctypes import wintypes

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
        print("Windows Job Object enabled.")  # 此时logger还未初始化

    except Exception as e:
        print(f"Job Object setup failed: {e}")


_job_handle = None


def main():
    """主函数"""
    multiprocessing.freeze_support()

    base_path = get_base_path()
    clean_up_old_pyinstaller_temps()
    os.chdir(base_path)

    # 解析命令行参数
    args = parse_arguments()

    # 初始化日志管理器
    log_manager = initialize_logging_manager(args)

    # 初始化全局logger
    initialize_global_logger(log_manager)

    # 现在logger已初始化，可以安全调用需要logger的函数
    setup_windows_job_object()

    # 加载并迁移配置文件
    load_and_migrate_config()

    # 初始化Qt应用程序
    app, loop = initialize_application(args, base_path)

    # 设置信号处理器
    setup_signal_handlers()

    # 根据模式创建组件
    if not args.headless:
        window = create_main_window(app, loop, base_path)
    else:
        logger.info("运行在无窗口模式")
        window = None

    # 调度任务启动
    schedule_task_startup(args)

    # 运行事件循环
    run_event_loop(loop)


if __name__ == "__main__":
    main()
