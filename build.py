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
from typing import List, Optional

import PyInstaller.__main__
import semver

# 常量定义
APP_NAME = "MFWPH"
UPDATER_NAME = "updater"
DEFAULT_VERSION = "0.0.1"
DEFAULT_EXCLUSIONS = ['.git', '.github', '.gitignore', '.gitmodules', '.nicegui', '.idea',
                      'config', 'debug', 'logs', 'pending_updates', 'resource', '__pycache__',
                      '*.pyc', '*.pyo', '.DS_Store', 'Thumbs.db', 'build', 'dist']

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class BuildContext:
    """构建上下文管理器，处理临时文件"""

    def __init__(self, keep_files: bool = False):
        self.keep_files = keep_files
        self.temp_files = []

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


def get_platform_info():
    """获取平台信息"""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # 标准化系统名称
    if system == 'darwin':
        system = 'macos'

    # 标准化架构名称
    arch_map = {
        'x86_64': 'x64',
        'amd64': 'x64',
        'arm64': 'arm64',
        'aarch64': 'arm64',
    }
    arch = arch_map.get(machine, machine)

    return system, arch


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
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'],
                                capture_output=True, text=True, check=False)
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


def find_site_package_path(target: str) -> str:
    """查找site-packages中的路径"""
    for path in site.getsitepackages():
        target_path = os.path.join(path, target)
        if os.path.exists(target_path):
            logger.info(f"找到 {target} 在: {target_path}")
            return target_path

    # 创建后备路径
    fallback_path = os.path.join(os.getcwd(), f"{target.replace('/', '_')}_fallback")
    os.makedirs(fallback_path, exist_ok=True)
    logger.info(f"创建后备路径: {fallback_path}")
    return fallback_path


def create_file_with_content(content: str, suffix: str = '.txt') -> str:
    """创建包含指定内容的临时文件"""
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
        f.write(content)
        return f.name


def create_version_info_files(version: str, build_time: str, ctx: BuildContext, app_name: str = APP_NAME,
                              create_version_txt: bool = True, platform_name: str = None):
    """创建版本相关的信息文件"""
    version_file = None

    # 只为主程序创建版本信息文件
    if create_version_txt:
        system, arch = get_platform_info()
        if platform_name:
            platform_info = platform_name
        else:
            platform_info = f"{system}-{arch}"

        version_content = f"version={version}\nbuild_time={build_time}\nplatform={platform_info}\n"
        version_file = os.path.join(tempfile.gettempdir(), f"versioninfo_{app_name}.txt")
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(version_content)
        ctx.add_temp_file(version_file)
        logger.info(f"创建版本信息文件: {version_file}")

    # Windows平台需要文件版本信息
    win_version_file = None
    if sys.platform == 'win32':
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
        win_version_file = create_file_with_content(win_version_content)
        ctx.add_temp_file(win_version_file)

    return version_file, win_version_file

def run_pyinstaller(version_file: str, win_version_file: str):
    """运行PyInstaller构建主程序"""
    maa_bin_path = find_site_package_path('maa/bin')
    maa_agent_path = find_site_package_path('MaaAgentBinary')

    # --- 修改开始 ---
    # 根据不同平台设置图标路径
    icon_path = ''
    if sys.platform == 'win32':
        icon_path = 'assets/icons/app/logo.ico'
    elif sys.platform == 'darwin':
        icon_path = 'assets/icons/app/logo.icns'
    else:  # Linux and others
        icon_path = 'assets/icons/app/logo.png'
    # --- 修改结束 ---

    args = [
        'main.py',
        '--onefile',
        f'--name={APP_NAME}',
        '--clean',
        '--runtime-tmpdir=.',  # 添加这行，使用当前目录作为临时目录
    ]

    # --- 修改开始 ---
    # 如果图标文件存在，则添加 --icon 参数
    if os.path.exists(icon_path):
        args.append(f'--icon={icon_path}')
        logger.info(f"使用图标: {icon_path}")
    else:
        logger.warning(f"图标文件不存在，将不为程序设置图标: {icon_path}")
    # --- 修改结束 ---

    # 平台特定参数
    if sys.platform == 'win32':
        args.extend(['--windowed', '--uac-admin'])
        if win_version_file:
            args.append(f'--version-file={win_version_file}')
    elif sys.platform == 'darwin':
        args.append('--windowed')

    args.extend([
        f'--add-binary={maa_bin_path}{os.pathsep}maa/bin',
        f'--add-binary={maa_agent_path}{os.pathsep}MaaAgentBinary',
    ])

    if version_file:
        args.append(f'--add-data={version_file}{os.pathsep}.')

    logger.info("正在运行PyInstaller构建主程序...")
    logger.info(f"PyInstaller 参数: {' '.join(args)}")  # 增加这行日志，方便调试
    PyInstaller.__main__.run(args)
    logger.info("PyInstaller构建主程序成功")


def run_pyinstaller_updater(win_version_file: str):
    """运行PyInstaller构建更新程序"""
    args = [
        'update.py',
        '--onefile',
        '--console',
        f'--name={UPDATER_NAME}',
        '--clean',
    ]

    if sys.platform == 'win32':
        args.append('--uac-admin')
        if win_version_file:
            args.append(f'--version-file={win_version_file}')

    logger.info("正在运行PyInstaller构建更新程序...")
    PyInstaller.__main__.run(args)
    logger.info("PyInstaller构建更新程序成功")


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


def create_archive(dist_dir: str, archive_path: str, exclusions: List[str], include_updater: bool = True):
    """创建归档包（ZIP或TAR.GZ）"""
    system, _ = get_platform_info()

    if system == 'windows':
        create_zip_archive(dist_dir, archive_path, exclusions, include_updater)
    else:
        create_tar_archive(dist_dir, archive_path, exclusions, include_updater)


def create_zip_archive(dist_dir: str, zip_path: str, exclusions: List[str], include_updater: bool = True):
    """创建ZIP包（Windows）"""
    logger.info(f"开始创建ZIP包: {zip_path}")

    # 先收集要添加的文件列表
    files_to_add = []

    # 添加主程序
    main_exe = os.path.join(dist_dir, f"{APP_NAME}.exe")
    if os.path.exists(main_exe):
        files_to_add.append((main_exe, f"{APP_NAME}.exe"))
        logger.info(f"准备添加: {APP_NAME}.exe")

    # 添加更新程序
    if include_updater:
        updater_exe = os.path.join(dist_dir, f"{UPDATER_NAME}.exe")
        if os.path.exists(updater_exe):
            files_to_add.append((updater_exe, f"{UPDATER_NAME}.exe"))
            logger.info(f"准备添加: {UPDATER_NAME}.exe")

    # 收集其他文件
    for root, dirs, files in os.walk(dist_dir):
        # 排除不需要的目录
        dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclusions)]

        rel_root = os.path.relpath(root, dist_dir)
        if rel_root == '.':
            rel_root = ''

        for file in files:
            # 跳过exe文件和排除的文件
            if file.endswith('.exe'):
                continue
            if any(pattern in file for pattern in exclusions):
                continue
            if file == os.path.basename(zip_path):
                continue

            file_path = os.path.join(root, file)
            if rel_root:
                arcname = os.path.join(rel_root, file)
            else:
                arcname = file
            files_to_add.append((file_path, arcname))

    # 创建ZIP文件
    logger.info(f"创建ZIP文件，共 {len(files_to_add)} 个文件")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path, arcname in files_to_add:
            logger.debug(f"添加到ZIP: {arcname}")
            zipf.write(file_path, arcname)

    logger.info(f"成功创建ZIP包: {zip_path}")


def create_tar_archive(dist_dir: str, tar_path: str, exclusions: List[str], include_updater: bool = True):
    """创建TAR.GZ包（macOS/Linux）"""
    logger.info(f"开始创建TAR.GZ包: {tar_path}")

    with tarfile.open(tar_path, 'w:gz') as tarf:
        # --- 修改开始 ---

        # 添加主程序 (.app 包)
        main_app_path = os.path.join(dist_dir, f"{APP_NAME}.app")
        if os.path.exists(main_app_path):
            logger.info(f"添加主程序包到TAR: {APP_NAME}.app")
            # tarf.add() 可以递归地添加整个目录
            tarf.add(main_app_path, arcname=f"{APP_NAME}.app")
        else:
            # 如果 .app 包不存在，再尝试寻找单个可执行文件 (适用于 Linux)
            main_executable = os.path.join(dist_dir, APP_NAME)
            if os.path.exists(main_executable):
                logger.info(f"添加主程序到TAR: {APP_NAME}")
                info = tarf.gettarinfo(main_executable, APP_NAME)
                info.mode = 0o755  # 设置可执行权限
                with open(main_executable, 'rb') as f:
                    tarf.addfile(info, f)

        # --- 修改结束 ---

        # 添加更新程序
        if include_updater:
            updater_exe = os.path.join(dist_dir, UPDATER_NAME)
            if os.path.exists(updater_exe):
                info = tarf.gettarinfo(updater_exe, UPDATER_NAME)
                info.mode = 0o755
                with open(updater_exe, 'rb') as f:
                    tarf.addfile(info, f)
                logger.info(f"添加更新程序到TAR: {UPDATER_NAME}")

        # 添加其他文件
        for root, dirs, files in os.walk(dist_dir):
            # 排除不需要的目录和 .app 包（因为它已经被添加过了）
            if f"{APP_NAME}.app" in dirs:
                dirs.remove(f"{APP_NAME}.app")
            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in exclusions)]

            for file in files:
                # 跳过可执行文件和排除的文件
                if file in [APP_NAME, UPDATER_NAME]:
                    continue
                if any(pattern in file for pattern in exclusions):
                    continue

                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                tarf.add(file_path, arcname)

    logger.info(f"成功创建TAR.GZ包: {tar_path}")


def main():
    parser = argparse.ArgumentParser(description=f'Build script for {APP_NAME}')
    parser.add_argument('--keep-files', '-k', action='store_true', help='Keep intermediate files')
    parser.add_argument('--archive-name', '-a', help='Custom name for the output archive file')
    parser.add_argument('--exclude', '-e', nargs='+', default=DEFAULT_EXCLUSIONS, help='Files to exclude')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    parser.add_argument('--skip-updater', action='store_true', help='Skip building updater')
    parser.add_argument('--platform', help='Target platform (e.g., windows-x64, macos-arm64, linux-x64)')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    start_time = datetime.datetime.now()
    logger.info(f"开始 {APP_NAME} 构建过程")

    try:
        # 获取版本号
        version = get_version()

        # 获取平台信息
        system, arch = get_platform_info()
        if args.platform:
            platform_name = args.platform
        else:
            platform_name = f"{system}-{arch}"

        logger.info(f"构建平台: {platform_name}")

        # 设置目录和文件名
        dist_dir = os.path.join(os.getcwd(), 'dist')
        Path(dist_dir).mkdir(exist_ok=True)

        build_time = start_time.strftime("%Y%m%d_%H%M%S")

        # 根据平台选择归档格式
        if system == 'windows':
            archive_ext = '.zip'
        else:
            archive_ext = '.tar.gz'

        if args.archive_name:
            archive_name = args.archive_name
        else:
            archive_name = f"{APP_NAME}_v{version}_{platform_name}_{build_time}"

        archive_path = os.path.join(dist_dir, f"{archive_name}{archive_ext}")

        with BuildContext(args.keep_files) as ctx:
            # 创建主程序版本信息文件
            version_file, win_version_file = create_version_info_files(
                version, build_time, ctx, APP_NAME, create_version_txt=True, platform_name=platform_name
            )

            # 运行PyInstaller构建主程序
            run_pyinstaller(version_file, win_version_file)

            # 构建更新程序
            if not args.skip_updater:
                _, updater_win_version_file = create_version_info_files(
                    version, build_time, ctx, UPDATER_NAME, create_version_txt=False, platform_name=platform_name
                )
                run_pyinstaller_updater(updater_win_version_file)

            # 复制assets并创建归档包
            copy_assets(dist_dir)
            create_archive(dist_dir, archive_path, args.exclude, include_updater=not args.skip_updater)

        # 设置GitHub Actions输出
        if 'GITHUB_OUTPUT' in os.environ:
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f"archive_file={archive_path}\n")
                f.write(f"version=v{version}\n")
                f.write(f"platform={platform_name}\n")

        duration = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"构建成功完成，用时: {duration:.2f} 秒")
        logger.info(f"输出文件: {archive_path}")

        return 0
    except Exception as e:
        logger.error(f"构建过程失败: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())