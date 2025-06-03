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
        logging.FileHandler('updater.log', encoding='utf-8'),
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
            update_package: 更新包路径
            update_type: 更新类型 ('incremental' 或 'full')
            target_dir: 目标目录，默认为当前目录
            restart_program: 更新完成后要启动的程序
            wait_pid: 需要等待退出的进程PID
        """
        self.update_package = Path(update_package)
        self.update_type = update_type
        self.target_dir = Path(target_dir) if target_dir else Path.cwd()
        self.restart_program = restart_program
        self.wait_pid = wait_pid
        self.backup_dir = self.target_dir / "update_backup"
        self.temp_dir = self.target_dir / "update_temp"

        # 需要跳过的文件列表
        self.skip_files = ['update.exe', 'updater.exe']

    def wait_for_process_exit(self, pid, timeout=30):
        """等待指定进程退出"""
        if not pid:
            return True

        logger.info(f"等待进程 {pid} 退出...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                process = psutil.Process(pid)
                if not process.is_running():
                    logger.info(f"进程 {pid} 已退出")
                    return True
            except psutil.NoSuchProcess:
                logger.info(f"进程 {pid} 已退出")
                return True

            time.sleep(0.5)

        logger.warning(f"等待进程 {pid} 退出超时")
        return False

    def create_backup(self, files_to_backup):
        """创建备份"""
        logger.info("创建备份...")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        for file_path in files_to_backup:
            source = self.target_dir / file_path
            if source.exists():
                backup_path = self.backup_dir / file_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)

                try:
                    if source.is_file():
                        shutil.copy2(source, backup_path)
                    else:
                        shutil.copytree(source, backup_path)
                    logger.debug(f"备份文件: {file_path}")
                except Exception as e:
                    logger.error(f"备份文件失败 {file_path}: {e}")

    def restore_backup(self):
        """恢复备份"""
        logger.info("恢复备份...")
        if not self.backup_dir.exists():
            return

        for root, dirs, files in os.walk(self.backup_dir):
            for file in files:
                backup_file = Path(root) / file
                relative_path = backup_file.relative_to(self.backup_dir)
                target_file = self.target_dir / relative_path

                try:
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, target_file)
                    logger.debug(f"恢复文件: {relative_path}")
                except Exception as e:
                    logger.error(f"恢复文件失败 {relative_path}: {e}")

    def extract_update_package(self):
        """解压更新包"""
        logger.info(f"解压更新包: {self.update_package}")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(self.update_package, 'r') as zip_ref:
                zip_ref.extractall(self.temp_dir)
            logger.info("解压完成")
            return True
        except Exception as e:
            logger.error(f"解压失败: {e}")
            return False

    def apply_incremental_update(self):
        """应用增量更新"""
        logger.info("应用增量更新...")
        changes_file = self.temp_dir / "changes.json"

        if not changes_file.exists():
            logger.error("changes.json 文件不存在")
            return False

        try:
            with open(changes_file, 'r', encoding='utf-8') as f:
                changes = json.load(f)

            # 收集需要备份的文件
            files_to_backup = []

            # 处理修改的文件
            if "modified" in changes:
                files_to_backup.extend(changes["modified"])

            # 处理删除的文件
            if "deleted" in changes:
                files_to_backup.extend(changes["deleted"])

            # 创建备份
            self.create_backup(files_to_backup)

            success = True

            # 处理添加的文件
            if "added" in changes:
                for file_path in changes["added"]:
                    source = self.temp_dir / file_path
                    target = self.target_dir / file_path

                    if source.exists():
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                            logger.info(f"添加文件: {file_path}")
                        except Exception as e:
                            logger.error(f"添加文件失败 {file_path}: {e}")
                            success = False

            # 处理修改的文件
            if "modified" in changes:
                for file_path in changes["modified"]:
                    source = self.temp_dir / file_path
                    target = self.target_dir / file_path

                    if source.exists():
                        try:
                            # 确保目标目录存在
                            target.parent.mkdir(parents=True, exist_ok=True)

                            # 删除原文件（如果存在）
                            if target.exists():
                                target.unlink()

                            # 复制新文件
                            shutil.copy2(source, target)
                            logger.info(f"更新文件: {file_path}")
                        except Exception as e:
                            logger.error(f"更新文件失败 {file_path}: {e}")
                            success = False

            # 处理删除的文件
            if "deleted" in changes:
                for file_path in changes["deleted"]:
                    target = self.target_dir / file_path

                    if target.exists():
                        try:
                            target.unlink()
                            logger.info(f"删除文件: {file_path}")
                        except Exception as e:
                            logger.error(f"删除文件失败 {file_path}: {e}")
                            success = False

            return success

        except Exception as e:
            logger.error(f"应用增量更新失败: {e}")
            return False

    def apply_full_update(self):
        """应用完整更新 - 直接覆盖根目录文件"""
        logger.info("应用完整更新...")

        try:
            # 收集所有需要更新的文件
            files_to_update = []
            files_to_backup = []

            # 遍历临时目录中的所有文件
            for root, dirs, files in os.walk(self.temp_dir):
                for file in files:
                    source_path = Path(root) / file
                    relative_path = source_path.relative_to(self.temp_dir)

                    # 跳过更新程序自身
                    if file.lower() in self.skip_files:
                        logger.info(f"跳过文件: {file}")
                        continue

                    files_to_update.append(relative_path)

                    # 如果目标文件存在，加入备份列表
                    target_path = self.target_dir / relative_path
                    if target_path.exists():
                        files_to_backup.append(relative_path)

            # 创建备份
            if files_to_backup:
                self.create_backup(files_to_backup)

            # 执行更新
            success = True
            for relative_path in files_to_update:
                source = self.temp_dir / relative_path
                target = self.target_dir / relative_path

                try:
                    # 确保目标目录存在
                    target.parent.mkdir(parents=True, exist_ok=True)

                    # 如果目标文件存在，先删除
                    if target.exists():
                        if target.is_file():
                            target.unlink()
                        else:
                            shutil.rmtree(target)

                    # 复制新文件
                    if source.is_file():
                        shutil.copy2(source, target)
                    else:
                        shutil.copytree(source, target)

                    logger.info(f"更新文件: {relative_path}")
                except Exception as e:
                    logger.error(f"更新文件失败 {relative_path}: {e}")
                    success = False

            # 如果更新失败，恢复备份
            if not success:
                logger.error("部分文件更新失败")
                return False

            logger.info(f"成功更新 {len(files_to_update)} 个文件")
            return True

        except Exception as e:
            logger.error(f"应用完整更新失败: {e}")
            return False

    def cleanup(self):
        """清理临时文件"""
        logger.info("清理临时文件...")

        # 清理临时目录
        if self.temp_dir.exists():
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                logger.warning(f"清理临时目录失败: {e}")

        # 清理备份目录（更新成功后）
        if self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir)
            except Exception as e:
                logger.warning(f"清理备份目录失败: {e}")

    def restart_application(self):
        """重启应用程序"""
        if not self.restart_program:
            return

        restart_path = self.target_dir / self.restart_program
        if not restart_path.exists():
            logger.warning(f"重启程序不存在: {restart_path}")
            return

        logger.info(f"启动程序: {restart_path}")

        try:
            # 使用 subprocess.Popen 启动程序，不等待其完成
            if sys.platform == "win32":
                subprocess.Popen([str(restart_path)],
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen([str(restart_path)])

            logger.info("程序已启动")
        except Exception as e:
            logger.error(f"启动程序失败: {e}")

    def run(self):
        """执行更新"""
        logger.info("=== 开始更新 ===")
        logger.info(f"更新包: {self.update_package}")
        logger.info(f"更新类型: {self.update_type}")
        logger.info(f"目标目录: {self.target_dir}")

        # 等待主程序退出
        if self.wait_pid:
            if not self.wait_for_process_exit(self.wait_pid):
                logger.error("等待进程退出超时，继续更新...")

        # 额外等待以确保文件句柄释放
        time.sleep(2)

        # 解压更新包
        if not self.extract_update_package():
            logger.error("解压更新包失败")
            return False

        # 应用更新
        if self.update_type == 'incremental':
            success = self.apply_incremental_update()
        else:
            success = self.apply_full_update()

        if not success:
            logger.error("更新失败，尝试恢复备份...")
            self.restore_backup()
            self.cleanup()
            return False

        # 清理
        self.cleanup()

        logger.info("=== 更新完成 ===")

        # 重启应用程序
        self.restart_application()

        return True


def main():
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
        success = updater.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"更新过程中发生错误: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()