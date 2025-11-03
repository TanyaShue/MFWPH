import os
import shutil
import sys
import time

import psutil
from PySide6.QtGui import QPalette, QColor

from app.models.config.global_config import global_config
from app.models.logging.log_manager import log_manager
from app.utils.notification_manager import notification_manager
from app.utils.update.checker import UpdateChecker
from app.utils.update.models import UpdateInfo

logger = log_manager.get_app_logger()

def clean_up_old_pyinstaller_temps():
    """
    清理由 PyInstaller 生成的旧的 _MEIxxxxxx 临时文件夹。
    此函数会查找并删除除当前正在使用的文件夹之外的所有残留临时文件夹。
    """
    # 检查程序是否由 PyInstaller 打包
    if not getattr(sys, 'frozen', False) or not hasattr(sys, '_MEIPASS'):
        return

    logger = log_manager.get_app_logger()
    logger.info("程序为打包版本，开始检查并清理旧的临时文件...")

    try:
        # sys._MEIPASS 是当前程序解压到的临时目录的绝对路径
        current_mei_dir = sys._MEIPASS
        # 获取包含 _MEI... 文件夹的父目录，通常是系统的临时目录
        temp_dir = os.path.dirname(current_mei_dir)

        logger.debug(f"当前临时目录: {current_mei_dir}")
        logger.debug(f"扫描目录: {temp_dir}")

        for item_name in os.listdir(temp_dir):
            if item_name.startswith('_MEI'):
                item_path = os.path.join(temp_dir, item_name)

                # 确保它是一个目录并且不是当前正在使用的目录
                if os.path.isdir(item_path) and os.path.abspath(item_path) != os.path.abspath(current_mei_dir):
                    logger.info(f"发现残留的临时目录，准备删除: {item_path}")
                    try:
                        shutil.rmtree(item_path)
                        logger.info(f"成功删除: {item_path}")
                    except Exception as e:
                        logger.warning(f"删除 {item_path} 失败: {e}。可能仍有进程在使用它。")

        logger.info("旧临时文件清理完成。")

    except Exception as e:
        logger.error(f"清理旧的 PyInstaller 临时文件时发生错误: {e}")

def load_light_palette() -> QPalette:
    """构造并返回一个浅色调 QPalette"""
    palette = QPalette()
    # 窗口和背景
    palette.setColor(QPalette.Window, QColor("#FFFFFF"))
    palette.setColor(QPalette.Base, QColor("#F0F0F0"))
    palette.setColor(QPalette.AlternateBase, QColor("#E0E0E0"))
    # 文本
    palette.setColor(QPalette.WindowText, QColor("#000000"))
    palette.setColor(QPalette.Text, QColor("#000000"))
    # 按钮
    palette.setColor(QPalette.Button, QColor("#FFFFFF"))
    palette.setColor(QPalette.ButtonText, QColor("#000000"))
    # 选中高亮
    palette.setColor(QPalette.Highlight, QColor("#0078D7"))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    # ToolTip
    palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    palette.setColor(QPalette.ToolTipText, QColor("#000000"))
    return palette

def kill_processes():
    app_logger = log_manager.get_app_logger()

    try:
        # 修改：检查复数形式的 agent_processes 列表
        if hasattr(global_config, "agent_processes") and global_config.agent_processes:
            app_logger.info(f"正在清理 {len(global_config.agent_processes)} 个 Agent 进程...")
            # 遍历列表中的每一个 agent 进程
            for proc in list(global_config.agent_processes):
                try:
                    # 获取进程组成员（Windows只能通过children递归）
                    if os.name == 'nt':
                        ps_proc = psutil.Process(proc.pid)
                        group_members = [ps_proc] + ps_proc.children(recursive=True)
                    else:
                        pgid = os.getpgid(proc.pid)
                        group_members = [p for p in psutil.process_iter(['pid', 'name'])
                                         if os.getpgid(p.pid) == pgid]

                    app_logger.debug(f"准备清理 Agent 进程组 (父进程 PID: {proc.pid})...")

                    # 直接 kill 组内所有进程
                    for p in group_members:
                        try:
                            p.kill()
                            app_logger.info(f"已终止 agent 进程: PID={p.pid}, 名称={p.name()}")
                        except psutil.NoSuchProcess:
                            pass # 进程已不存在，忽略
                        except Exception as e:
                            app_logger.error(f"终止 agent 进程 PID={p.pid} 失败: {e}")

                except Exception as e:
                    app_logger.error(f"清理 agent 进程组 {proc.pid} 失败: {e}")
    except Exception as e:
        app_logger.error(f"处理 agent 进程组终止时发生错误: {e}")


    # ---------- 2. 杀掉 adb ----------
    # current_process = psutil.Process(os.getpid())
    # current_process_name = current_process.name()
    #
    # for proc in psutil.process_iter(['name', 'pid']):
    #     if proc.info.get('name', '').lower() == "adb.exe":
    #         try:
    #             proc.kill()
    #             app_logger.info(f"已终止 adb.exe 进程，PID: {proc.pid}")
    #         except Exception as e:
    #             app_logger.error(f"终止 adb.exe 进程 (PID: {proc.pid}) 失败: {e}")

    # ---------- 3. 杀掉同名程序 ----------
    # for proc in psutil.process_iter(['name', 'pid']):
    #     try:
    #         if proc.info['name'] == current_process_name and proc.pid != current_process.pid:
    #             for child in proc.children(recursive=True):
    #                 try:
    #                     child.kill()
    #                     app_logger.info(f"已终止子进程 {child.name()}，PID: {child.pid}")
    #                 except Exception as e:
    #                     app_logger.error(f"终止子进程 (PID: {child.pid}) 失败: {e}")
    #             proc.kill()
    #             app_logger.info(f"已终止同名进程 {current_process_name}，PID: {proc.pid}")
    #     except Exception as e:
    #         app_logger.error(f"处理进程时发生错误: {e}")
    #
    time.sleep(0.5)
    app_logger.info("进程清理完成")


logger = log_manager.get_app_logger()


class StartupResourceUpdateChecker:
    """启动时的资源更新检查器 (已适配新版)"""

    def __init__(self, main_window):
        self.main_window = main_window
        self.update_checker_thread = None
        self.resources_with_updates: list[UpdateInfo] = []  # <-- 类型提示为 UpdateInfo 列表

    def check_for_updates(self):
        """检查是否需要自动检查资源更新"""
        try:
            auto_check = global_config.get_app_config().auto_check_update
            if not isinstance(auto_check, bool):
                auto_check = False

            if auto_check:
                logger.info("自动检查资源更新已启用，开始检查...")
                resources = self._get_installed_resources()
                if not resources:
                    logger.info("没有已安装的资源需要检查更新")
                    return

                notification_manager.show_info(
                    f"正在后台检查 {len(resources)} 个资源的更新...",
                    "自动更新检查"
                )

                self.update_checker_thread = UpdateChecker(resources, single_mode=False)
                # 连接信号到新的处理方法
                self.update_checker_thread.update_found.connect(self._handle_resource_update_found)
                self.update_checker_thread.update_not_found.connect(self._handle_resource_update_not_found)
                self.update_checker_thread.check_failed.connect(self._handle_resource_check_failed)
                self.update_checker_thread.check_completed.connect(self._handle_check_completed)
                self.update_checker_thread.start()
            else:
                logger.info("自动检查更新未启用")

        except Exception as e:
            logger.error(f"启动时检查更新配置失败: {e}", exc_info=True)

    def _get_installed_resources(self):
        """获取所有已安装的资源"""
        try:
            # global_config.resource_configs 是一个字典，我们需要它的值
            resources = list(global_config.resource_configs.values())
            return resources
        except Exception as e:
            logger.error(f"获取已安装资源列表失败: {e}", exc_info=True)
            return []

    def _handle_resource_update_found(self, update_info: UpdateInfo):
        """
        【已修改】处理发现资源更新的情况。
        现在接收一个 UpdateInfo 对象。
        """
        logger.info(
            f"资源 {update_info.resource_name} 发现新版本: {update_info.new_version} (当前版本: {update_info.current_version})")

        # 直接存储 UpdateInfo 对象
        self.resources_with_updates.append(update_info)

    def _handle_resource_update_not_found(self, resource_name: str):
        """处理资源未发现更新的情况"""
        logger.info(f"资源 {resource_name} 已是最新版本")

    def _handle_resource_check_failed(self, resource_name: str, error_message: str):
        """处理资源检查失败的情况"""
        logger.error(f"资源 {resource_name} 检查更新失败: {error_message}")

    def _handle_check_completed(self, total_checked: int, updates_found: int):
        """
        【已修改】处理所有资源检查完成。
        """
        logger.info(f"资源更新检查完成: 共检查 {total_checked} 个资源，发现 {updates_found} 个更新")

        if updates_found > 0:
            # 确保收集到的更新数量与报告的一致
            if len(self.resources_with_updates) != updates_found:
                logger.warning(
                    f"Updates found count mismatch. Reported: {updates_found}, Collected: {len(self.resources_with_updates)}")

            # 构建更新通知消息
            update_list = []
            for update in self.resources_with_updates[:3]:  # 最多显示3个
                # 从 UpdateInfo 对象中获取信息
                update_list.append(f"• {update.resource_name} → {update.new_version}")

            if updates_found > 3:
                update_list.append(f"• ... 以及其他 {updates_found - 3} 个资源")

            message = f"发现 {updates_found} 个资源有可用更新：\n" + "\n".join(update_list)

            notification_manager.show_warning(
                message + "\n\n请前往资源管理页面查看详情",
                "资源更新可用",
                duration=10000
            )

            if hasattr(self.main_window, 'set_resource_updates_available'):
                # 传递 UpdateInfo 对象列表
                self.main_window.set_resource_updates_available(True, self.resources_with_updates)
        else:
            logger.info("所有资源均为最新版本")