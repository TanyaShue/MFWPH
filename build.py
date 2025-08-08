import argparse
import datetime
import logging
import os
import platform
import shutil
import site
import subprocess
import sys
import tempfile
import zipfile
import tarfile
from pathlib import Path
from typing import List, Optional, Dict, Tuple

import PyInstaller.__main__
import semver

# 常量定义
APP_NAME = "MFWPH"
UPDATER_NAME = "updater"
DEFAULT_VERSION = "0.0.1"
DEFAULT_EXCLUSIONS = [
    '.git', '.github', '.gitignore', '.gitmodules', '.nicegui',
    '.idea', 'config', 'debug', 'logs', 'pending_updates', 'resource',
    '__pycache__', '*.pyc', '.DS_Store', 'Thumbs.db'
]

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class Platform:
    """平台检测和配置"""

    @staticmethod
    def get_current() -> Dict[str, str]:
        """获取当前平台信息"""
        system = platform.system().lower()
        machine = platform.machine().lower()

        # 标准化架构名称
        arch_map = {
            'x86_64': 'x64',
            'amd64': 'x64',
            'arm64': 'arm64',
            'aarch64': 'arm64',
            'x86': 'x86',
            'i386': 'x86',
            'i686': 'x86',
        }

        arch = arch_map.get(machine, machine)

        return {
            'system': system,
            'arch': arch,
            'platform_tag': f"{system}-{arch}"
        }

    @staticmethod
    def get_executable_extension() -> str:
        """获取可执行文件扩展名"""
        system = platform.system().lower()
        return '.exe' if system == 'windows' else ''

    @staticmethod
    def get_archive_extension() -> str:
        """获取归档文件扩展名"""
        system = platform.system().lower()
        return '.zip' if system == 'windows' else '.tar.gz'


class BuildContext:
    """构建上下文管理器，处理临时文件"""

    def __init__(self, keep_files: bool = False):
        self.keep_files = keep_files
        self.temp_files = []
        self.platform_info = Platform.get_current()

    def add_temp_file(self, file_path: str) -> str:
        self.temp_files.append(file_path)
        return file_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.keep_files:
            for file_path in self.temp_files:
                if file_path and os.path.exists(file_path):
                    try:
                        os.unlink(file_path)
                        logger.debug(f"删除临时文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除临时文件失败 {file_path}: {str(e)}")


def get_version() -> str:
    """获取版本号"""
    # 从GitHub Actions环境变量获取
    github_ref = os.environ.get('GITHUB_REF', '')
    if github_ref.startswith('refs/tags/v'):
        version = github_ref.replace('refs/tags/v', '')
        try:
            semver.VersionInfo.parse(version)
            logger.info(f"使用GitHub标签版本: {version}")
            return version
        except ValueError:
            logger.warning(f"GitHub标签 {version} 不符合SemVer格式")

    # 从git命令获取
    try:
        result = subprocess.run(
            ['git', 'describe', '--tags', '--abbrev=0'],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip().startswith('v'):
            version = result.stdout.strip()[1:]
            try:
                semver.VersionInfo.parse(version)
                logger.info(f"使用git标签版本: {version}")
                return version
            except ValueError:
                logger.warning(f"Git标签 {version} 不符合SemVer格式")
    except Exception as e:
        logger.error(f"获取git标签时出错: {str(e)}")

    logger.info(f"使用默认版本: {DEFAULT_VERSION}")
    return DEFAULT_VERSION


def find_site_package_path(target: str) -> Optional[str]:
    """查找site-packages中的路径"""
    for path in site.getsitepackages():
        target_path = os.path.join(path, target)
        if os.path.exists(target_path):
            logger.info(f"找到 {target} 在: {target_path}")
            return target_path

    # 尝试用户site-packages
    user_path = os.path.join(site.getusersitepackages(), target)
    if os.path.exists(user_path):
        logger.info(f"找到 {target} 在用户目录: {user_path}")
        return user_path

    logger.warning(f"未找到 {target} 在site-packages中")
    return None


def create_version_info_files(
        version: str,
        build_time: str,
        ctx: BuildContext,
        app_name: str = APP_NAME,
        create_version_txt: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """创建版本相关的信息文件"""
    version_file = None
    win_version_file = None

    # 创建通用版本信息文件
    if create_version_txt:
        version_content = f"version={version}\nbuild_time={build_time}\nplatform={ctx.platform_info['platform_tag']}\n"
        version_file = os.path.join(tempfile.gettempdir(), f"versioninfo_{app_name}.txt")
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(version_content)
        ctx.add_temp_file(version_file)
        logger.info(f"创建版本信息文件: {version_file}")

    # Windows平台特定的版本信息
    if ctx.platform_info['system'] == 'windows':
        ver_info = semver.VersionInfo.parse(version)
        version_tuple = (ver_info.major, ver_info.minor, ver_info.patch, 0)

        win_version_content = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u''),
           StringStruct(u'FileDescription', u'{app_name}'),
           StringStruct(u'FileVersion', u'{version}'),
           StringStruct(u'InternalName', u'{app_name}'),
           StringStruct(u'LegalCopyright', u''),
           StringStruct(u'OriginalFilename', u'{app_name}.exe'),
           StringStruct(u'ProductName', u'{app_name}'),
           StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(win_version_content)
            win_version_file = f.name
        ctx.add_temp_file(win_version_file)

    return version_file, win_version_file


def get_pyinstaller_args(
        app_name: str,
        entry_point: str,
        version_file: Optional[str],
        win_version_file: Optional[str],
        is_windowed: bool = True,
        platform_info: Dict[str, str] = None
) -> List[str]:
    """构建PyInstaller参数"""
    if platform_info is None:
        platform_info = Platform.get_current()

    args = [
        entry_point,
        '--onefile',
        f'--name={app_name}',
        '--clean',
    ]

    # 平台特定的参数
    if platform_info['system'] == 'windows':
        if is_windowed:
            args.append('--windowed')
        else:
            args.append('--console')
        args.append('--uac-admin')
        if win_version_file:
            args.append(f'--version-file={win_version_file}')
    elif platform_info['system'] == 'darwin':  # macOS
        if is_windowed:
            args.append('--windowed')
        # macOS特定选项
        args.append('--osx-bundle-identifier=com.mfwph.app')
    else:  # Linux和其他Unix系统
        if not is_windowed:
            args.append('--console')

    # 添加数据文件
    if version_file:
        args.append(f'--add-data={version_file}{os.pathsep}.')

    # 查找并添加依赖库
    maa_bin_path = find_site_package_path('maa/bin')
    if maa_bin_path:
        args.append(f'--add-data={maa_bin_path}{os.pathsep}maa/bin')

    maa_agent_path = find_site_package_path('MaaAgentBinary')
    if maa_agent_path:
        args.append(f'--add-data={maa_agent_path}{os.pathsep}MaaAgentBinary')

    return args


def run_pyinstaller(
        app_name: str,
        entry_point: str,
        version_file: Optional[str],
        win_version_file: Optional[str],
        is_windowed: bool = True,
        platform_info: Dict[str, str] = None
):
    """运行PyInstaller构建"""
    args = get_pyinstaller_args(
        app_name, entry_point, version_file,
        win_version_file, is_windowed, platform_info
    )

    logger.info(f"正在运行PyInstaller构建 {app_name}...")
    logger.info(f"入口点: {entry_point}")
    if version_file:
        logger.info(f"版本信息文件: {version_file}")

    PyInstaller.__main__.run(args)
    logger.info(f"PyInstaller构建 {app_name} 成功")


def copy_assets(dist_dir: str):
    """复制assets文件夹"""
    src = 'assets'
    dst = os.path.join(dist_dir, 'assets')

    if os.path.exists(src):
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        logger.info(f"已复制assets文件夹到: {dst}")
    else:
        logger.warning(f"assets文件夹不存在: {src}")


def create_archive(
        dist_dir: str,
        archive_path: str,
        exclusions: List[str],
        include_updater: bool = True,
        platform_info: Dict[str, str] = None
):
    """创建归档包（ZIP或TAR.GZ）"""
    if platform_info is None:
        platform_info = Platform.get_current()

    exe_ext = Platform.get_executable_extension()

    if platform_info['system'] == 'windows':
        # Windows使用ZIP
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 添加主程序
            main_exe = os.path.join(dist_dir, f"{APP_NAME}{exe_ext}")
            if os.path.exists(main_exe):
                zipf.write(main_exe, f"{APP_NAME}{exe_ext}")
                logger.info(f"添加主程序到ZIP: {APP_NAME}{exe_ext}")

            # 添加更新程序
            if include_updater:
                updater_exe = os.path.join(dist_dir, f"{UPDATER_NAME}{exe_ext}")
                if os.path.exists(updater_exe):
                    zipf.write(updater_exe, f"{UPDATER_NAME}{exe_ext}")
                    logger.info(f"添加更新程序到ZIP: {UPDATER_NAME}{exe_ext}")

            # 添加其他文件
            _add_files_to_archive(zipf, dist_dir, exclusions, exe_ext, 'zip')
    else:
        # Unix系统使用TAR.GZ
        with tarfile.open(archive_path, 'w:gz') as tarf:
            # 添加主程序
            main_exe = os.path.join(dist_dir, f"{APP_NAME}{exe_ext}")
            if os.path.exists(main_exe):
                # 设置可执行权限
                info = tarf.gettarinfo(main_exe, f"{APP_NAME}{exe_ext}")
                info.mode = 0o755
                with open(main_exe, 'rb') as f:
                    tarf.addfile(info, f)
                logger.info(f"添加主程序到TAR: {APP_NAME}{exe_ext}")

            # 添加更新程序
            if include_updater:
                updater_exe = os.path.join(dist_dir, f"{UPDATER_NAME}{exe_ext}")
                if os.path.exists(updater_exe):
                    info = tarf.gettarinfo(updater_exe, f"{UPDATER_NAME}{exe_ext}")
                    info.mode = 0o755
                    with open(updater_exe, 'rb') as f:
                        tarf.addfile(info, f)
                    logger.info(f"添加更新程序到TAR: {UPDATER_NAME}{exe_ext}")

            # 添加其他文件
            _add_files_to_archive(tarf, dist_dir, exclusions, exe_ext, 'tar')

    logger.info(f"成功创建归档包: {archive_path}")


def _add_files_to_archive(archive, dist_dir: str, exclusions: List[str], exe_ext: str, archive_type: str):
    """辅助函数：添加文件到归档"""
    for root, dirs, files in os.walk(dist_dir):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclusions]

        for file in files:
            # 跳过可执行文件（已经单独处理）
            if file.endswith(exe_ext) and file.startswith((APP_NAME, UPDATER_NAME)):
                continue

            if file in exclusions:
                continue

            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, dist_dir)

            if archive_type == 'zip':
                archive.write(file_path, arcname)
            else:  # tar
                archive.add(file_path, arcname)


def main():
    parser = argparse.ArgumentParser(description=f'Cross-platform build script for {APP_NAME}')
    parser.add_argument('--keep-files', '-k', action='store_true', help='Keep intermediate files')
    parser.add_argument('--archive-name', '-a', help='Custom name for the output archive file')
    parser.add_argument('--exclude', '-e', nargs='+', default=DEFAULT_EXCLUSIONS, help='Files to exclude')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--skip-updater', action='store_true', help='Skip building updater')
    parser.add_argument('--platform', help='Override platform detection (format: system-arch)')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = datetime.datetime.now()
    logger.info(f"开始 {APP_NAME} 构建过程")

    try:
        # 获取版本号
        version = get_version()

        # 设置平台信息
        if args.platform:
            parts = args.platform.split('-')
            platform_info = {
                'system': parts[0],
                'arch': parts[1] if len(parts) > 1 else 'x64',
                'platform_tag': args.platform
            }
        else:
            platform_info = Platform.get_current()

        logger.info(f"构建平台: {platform_info['platform_tag']}")

        # 设置目录和文件名
        dist_dir = os.path.join(os.getcwd(), 'dist')
        Path(dist_dir).mkdir(exist_ok=True)

        build_time = start_time.strftime("%Y%m%d_%H%M%S")
        archive_ext = Platform.get_archive_extension()

        if args.archive_name:
            archive_name = args.archive_name
        else:
            archive_name = f"{APP_NAME}_v{version}_{platform_info['platform_tag']}_{build_time}"

        archive_path = os.path.join(dist_dir, f"{archive_name}{archive_ext}")

        with BuildContext(args.keep_files) as ctx:
            ctx.platform_info = platform_info

            # 创建主程序版本信息文件
            version_file, win_version_file = create_version_info_files(
                version, build_time, ctx, APP_NAME, create_version_txt=True
            )

            # 构建主程序
            run_pyinstaller(
                APP_NAME, 'main.py', version_file, win_version_file,
                is_windowed=True, platform_info=platform_info
            )

            # 构建更新程序
            if not args.skip_updater:
                _, updater_win_version_file = create_version_info_files(
                    version, build_time, ctx, UPDATER_NAME, create_version_txt=False
                )
                run_pyinstaller(
                    UPDATER_NAME, 'update.py', None, updater_win_version_file,
                    is_windowed=False, platform_info=platform_info
                )

            # 复制assets并创建归档包
            copy_assets(dist_dir)
            create_archive(
                dist_dir, archive_path, args.exclude,
                include_updater=not args.skip_updater,
                platform_info=platform_info
            )

        # 设置GitHub Actions输出
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"archive_file={archive_path}\n")
                f.write(f"version=v{version}\n")
                f.write(f"platform={platform_info['platform_tag']}\n")

        duration = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"构建成功完成，用时: {duration:.2f} 秒")
        logger.info(f"输出文件: {archive_path}")

        return 0
    except Exception as e:
        logger.error(f"构建过程失败: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())