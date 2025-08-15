"""
独立更新程序
用于在主程序退出后执行更新操作，支持增量更新和完整更新
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
import psutil
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        # 将日志同时输出到文件和控制台
        logging.FileHandler('updater.log', encoding='utf-8', mode='w'), # mode='w' 每次启动时覆盖日志
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class StandaloneUpdater:
    def __init__(self, update_package, update_type='full', target_dir=None,
                 restart_program=None, wait_pid=None):
        """
        初始化更新器

        Args:
            update_package (str): 更新包路径
            update_type (str): 更新类型 ('incremental' 或 'full')
            target_dir (str): 目标目录，默认为当前目录
            restart_program (str): 更新完成后要启动的程序
            wait_pid (int): 需要等待退出的进程PID
        """
        # ==================== 开始修改 ====================
        # 优先使用绝对路径，增加健壮性
        self.target_dir = Path(target_dir).resolve() if target_dir else Path.cwd().resolve()
        self.update_package = self.target_dir.joinpath(update_package).resolve()

        self.update_type = update_type
        self.restart_program = restart_program
        self.wait_pid = wait_pid
        self.backup_dir = self.target_dir / "update_backup"
        self.temp_dir = self.target_dir / "update_temp"

        # 需要跳过更新的文件列表（不区分大小写）
        self.skip_files = ['update', 'updater', 'update.exe', 'updater.exe'] # 适配多平台

    def _retry_operation(self, operation, max_retries=5, delay=1):
        """
        带有重试逻辑的文件操作函数。

        Args:
            operation (callable): 需要执行的操作，例如 lambda: shutil.copy2(src, dst)
            max_retries (int): 最大重试次数
            delay (int): 每次重试的间隔时间（秒）

        Returns:
            bool: 成功返回 True，失败返回 False
        """
        for i in range(max_retries):
            try:
                operation()
                return True
            except (PermissionError, OSError) as e:
                # 只处理特定的文件占用错误
                is_access_error = isinstance(e, PermissionError) or \
                                  (isinstance(e, OSError) and e.winerror in [5, 32])
                if not is_access_error:
                    logger.error(f"发生非预期的文件错误: {e}", exc_info=True)
                    return False

                logger.warning(f"操作失败: {e}. 将在 {delay} 秒后重试... ({i + 1}/{max_retries})")
                time.sleep(delay)
        logger.error(f"操作在重试 {max_retries} 次后仍然失败。")
        return False

    def wait_for_process_exit(self, pid, timeout=30):
        """等待指定进程退出"""
        if not pid:
            return True

        logger.info(f"等待进程 {pid} 退出...")
        try:
            process = psutil.Process(pid)
            process.wait(timeout=timeout)
            logger.info(f"进程 {pid} 已退出")
            return True
        except psutil.TimeoutExpired:
            logger.warning(f"等待进程 {pid} 退出超时")
            return False
        except psutil.NoSuchProcess:
            logger.info(f"进程 {pid} 在等待开始前就已退出")
            return True

    def create_backup(self, files_to_backup):
        """创建备份"""
        logger.info("创建备份...")
        if self.backup_dir.exists():
            self._retry_operation(lambda: shutil.rmtree(self.backup_dir))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        for file_path_str in files_to_backup:
            file_path = Path(file_path_str)
            source = self.target_dir / file_path
            if source.exists():
                backup_path = self.backup_dir / file_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)

                if source.is_file():
                    success = self._retry_operation(lambda: shutil.copy2(source, backup_path))
                    if success:
                        logger.debug(f"备份文件: {file_path}")
                    else:
                        logger.error(f"备份文件失败: {file_path}")
                elif source.is_dir():
                    success = self._retry_operation(lambda: shutil.copytree(source, backup_path, dirs_exist_ok=True))
                    if success:
                        logger.debug(f"备份目录: {file_path}")
                    else:
                        logger.error(f"备份目录失败: {file_path}")

    def restore_backup(self):
        """恢复备份"""
        logger.info("恢复备份...")
        if not self.backup_dir.exists():
            logger.warning("备份目录不存在，无法恢复。")
            return

        for root, _, files in os.walk(self.backup_dir):
            for file in files:
                backup_file = Path(root) / file
                relative_path = backup_file.relative_to(self.backup_dir)
                target_file = self.target_dir / relative_path

                target_file.parent.mkdir(parents=True, exist_ok=True)
                success = self._retry_operation(lambda: shutil.copy2(backup_file, target_file))
                if success:
                    logger.debug(f"恢复文件: {relative_path}")
                else:
                    logger.error(f"恢复文件失败: {relative_path}")

    def extract_update_package(self):
        """解压更新包"""
        logger.info(f"解压更新包: {self.update_package}")
        if self.temp_dir.exists():
            self._retry_operation(lambda: shutil.rmtree(self.temp_dir))
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(self.update_package, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            logger.info("解压完成")
            return True
        except Exception as e:
            logger.error(f"解压失败: {e}", exc_info=True)
            return False

    def apply_incremental_update(self):
        """应用增量更新"""
        logger.info("应用增量更新...")
        changes_file = self.temp_dir / "changes.json"

        if not changes_file.exists():
            logger.error("changes.json 文件不存在，无法执行增量更新")
            return False

        try:
            with open(changes_file, 'r', encoding='utf-8') as f:
                changes = json.load(f)

            files_to_backup = set()
            files_to_process = changes.get("modified", []) + changes.get("deleted", [])
            for file_path in files_to_process:
                files_to_backup.add(file_path)

            if files_to_backup:
                self.create_backup(list(files_to_backup))

            success = True

            # 统一处理添加和修改的文件
            for file_path_str in changes.get("added", []) + changes.get("modified", []):
                file_path = Path(file_path_str)
                # 【关键修复】跳过更新程序自身
                if file_path.name.lower() in self.skip_files:
                    logger.info(f"跳过更新自身或相关文件: {file_path}")
                    continue

                source = self.temp_dir / file_path
                target = self.target_dir / file_path

                if source.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not self._retry_operation(lambda: shutil.copy2(source, target)):
                        logger.error(f"更新/添加文件失败: {file_path}")
                        success = False
                    else:
                        logger.info(f"更新/添加文件: {file_path}")
                else:
                    logger.warning(f"更新源文件不存在: {source}")


            # 处理删除的文件
            for file_path_str in changes.get("deleted", []):
                file_path = Path(file_path_str)
                target = self.target_dir / file_path

                if target.exists():
                    if not self._retry_operation(target.unlink):
                        logger.error(f"删除文件失败: {file_path}")
                        success = False
                    else:
                        logger.info(f"删除文件: {file_path}")

            return success

        except Exception as e:
            logger.error(f"应用增量更新时发生意外错误: {e}", exc_info=True)
            return False

    def apply_full_update(self):
        """应用完整更新 - 直接覆盖根目录文件"""
        logger.info("应用完整更新...")

        try:
            files_to_update = []
            for root, _, files in os.walk(self.temp_dir):
                for file in files:
                    files_to_update.append(Path(root) / file)

            # 备份所有将被覆盖的目标文件
            files_to_backup = []
            for source_path in files_to_update:
                relative_path = source_path.relative_to(self.temp_dir)
                if (self.target_dir / relative_path).exists():
                    files_to_backup.append(str(relative_path))

            if files_to_backup:
                self.create_backup(files_to_backup)

            # 执行更新
            success = True
            for source in files_to_update:
                relative_path = source.relative_to(self.temp_dir)

                # 【安全检查】跳过更新程序自身
                if relative_path.name.lower() in self.skip_files:
                    logger.info(f"跳过文件: {relative_path.name}")
                    continue

                target = self.target_dir / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)

                if not self._retry_operation(lambda: shutil.copy2(source, target)):
                    logger.error(f"更新文件失败: {relative_path}")
                    success = False
                else:
                    logger.info(f"更新文件: {relative_path}")

            return success

        except Exception as e:
            logger.error(f"应用完整更新时发生意外错误: {e}", exc_info=True)
            return False

    def cleanup(self, success):
        """清理临时文件"""
        logger.info("清理临时文件...")
        if self.temp_dir.exists():
            if not self._retry_operation(lambda: shutil.rmtree(self.temp_dir)):
                logger.warning(f"清理临时目录失败: {self.temp_dir}")

        # 只有在更新成功后才删除备份
        if success and self.backup_dir.exists():
            if not self._retry_operation(lambda: shutil.rmtree(self.backup_dir)):
                logger.warning(f"清理备份目录失败: {self.backup_dir}")

    def restart_application(self):
        """重启应用程序"""
        if not self.restart_program:
            return

        restart_path = self.target_dir / self.restart_program
        if not restart_path.exists():
            logger.error(f"重启程序不存在: {restart_path}")
            return

        logger.info(f"正在启动程序: {restart_path}")
        try:
            # 使用 Popen 启动新进程，不阻塞更新器
            if sys.platform == "win32":
                subprocess.Popen([str(restart_path)], creationflags=subprocess.DETACHED_PROCESS, cwd=self.target_dir)
            else:
                subprocess.Popen([str(restart_path)], cwd=self.target_dir)
            logger.info("程序已启动")
        except Exception as e:
            logger.error(f"启动程序失败: {e}", exc_info=True)

    def run(self):
        """执行更新流程"""
        logger.info("=" * 20 + " 开始更新 " + "=" * 20)
        logger.info(f"更新包: {self.update_package}")
        logger.info(f"更新类型: {self.update_type}")
        logger.info(f"目标目录: {self.target_dir}")

        if self.wait_pid:
            self.wait_for_process_exit(self.wait_pid)

        # 额外等待，确保主程序文件句柄完全释放
        time.sleep(1)

        if not self.extract_update_package():
            self.cleanup(success=False)
            return False

        if self.update_type == 'incremental':
            success = self.apply_incremental_update()
        else:
            success = self.apply_full_update()

        if not success:
            logger.error("更新失败，正在从备份恢复...")
            self.restore_backup()
            self.cleanup(success=False)
            logger.error("="*20 + " 更新失败 " + "="*20)
            return False

        # 清理临时文件和备份
        self.cleanup(success=True)

        logger.info("=" * 21 + " 更新完成 " + "=" * 21)

        # 重启应用程序
        self.restart_application()

        return True

def get_base_path():
    """
    获取资源文件的绝对基础路径。
    这对于在开发环境和打包后的应用中都能正确定位资源文件至关重要。
    """
    if getattr(sys, 'frozen', False):
        # 如果应用被 PyInstaller 打包（无论是单文件还是单目录）
        # `sys.executable` 指向的是可执行文件（例如 MFWPH）的路径
        return os.path.dirname(sys.executable)
    else:
        # 如果是在正常的开发环境中运行 .py 脚本
        # `__file__` 指向当前脚本的路径
        return os.path.dirname(os.path.abspath(__file__))

def main():
    base_path = get_base_path()

    os.chdir(base_path)
    parser = argparse.ArgumentParser(description='独立更新程序')
    parser.add_argument('update_package', help='更新包路径')
    parser.add_argument('--type', choices=['incremental', 'full'],
                        default='full', help='更新类型')
    parser.add_argument('--target-dir', help='目标目录，默认为当前目录')
    parser.add_argument('--restart', help='更新完成后要启动的程序')
    parser.add_argument('--wait-pid', type=int, help='需要等待退出的进程PID')

    args = parser.parse_args()

    updater = StandaloneUpdater(
        update_package=args.update_package,
        update_type=args.type,
        target_dir=args.target_dir,
        restart_program=args.restart,
        wait_pid=args.wait_pid
    )

    try:
        is_successful = updater.run()
        # 等待几秒钟让用户看到最终状态
        time.sleep(5)
        sys.exit(0 if is_successful else 1)
    except Exception as e:
        logger.error(f"更新过程中发生致命错误: {e}", exc_info=True)
        time.sleep(5)
        sys.exit(1)


if __name__ == '__main__':
    main()